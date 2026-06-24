from typing import Any

from app.pricing.assumptions_engine import build_mold_pricing_assumptions
from app.pricing.commercial_engine import calculate_mold_commercials
from app.pricing.cost_estimator import build_industrial_cost_groups, build_service_costs
from app.pricing.cost_dominance_analyzer import analyze_cost_dominance
from app.pricing.edm_engine import estimate_edm
from app.pricing.effective_mrr_engine import estimate_fractioned_cnc_machining
from app.pricing.engineering_engine import estimate_bench_assembly, estimate_engineering, estimate_treatments
from app.pricing.hardware_components_engine import estimate_hardware_components, estimate_hot_runner
from app.pricing.material_engine import consolidate_material_costs, plastic_material_meta
from app.pricing.materials_sanity_engine import apply_materials_sanity_check
from app.pricing.movement_cost_templates import movement_totals
from app.pricing.quote_breakdown import build_quote_breakdown
from app.pricing.steel_package_engine import estimate_steel_package
from app.pricing.tryout_engine import estimate_tryout
from app.schemas.mold_quote_schema import MoldPricingEstimate, MoldTechnicalInput
from app.pricing.calibration_settings import load_calibration_settings


def calculate_mold_pricing_estimate(
    analysis: dict[str, Any],
    technical_input: MoldTechnicalInput,
) -> MoldPricingEstimate:
    steel_package = estimate_steel_package(analysis, technical_input)
    material_costs = consolidate_material_costs(
        steel_package["groups"],
        steel_package.get("material_selection_alerts", []),
    )
    _apply_moldbase_purchase_to_materials(material_costs, steel_package)
    material_costs["plastic_material_meta"] = plastic_material_meta(technical_input.plastic_material)
    hardware = estimate_hardware_components(steel_package, technical_input)
    hot_runner = estimate_hot_runner(technical_input)
    cnc = estimate_fractioned_cnc_machining(analysis, technical_input, steel_package)
    edm = estimate_edm(analysis, technical_input, cnc)
    engineering = estimate_engineering(analysis, technical_input)
    treatments = estimate_treatments(steel_package, technical_input)
    bench = estimate_bench_assembly(steel_package, technical_input)
    tryout = estimate_tryout(analysis, technical_input, steel_package)
    confidence = calculate_mold_confidence(analysis, technical_input, steel_package, cnc, edm)
    service_costs = build_service_costs(
        cnc=cnc,
        edm=edm,
        engineering=engineering,
        treatments=treatments,
        bench=bench,
        tryout=tryout,
    )
    materials_sanity = apply_materials_sanity_check(
        material_costs=material_costs,
        hardware_components=hardware,
        hot_runner=hot_runner,
        service_costs=service_costs,
        calibration=load_calibration_settings(),
    )
    material_costs["materials_sanity_check"] = materials_sanity
    if materials_sanity["alerts"]:
        confidence["module_notes"] = confidence.get("module_notes", []) + materials_sanity["alerts"]
        confidence["engineering_review_required"] = True
    costs = build_industrial_cost_groups(
        material_costs=material_costs,
        hardware_components=hardware,
        hot_runner=hot_runner,
        materials_sanity=materials_sanity,
        service_costs=service_costs,
    )
    commercial = calculate_mold_commercials(technical_input, costs, confidence)
    cost_dominance = analyze_cost_dominance(costs)
    technical_breakdown = build_quote_breakdown(
        analysis=analysis,
        technical_input=technical_input,
        steel_package=steel_package,
        material_costs=material_costs,
        hardware_components=hardware,
        hot_runner=hot_runner,
        cnc_machining=cnc,
        commercial=commercial,
        confidence=confidence,
    )

    return MoldPricingEstimate(
        steel_package=steel_package,
        material_costs=material_costs,
        hardware_components=hardware,
        hot_runner=hot_runner,
        cnc_machining=cnc,
        edm=edm,
        engineering=engineering,
        treatments=treatments,
        bench_assembly=bench,
        tryout=tryout,
        commercial=commercial,
        assumptions=build_mold_pricing_assumptions(technical_input),
        cost_dominance=cost_dominance,
        confidence=confidence,
        technical_breakdown=technical_breakdown,
    )


