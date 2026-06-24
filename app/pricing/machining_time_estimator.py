from collections import defaultdict
from copy import deepcopy
from typing import Any

from app.pricing.mrr_library import estimate_machining_time_from_mrr, lookup_mrr_entry, material_machinability_factor
from app.schemas.mold_quote_schema import MoldTechnicalInput


def estimate_component_machining(
    analysis: dict[str, Any],
    technical_input: MoldTechnicalInput,
    fabricated_components: list[dict[str, Any]],
    calibration: dict[str, Any],
) -> dict[str, Any]:
    selected_base = analysis.get("mold_sizing", {}).get("selected_mold_base", {})
    mold_size_class = classify_mold_size_class(
        calibration,
        selected_base or _selected_base_from_components(fabricated_components),
    )
    complexity_preset_name = select_complexity_preset(analysis, technical_input)
    mold_type_preset_name = select_mold_type_preset(analysis, technical_input)
    complexity_preset = calibration["complexity_presets"][complexity_preset_name]
    mold_type_preset = calibration["mold_type_presets"][mold_type_preset_name]
    conservatism = float(calibration.get("quote_conservatism_factor", 1.0))
    calibration_factors = calibration.get("calibration_factors", {})

    operation_rows: list[dict[str, Any]] = []
    component_rows: list[dict[str, Any]] = []
    operation_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"hours": 0.0, "cost_brl": 0.0})
    cost_by_center: dict[str, dict[str, float]] = defaultdict(lambda: {"hours": 0.0, "cost_brl": 0.0})
    alerts: list[str] = []
    total_hours = 0.0
    total_cost = 0.0

    for component in fabricated_components:
        component_result = _estimate_component(
            analysis=analysis,
            technical_input=technical_input,
            component=component,
            calibration=calibration,
            mold_size_class=mold_size_class,
            complexity_preset_name=complexity_preset_name,
            complexity_preset=complexity_preset,
            mold_type_preset_name=mold_type_preset_name,
            mold_type_preset=mold_type_preset,
            conservatism=conservatism,
            calibration_factors=calibration_factors,
        )
        component_rows.append(component_result["component"])
        alerts.extend(component_result["alerts"])
        for row in component_result["operations"]:
            operation_rows.append(row)
            operation_totals[row["operation_type"]]["hours"] += row["estimated_hours"]
            operation_totals[row["operation_type"]]["cost_brl"] += row["machining_cost_brl"]
            cost_by_center[row["cost_center"]]["hours"] += row["estimated_hours"]
            cost_by_center[row["cost_center"]]["cost_brl"] += row["machining_cost_brl"]
            total_hours += row["estimated_hours"]
            total_cost += row["machining_cost_brl"]

    total_sanity = _check_total_hours(
        total_hours=total_hours,
        mold_size_class=mold_size_class,
        mold_type_preset_name=mold_type_preset_name,
        complexity_preset_name=complexity_preset_name,
        calibration=calibration,
    )
    alerts.extend(total_sanity["alerts"])

    groups = [
        {
            "group": row["component_type"],
            "component_type": row["component_type"],
            "component_role": row.get("component_role"),
            "manufacturing_template": row.get("manufacturing_template"),
            "geometry_owner": row.get("geometry_owner"),
            "operation_template_used": row.get("operation_template_used"),
            "operations_blocked": row.get("operations_blocked", []),
            "operation": row["operation_type"],
            "steel_material": row["material"],
            "machine_route": row["cost_center"],
            "base_mrr_cm3_min": row["base_mrr_cm3_min"],
            "effective_mrr_cm3_min": row["effective_mrr_cm3_min"],
            "effective_mrr_cm3_hour": round(row["effective_mrr_cm3_min"] * 60, 4),
            "removed_volume_cm3": row["removed_volume_cm3"],
            "estimated_hours": row["estimated_hours"],
            "base_operation_hours": row["base_operation_hours"],
            "mrr_audit_hours": row["mrr_audit_hours"],
            "mrr_weight": row["mrr_weight"],
            "machine_rate_brl_hour": row["hourly_rate_brl"],
            "machining_cost_brl": row["machining_cost_brl"],
            "requires_manual_review": bool(row["alerts"]),
            "mrr_config_used": row["mrr_config_used"],
            "calculation_method": row["calculation_method"],
            "alerts": row["alerts"],
        }
        for row in operation_rows
    ]

    return {
        "groups": groups,
        "components": component_rows,
        "operation_totals": _round_nested(operation_totals),
        "cost_by_center": _round_nested(cost_by_center),
        "total_cnc_hours": round(total_hours, 4),
        "total_cnc_cost_brl": round(total_cost, 2),
        "mrr_config_version": calibration.get("version"),
        "mrr_unit": calibration.get("mrr_unit", "cm3/min"),
        "mold_size_class": mold_size_class,
        "mold_type_preset": mold_type_preset_name,
        "complexity_preset": complexity_preset_name,
        "quote_conservatism_factor": conservatism,
        "calibration_factors": calibration_factors,
        "sanity_checks": {
            "component_bounds_applied": True,
            "total_hours": total_sanity,
        },
        "manual_review_required": bool(alerts),
        "manual_review_reasons": _dedupe(alerts),
        "method": "hybrid_base_hours_with_mrr_audit_and_sanity_bounds",
    }


