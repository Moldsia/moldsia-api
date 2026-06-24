from typing import Any

from app.pricing.movement_cost_templates import movement_totals
from app.schemas.mold_quote_schema import MoldTechnicalInput


def estimate_engineering(analysis: dict[str, Any], technical_input: MoldTechnicalInput) -> dict[str, Any]:
    complexity = analysis.get("complexity", {})
    complexity_level = complexity.get("complexity_level", "medium")
    senior_rate = 180
    cam_rate = 150
    base_hours = {"low": 12, "medium": 22, "high": 36}.get(complexity_level, 22)
    cavity_hours = technical_input.cavity_count * 4
    movement_metrics = movement_totals(technical_input)
    slider_hours = movement_metrics["engineering_hours"] if technical_input.special_movements else technical_input.slider_count * 6
    dfm_hours = 8 if technical_input.extras.dfm else 0
    moldflow_hours = 14 if technical_input.extras.moldflow else 0
    senior_hours = 6 if technical_input.plastic_material in {"PA_GLASS_FIBER", "PP_GLASS_FIBER", "PVC"} else 3
    if technical_input.dimensional_requirement in {"HIGH_PRECISION", "CRITICAL"}:
        senior_hours += 4
    if technical_input.visual_requirement in {"CRITICAL_APPEARANCE", "HIGH_GLOSS", "SPECIFIED_TEXTURE"}:
        senior_hours += 3
    cad_cam_hours = base_hours + cavity_hours + slider_hours + dfm_hours + moldflow_hours
    cost = cad_cam_hours * cam_rate + senior_hours * senior_rate
    return {
        "cad_cam_base_hours": base_hours,
        "hours_per_cavity": cavity_hours,
        "hours_for_sliders": slider_hours,
        "dfm_hours": dfm_hours,
        "moldflow_hours": moldflow_hours,
        "senior_engineering_hours": senior_hours,
        "total_engineering_hours": round(cad_cam_hours + senior_hours, 4),
        "engineering_cost_brl": round(cost, 2),
        "method": "parametric_hours_by_complexity_cavities_and_movements",
    }


def estimate_treatments(steel_package: dict[str, Any], technical_input: MoldTechnicalInput) -> dict[str, Any]:
    molding_weight = sum(
        float(group["estimated_weight_kg"])
        for group in steel_package["groups"]
        if group.get("uses_treatment") or group["group"] in {
            "molding_set",
            "cavity_inserts",
            "cores",
            "additional_insert_support",
            "placa_cavidade",
            "placa_macho",
            "inserto_cavidade",
            "inserto_macho",
            "gaveta",
            "lifter",
            "macho_movel",
            "postico",
        }
    )
    nitriding_cost = molding_weight * 18 if technical_input.surface_treatment == "NITRIDING" else 0
    hard_chrome_cost = molding_weight * 26 if technical_input.surface_treatment == "HARD_CHROME" else 0
    coating_cost = molding_weight * 35 if technical_input.surface_treatment == "SPECIAL_COATING" else 0
    heat_treatment_cost = molding_weight * 22 if technical_input.plastic_material in {"PA_GLASS_FIBER", "PP_GLASS_FIBER"} else 0
    polishing_cost = molding_weight * 14 if technical_input.main_finish in {"HIGH_GLOSS", "MIRROR_POLISH"} or technical_input.has_mirror_polish_areas else 0
    texture_cost = molding_weight * 10 if technical_input.main_finish == "TEXTURED" or technical_input.has_textured_areas else 0
    total = nitriding_cost + hard_chrome_cost + coating_cost + heat_treatment_cost + polishing_cost + texture_cost
    return {
        "molding_set_weight_kg": round(molding_weight, 4),
        "nitriding_cost_brl": round(nitriding_cost, 2),
        "hard_chrome_cost_brl": round(hard_chrome_cost, 2),
        "special_coating_cost_brl": round(coating_cost, 2),
        "heat_treatment_cost_brl": round(heat_treatment_cost, 2),
        "mirror_polishing_cost_brl": round(polishing_cost, 2),
        "texture_cost_brl": round(texture_cost, 2),
        "total_treatments_cost_brl": round(total, 2),
        "method": "kg_based_molding_set_treatment_heuristic",
    }


