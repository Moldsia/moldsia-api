import math
from typing import Any

from app.schemas.analysis_schema import (
    DerivedMetrics,
    GeometryMetrics,
    ManufacturingProfile,
    ManufacturingRisk,
    MaterialSupplyMode,
    PricingEstimate,
    PricingParameters,
    ComplexityProfile,
    ShapeProfile,
)
from app.pricing.effective_mrr_engine import calculate_effective_mrr, calculate_material_efficiency_factor


def calculate_pricing_estimate(
    geometry: GeometryMetrics,
    derived_metrics: DerivedMetrics,
    manufacturing_profile: ManufacturingProfile,
    manufacturing_risk: ManufacturingRisk,
    parameters: PricingParameters,
    material_id: str,
    quantity: int,
    material_supply_mode: MaterialSupplyMode,
    stock_allowance_mm: float,
    complexity: ComplexityProfile | None = None,
    shape_profile: ShapeProfile | None = None,
) -> PricingEstimate:
    material = _find_material(parameters, material_id)
    if complexity is None or shape_profile is None:
        base_mrr = parameters.base_mrr_by_material.get(material.material_id) or _removal_rate(
            parameters,
            manufacturing_profile.machining_profile,
        )
        effective_mrr_breakdown = {
            "base_mrr_cm3_hour": base_mrr,
            "geometry_factor": 1.0,
            "complexity_factor": 1.0,
            "machine_factor": 1.0,
            "finish_factor": 1.0,
            "rigidity_factor": 1.0,
            "setup_factor": 1.0,
            "effective_mrr_cm3_hour": base_mrr,
        }
        material_efficiency_factor = 0.85
    else:
        effective_mrr_breakdown = calculate_effective_mrr(
            material_id=material.material_id,
            geometry=geometry,
            derived_metrics=derived_metrics,
            complexity=complexity,
            shape_profile=shape_profile,
            manufacturing_profile=manufacturing_profile,
            manufacturing_risk=manufacturing_risk,
            parameters=parameters,
        )
        material_efficiency_factor = calculate_material_efficiency_factor(geometry, derived_metrics, shape_profile)
    effective_mrr = effective_mrr_breakdown["effective_mrr_cm3_hour"]
    quantity = max(quantity, 1)
    stock_allowance_mm = max(stock_allowance_mm, 0)

    adjusted_stock_volume_cm3 = _adjusted_stock_volume_cm3(geometry, stock_allowance_mm)
    removed_volume_cm3 = max(adjusted_stock_volume_cm3 - geometry.real_volume_cm3, 0.0)
    material_weight_kg = adjusted_stock_volume_cm3 * material.density_g_cm3 / 1000
    raw_material_cost_brl = material_weight_kg * material.material_price_brl_kg
    real_material_cost_brl = raw_material_cost_brl / max(material_efficiency_factor, 0.001)
    material_cost_brl = (
        real_material_cost_brl
        if material_supply_mode == "moldsia_supplies"
        else 0.0
    )

    base_machine_hours = removed_volume_cm3 / effective_mrr
    complexity_multiplier = 1.0
    risk_multiplier = 1.0
    finishing_multiplier = 1.0
    estimated_machine_hours = base_machine_hours

    setup_cost_brl = manufacturing_profile.setup_hours * manufacturing_profile.machine_rate_brl_hour
    machining_cost_brl = estimated_machine_hours * manufacturing_profile.machine_rate_brl_hour
    total_cpv_brl = material_cost_brl + setup_cost_brl + machining_cost_brl
    unit_cpv_brl = total_cpv_brl / quantity
    markup_floor, markup_ceiling = _markup_range(parameters, quantity)

    if manufacturing_risk.risk_level == "high":
        markup_ceiling += parameters.risk_markup_adjustment.high_risk_ceiling_addition
    if manufacturing_profile.machining_profile == "engineering_review_required":
        markup_ceiling += parameters.risk_markup_adjustment.engineering_review_ceiling_addition

    price_floor_brl = max(total_cpv_brl * markup_floor, parameters.minimum_order_value_brl)
    price_ceiling_brl = max(total_cpv_brl * markup_ceiling, price_floor_brl)
    minimum_order_value_applied = price_floor_brl == parameters.minimum_order_value_brl

    return PricingEstimate(
        currency=parameters.currency,
        parameters_version=parameters.version,
        material={
            "material_id": material.material_id,
            "label": material.label,
            "density_g_cm3": material.density_g_cm3,
            "material_price_brl_kg": material.material_price_brl_kg,
            "machinability_factor": material.machinability_factor,
            "material_supply_mode": material_supply_mode,
            "stock_allowance_mm": stock_allowance_mm,
            "adjusted_stock_volume_cm3": round(adjusted_stock_volume_cm3, 4),
            "removed_volume_cm3": round(removed_volume_cm3, 4),
            "material_weight_kg": round(material_weight_kg, 4),
            "raw_material_cost_brl": round(raw_material_cost_brl, 2),
            "material_efficiency_factor": round(material_efficiency_factor, 4),
            "real_material_cost_brl": round(real_material_cost_brl, 2),
            "material_cost_brl": round(material_cost_brl, 2),
        },
        machining={
            "removal_rate_cm3_hour": effective_mrr,
            "effective_mrr_breakdown": effective_mrr_breakdown,
            "base_machine_hours": round(base_machine_hours, 4),
            "estimated_machine_hours": round(estimated_machine_hours, 4),
            "setup_hours": manufacturing_profile.setup_hours,
            "setup_cost_brl": round(setup_cost_brl, 2),
            "machining_cost_brl": round(machining_cost_brl, 2),
            "machine_rate_brl_hour": manufacturing_profile.machine_rate_brl_hour,
        },
        commercial={
            "quantity": quantity,
            "total_cpv_brl": round(total_cpv_brl, 2),
            "unit_cpv_brl": round(unit_cpv_brl, 2),
            "markup_floor": round(markup_floor, 4),
            "markup_ceiling": round(markup_ceiling, 4),
            "price_floor_brl": round(price_floor_brl, 2),
            "price_ceiling_brl": round(price_ceiling_brl, 2),
            "minimum_order_value_brl": parameters.minimum_order_value_brl,
            "minimum_order_value_applied": minimum_order_value_applied,
        },
        confidence={
            "pricing_confidence": _confidence(manufacturing_risk.risk_level),
            "risk_level": manufacturing_risk.risk_level,
            "machining_profile": manufacturing_profile.machining_profile,
            "complexity_multiplier": complexity_multiplier,
            "risk_multiplier": risk_multiplier,
            "finishing_multiplier": finishing_multiplier,
            "notes": _confidence_notes(manufacturing_risk, manufacturing_profile),
        },
        calculation_memory=_calculation_memory(
            geometry=geometry,
            material=material,
            quantity=quantity,
            material_supply_mode=material_supply_mode,
            stock_allowance_mm=stock_allowance_mm,
            stock_adjusted_volume_cm3=adjusted_stock_volume_cm3,
            removed_volume_cm3=removed_volume_cm3,
            material_weight_kg=material_weight_kg,
            raw_material_cost_brl=raw_material_cost_brl,
            material_efficiency_factor=material_efficiency_factor,
            real_material_cost_brl=real_material_cost_brl,
            material_cost_brl=material_cost_brl,
            removal_rate_cm3_hour=effective_mrr,
            effective_mrr_breakdown=effective_mrr_breakdown,
            base_machine_hours=base_machine_hours,
            complexity_multiplier=complexity_multiplier,
            risk_multiplier=risk_multiplier,
            finishing_multiplier=finishing_multiplier,
            final_machine_hours=estimated_machine_hours,
            machining_cost_brl=machining_cost_brl,
            setup_hours=manufacturing_profile.setup_hours,
            machine_rate_brl_hour=manufacturing_profile.machine_rate_brl_hour,
            setup_cost_brl=setup_cost_brl,
            total_cpv_brl=total_cpv_brl,
            unit_cpv_brl=unit_cpv_brl,
            markup_floor=markup_floor,
            markup_ceiling=markup_ceiling,
            price_floor_brl=price_floor_brl,
            price_ceiling_brl=price_ceiling_brl,
            minimum_order_value_brl=parameters.minimum_order_value_brl,
            minimum_order_value_applied=minimum_order_value_applied,
        ),
    )