def _estimate_component(
    *,
    analysis: dict[str, Any],
    technical_input: MoldTechnicalInput,
    component: dict[str, Any],
    calibration: dict[str, Any],
    mold_size_class: str,
    complexity_preset_name: str,
    complexity_preset: dict[str, Any],
    mold_type_preset_name: str,
    mold_type_preset: dict[str, Any],
    conservatism: float,
    calibration_factors: dict[str, Any],
) -> dict[str, Any]:
    component_type = str(component["component_type"])
    manufacturing_template = str(component.get("manufacturing_template") or component_type)
    library_item = _resolve_component_time_item(calibration, manufacturing_template)
    operation_configs = _operation_configs_for_size(calibration, library_item, mold_size_class)
    planned_operations = {item["operation_type"]: item for item in component.get("operation_plan", [])}
    operations_to_estimate = list(dict.fromkeys([*operation_configs.keys(), *planned_operations.keys()]))
    operation_rows = []
    alerts: list[str] = list(component.get("alerts", []))

    for operation in operations_to_estimate:
        operation_config = operation_configs.get(
            operation,
            _fallback_operation_config(calibration, mold_size_class, operation),
        )
        planned = planned_operations.get(
            operation,
            {"operation_type": operation, "removed_volume_ratio": 0.0, "estimated_removed_volume_cm3": 0.0},
        )
        row = _estimate_operation(
            analysis=analysis,
            technical_input=technical_input,
            component=component,
            operation_config=operation_config,
            planned=planned,
            calibration=calibration,
            mold_size_class=mold_size_class,
            library_item=library_item,
            complexity_preset_name=complexity_preset_name,
            complexity_preset=complexity_preset,
            mold_type_preset_name=mold_type_preset_name,
            mold_type_preset=mold_type_preset,
            conservatism=conservatism,
            calibration_factors=calibration_factors,
        )
        operation_rows.append(row)
        alerts.extend(row["alerts"])

    raw_total_hours = sum(row["estimated_hours"] for row in operation_rows)
    component_sanity = _check_component_bounds(
        component_type=manufacturing_template,
        mold_size_class=mold_size_class,
        calculated_hours=raw_total_hours,
        calibration=calibration,
    )
    alerts.extend(component_sanity["alerts"])
    final_total_hours = raw_total_hours
    if component_sanity["clamped"]:
        final_total_hours = component_sanity["clamped_hours"]
        scale = final_total_hours / raw_total_hours if raw_total_hours > 0 else 1.0
        for row in operation_rows:
            row["pre_component_clamp_hours"] = row["estimated_hours"]
            row["estimated_hours"] = round(row["estimated_hours"] * scale, 4)
            row["machining_cost_brl"] = round(row["estimated_hours"] * row["hourly_rate_brl"], 2)
            row["alerts"].append("component_total_hours_clamped")

    total_cost = sum(row["machining_cost_brl"] for row in operation_rows)
    return {
        "component": {
            "component_id": component["component_id"],
            "component_type": component_type,
            "component_role": component.get("component_role", manufacturing_template),
            "manufacturing_template": manufacturing_template,
            "geometry_owner": component.get("geometry_owner"),
            "operation_template_used": component.get("operation_template_used"),
            "material_rule_used": component.get("material_rule_used"),
            "thickness_rule_used": component.get("thickness_rule_used"),
            "operations_blocked": component.get("operations_blocked", []),
            "quantity": component["quantity"],
            "material": component["material"],
            "width_mm": component.get("width_mm"),
            "length_mm": component.get("length_mm"),
            "thickness_mm": component.get("thickness_mm"),
            "raw_volume_cm3": component["raw_volume_cm3"],
            "estimated_removed_volume_cm3": component["estimated_removed_volume_cm3"],
            "base_hours_before_bounds": round(raw_total_hours, 4),
            "estimated_hours": round(final_total_hours, 4),
            "machining_cost_brl": round(total_cost, 2),
            "operations": operation_rows,
            "is_material_component": component.get("is_material_component", True),
            "criticality": library_item.get("criticality", "simple"),
            "calculation_method": "base_operation_packages_plus_secondary_mrr_audit",
            "sanity_check": component_sanity,
            "alerts": _dedupe(alerts),
        },
        "operations": operation_rows,
        "alerts": alerts,
    }


