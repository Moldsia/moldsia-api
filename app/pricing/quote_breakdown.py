from typing import Any

from app.schemas.mold_quote_schema import MoldTechnicalInput


def build_quote_breakdown(
    *,
    analysis: dict[str, Any],
    technical_input: MoldTechnicalInput,
    steel_package: dict[str, Any],
    material_costs: dict[str, Any],
    hardware_components: dict[str, Any],
    hot_runner: dict[str, Any],
    cnc_machining: dict[str, Any],
    commercial: dict[str, Any],
    confidence: dict[str, Any],
) -> dict[str, Any]:
    sizing = steel_package.get("mold_sizing", {})
    components = cnc_machining.get("components", [])
    alerts = list(sizing.get("alerts", []))
    alerts.extend(steel_package.get("material_selection_alerts", []))
    if confidence.get("engineering_review_required"):
        alerts.append("engineering_review_required_by_confidence_engine")
    if analysis.get("review_recommendation", {}).get("requires_engineering_review"):
        alerts.append("step_analysis_recommends_engineering_review")
    alerts.extend(material_costs.get("materials_sanity_check", {}).get("alerts", []))
    alerts.extend(hot_runner.get("alerts", []))

    return {
        "step_data": _step_data(analysis),
        "user_inputs": technical_input.model_dump(),
        "cavity_layout": sizing.get("cavity_layout", {}),
        "raw_mold_base": sizing.get("raw_mold_base", {}),
        "selected_mold_base": sizing.get("selected_mold_base", {}),
        "height_breakdown": sizing.get("height_breakdown", {}),
        "steel_margins": sizing.get("steel_margins", {}),
        "mold_construction_type": steel_package.get("mold_construction_type"),
        "material_breakdown": _material_breakdown(material_costs, steel_package),
        "component_bom": _component_bom(hardware_components),
        "hot_runner_breakdown": hot_runner,
        "materials_sanity_check": material_costs.get("materials_sanity_check", {}),
        "components": _component_summary(steel_package, components),
        "mrr_application": _mrr_application(components),
        "cost_by_center": cnc_machining.get("cost_by_center", {}),
        "real_quote_comparison": _real_quote_comparison(
            technical_input=technical_input,
            commercial=commercial,
            cnc_machining=cnc_machining,
        ),
        "commercial_summary": commercial,
        "alerts": _dedupe(alerts),
        "calibration": {
            "mold_calibration_version": steel_package.get("calibration_version"),
            "mrr_config_version": cnc_machining.get("mrr_config_version"),
            "mrr_unit": cnc_machining.get("mrr_unit", "cm3/min"),
        },
        "method": "audit_snapshot_for_parametric_injection_mold_quote",
    }


def _step_data(analysis: dict[str, Any]) -> dict[str, Any]:
    geometry = analysis.get("geometry", {})
    derived = analysis.get("derived_metrics", {})
    complexity = analysis.get("complexity", {})
    return {
        "file_name": analysis.get("file_name"),
        "xlen_mm": geometry.get("xlen_mm"),
        "ylen_mm": geometry.get("ylen_mm"),
        "zlen_mm": geometry.get("zlen_mm"),
        "part_volume_cm3": geometry.get("real_volume_cm3"),
        "bounding_box_volume_mm3": geometry.get("bounding_box_volume_mm3"),
        "occupancy_ratio": geometry.get("occupancy_ratio"),
        "face_count": geometry.get("face_count"),
        "shell_count": geometry.get("shell_count"),
        "feature_density_by_volume": derived.get("feature_density_by_volume"),
        "surface_complexity_signal": derived.get("surface_complexity_signal"),
        "complexity_score": complexity.get("complexity_score"),
        "complexity_level": complexity.get("complexity_level"),
        "risk_flags": analysis.get("manufacturing_risk", {}).get("risk_flags", []),
    }