def _adjusted_stock_volume_cm3(geometry: GeometryMetrics, stock_allowance_mm: float) -> float:
    x = geometry.xlen_mm + (stock_allowance_mm * 2)
    y = geometry.ylen_mm + (stock_allowance_mm * 2)
    z = geometry.zlen_mm + (stock_allowance_mm * 2)
    return (x * y * z) / 1000


def _find_material(parameters: PricingParameters, material_id: str):
    for material in parameters.materials:
        if material.material_id == material_id:
            return material
    return parameters.materials[0]


def _removal_rate(parameters: PricingParameters, machining_profile: str) -> float:
    profile = parameters.removal_rates.get(machining_profile) or parameters.removal_rates["vertical_milling"]
    return profile.removal_rate_cm3_hour


def _finishing_multiplier(parameters: PricingParameters, feature_density_by_volume: float) -> float:
    if feature_density_by_volume > 5:
        return parameters.finishing_multipliers.high_feature_density_multiplier
    if feature_density_by_volume > 1:
        return parameters.finishing_multipliers.medium_feature_density_multiplier
    return parameters.finishing_multipliers.low_feature_density_multiplier


def _markup_range(parameters: PricingParameters, quantity: int) -> tuple[float, float]:
    for tier in parameters.markup_tiers:
        if quantity >= tier.quantity_min and (tier.quantity_max is None or quantity <= tier.quantity_max):
            return tier.markup_floor, tier.markup_ceiling
    last_tier = parameters.markup_tiers[-1]
    return last_tier.markup_floor, last_tier.markup_ceiling


