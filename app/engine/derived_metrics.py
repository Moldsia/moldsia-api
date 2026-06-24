from app.schemas.analysis_schema import DerivedMetrics, GeometryMetrics


def calculate_derived_metrics(
    geometry: GeometryMetrics,
    processing_time_ms: int,
) -> DerivedMetrics:
    dimensions = [geometry.xlen_mm, geometry.ylen_mm, geometry.zlen_mm]
    min_dimension = max(min(dimensions), 0.001)
    max_dimension = max(max(dimensions), 0.001)
    bounding_box_volume_cm3 = max(geometry.bounding_box_volume_mm3 / 1000, 0.001)
    real_volume_cm3 = max(geometry.real_volume_cm3, 0.001)

    thinness_ratio = min_dimension / max_dimension
    slenderness_ratio = max_dimension / min_dimension
    feature_density_by_volume = geometry.face_count / real_volume_cm3
    feature_density_by_bbox = geometry.face_count / bounding_box_volume_cm3
    occupancy_extremity_score = _occupancy_extremity_score(geometry.occupancy_ratio)
    processing_complexity_signal = _processing_complexity_signal(
        processing_time_ms=processing_time_ms,
        real_volume_cm3=real_volume_cm3,
        face_count=geometry.face_count,
    )
    surface_complexity_signal = _surface_complexity_signal(
        face_count=geometry.face_count,
        shell_count=geometry.shell_count,
        processing_time_ms=processing_time_ms,
    )

    return DerivedMetrics(
        thinness_ratio=round(thinness_ratio, 6),
        slenderness_ratio=round(slenderness_ratio, 4),
        feature_density_by_volume=round(feature_density_by_volume, 6),
        feature_density_by_bbox=round(feature_density_by_bbox, 6),
        occupancy_extremity_score=round(occupancy_extremity_score, 4),
        processing_complexity_signal=round(processing_complexity_signal, 4),
        surface_complexity_signal=round(surface_complexity_signal, 4),
    )


def _occupancy_extremity_score(occupancy_ratio: float) -> float:
    if occupancy_ratio < 0.02:
        return 1.0
    if occupancy_ratio < 0.05:
        return 0.9
    if occupancy_ratio < 0.12:
        return 0.72
    if occupancy_ratio < 0.25:
        return 0.45
    if occupancy_ratio > 0.92:
        return 0.28
    return 0.0


def _processing_complexity_signal(
    processing_time_ms: int,
    real_volume_cm3: float,
    face_count: int,
) -> float:
    if processing_time_ms <= 0:
        return 0.0

    time_per_100_faces = processing_time_ms / max(face_count / 100, 1)
    time_per_cm3 = processing_time_ms / real_volume_cm3
    signal = 0.0

    if processing_time_ms > 20_000:
        signal += 0.45
    elif processing_time_ms > 10_000:
        signal += 0.34
    elif processing_time_ms > 5_000:
        signal += 0.22
    elif processing_time_ms > 2_000:
        signal += 0.10

    if time_per_100_faces > 900:
        signal += 0.25
    elif time_per_100_faces > 450:
        signal += 0.16
    elif time_per_100_faces > 180:
        signal += 0.08

    if real_volume_cm3 < 250 and time_per_cm3 > 18:
        signal += 0.35
    elif real_volume_cm3 < 250 and time_per_cm3 > 8:
        signal += 0.22

    return min(signal, 1.0)


def _surface_complexity_signal(
    face_count: int,
    shell_count: int,
    processing_time_ms: int,
) -> float:
    signal = 0.0

    if face_count > 2500:
        signal += 0.55
    elif face_count > 1500:
        signal += 0.45
    elif face_count > 600:
        signal += 0.30
    elif face_count > 150:
        signal += 0.16

    if shell_count > 6:
        signal += 0.22
    elif shell_count > 1:
        signal += 0.12

    if processing_time_ms > 10_000:
        signal += 0.18
    elif processing_time_ms > 5_000:
        signal += 0.10

    return min(signal, 1.0)
