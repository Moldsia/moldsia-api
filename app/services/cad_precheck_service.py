from pathlib import Path
import re

from app.schemas.analysis_schema import AnalysisPrecheck, IgesDiagnostics


def build_analysis_precheck(file_path: Path, original_file_name: str) -> AnalysisPrecheck:
    extension = Path(original_file_name).suffix.lower().lstrip(".")
    file_size_bytes = file_path.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)
    estimated_entity_count = estimate_entity_count(file_path)
    estimated_processing_risk = classify_processing_risk(file_size_mb, estimated_entity_count)
    iges_diagnostics = (
        build_iges_diagnostics(file_path)
        if extension in {"igs", "iges"}
        else None
    )

    return AnalysisPrecheck(
        file_size_mb=round(file_size_mb, 2),
        extension=extension,
        estimated_entity_count=estimated_entity_count,
        estimated_processing_risk=estimated_processing_risk,
        recommended_analysis_mode=recommended_analysis_mode(file_size_mb, estimated_entity_count),
        iges_diagnostics=iges_diagnostics,
    )


def estimate_entity_count(file_path: Path) -> int | None:
    try:
        sample_size = min(file_path.stat().st_size, 2 * 1024 * 1024)
        with file_path.open("rb") as handle:
            sample = handle.read(sample_size).decode("latin-1", errors="ignore").upper()
    except OSError:
        return None

    markers = [
        "ADVANCED_FACE",
        "CARTESIAN_POINT",
        "LINE",
        "CIRCLE",
        "B_SPLINE",
        "TRIMMED_CURVE",
        "MANIFOLD_SOLID_BREP",
    ]
    count = sum(sample.count(marker) for marker in markers)
    if count == 0:
        count = sample.count(";")
    return count or None


def classify_processing_risk(file_size_mb: float, estimated_entity_count: int | None) -> str:
    entities = estimated_entity_count or 0
    if file_size_mb >= 180 or entities >= 120_000:
        return "high"
    if file_size_mb >= 75 or entities >= 35_000:
        return "medium"
    return "low"


def recommended_analysis_mode(file_size_mb: float, estimated_entity_count: int | None) -> str:
    risk = classify_processing_risk(file_size_mb, estimated_entity_count)
    if risk == "high":
        return "heavy"
    return "standard"


def build_iges_diagnostics(file_path: Path) -> IgesDiagnostics:
    entity_counts = count_iges_entity_types(file_path)
    brep_solid_count = entity_counts.get(186, 0)
    shell_count = entity_counts.get(514, 0)
    face_count = entity_counts.get(510, 0)
    loop_count = entity_counts.get(508, 0)
    trimmed_surface_count = entity_counts.get(144, 0)
    bspline_surface_count = entity_counts.get(128, 0)
    bspline_curve_count = entity_counts.get(126, 0)

    if brep_solid_count > 0:
        diagnosis = "solid_brep"
    elif trimmed_surface_count > 0 or bspline_surface_count > 0 or face_count > 0 or shell_count > 0:
        diagnosis = "surface_model"
    elif bspline_curve_count > 0 or loop_count > 0:
        diagnosis = "wireframe_or_curves"
    else:
        diagnosis = "unknown"

    return IgesDiagnostics(
        has_brep_solid=brep_solid_count > 0,
        has_shells=shell_count > 0,
        face_entity_count=face_count,
        trimmed_surface_count=trimmed_surface_count,
        bspline_surface_count=bspline_surface_count,
        bspline_curve_count=bspline_curve_count,
        diagnosis=diagnosis,
    )


def count_iges_entity_types(file_path: Path) -> dict[int, int]:
    counts: dict[int, int] = {}
    directory_section_found = False

    try:
        with file_path.open("rb") as handle:
            for raw_line in handle:
                line = raw_line.decode("latin-1", errors="ignore")
                section = line[72:73].upper() if len(line) >= 73 else ""

                if section == "D":
                    directory_section_found = True
                    entity_type = _parse_iges_directory_entity_type(line)
                    if entity_type is not None:
                        counts[entity_type] = counts.get(entity_type, 0) + 1
    except OSError:
        return counts

    if counts or directory_section_found:
        return counts

    return _count_iges_entity_types_from_text(file_path)


def _parse_iges_directory_entity_type(line: str) -> int | None:
    raw_value = line[:8].strip()
    if not raw_value.isdigit():
        return None
    return int(raw_value)


def _count_iges_entity_types_from_text(file_path: Path) -> dict[int, int]:
    try:
        sample_size = min(file_path.stat().st_size, 8 * 1024 * 1024)
        with file_path.open("rb") as handle:
            sample = handle.read(sample_size).decode("latin-1", errors="ignore")
    except OSError:
        return {}

    counts: dict[int, int] = {}
    entity_patterns = {
        186: [r"\b186\s*,", "MANIFOLD SOLID B-REP", "MANIFOLD_SOLID_BREP"],
        514: [r"\b514\s*,", "SHELL"],
        510: [r"\b510\s*,", "FACE"],
        508: [r"\b508\s*,", "LOOP"],
        144: [r"\b144\s*,", "TRIMMED SURFACE", "TRIMMED_SURFACE"],
        128: [r"\b128\s*,", "RATIONAL B-SPLINE SURFACE", "B_SPLINE_SURFACE"],
        126: [r"\b126\s*,", "RATIONAL B-SPLINE CURVE", "B_SPLINE_CURVE"],
    }
    upper_sample = sample.upper()

    for entity_type, patterns in entity_patterns.items():
        count = 0
        for pattern in patterns:
            if pattern.startswith(r"\b"):
                count += len(re.findall(pattern, sample))
            else:
                count += upper_sample.count(pattern)
        if count:
            counts[entity_type] = count

    return counts