def _confidence(risk_level: str) -> str:
    if risk_level == "high":
        return "low"
    if risk_level == "medium":
        return "medium"
    return "high"


def _confidence_notes(
    manufacturing_risk: ManufacturingRisk,
    manufacturing_profile: ManufacturingProfile,
) -> list[str]:
    notes = []
    if manufacturing_profile.machining_profile == "engineering_review_required":
        notes.append("Revisão de engenharia recomendada antes de fechar preço.")
    if manufacturing_risk.risk_flags:
        notes.append("Preço preliminar influenciado por flags de risco industrial.")
    if not notes:
        notes.append("Estimativa preliminar calculada com parâmetros atuais.")
    return notes


def _machining_complexity_level(machining_profile: str) -> str:
    if machining_profile in {
        "complex_3_axis_milling",
        "precision_fixture_required",
        "engineering_review_required",
    }:
        return "high"
    if machining_profile in {"portal_milling", "mold_base_candidate"}:
        return "medium"
    return "low"


def _calculation_memory(**values: Any) -> dict[str, Any]:
    quantity = max(values["quantity"], 1)
    bounding_box_volume_cm3 = values["geometry"].bounding_box_volume_mm3 / 1000
    material_cost_applied = values["material_supply_mode"] == "moldsia_supplies"
    memory = {
        "title": "Memória de Cálculo da Estimativa Comercial",
        "inputs": {
            "material": _field(values["material"].label, "label"),
            "material_id": _field(values["material"].material_id, "id"),
            "quantity": _field(quantity, "un"),
            "material_supply_mode": _field(values["material_supply_mode"], "mode"),
            "stock_allowance_mm": _field(values["stock_allowance_mm"], "mm"),
            "setup_hours": _field(values["setup_hours"], "h"),
            "machine_rate_brl_hour": _field(values["machine_rate_brl_hour"], "BRL/h"),
            "removal_rate_cm3_hour": _field(values["removal_rate_cm3_hour"], "cm3/h"),
            "markup_floor": _field(values["markup_floor"], "multiplier"),
            "markup_ceiling": _field(values["markup_ceiling"], "multiplier"),
            "minimum_order_value_brl": _field(values["minimum_order_value_brl"], "BRL"),
        },
        "volumes": {
            "bounding_box_volume_mm3": _field(values["geometry"].bounding_box_volume_mm3, "mm3"),
            "bounding_box_volume_cm3": _field(bounding_box_volume_cm3, "cm3"),
            "stock_adjusted_volume_cm3": _field(values["stock_adjusted_volume_cm3"], "cm3"),
            "real_volume_cm3": _field(values["geometry"].real_volume_cm3, "cm3"),
            "removed_volume_cm3": _field(values["removed_volume_cm3"], "cm3"),
        },
        "material": {
            "density_g_cm3": _field(values["material"].density_g_cm3, "g/cm3"),
            "material_price_brl_kg": _field(values["material"].material_price_brl_kg, "BRL/kg"),
            "estimated_weight_kg": _field(values["material_weight_kg"], "kg"),
            "raw_material_cost_brl": _field(values["raw_material_cost_brl"], "BRL"),
            "material_efficiency_factor": _field(values["material_efficiency_factor"], "factor"),
            "real_material_cost_brl": _field(values["real_material_cost_brl"], "BRL", "raw_material_cost_brl / material_efficiency_factor"),
            "material_cost_brl": _field(values["material_cost_brl"], "BRL"),
            "material_cost_applied": _field(material_cost_applied, "boolean"),
        },
        "machining": {
            "base_machine_hours": _field(values["base_machine_hours"], "h", "removed_volume_cm3 / effective_mrr_cm3_hour"),
            "effective_mrr_cm3_hour": _field(values["removal_rate_cm3_hour"], "cm3/h"),
            "machinability_factor": _field(values["material"].machinability_factor, "multiplier"),
            "complexity_multiplier": _field(values["complexity_multiplier"], "multiplier"),
            "risk_multiplier": _field(values["risk_multiplier"], "multiplier"),
            "finishing_multiplier": _field(values["finishing_multiplier"], "multiplier"),
            "final_machine_hours": _field(
                values["final_machine_hours"],
                "h",
                "base_machine_hours * machinability_factor * complexity_multiplier * risk_multiplier * finishing_multiplier",
            ),
            "machining_cost_brl": _field(values["machining_cost_brl"], "BRL", "final_machine_hours * machine_rate_brl_hour"),
        },
        "setup": {
            "setup_hours": _field(values["setup_hours"], "h"),
            "setup_cost_brl": _field(values["setup_cost_brl"], "BRL"),
            "setup_cost_per_unit": _field(values["setup_cost_brl"] / quantity, "BRL/un"),
        },
        "cpv": {
            "total_cpv_brl": _field(values["total_cpv_brl"], "BRL"),
            "unit_cpv_brl": _field(values["unit_cpv_brl"], "BRL/un"),
        },
        "sale": {
            "markup_floor": _field(values["markup_floor"], "multiplier"),
            "markup_ceiling": _field(values["markup_ceiling"], "multiplier"),
            "price_floor_brl": _field(values["price_floor_brl"], "BRL"),
            "price_ceiling_brl": _field(values["price_ceiling_brl"], "BRL"),
            "minimum_order_value_applied": _field(values["minimum_order_value_applied"], "boolean"),
        },
    }
    memory["effective_mrr_breakdown"] = values["effective_mrr_breakdown"]
    memory["estimated_hours_breakdown"] = {
        "removed_volume_cm3": values["removed_volume_cm3"],
        "effective_mrr_cm3_hour": values["removal_rate_cm3_hour"],
        "estimated_machine_hours": values["final_machine_hours"],
        "formula": "removed_volume_cm3 / effective_mrr_cm3_hour",
    }
    memory["diagnostics"] = _diagnostics(memory)
    return memory