def _material_breakdown(material_costs: dict[str, Any], steel_package: dict[str, Any]) -> dict[str, Any]:
    sanity = material_costs.get("materials_sanity_check", {})
    return {
        "moldbase_supply": steel_package.get("moldbase_supply", {}),
        "moldbase_purchase": steel_package.get("moldbase_purchase", {}),
        "peso_total_aco_kg": material_costs.get("peso_total_aco_kg"),
        "custo_total_aco": material_costs.get("custo_total_aco"),
        "materia_prima_aco_brl": material_costs.get("materia_prima_aco_brl"),
        "porta_molde_brl": material_costs.get("porta_molde_brl"),
        "insertos_brl": material_costs.get("insertos_brl"),
        "material_cost_groups": material_costs.get("material_cost_groups", {}),
        "by_material": material_costs.get("by_material", []),
        "steel_component_breakdown": [
            {
                "component_id": item.get("component_id"),
                "component_type": item.get("component_type") or item.get("group"),
                "component_role": item.get("component_role"),
                "manufacturing_template": item.get("manufacturing_template"),
                "geometry_owner": item.get("geometry_owner"),
                "operation_template_used": item.get("operation_template_used"),
                "material_rule_used": item.get("material_rule_used"),
                "thickness_rule_used": item.get("thickness_rule_used"),
                "operations_blocked": item.get("operations_blocked", []),
                "quantity": item.get("quantity", 1),
                "material": item.get("material"),
                "final_dimensions_mm": item.get("final_dimensions_mm"),
                "stock_allowance_mm": item.get("stock_allowance_mm"),
                "stock_dimensions_mm": item.get("stock_dimensions_mm"),
                "volume_bruto_cm3": item.get("volume_bruto_cm3"),
                "peso_kg": item.get("peso_kg") or item.get("estimated_weight_kg"),
                "preco_kg": item.get("preco_kg") or item.get("material_price_brl_kg"),
                "base_material_cost_brl": item.get("base_material_cost_brl"),
                "material_purchase_factors": item.get("material_purchase_factors"),
                "material_cost_brl": item.get("material_cost_brl"),
                "material_cost_applied_brl": item.get("material_cost_applied_brl"),
                "material_cost_group": item.get("material_cost_group"),
                "is_manual_override": item.get("is_manual_override", False),
                "is_locked": item.get("is_locked", False),
                "technical_definition": item.get("technical_definition"),
                "calculation_status": item.get("calculation_status"),
                "needs_review": item.get("needs_review", False),
                "movement_geometry_estimate": item.get("movement_geometry_estimate"),
                "cost_basis": item.get("cost_basis"),
                "excluded_reason": item.get("material_cost_excluded_reason"),
            }
            for item in material_costs.get("steel_component_breakdown", [])
        ],
        "materials_sanity_check": sanity,
    }


def _component_bom(hardware_components: dict[str, Any]) -> dict[str, Any]:
    return {
        "standard_components": hardware_components.get("standard_components", []),
        "peripherals": hardware_components.get("peripherals", []),
        "bom": hardware_components.get("bom", hardware_components.get("components", [])),
        "total_standard_components_cost_brl": hardware_components.get("total_standard_components_cost_brl", 0),
        "total_peripherals_cost_brl": hardware_components.get("total_peripherals_cost_brl", 0),
        "total_components_cost_brl": hardware_components.get("total_components_cost_brl", 0),
        "method": hardware_components.get("method"),
    }