def _estimate_operation(
    *,
    analysis: dict[str, Any],
    technical_input: MoldTechnicalInput,
    component: dict[str, Any],
    operation_config: dict[str, Any],
    planned: dict[str, Any],
    calibration: dict[str, Any],
    mold_size_class: str,
    library_item: dict[str, Any],
    complexity_preset_name: str,
    complexity_preset: dict[str, Any],
    mold_type_preset_name: str,
    mold_type_preset: dict[str, Any],
    conservatism: float,
    calibration_factors: dict[str, Any],
) -> dict[str, Any]:
    operation = str(planned["operation_type"])
    material = str(component["material"])
    cost_center = _cost_center(operation)
    mrr_entry = lookup_mrr_entry(
        calibration,
        material=material,
        component_type=str(component.get("manufacturing_template") or component["component_type"]),
        operation_type=operation,
    )
    effective_mrr = _effective_mrr_cm3_min(
        calibration=calibration,
        material=material,
        operation=operation,
        component=component,
        mrr_entry=mrr_entry,
        technical_input=technical_input,
        analysis=analysis,
    )
    removed_volume = float(planned.get("estimated_removed_volume_cm3", 0.0))
    mrr_time = estimate_machining_time_from_mrr(
        removed_volume_cm3=removed_volume,
        effective_mrr_cm3_min=effective_mrr,
    )
    mrr_minutes = float(mrr_time["machining_time_minutes"])
    mrr_hours = float(mrr_time["machining_time_hours"])
    base_hours = float(operation_config.get("base_hours", 0.0))
    adjusted_base_hours = base_hours * _combined_hour_factors(
        analysis=analysis,
        technical_input=technical_input,
        component=component,
        operation=operation,
        mold_size_class=mold_size_class,
        library_item=library_item,
        complexity_preset=complexity_preset,
        mold_type_preset=mold_type_preset,
        calibration=calibration,
        cost_center=cost_center,
        conservatism=conservatism,
        calibration_factors=calibration_factors,
    )["combined_factor"]
    mrr_weight = _mrr_weight(operation_config, library_item)
    hybrid_hours = adjusted_base_hours * (1 - mrr_weight) + mrr_hours * mrr_weight
    operation_sanity = _clamp_operation_hours(hybrid_hours, operation_config)
    hourly_rate = float(calibration.get("hourly_rates_brl", {}).get(operation, _rate_from_center(calibration, cost_center)))
    final_hours = operation_sanity["hours"]
    cost = final_hours * hourly_rate
    factors = _combined_hour_factors(
        analysis=analysis,
        technical_input=technical_input,
        component=component,
        operation=operation,
        mold_size_class=mold_size_class,
        library_item=library_item,
        complexity_preset=complexity_preset,
        mold_type_preset=mold_type_preset,
        calibration=calibration,
        cost_center=cost_center,
        conservatism=conservatism,
        calibration_factors=calibration_factors,
    )
    alerts = list(operation_sanity["alerts"])
    if mrr_hours > adjusted_base_hours * 3 and mrr_weight > 0:
        alerts.append("mrr_audit_time_much_higher_than_base_hours")
    if adjusted_base_hours > 0 and mrr_hours < adjusted_base_hours * 0.08 and removed_volume > 0:
        alerts.append("mrr_audit_time_much_lower_than_base_hours")

    return {
        "component_id": component["component_id"],
        "component_type": component["component_type"],
        "component_role": component.get("component_role"),
        "manufacturing_template": component.get("manufacturing_template", component["component_type"]),
        "geometry_owner": component.get("geometry_owner"),
        "operation_template_used": component.get("operation_template_used"),
        "operations_blocked": component.get("operations_blocked", []),
        "operation_type": operation,
        "material": material,
        "cost_center": cost_center,
        "removed_volume_ratio": planned.get("removed_volume_ratio", 0.0),
        "removed_volume_cm3": round(removed_volume, 4),
        "base_mrr_cm3_min": round(float(mrr_entry.get("base_mrr_cm3_min", mrr_entry.get("mrr_cm3_min", 0.0))), 4),
        "effective_mrr_cm3_min": round(effective_mrr, 4),
        "machining_time_minutes": round(mrr_minutes, 4),
        "machining_time_formula": mrr_time["formula"],
        "mrr_audit_minutes": round(mrr_minutes, 4),
        "mrr_audit_hours": round(mrr_hours, 4),
        "mrr_weight": round(mrr_weight, 4),
        "base_operation_hours": round(base_hours, 4),
        "adjusted_base_operation_hours": round(adjusted_base_hours, 4),
        "estimated_hours_before_operation_bounds": round(hybrid_hours, 4),
        "estimated_hours": round(final_hours, 4),
        "hourly_rate_brl": hourly_rate,
        "machining_cost_brl": round(cost, 2),
        "factors": factors,
        "mrr_lookup_level": mrr_entry.get("lookup_level", "unknown"),
        "mrr_config_used": mrr_entry,
        "calculation_method": "weighted_base_hours_and_mrr_audit",
        "complexity_preset": complexity_preset_name,
        "mold_type_preset": mold_type_preset_name,
        "mold_size_class": mold_size_class,
        "alerts": _dedupe(alerts),
    }


