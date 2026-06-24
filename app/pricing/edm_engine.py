from typing import Any

from app.schemas.mold_quote_schema import MoldTechnicalInput


def estimate_edm(
    analysis: dict[str, Any],
    technical_input: MoldTechnicalInput,
    cnc_machining: dict[str, Any],
) -> dict[str, Any]:
    edm_need = _edm_need(analysis, technical_input)
    face_count = int(analysis.get("geometry", {}).get("face_count", 0))
    target_components = _target_components(edm_need["edm_target_component"])
    cavity_hours = sum(
        float(group["estimated_hours"])
        for group in cnc_machining.get("groups", [])
        if group.get("group") in target_components
        or group.get("component_type") in target_components
        or group.get("manufacturing_template") in target_components
    )
    reasons = list(edm_need["reasons"])
    if edm_need["edm_required"] and cavity_hours <= 0:
        all_cnc_hours = sum(float(group.get("estimated_hours", 0.0)) for group in cnc_machining.get("groups", []))
        cavity_hours = max(all_cnc_hours * 0.28, max(technical_input.cavity_count, 1) * 4.0)
        reasons.append("edm_fallback_hours_due_to_missing_target_allocation")
    multiplier = edm_need["edm_multiplier"]
    if technical_input.cavity_count > 1 and multiplier:
        multiplier = max(multiplier, 0.12)
        reasons.append("multiple_cavities")
    if technical_input.has_sliders and multiplier:
        multiplier += 0.04
        reasons.append("sliders_present")
    if face_count > 1500 and multiplier:
        multiplier += 0.04
        reasons.append("high_face_count")

    edm_burning_hours = cavity_hours * multiplier
    minimum_burning_hours = _minimum_edm_burning_hours(
        edm_need["edm_required"],
        edm_need["edm_intensity"],
        technical_input,
    )
    if edm_need["edm_required"] and edm_burning_hours < minimum_burning_hours:
        edm_burning_hours = minimum_burning_hours
        reasons.append("minimum_edm_hours_for_local_molding_details")
    electrode_machining_hours = edm_burning_hours * 0.35
    electrode_material_cost = (
        max(technical_input.cavity_count, 1)
        * 180
        * (1 + technical_input.slider_count * 0.15)
        if edm_need["edm_required"]
        else 0
    )
    edm_rate = 180
    electrode_rate = 150
    total_cost = edm_burning_hours * edm_rate + electrode_machining_hours * electrode_rate + electrode_material_cost
    return {
        "edm_required": edm_need["edm_required"],
        "edm_intensity": edm_need["edm_intensity"],
        "edm_target_component": edm_need["edm_target_component"],
        "edm_target_components": sorted(target_components),
        "eletroerosao_edm_hours": round(edm_burning_hours, 4),
        "eletroerosao_edm_cost_brl": round(edm_burning_hours * edm_rate, 2),
        "eletroerosao_wire_edm_hours": 0.0,
        "eletroerosao_wire_edm_cost_brl": 0.0,
        "required_likelihood": edm_need["required_likelihood"],
        "edm_multiplier_over_cavity_cnc": round(multiplier, 4),
        "electrode_machining_hours": round(electrode_machining_hours, 4),
        "electrode_material_cost_brl": round(electrode_material_cost, 2),
        "edm_burning_hours": round(edm_burning_hours, 4),
        "edm_total_cost_brl": round(total_cost, 2),
        "reasons": reasons,
        "method": "targeted_edm_by_geometry_complexity_and_mold_construction",
    }