def _component_summary(
    steel_package: dict[str, Any],
    machining_components: list[dict[str, Any]],
) -> dict[str, Any]:
    material_components = steel_package.get("groups", [])
    purchased = steel_package.get("purchased_components", [])
    machining_by_component = {item["component_id"]: item for item in machining_components}
    fabricated = []
    for component in material_components:
        machining = machining_by_component.get(component["component_id"], {})
        fabricated.append(
            {
                "component_id": component.get("component_id"),
                "component_type": component.get("component_type") or component.get("group"),
                "component_role": component.get("component_role"),
                "manufacturing_template": component.get("manufacturing_template"),
                "geometry_owner": component.get("geometry_owner"),
                "operation_template_used": component.get("operation_template_used"),
                "material_rule_used": component.get("material_rule_used"),
                "thickness_rule_used": component.get("thickness_rule_used"),
                "operations_blocked": component.get("operations_blocked", []),
                "quantity": component.get("quantity", 1),
                "material": component.get("material"),
                "dimensions_mm": {
                    "width": component.get("width_mm"),
                    "length": component.get("length_mm"),
                    "thickness": component.get("thickness_mm"),
                },
                "stock_dimensions_mm": component.get("stock_dimensions_mm"),
                "stock_allowance_mm": component.get("stock_allowance_mm"),
                "raw_volume_cm3": component.get("raw_volume_cm3") or component.get("volume_cm3"),
                "volume_bruto_cm3": component.get("volume_bruto_cm3"),
                "estimated_removed_volume_cm3": component.get("estimated_removed_volume_cm3"),
                "estimated_weight_kg": component.get("estimated_weight_kg"),
                "preco_kg": component.get("preco_kg"),
                "material_cost_brl": component.get("material_cost_brl"),
                "material_cost_applied_brl": component.get("material_cost_applied_brl"),
                "material_cost_group": component.get("material_cost_group"),
                "is_manual_override": component.get("is_manual_override", False),
                "is_locked": component.get("is_locked", False),
                "movement_id": component.get("movement_id"),
                "movement_type": component.get("movement_type"),
                "movement_position": component.get("movement_position"),
                "movement_cost_template": component.get("movement_cost_template"),
                "movement_stroke_mm": component.get("movement_stroke_mm"),
                "movement_actuation": component.get("movement_actuation"),
                "movement_complexity": component.get("movement_complexity"),
                "technical_definition": component.get("technical_definition"),
                "calculation_status": component.get("calculation_status"),
                "manual_override": component.get("manual_override", False),
                "needs_review": component.get("needs_review", False),
                "movement_geometry_estimate": component.get("movement_geometry_estimate"),
                "machining_hours": machining.get("estimated_hours"),
                "machining_cost_brl": machining.get("machining_cost_brl"),
                "calculation_method": machining.get("calculation_method"),
                "operations": machining.get("operations", []),
                "alerts": machining.get("alerts", []),
            }
        )
    return {
        "fabricated": fabricated,
        "service_operations": [
            {
                    "component_type": item.get("component_type"),
                    "component_role": item.get("component_role"),
                    "manufacturing_template": item.get("manufacturing_template"),
                    "geometry_owner": item.get("geometry_owner"),
                    "operation_template_used": item.get("operation_template_used"),
                    "operations_blocked": item.get("operations_blocked", []),
                    "raw_volume_cm3": item.get("raw_volume_cm3"),
                "estimated_removed_volume_cm3": item.get("estimated_removed_volume_cm3"),
            }
            for item in steel_package.get("service_components", [])
        ],
        "purchased": purchased,
    }


