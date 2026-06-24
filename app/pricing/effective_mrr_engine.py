from app.schemas.analysis_schema import (
    ComplexityProfile,
    DerivedMetrics,
    GeometryMetrics,
    ManufacturingProfile,
    ManufacturingRisk,
    PricingParameters,
    ShapeProfile,
)
from app.schemas.mold_quote_schema import MoldTechnicalInput
from app.pricing.machining_time_estimator import estimate_component_machining
from app.pricing.mrr_config import (
    MRR_CONFIG_VERSION,
    estimate_machining_time_by_volume,
    steel_material_from_internal,
)
from app.services.mold_calibration_service import load_mold_calibration


def calculate_effective_mrr(
    *,
    material_id: str,
    geometry: GeometryMetrics,
    derived_metrics: DerivedMetrics,
    complexity: ComplexityProfile,
    shape_profile: ShapeProfile,
    manufacturing_profile: ManufacturingProfile,
    manufacturing_risk: ManufacturingRisk,
    parameters: PricingParameters,
) -> dict[str, float]:
    base_mrr = parameters.base_mrr_by_material.get(material_id) or parameters.base_mrr_by_material.get("steel_1045", 1200)
    geometry_factor = _geometry_factor(geometry, derived_metrics, shape_profile)
    complexity_factor = _complexity_factor(geometry, derived_metrics, complexity)
    machine_factor = _machine_factor(manufacturing_profile.machining_profile)
    finish_factor = _finish_factor(derived_metrics, geometry)
    rigidity_factor = _rigidity_factor(geometry, derived_metrics, manufacturing_risk)
    setup_factor = _setup_factor(manufacturing_risk, manufacturing_profile)
    effective_mrr = max(
        base_mrr
        * geometry_factor
        * complexity_factor
        * machine_factor
        * finish_factor
        * rigidity_factor
        * setup_factor,
        1.0,
    )
    return {
        "base_mrr_cm3_hour": round(base_mrr, 4),
        "geometry_factor": round(geometry_factor, 4),
        "complexity_factor": round(complexity_factor, 4),
        "machine_factor": round(machine_factor, 4),
        "finish_factor": round(finish_factor, 4),
        "rigidity_factor": round(rigidity_factor, 4),
        "setup_factor": round(setup_factor, 4),
        "effective_mrr_cm3_hour": round(effective_mrr, 4),
    }


def calculate_material_efficiency_factor(
    geometry: GeometryMetrics,
    derived_metrics: DerivedMetrics,
    shape_profile: ShapeProfile,
) -> float:
    if shape_profile.primary_shape == "plate_like":
        return 0.92
    if shape_profile.primary_shape == "block_like" and geometry.occupancy_ratio > 0.65:
        return 0.95
    if shape_profile.primary_shape in {"sparse_geometry", "thin_featured_geometry", "unknown_complex"}:
        return 0.55
    if geometry.occupancy_ratio < 0.25 or derived_metrics.occupancy_extremity_score > 0.4:
        return 0.68
    if shape_profile.primary_shape in {"compact_complex", "unknown"}:
        return 0.72
    return 0.85


