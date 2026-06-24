from typing import Any

from app.pricing.material_engine import material_record
from app.pricing.movement_cost_templates import movement_template
from app.pricing.movement_geometry_estimator import estimate_movement_geometry
from app.schemas.mold_quote_schema import MoldTechnicalInput


FIGURE_OPERATIONS = {"desbaste_3d", "pre_acabamento", "acabamento", "polimento", "eletroerosao"}
HOLDER_ROLES = {"porta_inserto_cavidade", "porta_inserto_macho"}


def generate_mold_components(
    *,
    analysis: dict[str, Any],
    technical_input: MoldTechnicalInput,
    sizing: dict[str, Any],
    molding_material: str,
    calibration: dict[str, Any],
) -> dict[str, Any]:
    height = sizing["height_breakdown"]
    base = sizing["selected_mold_base"]
    layout = sizing["cavity_layout"]
    corrected = sizing["corrected_part_envelope"]
    width = float(base["width_mm"])
    length = float(base["length_mm"])
    part_depth = float(corrected["z_mm"])
    construction_type = mold_construction_type(technical_input)
    inserted = construction_type in {"insertado_posticado", "hibrido"}
    cavity_role = "porta_inserto_cavidade" if inserted else "placa_cavidade_monobloco"
    core_role = "porta_inserto_macho" if inserted else "placa_macho_monobloco"
    geometry_owner = _geometry_owner(construction_type)
    cavity_plate_thickness = (
        height.get("porta_inserto_cavidade_thickness_mm", height["cavity_plate_mm"])
        if inserted
        else height["cavity_plate_mm"]
    )
    core_plate_thickness = (
        height.get("porta_inserto_macho_thickness_mm", height["core_plate_mm"])
        if inserted
        else height["core_plate_mm"]
    )

    fabricated = [
        _component("placa_superior", width, length, height["top_clamping_plate_mm"], 1, calibration, molding_material),
        _component(
            "placa_cavidade",
            width,
            length,
            cavity_plate_thickness,
            1,
            calibration,
            molding_material,
            template_key=cavity_role,
            component_role=cavity_role,
            geometry_owner=geometry_owner,
            thickness_rule_used="holder_plate_thickness_logic" if inserted else "monoblock_cavity_plate_depth_logic",
        ),
        _component(
            "placa_macho",
            width,
            length,
            core_plate_thickness,
            1,
            calibration,
            molding_material,
            template_key=core_role,
            component_role=core_role,
            geometry_owner=geometry_owner,
            thickness_rule_used="holder_plate_thickness_logic" if inserted else "monoblock_core_plate_depth_logic",
        ),
        _component("placa_suporte", width, length, height["support_plate_mm"], 1, calibration, molding_material),
        _component("paralelas", width * 0.18, length, height["spacer_block_height_mm"], 2, calibration, molding_material),
        _component("placa_extratora_1", width * 0.78, length * 0.78, height["ejector_plate_1_mm"], 1, calibration, molding_material),
        _component("placa_extratora_2", width * 0.78, length * 0.78, height["ejector_plate_2_mm"], 1, calibration, molding_material),
        _component("placa_inferior", width, length, height["bottom_clamping_plate_mm"], 1, calibration, molding_material),
    ]
    if float(height.get("manifold_support_plate_mm", 0.0)) > 0:
        fabricated.insert(
            1,
            _component(
                "placa_porta_manifold",
                width,
                length,
                float(height["manifold_support_plate_mm"]),
                1,
                calibration,
                molding_material,
                component_role="placa_porta_manifold",
                geometry_owner="none",
                thickness_rule_used="hot_runner_manifold_support_plate_logic",
            ),
        )

    if inserted:
        insert_width = max(float(corrected["x_mm"]) + layout["center_margin_between_cavities_mm"] * 0.65, 45)
        insert_length = max(float(corrected["y_mm"]) + layout["center_margin_between_cavities_mm"] * 0.65, 45)
        insert_height = float(height.get("inserto_cavidade_thickness_mm") or max(part_depth * 0.85, 45))
        fabricated.append(
            _component(
                "inserto_cavidade",
                insert_width,
                insert_length,
                insert_height,
                technical_input.cavity_count,
                calibration,
                molding_material,
                component_role="inserto_cavidade",
                geometry_owner=geometry_owner,
                thickness_rule_used="insert_thickness_logic",
            )
        )
        fabricated.append(
            _component(
                "inserto_macho",
                insert_width,
                insert_length,
                float(height.get("inserto_macho_thickness_mm") or max(part_depth * 0.80, 45)),
                technical_input.cavity_count,
                calibration,
                molding_material,
                component_role="inserto_macho",
                geometry_owner=geometry_owner,
                thickness_rule_used="insert_thickness_logic",
            )
        )

    if technical_input.special_movements:
        for movement in technical_input.special_movements:
            template = movement_template(str(movement.movement_type))
            geometry = estimate_movement_geometry(
                movement=movement,
                corrected_part=corrected,
                selected_mold_base=base,
                technical_input=technical_input,
            )
            component_type = str(template["component_type"])
            component = _component(
                component_type,
                float(geometry["applied_width_mm"]),
                float(geometry["applied_length_mm"]),
                float(geometry["applied_height_mm"]),
                movement.quantity,
                calibration,
                molding_material,
                template_key="lifter" if component_type == "lifter" else "gaveta",
                component_role=f"movimento_especial:{movement.movement_type}",
                geometry_owner="hybrid" if construction_type == "hibrido" else geometry_owner,
                thickness_rule_used="movement_geometry_estimator_or_manual_override",
            )
            component["component_id"] = movement.id
            component["movement_id"] = movement.id
            component["movement_type"] = movement.movement_type
            component["movement_position"] = movement.position
            component["movement_stroke_mm"] = geometry["applied_stroke_mm"]
            component["movement_actuation"] = movement.actuation
            component["movement_complexity"] = movement.complexity
            component["movement_cost_template"] = movement.movement_type
            component["movement_geometry_estimate"] = geometry
            component["technical_definition"] = geometry["technical_definition"]
            component["calculation_status"] = geometry["calculation_status"]
            component["manual_override"] = geometry["manual_override"]
            component["is_manual_override"] = geometry["manual_override"]
            component["needs_review"] = geometry["needs_review"]
            component["uses_treatment"] = geometry["applied_uses_treatment"]
            _apply_material(component, str(geometry["applied_material"]))
            _apply_movement_operation_factors(component, template, bool(geometry["applied_uses_edm"]))
            fabricated.append(component)
    elif technical_input.has_movements:
        movement_type = "lifter" if technical_input.movement_type in {"ANGLED_SLIDER", "FORCED_EJECTION"} else "gaveta"
        fabricated.append(
            _component(
                movement_type,
                max(float(corrected["x_mm"]) * 0.45, 60),
                max(float(corrected["y_mm"]) * 0.38, 45),
                max(part_depth * 0.55, 35),
                technical_input.number_of_movements,
                calibration,
                molding_material,
                component_role="mecanismo_moldante",
                geometry_owner="hybrid" if construction_type == "hibrido" else geometry_owner,
                thickness_rule_used="mechanism_depth_logic",
            )
        )

    service_components = [
        _service_component("circuito_refrigeracao", width, length, 6.0, 1, calibration, molding_material),
        _service_component("furacoes_padrao", width, length, 5.0, 1, calibration, molding_material),
        _service_component("ajustes_montagem", width, length, 4.0, 1, calibration, molding_material),
    ]
    if technical_input.injection_type == "cold_runner":
        service_components.append(
            _service_component(
                "canal_injecao",
                layout["layout_width_mm"],
                layout["layout_length_mm"],
                7.0,
                1,
                calibration,
                molding_material,
            )
        )
    if technical_input.injection_type == "hot_runner":
        service_components.append(
            _service_component(
                "alojamento_camara_quente",
                layout["layout_width_mm"],
                layout["layout_length_mm"],
                14.0,
                max(technical_input.hot_runner_drops, 1),
                calibration,
                molding_material,
            )
        )

    _apply_dimension_overrides(fabricated, technical_input)
    purchased = _purchased_components(technical_input, sizing, calibration)
    purchased.extend(_movement_purchased_components(technical_input))
    all_fabricated = fabricated + service_components
    component_alerts = (
        _figure_allocation_alerts(all_fabricated, construction_type)
        + _holder_thickness_alerts(all_fabricated, height)
    )
    return {
        "fabricated_components": all_fabricated,
        "material_components": fabricated,
        "service_components": service_components,
        "purchased_components": purchased,
        "mold_construction_type": construction_type,
        "component_generation_alerts": component_alerts,
        "component_generation_method": "standard_moldbase_stack_plus_service_operations",
    }