def classify_mold_size_class(calibration: dict[str, Any], selected_base: dict[str, Any]) -> str:
    area = float(selected_base.get("area_mm2") or (float(selected_base.get("width_mm", 0)) * float(selected_base.get("length_mm", 0))))
    for item in calibration.get("mold_size_classes", []):
        max_area = item.get("max_area_mm2")
        if max_area is None or area <= float(max_area):
            return str(item["class"])
    return "extra_large_mold"


def select_complexity_preset(analysis: dict[str, Any], technical_input: MoldTechnicalInput) -> str:
    level = analysis.get("complexity", {}).get("complexity_level", "medium")
    if technical_input.dimensional_requirement == "CRITICAL" or (
        level == "high" and (technical_input.has_movements or technical_input.injection_type == "hot_runner")
    ):
        return "muito_complexo"
    if level == "high" or technical_input.dimensional_requirement == "HIGH_PRECISION":
        return "complexo"
    if level == "medium" or technical_input.main_finish in {"HIGH_GLOSS", "MIRROR_POLISH", "TEXTURED", "MIXED"}:
        return "medio"
    return "simples"


def select_mold_type_preset(analysis: dict[str, Any], technical_input: MoldTechnicalInput) -> str:
    if technical_input.has_movements:
        return "molde_com_lifters" if technical_input.movement_type in {"ANGLED_SLIDER", "FORCED_EJECTION"} else "molde_com_gavetas"
    if technical_input.injection_type == "hot_runner":
        return "molde_camara_quente"
    if getattr(technical_input, "mold_construction_type", None) in {"insertado_posticado", "hibrido"} or technical_input.cavity_type == "inserted":
        return "molde_insertado"
    if technical_input.cavity_count > 1:
        return "molde_multicavidade"
    if technical_input.dimensional_requirement in {"HIGH_PRECISION", "CRITICAL"}:
        return "molde_alta_precisao"
    if analysis.get("complexity", {}).get("complexity_level") == "high":
        return "molde_alta_complexidade"
    return "molde_monobloco_simples"


