from app.schemas.analysis_schema import (
    ComplexityProfile,
    DerivedMetrics,
    GeometryMetrics,
    MachiningProfile,
    PieceSize,
    ShapeProfile,
)


def classify_piece_size(xlen_mm: float, ylen_mm: float) -> PieceSize:
    if xlen_mm <= 600 and ylen_mm <= 600:
        return "small"

    return "large"


def classify_machining_profile(
    geometry: GeometryMetrics,
    shape_profile: ShapeProfile,
    complexity: ComplexityProfile,
    derived_metrics: DerivedMetrics,
) -> MachiningProfile:
    if _requires_engineering_review(geometry, complexity, derived_metrics, shape_profile):
        return "engineering_review_required"

    if geometry.xlen_mm > 900 or geometry.ylen_mm > 900:
        return "portal_milling"

    if _requires_precision_fixture(geometry, derived_metrics, shape_profile):
        return "precision_fixture_required"

    if _is_complex_small_milling(geometry, complexity, derived_metrics, shape_profile):
        return "complex_3_axis_milling"

    if shape_profile.primary_shape in {"shaft_like", "cylindrical_like"}:
        return "lathe_candidate"

    if (
        shape_profile.primary_shape == "block_like"
        and geometry.occupancy_ratio > 0.55
        and geometry.xlen_mm >= 250
        and geometry.ylen_mm >= 250
    ):
        return "mold_base_candidate"

    if geometry.xlen_mm <= 350 and geometry.ylen_mm <= 350 and geometry.zlen_mm <= 250:
        return "bench_milling"

    return "vertical_milling"


def _requires_engineering_review(
    geometry: GeometryMetrics,
    complexity: ComplexityProfile,
    derived_metrics: DerivedMetrics,
    shape_profile: ShapeProfile,
) -> bool:
    return (
        geometry.occupancy_ratio < 0.03
        and derived_metrics.feature_density_by_volume > 5
        and geometry.face_count > 500
    ) or (
        complexity.complexity_score >= 0.72
        and shape_profile.primary_shape in {"unknown_complex", "sparse_geometry", "thin_featured_geometry"}
    )


def _requires_precision_fixture(
    geometry: GeometryMetrics,
    derived_metrics: DerivedMetrics,
    shape_profile: ShapeProfile,
) -> bool:
    return (
        derived_metrics.thinness_ratio < 0.08
        and geometry.face_count > 250
        and shape_profile.primary_shape in {"thin_featured_geometry", "plate_like", "sparse_geometry"}
    )


def _is_complex_small_milling(
    geometry: GeometryMetrics,
    complexity: ComplexityProfile,
    derived_metrics: DerivedMetrics,
    shape_profile: ShapeProfile,
) -> bool:
    is_small_envelope = geometry.xlen_mm <= 600 and geometry.ylen_mm <= 600
    return is_small_envelope and (
        complexity.complexity_score >= 0.55
        or derived_metrics.feature_density_by_volume > 2.5
        or shape_profile.primary_shape in {"compact_complex", "unknown_complex", "sparse_geometry"}
    )