def recalculate_quote_from_inputs(
    analysis: dict[str, Any],
    technical_input: MoldTechnicalInput,
) -> MoldPricingEstimate:
    """Central recalculation entry point used by manual overrides and live editing."""
    return calculate_mold_pricing_estimate(analysis, technical_input)


def _apply_moldbase_purchase_to_materials(
    material_costs: dict[str, Any],
    steel_package: dict[str, Any],
) -> None:
    moldbase_cost = float(steel_package.get("moldbase_purchase", {}).get("applied_cost_brl", 0.0))
    if moldbase_cost <= 0:
        return
    material_costs["porta_molde_brl"] = round(float(material_costs.get("porta_molde_brl", 0.0)) + moldbase_cost, 2)
    material_costs["total_material_cost_brl"] = round(float(material_costs.get("total_material_cost_brl", 0.0)) + moldbase_cost, 2)
    groups = material_costs.setdefault("material_cost_groups", {})
    groups["porta_molde"] = round(float(groups.get("porta_molde", 0.0)) + moldbase_cost, 2)


def calculate_mold_confidence(
    analysis: dict[str, Any],
    technical_input: MoldTechnicalInput,
    steel_package: dict[str, Any],
    cnc_machining: dict[str, Any],
    edm: dict[str, Any],
) -> dict[str, Any]:
    geometry_confidence = float(analysis.get("geometry_confidence", {}).get("score", 0.82))
    complexity_level = analysis.get("complexity", {}).get("complexity_level", "medium")
    confidence = geometry_confidence
    reasons: list[str] = []
    if complexity_level == "high":
        confidence -= 0.08
        reasons.append("high_geometry_complexity")
    movement_metrics = movement_totals(technical_input)
    if technical_input.has_sliders:
        confidence -= min(
            movement_metrics["risk"] * 0.025 if technical_input.special_movements else technical_input.slider_count * 0.03,
            0.16,
        )
        reasons.append("moving_elements_present")
    if technical_input.injection_type == "hot_runner":
        confidence -= 0.05
        reasons.append("hot_runner_cost_table_assumption")
    if technical_input.mold_lifetime in {"HIGH_1M", "HEAVY_ABOVE_1M"}:
        confidence -= 0.04
        reasons.append("high_lifetime_mold_requires_more_robust_assumptions")
    if technical_input.dimensional_requirement in {"HIGH_PRECISION", "CRITICAL"}:
        confidence -= 0.05
        reasons.append("high_dimensional_requirement")
    if technical_input.visual_requirement in {"CRITICAL_APPEARANCE", "HIGH_GLOSS", "SPECIFIED_TEXTURE"}:
        confidence -= 0.04
        reasons.append("high_visual_requirement")
    if technical_input.cad_movement_warning:
        confidence -= 0.12
        reasons.append("cad_movement_warning")
    if cnc_machining.get("manual_review_required"):
        confidence -= 0.10
        reasons.append("missing_or_incomplete_mrr_configuration")
    if edm["required_likelihood"] == "medium":
        confidence -= 0.06
        reasons.append("edm_estimated_heuristically")
    if steel_package["mold_scale"] == "large_mold":
        confidence -= 0.04
        reasons.append("large_mold_package")

    score = round(max(min(confidence, 0.96), 0.35), 4)
    level = "high"
    if score < 0.50:
        level = "mandatory_review"
    elif score < 0.70:
        level = "low"
    elif score < 0.90:
        level = "medium"
    return {
        "overall_score": score,
        "overall_level": level,
        "geometry_confidence_score": geometry_confidence,
        "module_notes": reasons or ["baseline_parametric_mold_estimate"],
        "engineering_review_required": (
            level in {"low", "mandatory_review"}
            or technical_input.cad_movement_warning
            or cnc_machining.get("manual_review_required", False)
        ),
        "cnc_hours_basis": cnc_machining["total_cnc_hours"],
        "mrr_config_version": cnc_machining.get("mrr_config_version", technical_input.mrr_config_version),
    }


