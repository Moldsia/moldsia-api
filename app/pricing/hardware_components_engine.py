from typing import Any

from app.pricing.movement_cost_templates import movement_template
from app.schemas.mold_quote_schema import MoldTechnicalInput
from app.services.mold_calibration_service import load_mold_calibration


BASE_COMPONENT_TABLE = {
    "small_mold": {"screws": 850, "o_rings": 280, "springs": 420, "columns_bushings": 1800, "nipples": 220},
    "medium_mold": {"screws": 1400, "o_rings": 420, "springs": 720, "columns_bushings": 3200, "nipples": 380},
    "large_mold": {"screws": 2400, "o_rings": 680, "springs": 1200, "columns_bushings": 5600, "nipples": 620},
}


def estimate_hardware_components(steel_package: dict[str, Any], technical_input: MoldTechnicalInput) -> dict[str, Any]:
    calibration = load_mold_calibration()
    mold_scale = steel_package["mold_scale"]
    library = calibration.get("standard_component_library", {})
    if not library:
        return _fallback_hardware_components(steel_package, technical_input)

    bom = [
        _bom_item(key, item, mold_scale, technical_input)
        for key, item in library.items()
    ]
    bom.extend(_movement_hardware_bom(technical_input))
    if not technical_input.special_movements and technical_input.slider_motion_type == "hydraulic_cylinders":
        bom.append(
            {
                "component": "cilindros_hidraulicos",
                "nome": "Cilindros hidraulicos",
                "category": "componentes_normalizados",
                "quantity": technical_input.slider_count,
                "unit_price_brl": 2800.0,
                "size_factor": 1.0,
                "complexity_factor": 1.0,
                "cost_brl": round(technical_input.slider_count * 2800, 2),
                "formula": "quantity * unit_price_brl",
            }
        )
    if technical_input.extraction_type == "rotary_core":
        bom.append(
            {
                "component": "macho_rotativo_normalizado",
                "nome": "Macho rotativo normalizado",
                "category": "componentes_normalizados",
                "quantity": 1,
                "unit_price_brl": 4500.0,
                "size_factor": 1.0,
                "complexity_factor": 1.0,
                "cost_brl": 4500.0,
                "formula": "fixed_rotary_core_component_cost",
            }
        )

    standard_components = [item for item in bom if item["category"] == "componentes_normalizados"]
    peripherals = [item for item in bom if item["category"] == "perifericos"]
    standard_total = sum(float(item["cost_brl"]) for item in standard_components)
    peripherals_total = sum(float(item["cost_brl"]) for item in peripherals)
    return {
        "mold_scale": mold_scale,
        "bom": bom,
        "components": bom,
        "standard_components": standard_components,
        "peripherals": peripherals,
        "total_standard_components_cost_brl": round(standard_total, 2),
        "total_peripherals_cost_brl": round(peripherals_total, 2),
        "total_components_cost_brl": round(standard_total + peripherals_total, 2),
        "method": "configurable_bom_by_base_cavities_mechanisms_size_and_complexity",
    }


def _movement_hardware_bom(technical_input: MoldTechnicalInput) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for movement in technical_input.special_movements:
        template = movement_template(str(movement.movement_type))
        for component, unit_price in template.get("purchased_components", {}).items():
            result.append(
                {
                    "component": component,
                    "nome": component.replace("_", " ").title(),
                    "movement_id": movement.id,
                    "movement_type": movement.movement_type,
                    "category": "componentes_normalizados",
                    "quantity": movement.quantity,
                    "unit_price_brl": round(float(unit_price), 2),
                    "size_factor": 1.0,
                    "complexity_factor": 1.0,
                    "cost_brl": round(float(unit_price) * movement.quantity, 2),
                    "formula": "movement_quantity * movement_template_unit_price",
                }
            )
    return result