def _mrr_application(machining_components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for component in machining_components:
        for operation in component.get("operations", []):
            factors = operation.get("factors", {})
            rows.append(
                {
                    "component_type": component["component_type"],
                    "component_role": component.get("component_role"),
                    "manufacturing_template": component.get("manufacturing_template"),
                    "geometry_owner": component.get("geometry_owner"),
                    "operation_template_used": component.get("operation_template_used"),
                    "operations_blocked": component.get("operations_blocked", []),
                    "operation_type": operation["operation_type"],
                    "material": operation["material"],
                    "removed_volume_cm3": operation["removed_volume_cm3"],
                    "base_mrr_cm3_min": operation["base_mrr_cm3_min"],
                    "effective_mrr_cm3_min": operation["effective_mrr_cm3_min"],
                    "machining_time_minutes": operation.get("machining_time_minutes"),
                    "machining_time_formula": operation.get("machining_time_formula"),
                    "mrr_audit_hours": operation.get("mrr_audit_hours"),
                    "mrr_weight": operation.get("mrr_weight"),
                    "base_operation_hours": operation.get("base_operation_hours"),
                    "adjusted_base_operation_hours": operation.get("adjusted_base_operation_hours"),
                    "estimated_hours": operation["estimated_hours"],
                    "machining_cost_brl": operation["machining_cost_brl"],
                    "factors": factors,
                    "lookup_level": operation["mrr_lookup_level"],
                    "calculation_method": operation.get("calculation_method"),
                    "alerts": operation.get("alerts", []),
                }
            )
    return rows


def _real_quote_comparison(
    *,
    technical_input: MoldTechnicalInput,
    commercial: dict[str, Any],
    cnc_machining: dict[str, Any],
) -> dict[str, Any]:
    calibration_input = technical_input.real_quote_calibration
    calculated_price = float(commercial.get("price_suggested_brl") or 0.0)
    if calculated_price <= 0:
        calculated_price = (
            float(commercial.get("price_floor_brl", 0.0))
            + float(commercial.get("price_ceiling_brl", 0.0))
        ) / 2
    real_price = calibration_input.preco_real_referencia
    if not real_price:
        return {
            "has_real_reference": False,
            "preco_calculado": round(calculated_price, 2),
            "preco_real_referencia": None,
            "diferenca_absoluta": None,
            "diferenca_percentual": None,
            "fator_calibracao_sugerido": None,
            "principais_causas_da_diferenca": [],
        }

    absolute = float(real_price) - calculated_price
    percent = (absolute / float(real_price)) * 100 if real_price else 0
    factor = float(real_price) / calculated_price if calculated_price > 0 else None
    causes = _difference_causes(factor or 1.0, cnc_machining)
    return {
        "has_real_reference": True,
        "preco_calculado": round(calculated_price, 2),
        "preco_real_referencia": round(float(real_price), 2),
        "horas_calculadas_componentes_fabricados": cnc_machining.get("total_cnc_hours"),
        "horas_reais_referencia": calibration_input.horas_reais_referencia,
        "diferenca_absoluta": round(absolute, 2),
        "diferenca_percentual": round(percent, 2),
        "fator_calibracao_sugerido": round(factor, 4) if factor else None,
        "apply_global_factor_to_current_quote": calibration_input.apply_global_factor_to_current_quote,
        "principais_causas_da_diferenca": causes,
    }


def _difference_causes(factor: float, cnc_machining: dict[str, Any]) -> list[str]:
    if 0.92 <= factor <= 1.08:
        return ["calculated_quote_close_to_real_reference"]
    if factor < 0.92:
        return [
            "Orcamento calculado acima da referencia real",
            "Revisar conservadorismo, bounds maximos e margem comercial",
            "Verificar se acabamento, tolerancia ou complexidade foram marcados acima do necessario",
        ]
    cost_by_center = cnc_machining.get("cost_by_center", {})
    ranked = sorted(
        cost_by_center.items(),
        key=lambda item: float(item[1].get("cost_brl", 0.0)),
        reverse=True,
    )
    causes = []
    center_map = {
        "cnc_desbaste": "Componentes fabricados - desbaste CNC",
        "cnc_acabamento": "Componentes fabricados - acabamento CNC",
        "furacao": "Furacoes, roscas e alojamentos",
        "furacao_refrigeracao": "Circuitos de refrigeracao",
        "bancada": "Bancada e ajuste",
        "polimento": "Polimento",
        "montagem": "Montagem",
    }
    for center, _value in ranked[:4]:
        causes.append(center_map.get(center, center))
    if factor > 1.35:
        causes.append("Margem ou fator comercial possivelmente subestimado")
    return causes


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
