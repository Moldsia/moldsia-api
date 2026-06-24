import time
from dataclasses import dataclass
from pathlib import Path

import cadquery as cq
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid, BRepBuilderAPI_Sewing
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.IFSelect import IFSelect_RetDone
from OCP.IGESControl import IGESControl_Reader
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.ShapeFix import ShapeFix_Shape

from app.config import healing_settings
from app.schemas.analysis_schema import GeometryConfidence, GeometryHealingReport


@dataclass(frozen=True)
class GeometryHealingResult:
    report: GeometryHealingReport
    confidence: GeometryConfidence
    healed_step_path: Path | None = None


def attempt_geometry_healing(input_path: Path, output_step_path: Path) -> GeometryHealingResult:
    started_at = time.perf_counter()

    try:
        original_shape = _read_iges_shape(input_path)
        before = _shape_counts(original_shape)
        fixed_shape = _fix_shape(original_shape)
        sewed_shape, sewing = sew_surfaces(fixed_shape)
        healed_shape = build_solid_from_shells(sewed_shape)
        after = _shape_counts(healed_shape)
        report = measure_healing_impact(
            before=before,
            after=after,
            sewing=sewing,
            elapsed_ms=round((time.perf_counter() - started_at) * 1000),
        )

        if after["solids"] <= 0 or not _is_valid_shape(healed_shape):
            report = report.model_copy(
                update={
                    "success": False,
                    "error": "Healing executado, mas nao gerou solido fechado valido.",
                }
            )
            return GeometryHealingResult(
                report=report,
                confidence=calculate_geometry_confidence(report),
            )

        output_step_path.parent.mkdir(parents=True, exist_ok=True)
        _write_step(healed_shape, output_step_path)
        report = report.model_copy(update={"success": True})
        return GeometryHealingResult(
            report=report,
            confidence=calculate_geometry_confidence(report),
            healed_step_path=output_step_path,
        )
    except Exception as exc:
        report = GeometryHealingReport(
            attempted=True,
            success=False,
            healing_level="forced",
            gaps_closed_count=0,
            total_gap_distance_mm=0,
            max_gap_mm=0,
            modified_edges_ratio=0,
            modified_faces_ratio=0,
            shells_before_healing=0,
            shells_after_healing=0,
            solids_before_healing=0,
            solids_after_healing=0,
            healing_processing_time_ms=round((time.perf_counter() - started_at) * 1000),
            error=f"Falha ao executar healing geometrico: {exc}",
        )
        return GeometryHealingResult(
            report=report,
            confidence=calculate_geometry_confidence(report),
        )


def sew_surfaces(shape) -> tuple[object, BRepBuilderAPI_Sewing]:
    sewing = BRepBuilderAPI_Sewing(healing_settings.MAX_HEALING_GAP_MM)
    sewing.SetTolerance(healing_settings.MAX_HEALING_GAP_MM)
    sewing.SetMaxTolerance(healing_settings.MAX_HEALING_GAP_MM)
    sewing.SetFaceMode(True)
    sewing.SetFloatingEdgesMode(True)
    sewing.SetSameParameterMode(True)
    sewing.Add(shape)
    sewing.Perform()
    return sewing.SewedShape(), sewing


def build_solid_from_shells(shape):
    wrapped = cq.Shape.cast(shape)
    solids = wrapped.Solids()
    if solids:
        return shape

    shells = wrapped.Shells()
    if not shells:
        return shape

    make_solid = BRepBuilderAPI_MakeSolid()
    for shell in shells:
        make_solid.Add(shell.wrapped)
    make_solid.Build()
    if make_solid.IsDone():
        return make_solid.Solid()
    return shape