def _edm_need(analysis: dict[str, Any], technical_input: MoldTechnicalInput) -> dict[str, Any]:
    level = analysis.get("complexity", {}).get("complexity_level", "medium")
    geometry = analysis.get("geometry", {})
    derived = analysis.get("derived_metrics", {})
    face_count = int(geometry.get("face_count", 0))
    occupancy_ratio = float(geometry.get("occupancy_ratio", 0.0) or 0.0)
    feature_density = float(derived.get("feature_density_by_volume", 0.0) or 0.0)
    surface_signal = float(derived.get("surface_complexity_signal", 0.0) or 0.0)
    risk_flags = set(analysis.get("manufacturing_risk", {}).get("risk_flags", []))
    inserted = (
        getattr(technical_input, "mold_construction_type", None) in {"insertado_posticado", "hibrido"}
        or technical_input.cavity_type == "inserted"
    )
    target = "insert" if inserted else "plate"
    reasons: list[str] = []
    intensity = "none"
    multiplier = 0.0

    if level == "high":
        intensity = "medium"
        multiplier = 0.16
        reasons.append("high_geometry_complexity")
    elif level == "medium" and (
        technical_input.main_finish in {"HIGH_GLOSS", "MIRROR_POLISH", "TEXTURED", "MIXED"}
        or technical_input.dimensional_requirement in {"HIGH_PRECISION", "CRITICAL"}
    ):
        intensity = "low"
        multiplier = 0.08
        reasons.append("finish_or_precision_requires_edm_review")
    elif level == "medium":
        intensity = "low"
        multiplier = 0.05
        reasons.append("medium_geometry_complexity_local_edm_allowance")
    if (
        multiplier == 0.0
        and (
            face_count >= 420
            or feature_density >= 3.0
            or surface_signal >= 0.22
            or 0 < occupancy_ratio <= 0.08
            or "possible_thin_wall" in risk_flags
        )
    ):
        intensity = "low"
        multiplier = 0.035
        reasons.append("low_intensity_edm_for_molding_details")
    if face_count > 1800 or "high_feature_density" in risk_flags:
        intensity = "high" if intensity == "medium" else "medium"
        multiplier = max(multiplier, 0.22)
        reasons.append("high_feature_density_or_face_count")
    if technical_input.has_movements and level in {"medium", "high"}:
        multiplier = max(multiplier, 0.12)
        intensity = "medium" if intensity == "none" else intensity
        target = "both" if not inserted else "insert"
        reasons.append("mechanisms_may_require_local_edm")
    if technical_input.special_movements:
        edm_movement_types = {
            "COLLAPSIBLE_CORE",
            "NEGATIVE_JAW",
            "ROTARY_CORE",
            "MOVABLE_CORE",
            "MOVABLE_INSERT",
            "RETRACTABLE_CORE",
            "CUSTOM",
        }
        if any(
            movement.uses_edm
            or movement.complexity in {"HIGH", "CRITICAL"}
            or str(movement.movement_type) in edm_movement_types
            for movement in technical_input.special_movements
        ):
            multiplier = max(multiplier, 0.10)
            intensity = "medium" if intensity == "none" else intensity
            target = "both" if not inserted else "insert"
            reasons.append("movement_template_or_override_requires_edm")

    return {
        "edm_required": multiplier > 0,
        "edm_intensity": intensity,
        "edm_target_component": target,
        "edm_multiplier": multiplier,
        "required_likelihood": "medium" if multiplier else "low",
        "reasons": reasons,
    }


def _minimum_edm_burning_hours(
    edm_required: bool,
    intensity: str,
    technical_input: MoldTechnicalInput,
) -> float:
    if not edm_required:
        return 0.0
    cavities = max(int(technical_input.cavity_count or 1), 1)
    movements = max(int(technical_input.number_of_movements or 0), 0)
    base_by_intensity = {
        "low": 0.75,
        "medium": 1.5,
        "high": 2.5,
    }
    base = base_by_intensity.get(intensity, 0.75)
    cavity_extra = max(cavities - 1, 0) * 0.22
    movement_extra = movements * 0.18
    return round(base + cavity_extra + movement_extra, 4)


def _target_components(target: str) -> set[str]:
    inserts = {"inserto_cavidade", "inserto_macho", "gaveta", "lifter", "inserto_moldante"}
    plates = {"placa_cavidade", "placa_macho", "placa_cavidade_monobloco", "placa_macho_monobloco"}
    if target == "insert":
        return inserts
    if target == "both":
        return inserts | plates
    return plates