def _combined_hour_factors(
    *,
    analysis: dict[str, Any],
    technical_input: MoldTechnicalInput,
    component: dict[str, Any],
    operation: str,
    mold_size_class: str,
    library_item: dict[str, Any],
    complexity_preset: dict[str, Any],
    mold_type_preset: dict[str, Any],
    calibration: dict[str, Any],
    cost_center: str,
    conservatism: float,
    calibration_factors: dict[str, Any],
) -> dict[str, float]:
    sensitivity = _operation_sensitivity(operation, library_item)
    complexity_factor = 1 + (float(complexity_preset["complexity_factor"]) - 1) * sensitivity
    material_factor = _material_hour_factor(calibration, str(component["material"]), operation)
    tolerance_factor = 1 + (_tolerance_base_factor(technical_input) - 1) * sensitivity
    finishing_factor = 1 + (_finish_base_factor(technical_input) - 1) * _finish_sensitivity(operation)
    mechanism_factor = 1.0
    if technical_input.has_movements and library_item.get("criticality") == "critical":
        mechanism_factor += min(0.08 * technical_input.number_of_movements, 0.35)
    cavity_factor = _cavity_factor(technical_input, component, library_item)
    size_factor = _actual_size_factor(calibration, mold_size_class, component, library_item)
    mold_type_factor = _mold_type_factor(mold_type_preset, cost_center)
    calibration_factor = _calibration_factor(calibration_factors, cost_center)
    component_role_factor = _component_role_factor(calibration, component, cost_center)
    combined = (
        size_factor
        * complexity_factor
        * material_factor
        * tolerance_factor
        * finishing_factor
        * mechanism_factor
        * cavity_factor
        * mold_type_factor
        * component_role_factor
        * conservatism
        * calibration_factor
    )
    return {
        "size_factor": round(size_factor, 4),
        "complexity_factor": round(complexity_factor, 4),
        "material_factor": round(material_factor, 4),
        "tolerance_factor": round(tolerance_factor, 4),
        "finishing_factor": round(finishing_factor, 4),
        "mechanism_factor": round(mechanism_factor, 4),
        "cavity_factor": round(cavity_factor, 4),
        "mold_type_factor": round(mold_type_factor, 4),
        "component_role_factor": round(component_role_factor, 4),
        "quote_conservatism_factor": round(conservatism, 4),
        "calibration_factor": round(calibration_factor, 4),
        "combined_factor": round(combined, 4),
    }


def _effective_mrr_cm3_min(
    *,
    calibration: dict[str, Any],
    material: str,
    operation: str,
    component: dict[str, Any],
    mrr_entry: dict[str, Any],
    technical_input: MoldTechnicalInput,
    analysis: dict[str, Any],
) -> float:
    material_factor = material_machinability_factor(calibration, material)
    finish_factor = 1 + (_finish_base_factor(technical_input) - 1) * _finish_sensitivity(operation)
    tolerance_factor = 1 + (_tolerance_base_factor(technical_input) - 1) * _operation_sensitivity(operation, {"criticality": "critical"})
    complexity_factor = _dynamic_complexity_factor(analysis)
    depth_factor = _depth_factor(component)
    return max(
        float(mrr_entry.get("mrr_cm3_min", 1.0))
        * material_factor
        * float(mrr_entry.get("machine_factor", 1.0))
        * float(mrr_entry.get("complexity_factor", 1.0))
        * complexity_factor
        * float(mrr_entry.get("finishing_factor", 1.0))
        * finish_factor
        * float(mrr_entry.get("tolerance_factor", 1.0))
        * tolerance_factor
        * depth_factor,
        0.05,
    )


def _resolve_component_time_item(calibration: dict[str, Any], component_type: str) -> dict[str, Any]:
    library = calibration["component_manufacturing_time_library"]
    item = deepcopy(library.get(component_type, library["default"]))
    if "inherits" not in item:
        return item
    parent = _resolve_component_time_item(calibration, str(item["inherits"]))
    merged = deepcopy(parent)
    multiplier = float(item.get("operation_multiplier", 1.0))
    for size_ops in merged.get("operations_by_size", {}).values():
        for operation in size_ops.values():
            operation["base_hours"] = round(float(operation.get("base_hours", 0)) * multiplier, 4)
            operation["min_hours"] = round(float(operation.get("min_hours", 0)) * min(multiplier, 1.0), 4)
            operation["max_hours"] = round(float(operation.get("max_hours", 0)) * max(multiplier, 1.0), 4)
    for key, value in item.items():
        if key not in {"inherits", "operation_multiplier"}:
            merged[key] = value
    return merged


