from app.schemas.analysis_schema import (
    ComplexityProfile,
    DerivedMetrics,
    GeometryMetrics,
    ManufacturingProfile,
    ManufacturingRisk,
    ReviewRecommendation,
    RiskBreakdown,
    ShapeProfile,
)


def estimate_manufacturing_risk(
    geometry: GeometryMetrics,
    derived_metrics: DerivedMetrics,
    complexity: ComplexityProfile,
    shape_profile: ShapeProfile,
    manufacturing_profile: ManufacturingProfile,
) -> ManufacturingRisk:
    flags = _risk_flags(geometry, derived_metrics, complexity, shape_profile, manufacturing_profile)
    breakdown = _risk_breakdown(geometry, derived_metrics, complexity, shape_profile, manufacturing_profile)
    risk_score = round(
        min(
            (breakdown.geometric_risk * 0.30)
            + (breakdown.machining_risk * 0.28)
            + (breakdown.fixturing_risk * 0.24)
            + (breakdown.commercial_risk * 0.18),
            1.0,
        ),
        4,
    )

    return ManufacturingRisk(
        risk_score=risk_score,
        risk_level=_risk_level(risk_score),
        risk_breakdown=breakdown,
        risk_flags=flags,
    )


def build_review_recommendation(
    complexity: ComplexityProfile,
    manufacturing_risk: ManufacturingRisk,
) -> ReviewRecommendation:
    review_reasons = [
        flag
        for flag in manufacturing_risk.risk_flags
        if flag
        in {
            "extreme_low_occupancy",
            "high_feature_density",
            "possible_fixture_challenge",
            "possible_thin_wall",
            "fragmented_or_complex_import",
            "compact_but_complex",
            "engineering_review_required",
            "geometry_healed",
            "moderate_geometry_reconstruction",
            "aggressive_geometry_reconstruction",
            "forced_geometry_reconstruction",
            "low_geometry_confidence",
            "surface_based_geometry",
            "reconstructed_solid",
        }
    ]
    requires_review = (
        bool(review_reasons)
        or manufacturing_risk.risk_score >= 0.62
        or complexity.complexity_score >= 0.70
    )

    return ReviewRecommendation(
        requires_engineering_review=requires_review,
        reason=review_reasons,
        confidence=_review_confidence(requires_review, manufacturing_risk.risk_score, complexity.complexity_score),
    )


def _risk_flags(
    geometry: GeometryMetrics,
    derived_metrics: DerivedMetrics,
    complexity: ComplexityProfile,
    shape_profile: ShapeProfile,
    manufacturing_profile: ManufacturingProfile,
) -> list[str]:
    flags: list[str] = []

    if geometry.is_assembly and max(geometry.xlen_mm, geometry.ylen_mm, geometry.zlen_mm) > 800:
        flags.append("large_assembly")
    elif geometry.is_assembly:
        flags.append("multi_solid_geometry")

    if geometry.face_count > 1200:
        flags.extend(["very_high_face_count", "high_surface_complexity"])
    elif geometry.face_count > 500:
        flags.append("very_high_face_count")
    elif geometry.face_count > 180:
        flags.append("high_face_count")

    if geometry.occupancy_ratio < 0.03:
        flags.extend(["extreme_low_occupancy", "very_low_occupancy"])
    elif geometry.occupancy_ratio < 0.08:
        flags.append("very_low_occupancy")
    elif geometry.occupancy_ratio < 0.18:
        flags.append("low_occupancy")

    if derived_metrics.feature_density_by_volume > 5:
        flags.append("high_feature_density")
    elif derived_metrics.feature_density_by_volume > 2:
        flags.append("elevated_feature_density")

    if shape_profile.primary_shape in {"sparse_geometry", "thin_featured_geometry"}:
        flags.append("possible_thin_wall")

    if derived_metrics.thinness_ratio < 0.05 and max(geometry.xlen_mm, geometry.ylen_mm) > 500:
        flags.extend(["large_plate_geometry", "possible_vibration_risk"])
    elif derived_metrics.thinness_ratio < 0.12 and geometry.face_count > 250:
        flags.append("possible_fixture_challenge")

    if shape_profile.primary_shape in {"unknown_complex", "sparse_geometry", "compact_complex"}:
        flags.append("fragmented_or_complex_import")

    if geometry.real_volume_cm3 < 500 and geometry.face_count > 500:
        flags.append("compact_but_complex")

    if geometry.xlen_mm > 1000 or geometry.ylen_mm > 1000 or geometry.zlen_mm > 800:
        flags.append("large_part")

    if complexity.complexity_level == "high":
        flags.append("high_complexity")

    if manufacturing_profile.machining_profile == "engineering_review_required":
        flags.append("engineering_review_required")
    elif manufacturing_profile.machining_profile == "precision_fixture_required":
        flags.append("precision_fixture_required")

    return _dedupe(flags)


