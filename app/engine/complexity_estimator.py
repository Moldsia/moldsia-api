from app.schemas.analysis_schema import (
    ComplexityBreakdown,
    ComplexityProfile,
    DerivedMetrics,
    GeometryMetrics,
    ShapeProfile,
)


def estimate_complexity(
    geometry: GeometryMetrics,
    derived_metrics: DerivedMetrics,
    shape_profile: ShapeProfile,
) -> ComplexityProfile:
    occupancy_component = _occupancy_component(geometry, derived_metrics)
    topology_component = _topology_complexity_score(geometry, derived_metrics, shape_profile)
    surface_component = _surface_component(geometry, derived_metrics)
    shape_component = _shape_component(geometry, derived_metrics, shape_profile)
    processing_component = _processing_component(derived_metrics)

    score = (
        occupancy_component * 0.12
        + topology_component * 0.34
        + surface_component * 0.22
        + shape_component * 0.14
        + processing_component * 0.18
    )
    score = max(score, _minimum_score_floor(geometry, derived_metrics, shape_profile))

    complexity_score = round(min(score, 1.0), 4)
    return ComplexityProfile(
        complexity_score=complexity_score,
        complexity_level=_complexity_level(complexity_score),
        topology_complexity_score=round(topology_component, 4),
        complexity_breakdown=ComplexityBreakdown(
            occupancy_component=round(occupancy_component, 4),
            topology_component=round(topology_component, 4),
            surface_component=round(surface_component, 4),
            shape_component=round(shape_component, 4),
            processing_component=round(processing_component, 4),
        ),
        threshold_diagnostics=_threshold_diagnostics(geometry, derived_metrics, shape_profile),
    )


def _occupancy_component(
    geometry: GeometryMetrics,
    derived_metrics: DerivedMetrics,
) -> float:
    score = derived_metrics.occupancy_extremity_score * 0.65
    if geometry.occupancy_ratio < 0.02:
        score += 0.18
    elif geometry.occupancy_ratio < 0.05:
        score += 0.15
    elif geometry.occupancy_ratio < 0.12:
        score += 0.10
    elif geometry.occupancy_ratio < 0.25:
        score += 0.06
    return min(score, 1.0)


def _topology_complexity_score(
    geometry: GeometryMetrics,
    derived_metrics: DerivedMetrics,
    shape_profile: ShapeProfile,
) -> float:
    score = 0.0

    if geometry.face_count > 2500:
        score += 0.62
    elif geometry.face_count > 1500:
        score += 0.52
    elif geometry.face_count > 600:
        score += 0.36
    elif geometry.face_count > 150:
        score += 0.20

    if geometry.shell_count > 6:
        score += 0.16
    elif geometry.shell_count > 1:
        score += 0.10

    if geometry.solid_count > 8:
        score += 0.14
    elif geometry.solid_count > 1:
        score += 0.08

    if derived_metrics.feature_density_by_volume > 7:
        score += 0.24
    elif derived_metrics.feature_density_by_volume > 3:
        score += 0.18
    elif derived_metrics.feature_density_by_volume > 1:
        score += 0.11
    elif derived_metrics.feature_density_by_volume > 0.03 and geometry.face_count > 1500:
        score += 0.10

    if derived_metrics.feature_density_by_bbox > 0.08:
        score += 0.10
    elif derived_metrics.feature_density_by_bbox > 0.025:
        score += 0.06

    if shape_profile.primary_shape == "unknown" and geometry.face_count > 600:
        score += 0.10

    return min(score, 1.0)


def _surface_component(
    geometry: GeometryMetrics,
    derived_metrics: DerivedMetrics,
) -> float:
    score = derived_metrics.surface_complexity_signal

    if derived_metrics.thinness_ratio < 0.04:
        score += 0.16
    elif derived_metrics.thinness_ratio < 0.10:
        score += 0.10

    if geometry.face_count > 1500 and geometry.shell_count > 1:
        score += 0.10

    return min(score, 1.0)


def _shape_component(
    geometry: GeometryMetrics,
    derived_metrics: DerivedMetrics,
    shape_profile: ShapeProfile,
) -> float:
    score = 0.0
    if shape_profile.primary_shape in {"unknown_complex", "compact_complex", "sparse_geometry"}:
        score += 0.70
    elif shape_profile.primary_shape == "thin_featured_geometry":
        score += 0.78
    elif shape_profile.primary_shape == "unknown":
        score += 0.28
        if geometry.face_count > 1500:
            score += 0.26
        elif geometry.face_count > 600:
            score += 0.16
        if derived_metrics.processing_complexity_signal > 0.25:
            score += 0.14

    return min(score, 1.0)


def _processing_component(derived_metrics: DerivedMetrics) -> float:
    return min(derived_metrics.processing_complexity_signal, 1.0)


def _minimum_score_floor(
    geometry: GeometryMetrics,
    derived_metrics: DerivedMetrics,
    shape_profile: ShapeProfile,
) -> float:
    floor = 0.0
    if geometry.face_count > 2500:
        floor = max(floor, 0.42)
    elif geometry.face_count > 1500:
        floor = max(floor, 0.36)
    elif geometry.face_count > 1200:
        floor = max(floor, 0.34)
    elif geometry.face_count > 600:
        floor = max(floor, 0.28)

    if shape_profile.primary_shape == "unknown" and geometry.face_count > 1500:
        floor = max(floor, 0.46)

    if derived_metrics.processing_complexity_signal >= 0.34 and geometry.face_count > 1500:
        floor = max(floor, 0.48)

    if derived_metrics.surface_complexity_signal >= 0.70:
        floor = max(floor, 0.48)

    return floor


def _complexity_level(score: float) -> str:
    if score < 0.33:
        return "low"
    if score < 0.66:
        return "medium"
    return "high"


def _threshold_diagnostics(
    geometry: GeometryMetrics,
    derived_metrics: DerivedMetrics,
    shape_profile: ShapeProfile,
) -> list[str]:
    diagnostics: list[str] = []

    if geometry.face_count > 2500:
        diagnostics.append("face_count_gt_2500_high_topology")
    elif geometry.face_count > 1500:
        diagnostics.append("face_count_gt_1500_high_topology")
    elif geometry.face_count > 1200:
        diagnostics.append("face_count_gt_1200_medium_high_topology")
    elif geometry.face_count > 600:
        diagnostics.append("face_count_gt_600_medium_high_topology")
    elif geometry.face_count > 150:
        diagnostics.append("face_count_gt_150_medium_topology")

    if geometry.shell_count > 1:
        diagnostics.append("multiple_shells_fragmentation_signal")
    if shape_profile.primary_shape == "unknown":
        diagnostics.append("unknown_shape_penalty_applied")
    if derived_metrics.processing_complexity_signal >= 0.34:
        diagnostics.append("processing_time_gt_10000ms_signal")
    if derived_metrics.surface_complexity_signal >= 0.70:
        diagnostics.append("surface_complexity_high_signal")
    if derived_metrics.feature_density_by_volume > 0.03 and geometry.face_count > 1500:
        diagnostics.append("feature_density_relevant_for_high_face_count")

    return diagnostics