def _operation_configs_for_size(
    calibration: dict[str, Any],
    library_item: dict[str, Any],
    mold_size_class: str,
) -> dict[str, Any]:
    operations_by_size = library_item.get("operations_by_size", {})
    return deepcopy(operations_by_size.get(mold_size_class) or operations_by_size.get("medium_mold") or {})


def _fallback_operation_config(calibration: dict[str, Any], mold_size_class: str, operation: str) -> dict[str, Any]:
    default = _resolve_component_time_item(calibration, "default")
    configs = _operation_configs_for_size(calibration, default, mold_size_class)
    return deepcopy(
        configs.get(
            operation,
            {"base_hours": 0.25, "min_hours": 0.0, "max_hours": 4.0, "mrr_weight": 0.12},
        )
    )


def _selected_base_from_components(components: list[dict[str, Any]]) -> dict[str, Any]:
    width = max((float(component.get("width_mm", 0)) for component in components), default=0)
    length = max((float(component.get("length_mm", 0)) for component in components), default=0)
    return {"width_mm": width, "length_mm": length, "area_mm2": width * length}


def _operation_sensitivity(operation: str, library_item: dict[str, Any] | None = None) -> float:
    if operation in {"desbaste_3d", "pre_acabamento", "acabamento", "canais", "bolsoes"}:
        return 1.0
    if operation in {"circuito_refrigeracao", "mandrilamento", "ajuste_manual", "polimento"}:
        return 0.72
    if operation in {"furacao", "rosqueamento"}:
        return 0.45
    if operation in {"setup", "faceamento"}:
        return 0.30 if (library_item or {}).get("criticality") != "critical" else 0.45
    return 0.55


def _finish_sensitivity(operation: str) -> float:
    if operation in {"acabamento", "pre_acabamento", "polimento", "ajuste_manual"}:
        return 1.0
    if operation in {"desbaste_3d", "canais", "bolsoes"}:
        return 0.45
    return 0.18


def _mrr_weight(operation_config: dict[str, Any], library_item: dict[str, Any]) -> float:
    weight = float(operation_config.get("mrr_weight", 0.1))
    if library_item.get("criticality") != "critical":
        weight = min(weight, 0.12)
    return max(min(weight, 0.45), 0.0)


def _actual_size_factor(
    calibration: dict[str, Any],
    mold_size_class: str,
    component: dict[str, Any],
    library_item: dict[str, Any],
) -> float:
    area = float(component.get("width_mm", 0)) * float(component.get("length_mm", 0))
    class_item = next(
        (item for item in calibration.get("mold_size_classes", []) if item["class"] == mold_size_class),
        {"reference_area_mm2": max(area, 1)},
    )
    reference = max(float(class_item.get("reference_area_mm2") or area or 1), 1)
    exponent = float(library_item.get("size_exponent", 0.25))
    return max(min((max(area, 1) / reference) ** exponent, 1.45), 0.72)


def _material_hour_factor(calibration: dict[str, Any], material: str, operation: str) -> float:
    if operation in {"setup", "ajuste_manual", "montagem"}:
        return 1.0
    machinability = max(material_machinability_factor(calibration, material), 0.1)
    return max(min(1 / machinability, 1.75), 0.55)


def _tolerance_base_factor(technical_input: MoldTechnicalInput) -> float:
    return {
        "NORMAL": 1.0,
        "MEDIUM_PRECISION": 1.12,
        "HIGH_PRECISION": 1.28,
        "CRITICAL": 1.52,
    }.get(technical_input.dimensional_requirement, 1.12)


def _finish_base_factor(technical_input: MoldTechnicalInput) -> float:
    return {
        "MACHINED_TECHNICAL": 1.0,
        "SIMPLE_POLISHED": 1.12,
        "HIGH_GLOSS": 1.35,
        "MIRROR_POLISH": 1.65,
        "TEXTURED": 1.28,
        "MIXED": 1.45,
    }.get(technical_input.main_finish, 1.0)


