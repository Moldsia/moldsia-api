from typing import Any

from app.pricing.calibration_settings import load_calibration_settings
from app.schemas.mold_quote_schema import MoldTechnicalInput


def calculate_mold_commercials(
    technical_input: MoldTechnicalInput,
    costs: dict[str, float],
    confidence: dict[str, Any],
) -> dict[str, Any]:
    config = load_calibration_settings().get("commercial_markup", {})
    cpv_total = sum(costs.values())
    markup_floor = float(config.get("base_floor", 1.22))
    markup_suggested = float(config.get("base_target", 1.35))
    markup_ceiling = float(config.get("base_ceiling", 1.58))

    if technical_input.production_volume == "prototype":
        markup_floor += float(config.get("prototype_floor_add", 0.03))
        markup_suggested += float(config.get("prototype_target_add", 0.05))
        markup_ceiling += float(config.get("prototype_ceiling_add", 0.08))
    if technical_input.production_volume == "high":
        markup_suggested += float(config.get("high_volume_target_add", 0.0))
        markup_ceiling += float(config.get("high_volume_ceiling_add", 0.04))
    if technical_input.has_sliders:
        markup_suggested += float(config.get("slider_target_add", 0.02))
        markup_ceiling += float(config.get("slider_ceiling_add", 0.04))
    if confidence.get("overall_level") in {"low", "mandatory_review"}:
        markup_suggested += float(config.get("low_confidence_target_add", 0.03))
        markup_ceiling += float(config.get("low_confidence_ceiling_add", 0.08))

    markup_suggested = min(max(markup_suggested, markup_floor), markup_ceiling)
    price_floor = cpv_total * markup_floor
    price_suggested = cpv_total * markup_suggested
    price_ceiling = max(cpv_total * markup_ceiling, price_floor)

    return {
        "currency": "BRL",
        "cpv_total_brl": round(cpv_total, 2),
        "costs": {key: round(value, 2) for key, value in costs.items()},
        "markup_floor": round(markup_floor, 4),
        "markup_suggested": round(markup_suggested, 4),
        "markup_ceiling": round(markup_ceiling, 4),
        "price_floor_brl": round(price_floor, 2),
        "price_suggested_brl": round(price_suggested, 2),
        "price_ceiling_brl": round(price_ceiling, 2),
        "margin_range": {
            "floor": _margin(price_floor, cpv_total),
            "suggested": _margin(price_suggested, cpv_total),
            "ceiling": _margin(price_ceiling, cpv_total),
        },
        "pricing_policy": config.get("policy_name", "configurable_target_markup_not_ceiling"),
    }


def _margin(price: float, cpv_total: float) -> float:
    return round((price - cpv_total) / price, 4) if price else 0.0