def estimate_fractioned_cnc_machining(
    analysis: dict,
    technical_input: MoldTechnicalInput,
    steel_package: dict,
) -> dict:
    fabricated_components = steel_package.get("fabricated_components")
    if fabricated_components:
        calibration = load_mold_calibration()
        return estimate_component_machining(
            analysis,
            technical_input,
            fabricated_components,
            calibration,
        )

    complexity_level = analysis.get("complexity", {}).get("complexity_level", "medium")
    face_count = int(analysis.get("geometry", {}).get("face_count", 0))
    groups = []
    total_hours = 0.0
    total_cost = 0.0
    mappings = [
        ("base_plates", "base_set", "PLATE_ROUGHING", 0.30, 1.20),
        ("ejector_plates", "ejector_set", "PLATE_ROUGHING", 0.35, 1.08),
        ("cavity_blocks", "molding_set", "CAVITY_ROUGHING", 0.48, 0.72),
        ("cores", "cores", "CORE_ROUGHING", 0.55, 0.64),
        ("cavity_pockets", "cavity_inserts", "CAVITY_SEMI_FINISHING", 0.62, 0.56),
        ("inserts", "additional_insert_support", "CAVITY_SEMI_FINISHING", 0.52, 0.58),
    ]
    steel_groups = {group["group"]: group for group in steel_package["groups"]}
    manual_review_reasons: list[str] = []
    for machining_group, steel_group_name, operation, removal_ratio, group_productivity in mappings:
        steel_group = steel_groups.get(steel_group_name)
        if not steel_group:
            continue
        base_mrr = float(steel_group["base_mrr_cm3_hour"])
        removed_volume = float(steel_group["volume_cm3"]) * removal_ratio
        steel_material = steel_material_from_internal(str(steel_group["material"]))
        time_result = estimate_machining_time_by_volume(
            removed_volume_cm3=removed_volume,
            operation=operation,
            steel_material=steel_material,
        )
        material_factor = _mold_material_factor(str(steel_group["material"]))
        complexity_factor = _mold_complexity_factor(complexity_level, face_count)
        machine_factor, machine_route = _mold_machine_route(analysis, machining_group)
        finish_factor = _mold_finish_factor(machining_group, technical_input)
        rigidity_factor = _mold_rigidity_factor(analysis, machining_group)
        config = time_result["config_used"]
        configured_mrr = config.get("effective_mrr_cm3_hour") or base_mrr
        effective_mrr = max(
            float(configured_mrr)
            * group_productivity
            * material_factor
            * complexity_factor
            * machine_factor
            * finish_factor
            * rigidity_factor,
            25.0,
        )
        if time_result["requires_manual_review"]:
            manual_review_reasons.append(f"{operation}/{steel_material}: {time_result.get('reason')}")
        cutting_hours = removed_volume / effective_mrr
        setup_hours = float(config.get("fixed_setup_hours") or 0)
        hours = (cutting_hours + setup_hours) * float(config.get("complexity_factor") or 1) * float(config.get("conservative_factor") or 1.3)
        rate = float(config.get("machine_hour_rate") or _mold_machine_rate(machine_route))
        cost = hours * rate
        total_hours += hours
        total_cost += cost
        groups.append(
            {
                "group": machining_group,
                "source_steel_group": steel_group_name,
                "operation": operation,
                "steel_material": steel_material,
                "machine_route": machine_route,
                "base_mrr_cm3_hour": round(float(configured_mrr), 4),
                "material_factor": round(material_factor, 4),
                "geometry_factor": round(group_productivity, 4),
                "complexity_factor": round(complexity_factor, 4),
                "machine_factor": round(machine_factor, 4),
                "finish_factor": round(finish_factor, 4),
                "rigidity_factor": round(rigidity_factor, 4),
                "effective_mrr_cm3_hour": round(effective_mrr, 4),
                "removed_volume_cm3": round(removed_volume, 4),
                "estimated_hours": round(hours, 4),
                "machine_rate_brl_hour": rate,
                "machining_cost_brl": round(cost, 2),
                "requires_manual_review": time_result["requires_manual_review"],
                "mrr_config_used": config,
            }
        )
    return {
        "groups": groups,
        "total_cnc_hours": round(total_hours, 4),
        "total_cnc_cost_brl": round(total_cost, 2),
        "mrr_config_version": MRR_CONFIG_VERSION,
        "manual_review_required": bool(manual_review_reasons),
        "manual_review_reasons": manual_review_reasons,
        "method": "fractioned_effective_mrr_by_mold_group",
    }


def _geometry_factor(geometry: GeometryMetrics, derived_metrics: DerivedMetrics, shape_profile: ShapeProfile) -> float:
    factor = 1.0
    if shape_profile.primary_shape == "plate_like" and derived_metrics.thinness_ratio < 0.08:
        factor *= 0.72
    elif shape_profile.primary_shape == "block_like" and geometry.occupancy_ratio > 0.60:
        factor *= 1.05
    if shape_profile.primary_shape == "unknown":
        factor *= 0.82
    if geometry.occupancy_ratio < 0.18:
        factor *= 0.78
    return max(min(factor, 1.15), 0.45)


def _complexity_factor(geometry: GeometryMetrics, derived_metrics: DerivedMetrics, complexity: ComplexityProfile) -> float:
    factor = 1.0 - min(complexity.topology_complexity_score * 0.28, 0.28)
    if geometry.face_count > 2500:
        factor *= 0.78
    elif geometry.face_count > 1200:
        factor *= 0.86
    if derived_metrics.feature_density_by_volume > 1:
        factor *= 0.86
    if geometry.shell_count > 1:
        factor *= 0.92
    return max(factor, 0.40)