def estimate_bench_assembly(steel_package: dict[str, Any], technical_input: MoldTechnicalInput) -> dict[str, Any]:
    calibration = steel_package.get("assembly_calibration") or {}
    assembly_rules = calibration or _default_assembly_rules()
    mold_scale = steel_package["mold_scale"]
    groups = steel_package.get("groups", [])
    total_weight = sum(float(group.get("estimated_weight_kg", group.get("peso_kg", 0.0))) for group in groups)
    insert_count = sum(
        int(group.get("quantity", 1))
        for group in groups
        if str(group.get("component_type", "")).startswith("inserto_")
    )
    plate_count = sum(1 for group in groups if str(group.get("component_type", "")).startswith("placa_"))
    cooling_circuits = max(2, technical_input.cavity_count * 2 + technical_input.number_of_movements)
    ejector_count = 10 + technical_input.cavity_count * 8 + technical_input.number_of_movements * 2
    blocks_config = assembly_rules["blocks"]
    factors_config = assembly_rules["factors"]
    precision_factor = float(
        factors_config["assembly_precision_factor"].get(technical_input.dimensional_requirement, 1.0)
    )
    tryout_risk_factor = float(
        factors_config["assembly_tryout_risk_factor"].get(
            "high" if technical_input.has_movements or technical_input.cad_movement_warning else "normal",
            1.0,
        )
    )
    size_factor = float(factors_config["assembly_size_factor"].get(mold_scale, 1.0))
    weight_factor = max(1.0, min((total_weight / 650) ** 0.18, 1.35)) if total_weight > 0 else 1.0
    movement_metrics = movement_totals(technical_input)
    blocks = {
        "base_mold_assembly_hours": float(blocks_config["base_mold_assembly_hours"].get(mold_scale, 18)),
        "plate_stack_alignment_hours": float(blocks_config["plate_stack_alignment_hours"]) * max(plate_count, 1) * size_factor,
        "insert_fitting_hours": float(blocks_config["insert_fitting_hours_per_insert"]) * insert_count * float(factors_config["assembly_insert_count_factor"]),
        "ejector_system_assembly_hours": float(blocks_config["ejector_system_base_hours"]) + ejector_count * float(factors_config["assembly_ejector_count_factor"]),
        "cooling_system_assembly_hours": float(blocks_config["cooling_system_base_hours"]) + cooling_circuits * float(factors_config["assembly_cooling_circuit_factor"]),
        "standard_components_assembly_hours": float(blocks_config["standard_components_base_hours"]) + max(plate_count, 1) * 0.35,
        "mechanisms_assembly_hours": (
            movement_metrics["bench_hours"]
            if technical_input.special_movements
            else technical_input.number_of_movements * float(factors_config["assembly_mechanism_factor"])
        ),
        "hot_runner_assembly_hours": (
            float(blocks_config["hot_runner_base_hours"]) + technical_input.hot_runner_drops * float(factors_config["assembly_hot_runner_factor"])
            if technical_input.injection_type == "hot_runner"
            else 0.0
        ),
        "pre_tryout_check_hours": float(blocks_config["pre_tryout_check_hours"]),
        "post_tryout_adjustment_hours": float(blocks_config["post_tryout_adjustment_hours"]) * tryout_risk_factor,
    }
    raw_total = sum(blocks.values())
    total_hours = raw_total * precision_factor * weight_factor
    hourly_rate = float(assembly_rules.get("hourly_rate_brl", 120))
    return {
        "assembly_blocks": {key: round(value, 4) for key, value in blocks.items()},
        "assembly_inputs": {
            "mold_scale": mold_scale,
            "estimated_mold_steel_weight_kg": round(total_weight, 4),
            "plate_count": plate_count,
            "insert_count": insert_count,
            "estimated_ejector_count": ejector_count,
            "estimated_cooling_circuit_count": cooling_circuits,
            "movement_count": technical_input.number_of_movements,
            "movement_template_bench_hours": round(movement_metrics["bench_hours"], 4),
            "hot_runner_drops": technical_input.hot_runner_drops,
        },
        "assembly_factors": {
            "assembly_size_factor": round(size_factor, 4),
            "assembly_weight_factor": round(weight_factor, 4),
            "assembly_precision_factor": round(precision_factor, 4),
            "assembly_tryout_risk_factor": round(tryout_risk_factor, 4),
        },
        "assembly_base_hours": blocks["base_mold_assembly_hours"],
        "slider_adjustment_hours": blocks["mechanisms_assembly_hours"],
        "extraction_adjustment_hours": blocks["ejector_system_assembly_hours"],
        "hydraulic_or_cam_hours": 0,
        "total_bench_hours": round(total_hours, 4),
        "bench_assembly_cost_brl": round(total_hours * hourly_rate, 2),
        "hourly_rate_brl": hourly_rate,
        "method": "assembly_blocks_by_mold_size_inserts_ejection_cooling_mechanisms_and_tryout_risk",
    }


def _default_assembly_rules() -> dict[str, Any]:
    return {
        "hourly_rate_brl": 120,
        "blocks": {
            "base_mold_assembly_hours": {"small_mold": 18, "medium_mold": 30, "large_mold": 52, "extra_large_mold": 84},
            "plate_stack_alignment_hours": 1.2,
            "insert_fitting_hours_per_insert": 2.8,
            "ejector_system_base_hours": 4.0,
            "cooling_system_base_hours": 3.0,
            "standard_components_base_hours": 4.0,
            "hot_runner_base_hours": 8.0,
            "pre_tryout_check_hours": 3.0,
            "post_tryout_adjustment_hours": 6.0,
        },
        "factors": {
            "assembly_size_factor": {"small_mold": 0.9, "medium_mold": 1.0, "large_mold": 1.25, "extra_large_mold": 1.55},
            "assembly_insert_count_factor": 1.0,
            "assembly_ejector_count_factor": 0.18,
            "assembly_cooling_circuit_factor": 0.45,
            "assembly_mechanism_factor": 6.0,
            "assembly_hot_runner_factor": 1.8,
            "assembly_precision_factor": {"NORMAL": 1.0, "MEDIUM_PRECISION": 1.12, "HIGH_PRECISION": 1.28, "CRITICAL": 1.45},
            "assembly_tryout_risk_factor": {"normal": 1.0, "high": 1.35},
        },
    }


