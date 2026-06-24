from typing import Any

from app.pricing.calibration_settings import load_calibration_settings
from app.pricing.component_generator import generate_mold_components
from app.pricing.material_engine import calculate_group_material_cost, suggest_molding_steel
from app.pricing.mold_sizer import calculate_mold_sizing
from app.schemas.mold_quote_schema import MoldTechnicalInput


def estimate_steel_package(analysis: dict[str, Any], technical_input: MoldTechnicalInput) -> dict[str, Any]:
    calibration = load_calibration_settings()
    sizing = calculate_mold_sizing(analysis, technical_input, calibration)
    molding_material, alerts = suggest_molding_steel(technical_input)
    components = generate_mold_components(
        analysis=analysis,
        technical_input=technical_input,
        sizing=sizing,
        molding_material=molding_material,
        calibration=calibration,
    )
    costed_groups = [
        calculate_group_material_cost(component, calibration)
        for component in components["material_components"]
    ]
    supply = _apply_moldbase_supply_mode(costed_groups, sizing, calibration)
    alerts.extend(supply["alerts"])
    alerts.extend(components.get("component_generation_alerts", []))
    return {
        "mold_scale": sizing["mold_scale"],
        "estimated_total_volume_cm3": round(sum(float(group["raw_volume_cm3"]) for group in costed_groups), 4),
        "groups": costed_groups,
        "mold_sizing": sizing,
        "moldbase_supply": supply["moldbase_supply"],
        "moldbase_purchase": supply["moldbase_purchase"],
        "mold_construction_type": components["mold_construction_type"],
        "assembly_calibration": calibration.get("assembly_rules", {}),
        "fabricated_components": components["fabricated_components"],
        "material_components": components["material_components"],
        "service_components": components["service_components"],
        "purchased_components": components["purchased_components"],
        "material_selection_alerts": alerts,
        "method": "sized_moldbase_component_stack_from_part_envelope",
        "calibration_version": calibration.get("version"),
    }


_MOLDBASE_COMPONENTS = {
    "placa_superior",
    "placa_porta_manifold",
    "placa_cavidade",
    "placa_macho",
    "placa_suporte",
    "paralelas",
    "placa_extratora_1",
    "placa_extratora_2",
    "placa_inferior",
}

_INSERT_COMPONENTS = {"inserto_cavidade", "inserto_macho"}


def _apply_moldbase_supply_mode(
    groups: list[dict[str, Any]],
    sizing: dict[str, Any],
    calibration: dict[str, Any],
) -> dict[str, Any]:
    supply_config = calibration.get("moldbase_supply", {})
    mode = str(supply_config.get("moldbase_supply_mode", "porta_molde_fabricado_interno"))
    moldbase_purchase = _moldbase_purchase_cost(sizing, supply_config)
    alerts: list[str] = []

    if mode not in {"porta_molde_comprado", "porta_molde_fabricado_interno", "porta_molde_hibrido"}:
        alerts.append(f"unknown_moldbase_supply_mode:{mode}")
        mode = "porta_molde_fabricado_interno"

    for group in groups:
        component_type = str(group.get("component_type") or group.get("group"))
        bottom_up_cost = float(group["material_cost_brl"])
        if component_type in _INSERT_COMPONENTS:
            cost_group = "insertos"
            applied_cost = bottom_up_cost
        elif component_type in _MOLDBASE_COMPONENTS and mode in {"porta_molde_comprado", "porta_molde_hibrido"}:
            cost_group = "porta_molde"
            applied_cost = 0.0
        else:
            cost_group = "materia_prima_aco"
            applied_cost = bottom_up_cost

        group["material_cost_group"] = cost_group
        group["material_cost_applied_brl"] = round(applied_cost, 2)
        group["material_cost_excluded_reason"] = (
            "covered_by_purchased_moldbase"
            if applied_cost == 0 and cost_group == "porta_molde"
            else None
        )

    if mode in {"porta_molde_comprado", "porta_molde_hibrido"}:
        base_cost = float(moldbase_purchase["base_cost_brl"])
        factor_key = "hybrid_adjustment_factor" if mode == "porta_molde_hibrido" else "purchased_adjustment_factor"
        factor = float(supply_config.get(factor_key, 1.0))
        moldbase_purchase["applied_cost_brl"] = round(base_cost * factor, 2)
        moldbase_purchase["purchase_factor"] = factor
    else:
        moldbase_purchase["applied_cost_brl"] = 0.0
        moldbase_purchase["purchase_factor"] = 0.0

    return {
        "moldbase_supply": {
            "moldbase_supply_mode": mode,
            "base_stack_cost_source": (
                "purchased_moldbase_table"
                if mode in {"porta_molde_comprado", "porta_molde_hibrido"}
                else "fabricated_internal_plate_stock"
            ),
        },
        "moldbase_purchase": moldbase_purchase,
        "alerts": alerts,
    }


def _moldbase_purchase_cost(sizing: dict[str, Any], supply_config: dict[str, Any]) -> dict[str, Any]:
    selected = sizing.get("selected_mold_base", {})
    width = float(selected.get("width_mm", 0.0))
    length = float(selected.get("length_mm", 0.0))
    for item in supply_config.get("purchase_table", []):
        if float(item["width"]) >= width and float(item["length"]) >= length:
            return {
                "selected_width_mm": width,
                "selected_length_mm": length,
                "table_width_mm": float(item["width"]),
                "table_length_mm": float(item["length"]),
                "base_cost_brl": round(float(item["base_cost_brl"]), 2),
                "method": "nearest_standard_moldbase_purchase_table",
            }
    area = max(width * length, 1.0)
    largest = max(
        supply_config.get("purchase_table", []),
        key=lambda item: float(item["width"]) * float(item["length"]),
        default={"width": width, "length": length, "base_cost_brl": 0},
    )
    largest_area = max(float(largest["width"]) * float(largest["length"]), 1.0)
    base_cost = float(largest["base_cost_brl"]) * (area / largest_area) ** 0.82
    return {
        "selected_width_mm": width,
        "selected_length_mm": length,
        "table_width_mm": width,
        "table_length_mm": length,
        "base_cost_brl": round(base_cost, 2),
        "method": "extrapolated_moldbase_purchase_table",
    }
