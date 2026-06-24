from typing import Any


def apply_materials_sanity_check(
    *,
    material_costs: dict[str, Any],
    hardware_components: dict[str, Any],
    hot_runner: dict[str, Any],
    service_costs: dict[str, float],
    calibration: dict[str, Any],
) -> dict[str, Any]:
    config = calibration.get("materials_sanity_check", {})
    expected_share = float(config.get("expected_materials_share", 0.30))
    min_share = float(config.get("min_materials_share", 0.22))
    max_share = float(config.get("max_materials_share", 0.40))
    apply_floor = bool(config.get("apply_materials_floor", False))
    indicator_only = bool(config.get("materials_share_indicator_only", not apply_floor))

    material_groups = {
        "materia_prima_aco": float(material_costs.get("materia_prima_aco_brl", 0.0)),
        "porta_molde": float(material_costs.get("porta_molde_brl", 0.0)),
        "insertos": float(material_costs.get("insertos_brl", 0.0)),
        "componentes_normalizados": float(hardware_components.get("total_standard_components_cost_brl", 0.0)),
        "perifericos": float(hardware_components.get("total_peripherals_cost_brl", 0.0)),
        "camara_quente": float(hot_runner.get("total_hot_runner_cost_brl", 0.0)),
    }
    bottom_up_total = sum(material_groups.values())
    services_total = sum(max(float(value), 0.0) for value in service_costs.values())
    bottom_up_industrial = bottom_up_total + services_total
    bottom_up_share = bottom_up_total / bottom_up_industrial if bottom_up_industrial else 0.0

    materials_floor = expected_share / max(1 - expected_share, 0.01) * services_total
    floor_adjustment = max(materials_floor - bottom_up_total, 0.0) if apply_floor and not indicator_only else 0.0
    applied_total = bottom_up_total + floor_adjustment
    industrial_subtotal = applied_total + services_total
    applied_share = applied_total / industrial_subtotal if industrial_subtotal else 0.0

    alerts: list[str] = []
    if bottom_up_share < min_share:
        alerts.append(
            "materials_share_below_reference_indicator_only:"
            f"{round(bottom_up_share * 100, 2)}pct<{round(min_share * 100, 2)}pct"
        )
    if bottom_up_share > max_share:
        alerts.append(
            "materials_share_above_reference_indicator_only:"
            f"{round(bottom_up_share * 100, 2)}pct>{round(max_share * 100, 2)}pct"
        )
    if floor_adjustment > 0:
        alerts.append("materials_floor_applied_due_to_low_bottom_up_share")
    elif indicator_only and (bottom_up_share < min_share or bottom_up_share > max_share):
        alerts.append("materials_share_outside_reference_no_automatic_adjustment")
    if hot_runner.get("required") and float(hot_runner.get("total_hot_runner_cost_brl", 0.0)) <= 0:
        alerts.append("hot_runner_selected_but_cost_is_zero_review_configuration")

    return {
        "expected_materials_share": expected_share,
        "min_materials_share": min_share,
        "max_materials_share": max_share,
        "apply_materials_floor": apply_floor,
        "materials_share_indicator_only": indicator_only,
        "materials_groups_bottom_up_brl": {key: round(value, 2) for key, value in material_groups.items()},
        "materials_total_bottom_up_brl": round(bottom_up_total, 2),
        "services_total_brl": round(services_total, 2),
        "materials_floor_brl": round(materials_floor, 2),
        "materials_floor_adjustment_brl": round(floor_adjustment, 2),
        "materials_total_applied_brl": round(applied_total, 2),
        "industrial_subtotal_brl": round(industrial_subtotal, 2),
        "bottom_up_materials_share": round(bottom_up_share, 4),
        "materials_share": round(applied_share, 4),
        "alerts": alerts,
        "method": "bottom_up_materials_checked_against_configurable_industrial_share_floor",
    }