def _cavity_factor(technical_input: MoldTechnicalInput, component: dict[str, Any], library_item: dict[str, Any]) -> float:
    quantity = max(int(component.get("quantity", 1)), 1)
    exponent = float(library_item.get("quantity_exponent", 0.72))
    quantity_factor = quantity ** exponent
    if component.get("component_role") in {"porta_inserto_cavidade", "porta_inserto_macho"}:
        quantity_factor *= min(1 + max(technical_input.cavity_count - 1, 0) * 0.03, 1.18)
    elif component.get("component_type") in {"placa_cavidade", "placa_macho"}:
        quantity_factor *= min(1 + max(technical_input.cavity_count - 1, 0) * 0.08, 1.45)
    return max(quantity_factor, 1.0)


def _mold_type_factor(mold_type_preset: dict[str, Any], cost_center: str) -> float:
    if cost_center in {"bancada", "montagem"}:
        return float(mold_type_preset.get("benchwork_factor", 1.0))
    if cost_center in {"cnc_desbaste", "cnc_acabamento", "furacao", "furacao_refrigeracao"}:
        return float(mold_type_preset.get("machining_factor", 1.0))
    return float(mold_type_preset.get("risk_factor", 1.0))


def _component_role_factor(calibration: dict[str, Any], component: dict[str, Any], cost_center: str) -> float:
    factors = calibration.get("component_role_factors", {})
    role = component.get("component_role")
    if role in {"porta_inserto_cavidade", "porta_inserto_macho"} and cost_center in {
        "cnc_desbaste",
        "cnc_acabamento",
        "furacao",
        "furacao_refrigeracao",
    }:
        return float(factors.get("holder_plate_complexity_factor", 0.72))
    if component.get("geometry_owner") == "insert" and cost_center in {"cnc_desbaste", "cnc_acabamento"}:
        return float(factors.get("cavity_geometry_complexity_factor", 1.0))
    return 1.0


def _calibration_factor(calibration_factors: dict[str, Any], cost_center: str) -> float:
    global_factor = float(calibration_factors.get("global_quote_calibration_factor", 1.0))
    if cost_center in {"bancada", "montagem", "polimento"}:
        specific = float(calibration_factors.get("benchwork_calibration_factor", 1.0))
    elif cost_center in {"cnc_desbaste", "cnc_acabamento", "furacao", "furacao_refrigeracao"}:
        specific = float(calibration_factors.get("machining_calibration_factor", 1.0))
    else:
        specific = 1.0
    return global_factor * specific


def _dynamic_complexity_factor(analysis: dict[str, Any]) -> float:
    level = analysis.get("complexity", {}).get("complexity_level", "medium")
    face_count = int(analysis.get("geometry", {}).get("face_count", 0))
    factor = {"low": 1.0, "medium": 0.92, "high": 0.78}.get(level, 0.92)
    if face_count > 1500:
        factor *= 0.9
    elif face_count > 800:
        factor *= 0.95
    return max(factor, 0.5)


def _depth_factor(component: dict[str, Any]) -> float:
    thickness = float(component.get("thickness_mm", 0))
    if thickness > 180:
        return 0.76
    if thickness > 120:
        return 0.86
    if thickness > 80:
        return 0.94
    return 1.0


def _clamp_operation_hours(hours: float, operation_config: dict[str, Any]) -> dict[str, Any]:
    alerts = []
    minimum = operation_config.get("min_hours")
    maximum = operation_config.get("max_hours")
    final = hours
    if minimum is not None and final < float(minimum):
        alerts.append("operation_hours_below_minimum_bound")
        final = float(minimum)
    if maximum is not None and final > float(maximum):
        alerts.append("operation_hours_above_maximum_bound")
        final = float(maximum)
    return {"hours": round(final, 4), "alerts": alerts}