def mold_construction_type(technical_input: MoldTechnicalInput) -> str:
    explicit = getattr(technical_input, "mold_construction_type", None)
    if explicit:
        return str(explicit)
    return "insertado_posticado" if technical_input.cavity_type == "inserted" else "monobloco"


def _geometry_owner(construction_type: str) -> str:
    return {
        "monobloco": "plate",
        "insertado_posticado": "insert",
        "hibrido": "hybrid",
    }.get(construction_type, "none")


def _component(
    component_type: str,
    width_mm: float,
    length_mm: float,
    thickness_mm: float,
    quantity: int,
    calibration: dict[str, Any],
    molding_material: str,
    *,
    template_key: str | None = None,
    component_role: str | None = None,
    geometry_owner: str | None = None,
    thickness_rule_used: str | None = None,
) -> dict[str, Any]:
    return _build_component(
        component_type,
        width_mm,
        length_mm,
        thickness_mm,
        quantity,
        calibration,
        molding_material,
        is_material_component=True,
        template_key=template_key,
        component_role=component_role,
        geometry_owner=geometry_owner,
        thickness_rule_used=thickness_rule_used,
    )


def _service_component(
    component_type: str,
    width_mm: float,
    length_mm: float,
    thickness_mm: float,
    quantity: int,
    calibration: dict[str, Any],
    molding_material: str,
) -> dict[str, Any]:
    return _build_component(
        component_type,
        width_mm,
        length_mm,
        thickness_mm,
        quantity,
        calibration,
        molding_material,
        is_material_component=False,
    )


