from app.schemas.analysis_schema import DerivedMetrics, GeometryMetrics, ShapeProfile


def classify_shape(
    geometry: GeometryMetrics,
    derived_metrics: DerivedMetrics,
) -> ShapeProfile:
    dimensions = sorted([geometry.xlen_mm, geometry.ylen_mm, geometry.zlen_mm])
    smallest, middle, largest = [max(value, 0.001) for value in dimensions]
    flatness_ratio = smallest / largest
    slenderness_ratio = largest / middle
    occupancy = geometry.occupancy_ratio

    primary_shape = "unknown"
    secondary_shape = None

    if occupancy < 0.05 and derived_metrics.feature_density_by_volume > 3:
        primary_shape = "sparse_geometry"
    elif occupancy < 0.12 and flatness_ratio < 0.18 and derived_metrics.feature_density_by_volume > 1:
        primary_shape = "thin_featured_geometry"
    elif occupancy < 0.18 and geometry.face_count > 350:
        primary_shape = "unknown_complex"
    elif geometry.real_volume_cm3 < 500 and geometry.face_count > 450:
        primary_shape = "compact_complex"
    elif flatness_ratio < 0.12 and largest > 120:
        primary_shape = "plate_like"
    elif slenderness_ratio > 4 and middle / largest < 0.35:
        primary_shape = "shaft_like"
    elif _looks_cylindrical(geometry, slenderness_ratio):
        primary_shape = "cylindrical_like"
    elif occupancy > 0.65:
        primary_shape = "block_like"

    if occupancy < 0.22 and flatness_ratio < 0.25:
        secondary_shape = "thin_wall_like"
    elif primary_shape != "cylindrical_like" and _looks_cylindrical(geometry, slenderness_ratio):
        secondary_shape = "cylindrical_like"
    elif primary_shape != "block_like" and occupancy > 0.72:
        secondary_shape = "block_like"

    return ShapeProfile(primary_shape=primary_shape, secondary_shape=secondary_shape)


def _looks_cylindrical(geometry: GeometryMetrics, slenderness_ratio: float) -> bool:
    dimensions = sorted([geometry.xlen_mm, geometry.ylen_mm, geometry.zlen_mm])
    smallest, middle, _ = [max(value, 0.001) for value in dimensions]
    radial_similarity = smallest / middle
    return radial_similarity > 0.82 and 0.45 <= geometry.occupancy_ratio <= 0.9 and slenderness_ratio >= 1.2