def _check_component_bounds(
    *,
    component_type: str,
    mold_size_class: str,
    calculated_hours: float,
    calibration: dict[str, Any],
) -> dict[str, Any]:
    bounds_config = calibration.get("component_time_bounds", {})
    bounds = bounds_config.get(component_type, {}).get(mold_size_class)
    if not bounds:
        return {
            "component_type": component_type,
            "mold_size_class": mold_size_class,
            "calculated_hours": round(calculated_hours, 4),
            "clamped": False,
            "clamped_hours": round(calculated_hours, 4),
            "alerts": [],
        }
    minimum = float(bounds["min_hours"])
    maximum = float(bounds["max_hours"])
    alerts = []
    clamped = False
    final = calculated_hours
    if calculated_hours < minimum:
        alerts.append(
            f"{component_type}_hours_below_expected_range:{round(calculated_hours, 2)}h<{minimum}h"
        )
        if bounds_config.get("apply_clamp", True):
            final = minimum
            clamped = True
    if calculated_hours > maximum:
        alerts.append(
            f"{component_type}_hours_above_expected_range:{round(calculated_hours, 2)}h>{maximum}h"
        )
        if bounds_config.get("apply_clamp", True):
            final = maximum
            clamped = True
    return {
        "component_type": component_type,
        "mold_size_class": mold_size_class,
        "calculated_hours": round(calculated_hours, 4),
        "min_hours": minimum,
        "max_hours": maximum,
        "clamped": clamped,
        "clamped_hours": round(final, 4),
        "alerts": alerts,
    }


def _check_total_hours(
    *,
    total_hours: float,
    mold_size_class: str,
    mold_type_preset_name: str,
    complexity_preset_name: str,
    calibration: dict[str, Any],
) -> dict[str, Any]:
    bounds_table = calibration.get("mold_total_hour_bounds", {})
    key = mold_type_preset_name
    if complexity_preset_name == "muito_complexo":
        key = "molde_alta_complexidade"
    bounds = bounds_table.get(key, {}).get(mold_size_class)
    if not bounds:
        return {"mold_type": key, "mold_size_class": mold_size_class, "total_hours": round(total_hours, 4), "alerts": []}
    minimum = float(bounds["min_total_hours"])
    maximum = float(bounds["max_total_hours"])
    alerts = []
    if total_hours < minimum:
        alerts.append(f"mold_total_hours_below_expected_range:{round(total_hours, 2)}h<{minimum}h")
    if total_hours > maximum:
        alerts.append(f"mold_total_hours_above_expected_range:{round(total_hours, 2)}h>{maximum}h")
    return {
        "mold_type": key,
        "mold_size_class": mold_size_class,
        "total_hours": round(total_hours, 4),
        "min_total_hours": minimum,
        "max_total_hours": maximum,
        "alerts": alerts,
    }


def _cost_center(operation: str) -> str:
    return {
        "setup": "cnc_desbaste",
        "faceamento": "cnc_desbaste",
        "desbaste_2_5d": "cnc_desbaste",
        "desbaste_3d": "cnc_desbaste",
        "pre_acabamento": "cnc_acabamento",
        "acabamento": "cnc_acabamento",
        "furacao": "furacao",
        "rosqueamento": "furacao",
        "mandrilamento": "furacao",
        "bolsoes": "cnc_desbaste",
        "canais": "cnc_acabamento",
        "circuito_refrigeracao": "furacao_refrigeracao",
        "ajuste_manual": "bancada",
        "polimento": "polimento",
        "montagem": "montagem",
        "eletroerosao": "eletroerosao",
    }.get(operation, "usinagem")


def _rate_from_center(calibration: dict[str, Any], cost_center: str) -> float:
    rates = calibration.get("hourly_rates_brl", {})
    return {
        "cnc_desbaste": rates.get("desbaste_2_5d", 185),
        "cnc_acabamento": rates.get("acabamento", 240),
        "furacao": rates.get("furacao", 165),
        "furacao_refrigeracao": rates.get("circuito_refrigeracao", 190),
        "bancada": rates.get("ajuste_manual", 120),
        "polimento": rates.get("polimento", 120),
        "montagem": rates.get("montagem", 120),
        "eletroerosao": rates.get("eletroerosao", 180),
    }.get(cost_center, 180)


def _round_nested(items: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    return {
        key: {
            "hours": round(value["hours"], 4),
            "cost_brl": round(value["cost_brl"], 2),
        }
        for key, value in items.items()
    }


def _dedupe(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        result.append(item)
        seen.add(item)
    return result