def _build_component(
    component_type: str,
    width_mm: float,
    length_mm: float,
    thickness_mm: float,
    quantity: int,
    calibration: dict[str, Any],
    molding_material: str,
    *,
    is_material_component: bool,
    template_key: str | None = None,
    component_role: str | None = None,
    geometry_owner: str | None = None,
    thickness_rule_used: str | None = None,
) -> dict[str, Any]:
    manufacturing_template = template_key or component_type
    template = (
        calibration["component_templates"].get(manufacturing_template)
        or calibration["component_templates"].get(component_type)
        or calibration["component_templates"]["gaveta"]
    )
    role = component_role or manufacturing_template
    material = _material_for_role(calibration, role, template, molding_material)
    if material == "molding_steel":
        material = molding_material
    record = material_record(str(material))
    raw_volume_cm3 = max(width_mm * length_mm * thickness_mm * max(quantity, 1) / 1000, 0)
    raw_operations = dict(template["operations"])
    blocked_operations = sorted(FIGURE_OPERATIONS.intersection(raw_operations)) if role in HOLDER_ROLES else []
    allowed_operations = {
        operation: ratio
        for operation, ratio in raw_operations.items()
        if operation not in blocked_operations
    }
    operations = [
        {
            "operation_type": operation,
            "removed_volume_ratio": float(ratio),
            "estimated_removed_volume_cm3": round(raw_volume_cm3 * float(ratio), 4),
        }
        for operation, ratio in allowed_operations.items()
    ]
    total_removed = sum(item["estimated_removed_volume_cm3"] for item in operations)
    component_alerts = []
    if blocked_operations:
        component_alerts.append(
            "critical_conceptual_alert_insert_holder_figure_operations_blocked:"
            f"{','.join(blocked_operations)}"
        )
    material_rule = "material_by_component_role" if role in calibration.get("material_by_component_role", {}) else "component_template_material"
    return {
        "component_id": component_type,
        "component_type": component_type,
        "group": component_type,
        "component_role": role,
        "manufacturing_template": manufacturing_template,
        "geometry_owner": geometry_owner or ("insert" if component_type.startswith("inserto_") else "plate"),
        "figure_allocation": geometry_owner or ("insert" if component_type.startswith("inserto_") else "plate"),
        "operation_template_used": manufacturing_template,
        "material_rule_used": material_rule,
        "thickness_rule_used": thickness_rule_used or "component_stack_height_breakdown",
        "operations_blocked": blocked_operations or (sorted(FIGURE_OPERATIONS) if role in HOLDER_ROLES else []),
        "alerts": component_alerts,
        "quantity": int(max(quantity, 1)),
        "material": material,
        **record,
        "width_mm": round(width_mm, 4),
        "length_mm": round(length_mm, 4),
        "thickness_mm": round(thickness_mm, 4),
        "raw_volume_cm3": round(raw_volume_cm3, 4),
        "volume_cm3": round(raw_volume_cm3, 4),
        "estimated_removed_volume_cm3": round(total_removed, 4),
        "finished_volume_estimate_cm3": round(max(raw_volume_cm3 - total_removed, 0), 4),
        "material_efficiency_factor": float(template.get("efficiency", 0.85)),
        "operation_plan": operations,
        "operations_applied": [item["operation_type"] for item in operations],
        "is_material_component": is_material_component,
    }


