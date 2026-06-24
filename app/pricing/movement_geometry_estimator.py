from math import ceil
from typing import Any

from app.pricing.material_engine import plastic_material_meta
from app.schemas.mold_quote_schema import MoldTechnicalInput, SpecialMovementInput


def _rule(
    width_factor: float,
    length_factor: float,
    height_factor: float,
    stroke_factor: float,
    material: str,
    uses_edm: bool,
    uses_treatment: bool,
) -> dict[str, Any]:
    return {
        "width_factor": width_factor,
        "length_factor": length_factor,
        "height_factor": height_factor,
        "stroke_factor": stroke_factor,
        "material": material,
        "uses_edm": uses_edm,
        "uses_treatment": uses_treatment,
    }


# Editable parametric defaults. They estimate a manufacturing blank per movement,
# not the final kinematics of a production mold.
MOVEMENT_GEOMETRY_RULES: dict[str, dict[str, Any]] = {
    "SIMPLE_SIDE_SLIDER": _rule(0.36, 0.30, 0.44, 0.28, "steel_p20_2738", False, False),
    "ANGLED_PIN_SLIDER": _rule(0.40, 0.33, 0.48, 0.34, "steel_p20_2738", False, True),
    "HYDRAULIC_SLIDER": _rule(0.46, 0.38, 0.55, 0.45, "steel_p20_2738", False, True),
    "SPECIAL_MECHANICAL_SLIDER": _rule(0.45, 0.37, 0.55, 0.40, "steel_h13", True, True),
    "COLLAPSIBLE_CORE": _rule(0.28, 0.28, 0.72, 0.38, "steel_h13", True, True),
    "NEGATIVE_JAW": _rule(0.42, 0.35, 0.56, 0.36, "steel_h13", True, True),
    "ROTARY_CORE": _rule(0.30, 0.30, 0.78, 0.32, "steel_h13", True, True),
    "FORCED_EJECTION": _rule(0.26, 0.25, 0.42, 0.24, "steel_h13", False, True),
    "LIFTER": _rule(0.22, 0.26, 0.64, 0.34, "steel_h13", True, True),
    "MOVABLE_CORE": _rule(0.32, 0.32, 0.70, 0.42, "steel_h13", True, True),
    "MOVABLE_INSERT": _rule(0.30, 0.28, 0.46, 0.25, "steel_p20_2738", False, True),
    "RETRACTABLE_CORE": _rule(0.35, 0.32, 0.74, 0.46, "steel_h13", True, True),
    "CUSTOM": _rule(0.40, 0.35, 0.58, 0.40, "steel_h13", True, True),
    "UNKNOWN": _rule(0.40, 0.35, 0.58, 0.40, "steel_p20_2738", True, True),
}