def _risk_breakdown(
    geometry: GeometryMetrics,
    derived_metrics: DerivedMetrics,
    complexity: ComplexityProfile,
    shape_profile: ShapeProfile,
    manufacturing_profile: ManufacturingProfile,
) -> RiskBreakdown:
    geometric_risk = 0.0
    machining_risk = 0.0
    fixturing_risk = 0.0
    commercial_risk = 0.0

    geometric_risk += derived_metrics.occupancy_extremity_score * 0.42
    geometric_risk += min(derived_metrics.feature_density_by_volume / 12, 0.32)
    if shape_profile.primary_shape in {"unknown_complex", "sparse_geometry", "thin_featured_geometry"}:
        geometric_risk += 0.22
    elif shape_profile.primary_shape == "compact_complex":
        geometric_risk += 0.18

    machining_risk += min(geometry.face_count / 1800, 0.42)
    machining_risk += complexity.complexity_score * 0.34
    machining_risk += min(derived_metrics.processing_complexity_signal * 0.18, 0.18)
    if manufacturing_profile.machining_profile in {"complex_3_axis_milling", "engineering_review_required"}:
        machining_risk += 0.18

    if derived_metrics.thinness_ratio < 0.05:
        fixturing_risk += 0.42
    elif derived_metrics.thinness_ratio < 0.12:
        fixturing_risk += 0.24
    if geometry.occupancy_ratio < 0.05:
        fixturing_risk += 0.28
    if geometry.real_volume_cm3 < 500 and geometry.face_count > 500:
        fixturing_risk += 0.18
    if shape_profile.secondary_shape == "thin_wall_like":
        fixturing_risk += 0.12

    max_xy = max(geometry.xlen_mm, geometry.ylen_mm)
    if max_xy > 1500:
        commercial_risk += 0.34
    elif max_xy > 900:
        commercial_risk += 0.24
    if geometry.face_count > 1200:
        commercial_risk += 0.18
    if manufacturing_profile.machining_profile == "engineering_review_required":
        commercial_risk += 0.20

    return RiskBreakdown(
        geometric_risk=round(min(geometric_risk, 1.0), 4),
        machining_risk=round(min(machining_risk, 1.0), 4),
        fixturing_risk=round(min(fixturing_risk, 1.0), 4),
        commercial_risk=round(min(commercial_risk, 1.0), 4),
    )


def _risk_level(score: float) -> str:
    if score < 0.32:
        return "low"
    if score < 0.62:
        return "medium"
    return "high"


def _review_confidence(requires_review: bool, risk_score: float, complexity_score: float) -> str:
    if not requires_review:
        return "high"
    if risk_score >= 0.72 or complexity_score >= 0.78:
        return "high"
    return "medium"


def _dedupe(flags: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []

    for flag in flags:
        if flag not in seen:
            deduped.append(flag)
            seen.add(flag)

    return deduped