def _machine_factor(machining_profile: str) -> float:
    return {
        "bench_milling": 0.82,
        "vertical_milling": 1.0,
        "portal_milling": 0.93,
        "complex_3_axis_milling": 0.72,
        "precision_fixture_required": 0.64,
        "engineering_review_required": 0.55,
        "lathe_candidate": 1.08,
        "mold_base_candidate": 0.95,
    }.get(machining_profile, 0.9)


def _finish_factor(derived_metrics: DerivedMetrics, geometry: GeometryMetrics) -> float:
    factor = 1.0 - min(derived_metrics.surface_complexity_signal * 0.22, 0.22)
    if geometry.face_count > 1500:
        factor *= 0.88
    if derived_metrics.feature_density_by_bbox > 0.02:
        factor *= 0.92
    return max(factor, 0.55)


def _rigidity_factor(geometry: GeometryMetrics, derived_metrics: DerivedMetrics, manufacturing_risk: ManufacturingRisk) -> float:
    factor = 1.0
    if derived_metrics.thinness_ratio < 0.05:
        factor *= 0.77
    elif derived_metrics.thinness_ratio < 0.12:
        factor *= 0.88
    if "possible_vibration_risk" in manufacturing_risk.risk_flags or "possible_thin_wall" in manufacturing_risk.risk_flags:
        factor *= 0.84
    if max(geometry.xlen_mm, geometry.ylen_mm) > 1200 and derived_metrics.thinness_ratio < 0.08:
        factor *= 0.82
    return max(factor, 0.45)


def _setup_factor(manufacturing_risk: ManufacturingRisk, manufacturing_profile: ManufacturingProfile) -> float:
    factor = 1.0
    if "possible_fixture_challenge" in manufacturing_risk.risk_flags:
        factor *= 0.90
    if manufacturing_profile.setup_hours >= 1:
        factor *= 0.95
    if "engineering_review_required" in manufacturing_risk.risk_flags:
        factor *= 0.86
    return max(factor, 0.70)


def _mold_material_factor(material: str) -> float:
    return {
        "steel_1045": 1.0,
        "steel_p20": 0.88,
        "steel_h13": 0.66,
        "stainless_420": 0.70,
        "aluminum": 1.35,
    }.get(material, 0.9)


def _mold_complexity_factor(level: str, face_count: int) -> float:
    factor = {"low": 1.0, "medium": 0.82, "high": 0.62}.get(level, 0.82)
    if face_count > 2000:
        factor *= 0.78
    elif face_count > 900:
        factor *= 0.88
    return max(factor, 0.38)


def _mold_machine_route(analysis: dict, group: str) -> tuple[float, str]:
    geometry = analysis.get("geometry", {})
    max_xy = max(float(geometry.get("xlen_mm", 0.0)), float(geometry.get("ylen_mm", 0.0)))
    zlen = float(geometry.get("zlen_mm", 0.0))
    if group in {"cavity_blocks", "cores", "cavity_pockets", "inserts"}:
        return 0.78, "high_speed_milling"
    if max_xy > 1000 or zlen > 650:
        return 0.92, "portal"
    if max_xy < 450:
        return 0.86, "Romi D600"
    return 1.0, "bench_milling"


def _mold_machine_rate(route: str) -> float:
    return {
        "Romi D600": 170,
        "portal": 240,
        "high_speed_milling": 220,
        "bench_milling": 150,
    }.get(route, 180)


def _mold_finish_factor(group: str, technical_input: MoldTechnicalInput) -> float:
    factor = 1.0
    if group in {"cavity_blocks", "cores", "cavity_pockets", "inserts"}:
        factor *= 0.82
    if technical_input.main_finish in {"MIRROR_POLISH", "HIGH_GLOSS"} or technical_input.has_mirror_polish_areas:
        factor *= 0.78
    if technical_input.main_finish == "TEXTURED" or technical_input.has_textured_areas:
        factor *= 0.88
    return max(factor, 0.50)


def _mold_rigidity_factor(analysis: dict, group: str) -> float:
    derived = analysis.get("derived_metrics", {}) or {}
    thinness = float(derived.get("thinness_ratio", 0.2) or 0.2)
    factor = 1.0
    if thinness < 0.06 and group in {"cavity_blocks", "cores", "cavity_pockets"}:
        factor *= 0.82
    elif thinness < 0.12:
        factor *= 0.92
    return max(factor, 0.60)