def estimate_hot_runner(technical_input: MoldTechnicalInput) -> dict[str, Any]:
    calibration = load_mold_calibration()
    config = calibration.get("hot_runner_cost_library", {})
    if technical_input.injection_type != "hot_runner":
        return {
            "required": False,
            "drops": 0,
            "cost_per_drop_brl": 0,
            "breakdown": [],
            "alerts": [],
            "total_hot_runner_cost_brl": 0,
            "method": "not_applicable_cold_runner",
        }
    drops = max(technical_input.hot_runner_drops, 1)
    base_cost = float(config.get("hot_runner_base_cost", 8500))
    cost_per_nozzle = float(config.get("cost_per_nozzle", 4200))
    controller_cost = float(config.get("controller_cost", 3800))
    cable_sensor_cost = float(config.get("cable_sensor_cost_per_nozzle", 950)) * drops
    installation_hours = float(config.get("installation_hours", 6))
    installation_rate = float(config.get("installation_hourly_rate", 120))
    installation_cost = installation_hours * installation_rate
    supplier_markup = float(config.get("supplier_markup", 1.0))
    subtotal = base_cost + cost_per_nozzle * drops + controller_cost + cable_sensor_cost + installation_cost
    total = subtotal * supplier_markup
    alerts = []
    if total <= 0:
        alerts.append("hot_runner_selected_but_configured_cost_is_zero_review_configuration")
    return {
        "required": True,
        "drops": drops,
        "cost_per_drop_brl": cost_per_nozzle,
        "hot_runner_base_cost_brl": round(base_cost, 2),
        "controller_cost_brl": round(controller_cost, 2),
        "cable_sensor_cost_brl": round(cable_sensor_cost, 2),
        "installation_hours": round(installation_hours, 4),
        "installation_cost_brl": round(installation_cost, 2),
        "supplier_markup": supplier_markup,
        "breakdown": [
            {"item": "manifold_base", "cost_brl": round(base_cost, 2)},
            {"item": "bicos", "quantity": drops, "unit_cost_brl": cost_per_nozzle, "cost_brl": round(cost_per_nozzle * drops, 2)},
            {"item": "controlador", "cost_brl": round(controller_cost, 2)},
            {"item": "cabos_sensores", "quantity": drops, "cost_brl": round(cable_sensor_cost, 2)},
            {"item": "instalacao_ajustes", "hours": round(installation_hours, 4), "cost_brl": round(installation_cost, 2)},
        ],
        "alerts": alerts,
        "total_hot_runner_cost_brl": round(total, 2),
        "method": "configurable_hot_runner_manifold_nozzles_controller_installation",
    }


def _slider_cost(motion_type: str) -> float:
    return {
        "inclined_pins": 1800,
        "cams": 2600,
        "hydraulic_cylinders": 1800,
        "none": 0,
    }.get(motion_type, 0)


def _bom_item(
    key: str,
    config: dict[str, Any],
    mold_scale: str,
    technical_input: MoldTechnicalInput,
) -> dict[str, Any]:
    quantity = (
        float(config.get("quantidade_base", 0))
        + float(config.get("quantidade_por_cavidade", 0)) * technical_input.cavity_count
        + float(config.get("quantidade_por_mecanismo", 0)) * technical_input.number_of_movements
    )
    quantity = int(max(round(quantity), 0))
    size_factor = _size_factor(config.get("fator_tamanho_molde", 1.0), mold_scale)
    complexity_factor = float(config.get("fator_complexidade", 1.0))
    if technical_input.has_movements:
        complexity_factor *= 1.08
    if technical_input.dimensional_requirement in {"HIGH_PRECISION", "CRITICAL"}:
        complexity_factor *= 1.04
    unit_price = float(config.get("preco_unitario", 0.0))
    cost = quantity * unit_price * size_factor * complexity_factor
    return {
        "component": key,
        "nome": config.get("nome", key),
        "category": config.get("categoria", "componentes_normalizados"),
        "quantity": quantity,
        "unit_price_brl": round(unit_price, 2),
        "size_factor": round(size_factor, 4),
        "complexity_factor": round(complexity_factor, 4),
        "cost_brl": round(cost, 2),
        "formula": "quantity * unit_price_brl * size_factor * complexity_factor",
    }


def _size_factor(value: Any, mold_scale: str) -> float:
    if isinstance(value, dict):
        return float(value.get(mold_scale, value.get("medium_mold", 1.0)))
    return float(value or 1.0)


def _fallback_hardware_components(steel_package: dict[str, Any], technical_input: MoldTechnicalInput) -> dict[str, Any]:
    mold_scale = steel_package["mold_scale"]
    components = dict(BASE_COMPONENT_TABLE[mold_scale])
    if technical_input.has_sliders:
        components["cams_or_slider_hardware"] = technical_input.slider_count * _slider_cost(technical_input.slider_motion_type)
    if technical_input.slider_motion_type == "hydraulic_cylinders":
        components["hydraulic_components"] = technical_input.slider_count * 2800
    if technical_input.extraction_type == "rotary_core":
        components["rotary_core_components"] = 4500
    bom = [
        {
            "component": key,
            "category": "componentes_normalizados",
            "quantity": 1,
            "cost_brl": round(value, 2),
        }
        for key, value in components.items()
    ]
    total = sum(float(value) for value in components.values())
    return {
        "mold_scale": mold_scale,
        "bom": bom,
        "components": bom,
        "standard_components": bom,
        "peripherals": [],
        "total_standard_components_cost_brl": round(total, 2),
        "total_peripherals_cost_brl": 0.0,
        "total_components_cost_brl": round(total, 2),
        "method": "fallback_table_by_mold_scale_plus_movement_adders",
    }