def _material_for_role(
    calibration: dict[str, Any],
    role: str,
    template: dict[str, Any],
    molding_material: str,
) -> str:
    by_role = calibration.get("material_by_component_role", {})
    configured = by_role.get(role)
    if configured:
        return str(configured)
    template_material = str(template.get("material", "molding_steel"))
    return molding_material if template_material == "molding_steel" else template_material


def _apply_material(component: dict[str, Any], material: str) -> None:
    record = material_record(str(material))
    component["material"] = material
    component.update(record)


def _recalculate_component_volume(component: dict[str, Any]) -> None:
    raw_volume = max(
        float(component["width_mm"])
        * float(component["length_mm"])
        * float(component["thickness_mm"])
        * max(int(component.get("quantity", 1)), 1)
        / 1000,
        0,
    )
    for operation in component.get("operation_plan", []):
        operation["estimated_removed_volume_cm3"] = round(
            raw_volume * float(operation.get("removed_volume_ratio", 0.0)), 4
        )
    removed = sum(float(item.get("estimated_removed_volume_cm3", 0.0)) for item in component.get("operation_plan", []))
    component["raw_volume_cm3"] = round(raw_volume, 4)
    component["volume_cm3"] = round(raw_volume, 4)
    component["estimated_removed_volume_cm3"] = round(removed, 4)
    component["finished_volume_estimate_cm3"] = round(max(raw_volume - removed, 0), 4)


def _apply_movement_operation_factors(
    component: dict[str, Any],
    template: dict[str, Any],
    uses_edm: bool,
) -> None:
    cnc_factor = float(template.get("cnc_factor", 1.0))
    for operation in component.get("operation_plan", []):
        operation["removed_volume_ratio"] = min(
            float(operation.get("removed_volume_ratio", 0.0)) * cnc_factor, 0.85
        )
    if uses_edm and not any(item.get("operation_type") == "eletroerosao" for item in component.get("operation_plan", [])):
        component.setdefault("operation_plan", []).append(
            {
                "operation_type": "eletroerosao",
                "removed_volume_ratio": float(template.get("edm_removed_volume_ratio", 0.35)) * 0.04,
                "estimated_removed_volume_cm3": 0.0,
            }
        )
        component.setdefault("operations_applied", []).append("eletroerosao")
    _recalculate_component_volume(component)


def _apply_dimension_overrides(
    components: list[dict[str, Any]],
    technical_input: MoldTechnicalInput,
) -> None:
    for component in components:
        key = str(component.get("component_id") or component.get("component_type"))
        override = technical_input.dimension_overrides.get(key)
        if override is None:
            override = technical_input.dimension_overrides.get(str(component.get("component_type")))
        if override is None:
            component.setdefault("is_manual_override", False)
            component.setdefault("is_locked", False)
            continue
        for field in ("width_mm", "length_mm", "thickness_mm"):
            value = getattr(override, field)
            if value is not None:
                component[field] = round(float(value), 4)
        if override.material:
            _apply_material(component, override.material)
        component["is_manual_override"] = override.is_manual_override
        component["is_locked"] = override.is_locked
        component["dimension_override_source"] = "technical_input.dimension_overrides"
        _recalculate_component_volume(component)