def _field(value: Any, unit: str, formula: str | None = None) -> dict[str, Any]:
    payload = {"value": round(value, 4) if isinstance(value, float) else value, "unit": unit}
    if formula:
        payload["formula"] = formula
    return payload


def _diagnostics(memory: dict[str, Any]) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    real_volume = _value(memory, "volumes", "real_volume_cm3")
    removed_volume = _value(memory, "volumes", "removed_volume_cm3")
    stock_volume = _value(memory, "volumes", "stock_adjusted_volume_cm3")
    bbox_cm3 = _value(memory, "volumes", "bounding_box_volume_cm3")
    base_hours = _value(memory, "machining", "base_machine_hours")
    final_hours = _value(memory, "machining", "final_machine_hours")
    price_floor = _value(memory, "sale", "price_floor_brl")
    price_ceiling = _value(memory, "sale", "price_ceiling_brl")
    material_cost = _value(memory, "material", "material_cost_brl")
    total_cpv = _value(memory, "cpv", "total_cpv_brl")

    if real_volume > 0 and removed_volume / real_volume > 5:
        warnings.append(_warning("removed_volume_high", "Volume removido muito maior que volume real da peça."))
    if base_hours > 50:
        warnings.append(_warning("base_machine_hours_high", "Horas base acima de 50 h. Verifique removal rate e volume removido."))
    if final_hours > 100:
        warnings.append(_warning("final_machine_hours_high", "Horas finais acima de 100 h. Multiplicadores podem estar amplificando demais."))
    if price_floor > 0 and price_ceiling / price_floor > 2:
        warnings.append(_warning("price_range_too_wide", "Preço teto está mais que 2x acima do preço piso."))
    if total_cpv > 0 and material_cost / total_cpv > 0.7:
        warnings.append(_warning("material_cost_dominates_cpv", "Custo material representa mais de 70% do CPV."))
    if bbox_cm3 > 0 and stock_volume / bbox_cm3 > 1000:
        warnings.append(_warning("stock_volume_1000x_suspect", "Volume de tarugo ajustado parece 1000x maior que bounding box. Verifique unidades."))

    for section_name, section in memory.items():
        if not isinstance(section, dict):
            continue
        for field_name, field in section.items():
            if isinstance(field, dict) and "value" in field and _invalid_number(field["value"], field_name):
                warnings.append(_warning("invalid_numeric_value", f"Valor inválido em {section_name}.{field_name}: {field['value']}"))

    return warnings


def _value(memory: dict[str, Any], section: str, key: str) -> float:
    return float(memory[section][key]["value"] or 0)


def _warning(code: str, message: str) -> dict[str, str]:
    return {"level": "warning", "code": code, "message": message}


def _invalid_number(value: Any, field_name: str) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    if not math.isfinite(value) or value < 0:
        return True
    zero_allowed = {
        "material_cost_brl",
        "removed_volume_cm3",
        "setup_cost_brl",
        "setup_cost_per_unit",
    }
    return value == 0 and field_name not in zero_allowed