def measure_healing_impact(
    before: dict[str, int],
    after: dict[str, int],
    sewing: BRepBuilderAPI_Sewing,
    elapsed_ms: int,
) -> GeometryHealingReport:
    gaps_closed_count = max(int(sewing.NbContigousEdges()), 0)
    free_edges = max(int(sewing.NbFreeEdges()), 0)
    max_gap_mm = healing_settings.MAX_HEALING_GAP_MM if gaps_closed_count else 0.0
    total_gap_distance_mm = min(
        gaps_closed_count * healing_settings.MAX_HEALING_GAP_MM,
        healing_settings.MAX_TOTAL_HEALING_DISTANCE_MM,
    )
    modified_edges_ratio = min(
        (gaps_closed_count + free_edges) / max(before["edges"], 1),
        1.0,
    )
    modified_faces_ratio = min(
        abs(after["faces"] - before["faces"]) / max(before["faces"], 1),
        1.0,
    )
    healing_level = _healing_level(total_gap_distance_mm, modified_edges_ratio, modified_faces_ratio)

    if (
        total_gap_distance_mm > healing_settings.MAX_TOTAL_HEALING_DISTANCE_MM
        or modified_edges_ratio > healing_settings.MAX_MODIFIED_EDGE_RATIO
        or modified_faces_ratio > healing_settings.MAX_MODIFIED_FACE_RATIO
    ):
        healing_level = "forced"

    return GeometryHealingReport(
        attempted=True,
        success=False,
        healing_level=healing_level,
        gaps_closed_count=gaps_closed_count,
        total_gap_distance_mm=round(total_gap_distance_mm, 4),
        max_gap_mm=round(max_gap_mm, 4),
        modified_edges_ratio=round(modified_edges_ratio, 4),
        modified_faces_ratio=round(modified_faces_ratio, 4),
        shells_before_healing=before["shells"],
        shells_after_healing=after["shells"],
        solids_before_healing=before["solids"],
        solids_after_healing=after["solids"],
        healing_processing_time_ms=elapsed_ms,
    )


def calculate_geometry_confidence(report: GeometryHealingReport | None) -> GeometryConfidence:
    if report is None or not report.attempted:
        return GeometryConfidence(
            score=1.0,
            level="very_high",
            healing_impact="none",
            commercial_warning=False,
        )

    score = 0.94
    score -= min(report.total_gap_distance_mm / healing_settings.MAX_TOTAL_HEALING_DISTANCE_MM, 1.0) * 0.24
    score -= report.modified_edges_ratio * 0.22
    score -= report.modified_faces_ratio * 0.18
    score -= {
        "none": 0.0,
        "minimal": 0.04,
        "moderate": 0.14,
        "aggressive": 0.28,
        "forced": 0.42,
    }[report.healing_level]
    if report.solids_before_healing == 0 and report.solids_after_healing > 0:
        score -= 0.08
    if not report.success:
        score = min(score, 0.35)

    score = round(max(min(score, 1.0), 0.0), 4)
    return GeometryConfidence(
        score=score,
        level=_confidence_level(score),
        healing_impact=report.healing_level,
        commercial_warning=score < 0.75,
    )


def _read_iges_shape(input_path: Path):
    reader = IGESControl_Reader()
    read_status = reader.ReadFile(str(input_path))
    if read_status != IFSelect_RetDone:
        raise ValueError("OpenCascade nao conseguiu ler IGES para healing.")
    if reader.TransferRoots() == 0:
        raise ValueError("IGES nao possui geometrias transferiveis para healing.")
    return reader.OneShape()


def _fix_shape(shape):
    fixer = ShapeFix_Shape(shape)
    fixer.SetPrecision(healing_settings.MAX_HEALING_GAP_MM)
    fixer.SetMaxTolerance(healing_settings.MAX_HEALING_GAP_MM)
    fixer.Perform()
    return fixer.Shape()


def _shape_counts(shape) -> dict[str, int]:
    wrapped = cq.Shape.cast(shape)
    return {
        "solids": len(wrapped.Solids()),
        "shells": len(wrapped.Shells()),
        "faces": len(wrapped.Faces()),
        "edges": len(wrapped.Edges()),
    }


def _is_valid_shape(shape) -> bool:
    return bool(BRepCheck_Analyzer(shape).IsValid())


def _write_step(shape, output_path: Path) -> None:
    writer = STEPControl_Writer()
    if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone:
        raise ValueError("Nao foi possivel transferir shape healed para STEP.")
    if writer.Write(str(output_path)) != IFSelect_RetDone:
        raise ValueError("Nao foi possivel gravar STEP healed.")


def _healing_level(total_gap_distance_mm: float, edge_ratio: float, face_ratio: float) -> str:
    if total_gap_distance_mm == 0 and edge_ratio == 0 and face_ratio == 0:
        return "none"
    if total_gap_distance_mm <= 5 and edge_ratio <= 0.08 and face_ratio <= 0.04:
        return "minimal"
    if total_gap_distance_mm <= 20 and edge_ratio <= 0.20 and face_ratio <= 0.12:
        return "moderate"
    if total_gap_distance_mm <= healing_settings.MAX_TOTAL_HEALING_DISTANCE_MM:
        return "aggressive"
    return "forced"


def _confidence_level(score: float) -> str:
    if score >= 0.95:
        return "very_high"
    if score >= 0.80:
        return "high"
    if score >= 0.60:
        return "medium"
    if score >= 0.40:
        return "low"
    return "very_low"
