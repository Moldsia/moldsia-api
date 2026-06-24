from typing import Any

from app.pricing.movement_cost_templates import movement_totals
from app.schemas.mold_quote_schema import MoldTechnicalInput


def estimate_tryout(analysis: dict[str, Any], technical_input: MoldTechnicalInput, steel_package: dict[str, Any]) -> dict[str, Any]:
    geometry = analysis.get("geometry", {})
    mold_base = steel_package.get("mold_sizing", {}).get("selected_mold_base", {})
    xlen = float(mold_base.get("width_mm") or geometry.get("xlen_mm", 0.0))
    ylen = float(mold_base.get("length_mm") or geometry.get("ylen_mm", 0.0))
    total_weight = sum(float(group["estimated_weight_kg"]) for group in steel_package["groups"])
    machine = _suggest_injection_machine(max(xlen, ylen), total_weight)
    shot_count = 60
    if technical_input.production_volume == "high":
        shot_count = 120
    movement_metrics = movement_totals(technical_input)
    if technical_input.special_movements:
        shot_count += movement_metrics["tryout_shots"]
    elif technical_input.has_sliders:
        shot_count += technical_input.slider_count * 20
    plastic_weight_kg = max(float(geometry.get("real_volume_cm3", 0.0)) * 0.00105, 0.05)
    purge_kg = plastic_weight_kg * 8
    plastic_cost_kg = _plastic_cost(technical_input.plastic_material)
    material_cost = (shot_count * plastic_weight_kg + purge_kg) * plastic_cost_kg
    tryout_hours = max(4, shot_count / 18)
    total = tryout_hours * machine["hourly_rate_brl"] + material_cost
    return {
        "suggested_injection_machine": machine["machine"],
        "machine_hourly_rate_brl": machine["hourly_rate_brl"],
        "estimated_shots": round(shot_count, 2),
        "movement_tryout_shots": round(movement_metrics["tryout_shots"], 2),
        "plastic_weight_kg_per_shot": round(plastic_weight_kg, 4),
        "purge_kg": round(purge_kg, 4),
        "plastic_cost_brl": round(material_cost, 2),
        "tryout_hours": round(tryout_hours, 4),
        "tryout_cost_brl": round(total, 2),
        "method": "shots_plus_machine_rate_and_plastic_consumption",
    }


def _suggest_injection_machine(max_xy_mm: float, mold_weight_kg: float) -> dict[str, Any]:
    if max_xy_mm > 1200 or mold_weight_kg > 1800:
        return {"machine": "large_injection_press", "hourly_rate_brl": 520}
    if max_xy_mm > 650 or mold_weight_kg > 650:
        return {"machine": "medium_injection_press", "hourly_rate_brl": 360}
    return {"machine": "small_injection_press", "hourly_rate_brl": 240}


def _plastic_cost(plastic_material: str) -> float:
    return {
        "PP_VIRGIN": 12,
        "PP_COPOLYMER": 13,
        "PP_TALC_20": 15,
        "PP_TALC_40": 17,
        "PP_GLASS_FIBER": 24,
        "PEHD": 13,
        "PELD": 13,
        "ABS": 18,
        "PS_HIPS": 16,
        "POM": 28,
        "PA": 26,
        "PA_GLASS_FIBER": 34,
        "PC": 36,
        "PC_ABS": 32,
        "PMMA": 31,
        "PVC": 18,
        "TPU_TPE": 28,
        "OTHER": 25,
    }.get(plastic_material, 25)