def estimate_movement_geometry(
    *,
    movement: SpecialMovementInput,
    corrected_part: dict[str, Any],
    selected_mold_base: dict[str, Any],
    technical_input: MoldTechnicalInput,
) -> dict[str, Any]:
    """Estimate a purchasable blank and technical assumptions for one movement."""
    movement_type = str(movement.movement_type)
    rule = MOVEMENT_GEOMETRY_RULES.get(movement_type, MOVEMENT_GEOMETRY_RULES["UNKNOWN"])
    part_x = max(float(corrected_part.get("x_mm", 0.0)), 20.0)
    part_y = max(float(corrected_part.get("y_mm", 0.0)), 20.0)
    part_z = max(float(corrected_part.get("z_mm", 0.0)), 12.0)
    mold_width = max(float(selected_mold_base.get("width_mm", part_x * 2)), 150.0)
    mold_length = max(float(selected_mold_base.get("length_mm", part_y * 2)), 150.0)

    complexity_factor = {
        "LOW": 0.88,
        "MEDIUM": 1.0,
        "HIGH": 1.18,
        "CRITICAL": 1.35,
        "UNKNOWN": 1.08,
    }.get(str(movement.complexity), 1.08)
    cavity_factor = 1.0 + min(max(technical_input.cavity_count - 1, 0) * 0.025, 0.15)
    quantity_factor = 1.0 + min(max(movement.quantity - 1, 0) * 0.02, 0.10)
    extraction_factor = 1.10 if technical_input.extraction_type in {
        "ejector_plate",
        "forced_ejection",
        "rotary_core",
        "robot",
    } else 1.0
    total_factor = complexity_factor * cavity_factor * quantity_factor * extraction_factor

    estimated_width = _stock_round(
        _clamp(part_x * float(rule["width_factor"]) * total_factor, 45.0, mold_width * 0.46)
    )
    estimated_length = _stock_round(
        _clamp(part_y * float(rule["length_factor"]) * total_factor, 40.0, mold_length * 0.42)
    )
    estimated_height = _stock_round(
        _clamp(part_z * float(rule["height_factor"]) * total_factor, 30.0, max(part_z * 1.35, 45.0))
    )
    estimated_stroke = _stock_round(
        _clamp(part_z * float(rule["stroke_factor"]) * complexity_factor, 10.0, max(part_z * 0.95, 25.0))
    )

    meta = plastic_material_meta(technical_input.plastic_material)
    suggested_material = str(rule["material"])
    if bool(meta.get("abrasive")) or technical_input.mold_lifetime in {"HIGH_1M", "HEAVY_ABOVE_1M"}:
        suggested_material = "steel_h13"
    estimated_uses_edm = bool(rule["uses_edm"]) or movement.complexity in {"HIGH", "CRITICAL"}
    estimated_uses_treatment = (
        bool(rule["uses_treatment"])
        or bool(meta.get("treatment_recommended"))
        or technical_input.mold_lifetime in {"HIGH_1M", "HEAVY_ABOVE_1M"}
    )

    confidence_score = 0.88
    confidence_reasons: list[str] = ["parametric_geometry_from_part_and_mold_envelopes"]
    if movement_type in {"UNKNOWN", "CUSTOM"}:
        confidence_score -= 0.20
        confidence_reasons.append("movement_type_requires_engineering_definition")
    if movement.position in {"AUTO", "UNKNOWN"}:
        confidence_score -= 0.06 if movement.position == "AUTO" else 0.10
        confidence_reasons.append("movement_position_inferred")
    if movement.actuation in {"AUTO", "UNKNOWN"}:
        confidence_score -= 0.06
        confidence_reasons.append("movement_actuation_inferred")
    if movement.complexity == "UNKNOWN":
        confidence_score -= 0.06
        confidence_reasons.append("movement_complexity_inferred")
    if technical_input.cad_movement_warning:
        confidence_score -= 0.08
        confidence_reasons.append("client_requested_automatic_movement_review")
    confidence_score = round(_clamp(confidence_score, 0.35, 0.92), 4)
    confidence_level = "high" if confidence_score >= 0.82 else "medium" if confidence_score >= 0.62 else "low"

    is_manual = movement.technical_definition == "MANUAL"
    return {
        "estimated_width_mm": estimated_width,
        "estimated_length_mm": estimated_length,
        "estimated_height_mm": estimated_height,
        "estimated_stroke_mm": estimated_stroke,
        "suggested_material": suggested_material,
        "estimated_uses_edm": estimated_uses_edm,
        "estimated_uses_treatment": estimated_uses_treatment,
        "applied_width_mm": float(movement.width_mm) if is_manual and movement.width_mm is not None else estimated_width,
        "applied_length_mm": float(movement.length_mm) if is_manual and movement.length_mm is not None else estimated_length,
        "applied_height_mm": float(movement.height_mm) if is_manual and movement.height_mm is not None else estimated_height,
        "applied_stroke_mm": float(movement.stroke_mm) if is_manual and movement.stroke_mm is not None else estimated_stroke,
        "applied_material": movement.material if is_manual else suggested_material,
        "applied_uses_edm": movement.uses_edm if is_manual else estimated_uses_edm,
        "applied_uses_treatment": movement.uses_treatment if is_manual else estimated_uses_treatment,
        "technical_definition": movement.technical_definition,
        "calculation_status": "edited_manually" if is_manual else "calculated_automatically",
        "manual_override": is_manual,
        "needs_review": confidence_level == "low" or movement_type in {"UNKNOWN", "CUSTOM"},
        "confidence_score": confidence_score,
        "confidence_level": confidence_level,
        "confidence_reasons": confidence_reasons,
        "rule_factors": {
            **rule,
            "complexity_factor": complexity_factor,
            "cavity_factor": round(cavity_factor, 4),
            "quantity_factor": round(quantity_factor, 4),
            "extraction_factor": extraction_factor,
        },
        "method": "parametric_movement_blank_from_part_mold_and_project_inputs",
    }


def estimateMovementGeometry(**kwargs: Any) -> dict[str, Any]:
    """Public alias matching the product-domain function name."""
    return estimate_movement_geometry(**kwargs)


def estimateMovementTechnicalData(**kwargs: Any) -> dict[str, Any]:
    """Public alias for the public wizard terminology."""
    return estimate_movement_geometry(**kwargs)


def _stock_round(value: float, increment: float = 5.0) -> float:
    return round(ceil(value / increment) * increment, 4)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, max(maximum, minimum)))