def _movement_purchased_components(technical_input: MoldTechnicalInput) -> list[dict[str, Any]]:
    purchased: list[dict[str, Any]] = []
    for movement in technical_input.special_movements:
        template = movement_template(str(movement.movement_type))
        for component, unit_cost in template.get("purchased_components", {}).items():
            purchased.append(
                {
                    "component": component,
                    "movement_id": movement.id,
                    "movement_type": movement.movement_type,
                    "quantity": movement.quantity,
                    "unit_cost_brl": round(float(unit_cost), 2),
                    "cost_brl": round(float(unit_cost) * movement.quantity, 2),
                    "category": "componentes_normalizados",
                    "formula": "movement_quantity * movement_template_unit_cost",
                }
            )
    return purchased


def _figure_allocation_alerts(components: list[dict[str, Any]], construction_type: str) -> list[str]:
    if construction_type not in {"insertado_posticado", "hibrido"}:
        return []
    has_insert = any(str(item.get("component_type", "")).startswith("inserto_") for item in components)
    holder_with_figure = [
        str(item.get("component_type"))
        for item in components
        if item.get("component_role") in HOLDER_ROLES and any(
            str(alert).startswith("critical_conceptual_alert_insert_holder_figure_operations_blocked")
            for alert in item.get("alerts", [])
        )
    ]
    if has_insert and holder_with_figure:
        return [
            "possible_duplicate_figure_machining_inserted_mold:"
            f"holders_with_figure_ops={','.join(sorted(holder_with_figure))}"
        ]
    return []


def _holder_thickness_alerts(components: list[dict[str, Any]], height: dict[str, Any]) -> list[str]:
    total_height = float(height.get("total_mold_height_mm", 0.0))
    fixed_half_stack = (
        float(height.get("top_clamping_plate_mm", 0.0))
        + float(height.get("manifold_support_plate_mm", 0.0))
        + float(height.get("cavity_plate_mm", 0.0))
    )
    moving_half_stack = (
        float(height.get("core_plate_mm", 0.0))
        + float(height.get("support_plate_mm", 0.0))
        + float(height.get("ejector_box_height_mm", height.get("spacer_block_height_mm", 0.0)))
        + float(height.get("bottom_clamping_plate_mm", 0.0))
    )
    alerts = []
    for component in components:
        if component.get("component_role") not in HOLDER_ROLES:
            continue
        thickness = float(component.get("thickness_mm", 0.0))
        invalid_matches = [
            name
            for name, value in {
                "total_mold_height_mm": total_height,
                "complete_fixed_half_stack_height_mm": fixed_half_stack,
                "complete_moving_half_stack_height_mm": moving_half_stack,
            }.items()
            if value > 0 and abs(thickness - value) < 0.001
        ]
        if invalid_matches:
            alert = (
                "critical_holder_plate_thickness_uses_stack_height:"
                f"{component.get('component_type')}={thickness}mm matches {','.join(invalid_matches)}"
            )
            component.setdefault("alerts", []).append(alert)
            alerts.append(alert)
    return alerts


def _purchased_components(
    technical_input: MoldTechnicalInput,
    sizing: dict[str, Any],
    calibration: dict[str, Any],
) -> list[dict[str, Any]]:
    scale = sizing["mold_scale"]
    table = dict(calibration.get("purchased_components_table", {}).get(scale, {}))
    if technical_input.has_movements:
        table["travas_gavetas_mecanismos"] = technical_input.number_of_movements * 1800
    if technical_input.slider_motion_type == "hydraulic_cylinders":
        table["cilindros_hidraulicos"] = technical_input.number_of_movements * 2800
    if technical_input.injection_type == "hot_runner":
        table["bicos_camara_quente"] = max(technical_input.hot_runner_drops, 1) * 4200
        table["resistencias_sensores_conectores"] = max(technical_input.hot_runner_drops, 1) * 950
    if technical_input.extraction_type == "rotary_core":
        table["macho_rotativo_normalizado"] = 4500
    return [
        {"component": name, "cost_brl": round(float(cost), 2)}
        for name, cost in table.items()
    ]
