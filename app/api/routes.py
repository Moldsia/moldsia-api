import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.core.settings import settings
from app.engine.complexity_estimator import estimate_complexity
from app.engine.derived_metrics import calculate_derived_metrics
from app.engine.geometry_analyzer import (
    CadReadError,
    GeometryAnalysisError,
    IgesCadReadError,
    analyze_cad_geometry,
)
from app.engine.shape_classifier import classify_shape
from app.manufacturing.manufacturing_classifier import (
    classify_machining_profile,
    classify_piece_size,
)
from app.manufacturing.pricing_profile import get_pricing_profile
from app.manufacturing.risk_estimator import (
    build_review_recommendation,
    estimate_manufacturing_risk,
)
from app.pricing.pricing_engine import calculate_pricing_estimate
from app.schemas.analysis_schema import (
    AnalysisMetadata,
    AnalysisResponse,
    BenchmarkMetrics,
    CadConversionInfo,
    CalibrationInfo,
    GeometryConfidence,
    GeometryHealingReport,
    MaterialSupplyMode,
    ManufacturingRisk,
    RiskBreakdown,
    UploadArchive,
)
from app.services.analysis_history_writer import AnalysisHistoryWriter
from app.services.analysis_log_writer import save_analysis_log_txt
from app.services.cad_conversion_service import (
    CadConversionError,
    build_converted_step_path,
    can_attempt_iges_conversion,
    convert_iges_to_step,
)
from app.services.cad_precheck_service import build_analysis_precheck
from app.services.geometry_healing_service import attempt_geometry_healing, calculate_geometry_confidence
from app.services.pricing_parameter_service import load_current_pricing_parameters
from app.services.temp_file_manager import (
    FileValidationError,
    TempCadFileManager,
    UploadTooLargeError,
)
from app.services.upload_archive_service import (
    UploadArchiveResult,
    archive_uploaded_file,
    generate_file_sha256,
)


router = APIRouter(tags=["analysis"])
temp_file_manager = TempCadFileManager()
analysis_history_writer = AnalysisHistoryWriter()
logger = logging.getLogger(__name__)


@router.post(
    "/analisar-step",
    response_model=AnalysisResponse,
    status_code=status.HTTP_200_OK,
)
async def analyze_step(
    file: UploadFile | None = File(default=None),
    material_id: str | None = Form(default=None),
    quantity: int = Form(default=1),
    material_supply_mode: MaterialSupplyMode | None = Form(default=None),
    stock_allowance_mm: float | None = Form(default=None),
) -> AnalysisResponse:
    request_id = str(uuid4())
    started_at = time.perf_counter()
    temp_file_path: Path | None = None
    conversion: CadConversionInfo | None = None
    geometry_healing: GeometryHealingReport | None = None
    geometry_confidence = calculate_geometry_confidence(None)
    file_name = Path(file.filename).name if file and file.filename else None

    log_context = {"request_id": request_id, "file_name": file_name}
    logger.info("analysis_request_received", extra=log_context)

    if file is None or not file.filename:
        logger.warning("analysis_request_missing_file", extra=log_context)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivo ausente. Envie um arquivo STEP ou IGES no campo multipart 'file'.",
        )

    try:
        temp_file_path = await temp_file_manager.save_upload(file)
        analysis_precheck = build_analysis_precheck(temp_file_path, file.filename)
        file_hash_sha256 = generate_file_sha256(temp_file_path)
        upload_archive_result = try_archive_uploaded_file(
            source_path=temp_file_path,
            original_file_name=file.filename,
            request_id=request_id,
            file_hash_sha256=file_hash_sha256,
            log_context=log_context,
        )
        analysis_file_path = temp_file_path
        if is_iges_file(analysis_precheck.extension):
            conversion, converted_path = await asyncio.to_thread(
                try_convert_iges_upload,
                source_path=temp_file_path,
                original_file_name=file.filename,
                request_id=request_id,
                iges_diagnostics=analysis_precheck.iges_diagnostics,
                log_context=log_context,
            )
            if not conversion.success:
                geometry_healing, geometry_confidence, healed_path = await asyncio.to_thread(
                    try_heal_iges_upload,
                    source_path=temp_file_path,
                    original_file_name=file.filename,
                    request_id=request_id,
                    log_context=log_context,
                )
                if not geometry_healing.success or healed_path is None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail={
                            "message": (
                                "IGES parece conter superfícies abertas. Healing controlado não gerou sólido "
                                "fechado confiável. Para análise volumétrica, exporte como STEP sólido."
                            ),
                            "iges_diagnostics": (
                                analysis_precheck.iges_diagnostics.model_dump()
                                if analysis_precheck.iges_diagnostics
                                else None
                            ),
                            "conversion": conversion.model_dump(),
                            "geometry_healing": geometry_healing.model_dump(),
                            "geometry_confidence": geometry_confidence.model_dump(),
                        },
                    )
                analysis_file_path = healed_path
            else:
                analysis_file_path = converted_path

        geometry = await asyncio.wait_for(
            asyncio.to_thread(analyze_cad_geometry, analysis_file_path),
            timeout=settings.processing_timeout_seconds,
        )
        geometry_processing_time_ms = round((time.perf_counter() - started_at) * 1000)
        derived_metrics = calculate_derived_metrics(
            geometry,
            processing_time_ms=geometry_processing_time_ms,
        )
        shape_profile = classify_shape(geometry, derived_metrics)
        complexity = estimate_complexity(geometry, derived_metrics, shape_profile)
        piece_size = classify_piece_size(geometry.xlen_mm, geometry.ylen_mm)
        machining_profile = classify_machining_profile(
            geometry,
            shape_profile,
            complexity,
            derived_metrics,
        )
        manufacturing_profile = get_pricing_profile(piece_size, machining_profile)
        manufacturing_risk = estimate_manufacturing_risk(
            geometry,
            derived_metrics,
            complexity,
            shape_profile,
            manufacturing_profile,
        )
        manufacturing_risk = apply_geometry_confidence_to_risk(
            manufacturing_risk,
            geometry_confidence,
            geometry_healing,
        )
        review_recommendation = build_review_recommendation(complexity, manufacturing_risk)
        pricing_parameters_envelope = load_current_pricing_parameters()
        pricing_parameters = pricing_parameters_envelope.parameters
        pricing_estimate = calculate_pricing_estimate(
            geometry=geometry,
            derived_metrics=derived_metrics,
            manufacturing_profile=manufacturing_profile,
            manufacturing_risk=manufacturing_risk,
            parameters=pricing_parameters,
            material_id=material_id or pricing_parameters.materials[0].material_id,
            quantity=quantity,
            material_supply_mode=material_supply_mode or pricing_parameters.default_supply_mode,
            stock_allowance_mm=(
                stock_allowance_mm
                if stock_allowance_mm is not None
                else pricing_parameters.default_stock_allowance_mm
            ),
            complexity=complexity,
            shape_profile=shape_profile,
        )
        apply_geometry_confidence_to_pricing(pricing_estimate, geometry_confidence)
        processing_time_ms = round((time.perf_counter() - started_at) * 1000)

        response = AnalysisResponse(
            request_id=request_id,
            status="analyzed",
            processing_time_ms=processing_time_ms,
            file_name=Path(file.filename).name,
            geometry=geometry,
            derived_metrics=derived_metrics,
            complexity=complexity,
            shape_profile=shape_profile,
            manufacturing_profile=manufacturing_profile,
            manufacturing_risk=manufacturing_risk,
            review_recommendation=review_recommendation,
            analysis_precheck=analysis_precheck,
            iges_diagnostics=analysis_precheck.iges_diagnostics,
            conversion=conversion,
            geometry_healing=geometry_healing,
            geometry_confidence=geometry_confidence,
            pricing_estimate=pricing_estimate,
            pricing_parameters_used=pricing_parameters,
            calibration=CalibrationInfo(
                parameters_source=pricing_parameters_envelope.parameters_source,
                parameters_updated_at=pricing_parameters_envelope.parameters_updated_at,
                can_save_snapshot=True,
            ),
            benchmark=BenchmarkMetrics(),
            upload_archive=UploadArchive(
                stored=upload_archive_result.stored,
                archive_path=upload_archive_result.archive_path,
                file_hash_sha256=upload_archive_result.file_hash_sha256,
            ),
            metadata=AnalysisMetadata(
                engine="CadQuery",
                kernel="OpenCascade",
                version=settings.app_version,
                heuristics_version=settings.heuristics_version,
                file_hash_sha256=file_hash_sha256,
            ),
        )
        history_timestamp = datetime.now(timezone.utc).isoformat()
        json_history_path = analysis_history_writer.save(response, timestamp=history_timestamp)
        txt_log_path = save_analysis_log_txt(response, timestamp=history_timestamp)

        logger.info(
            "analysis_request_completed",
            extra={
                **log_context,
                "processing_time_ms": processing_time_ms,
                "xlen_mm": geometry.xlen_mm,
                "ylen_mm": geometry.ylen_mm,
                "zlen_mm": geometry.zlen_mm,
                "occupancy_ratio": geometry.occupancy_ratio,
                "solid_count": geometry.solid_count,
                "shell_count": geometry.shell_count,
                "face_count": geometry.face_count,
                "is_assembly": geometry.is_assembly,
                "precheck_file_size_mb": analysis_precheck.file_size_mb,
                "precheck_extension": analysis_precheck.extension,
                "precheck_estimated_entity_count": analysis_precheck.estimated_entity_count,
                "precheck_processing_risk": analysis_precheck.estimated_processing_risk,
                "precheck_analysis_mode": analysis_precheck.recommended_analysis_mode,
                "iges_diagnosis": (
                    analysis_precheck.iges_diagnostics.diagnosis
                    if analysis_precheck.iges_diagnostics
                    else None
                ),
                "iges_has_brep_solid": (
                    analysis_precheck.iges_diagnostics.has_brep_solid
                    if analysis_precheck.iges_diagnostics
                    else None
                ),
                "iges_face_entity_count": (
                    analysis_precheck.iges_diagnostics.face_entity_count
                    if analysis_precheck.iges_diagnostics
                    else None
                ),
                "iges_trimmed_surface_count": (
                    analysis_precheck.iges_diagnostics.trimmed_surface_count
                    if analysis_precheck.iges_diagnostics
                    else None
                ),
                "iges_bspline_surface_count": (
                    analysis_precheck.iges_diagnostics.bspline_surface_count
                    if analysis_precheck.iges_diagnostics
                    else None
                ),
                "iges_bspline_curve_count": (
                    analysis_precheck.iges_diagnostics.bspline_curve_count
                    if analysis_precheck.iges_diagnostics
                    else None
                ),
                "conversion_attempted": conversion.attempted if conversion else False,
                "conversion_success": conversion.success if conversion else None,
                "conversion_path": conversion.converted_file_path if conversion else None,
                "conversion_error": conversion.error if conversion else None,
                "geometry_healing_attempted": geometry_healing.attempted if geometry_healing else False,
                "geometry_healing_success": geometry_healing.success if geometry_healing else None,
                "geometry_healing_level": geometry_healing.healing_level if geometry_healing else None,
                "geometry_healing_gaps_closed_count": (
                    geometry_healing.gaps_closed_count if geometry_healing else None
                ),
                "geometry_confidence_score": geometry_confidence.score,
                "geometry_confidence_level": geometry_confidence.level,
                "geometry_confidence_commercial_warning": geometry_confidence.commercial_warning,
                "thinness_ratio": derived_metrics.thinness_ratio,
                "slenderness_ratio": derived_metrics.slenderness_ratio,
                "feature_density_by_volume": derived_metrics.feature_density_by_volume,
                "feature_density_by_bbox": derived_metrics.feature_density_by_bbox,
                "occupancy_extremity_score": derived_metrics.occupancy_extremity_score,
                "processing_complexity_signal": derived_metrics.processing_complexity_signal,
                "surface_complexity_signal": derived_metrics.surface_complexity_signal,
                "complexity_score": complexity.complexity_score,
                "complexity_level": complexity.complexity_level,
                "topology_complexity_score": complexity.topology_complexity_score,
                "complexity_occupancy_component": complexity.complexity_breakdown.occupancy_component,
                "complexity_topology_component": complexity.complexity_breakdown.topology_component,
                "complexity_surface_component": complexity.complexity_breakdown.surface_component,
                "complexity_shape_component": complexity.complexity_breakdown.shape_component,
                "complexity_processing_component": complexity.complexity_breakdown.processing_component,
                "complexity_threshold_diagnostics": complexity.threshold_diagnostics,
                "shape_primary": shape_profile.primary_shape,
                "shape_secondary": shape_profile.secondary_shape,
                "risk_score": manufacturing_risk.risk_score,
                "risk_level": manufacturing_risk.risk_level,
                "geometric_risk": manufacturing_risk.risk_breakdown.geometric_risk,
                "machining_risk": manufacturing_risk.risk_breakdown.machining_risk,
                "fixturing_risk": manufacturing_risk.risk_breakdown.fixturing_risk,
                "commercial_risk": manufacturing_risk.risk_breakdown.commercial_risk,
                "risk_flags": manufacturing_risk.risk_flags,
                "requires_engineering_review": review_recommendation.requires_engineering_review,
                "review_reasons": review_recommendation.reason,
                "review_confidence": review_recommendation.confidence,
                "pricing_parameters_source": pricing_parameters_envelope.parameters_source,
                "pricing_parameters_version": pricing_parameters.version,
                "pricing_price_floor_brl": pricing_estimate.commercial["price_floor_brl"],
                "pricing_price_ceiling_brl": pricing_estimate.commercial["price_ceiling_brl"],
                "pricing_material_id": pricing_estimate.material["material_id"],
                "pricing_quantity": pricing_estimate.commercial["quantity"],
                "pricing_material_supply_mode": pricing_estimate.material["material_supply_mode"],
                "machining_profile": manufacturing_profile.machining_profile,
                "estimated_machine_type": manufacturing_profile.estimated_machine_type,
                "file_hash_sha256": file_hash_sha256,
                "heuristics_version": settings.heuristics_version,
                "analysis_history_json": str(json_history_path),
                "analysis_history_txt": str(txt_log_path),
                "upload_archive_stored": upload_archive_result.stored,
                "upload_archive_path": upload_archive_result.archive_path,
                "upload_file_size_bytes": upload_archive_result.file_size_bytes,
            },
        )

        return response
    except FileValidationError as exc:
        logger.warning("analysis_request_invalid_file", extra={**log_context, "error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except UploadTooLargeError as exc:
        logger.warning(
            "analysis_request_upload_too_large",
            extra={
                **log_context,
                "error": str(exc),
                "limit_mb": exc.limit_mb,
                "received_mb": round(exc.received_mb, 2),
                "received_bytes": exc.received_bytes,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "message": str(exc),
                "limit_mb": exc.limit_mb,
                "received_mb": round(exc.received_mb, 2),
                "suggestion": "Arquivos CAD industriais complexos podem exigir processamento elevado. Reduza/simplifique o arquivo ou aumente o limite em ambiente controlado.",
            },
        ) from exc
    except asyncio.TimeoutError as exc:
        logger.exception(
            "analysis_request_timeout",
            extra={
                **log_context,
                "timeout_seconds": settings.processing_timeout_seconds,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(
                "Tempo limite de processamento CAD excedido. "
                f"Limite atual: {settings.processing_timeout_seconds} segundos."
            ),
        ) from exc
    except IgesCadReadError as exc:
        logger.exception("analysis_request_iges_read_failed", extra={**log_context, "error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except CadReadError as exc:
        logger.exception("analysis_request_cad_read_failed", extra={**log_context, "error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Falha de leitura CAD: {exc}",
        ) from exc
    except GeometryAnalysisError as exc:
        logger.exception("analysis_request_invalid_geometry", extra={**log_context, "error": str(exc)})
        if conversion is not None and conversion.success:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": (
                        "Arquivo IGES convertido para STEP, mas não contém sólido fechado válido "
                        "para cálculo de volume. Exporte como STEP sólido no CAD de origem."
                    ),
                    "conversion": conversion.model_dump(),
                    "geometry_healing": geometry_healing.model_dump() if geometry_healing else None,
                    "geometry_confidence": geometry_confidence.model_dump(),
                },
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    finally:
        if temp_file_path is not None:
            temp_file_manager.delete(temp_file_path)


def try_archive_uploaded_file(
    source_path: Path,
    original_file_name: str,
    request_id: str,
    file_hash_sha256: str,
    log_context: dict[str, str | None],
) -> UploadArchiveResult:
    try:
        result = archive_uploaded_file(
            source_path=source_path,
            original_file_name=original_file_name,
            request_id=request_id,
            file_hash_sha256=file_hash_sha256,
        )
        logger.info(
            "upload_file_archived",
            extra={
                **log_context,
                "file_hash_sha256": result.file_hash_sha256,
                "file_size_bytes": result.file_size_bytes,
                "archive_path": result.archive_path,
            },
        )
        return result
    except Exception as exc:
        file_size_bytes = source_path.stat().st_size if source_path.exists() else 0
        logger.warning(
            "upload_file_archive_failed",
            extra={
                **log_context,
                "file_hash_sha256": file_hash_sha256,
                "file_size_bytes": file_size_bytes,
                "error": str(exc),
            },
        )
        return UploadArchiveResult(
            stored=False,
            archive_path=None,
            file_hash_sha256=file_hash_sha256,
            file_size_bytes=file_size_bytes,
        )


def try_convert_iges_upload(
    source_path: Path,
    original_file_name: str,
    request_id: str,
    iges_diagnostics: object,
    log_context: dict[str, str | None],
) -> tuple[CadConversionInfo, Path]:
    diagnosis = iges_diagnostics.diagnosis if iges_diagnostics else None
    started_at = time.perf_counter()

    if not can_attempt_iges_conversion(iges_diagnostics):
        error = (
            "IGES contém superfícies abertas, mas não sólido fechado válido para análise volumétrica. "
            "Exporte como STEP sólido."
        )
        conversion = CadConversionInfo(
            attempted=True,
            source_format="IGES",
            target_format="STEP",
            success=False,
            error=error,
            diagnosis=diagnosis,
        )
        logger.warning(
            "cad_iges_conversion_skipped_surface_model",
            extra={
                **log_context,
                "conversion_attempted": True,
                "conversion_success": False,
                "conversion_error": error,
                "iges_diagnosis": diagnosis,
            },
        )
        return conversion, source_path

    output_path = build_converted_step_path(
        request_id=request_id,
        original_filename=original_file_name,
    )
    logger.info(
        "cad_iges_conversion_started",
        extra={
            **log_context,
            "iges_diagnosis": diagnosis,
            "converted_step_path": str(output_path),
        },
    )

    try:
        result = convert_iges_to_step(source_path, output_path)
        conversion_time_ms = round((time.perf_counter() - started_at) * 1000)
        conversion = CadConversionInfo(
            attempted=True,
            source_format="IGES",
            target_format="STEP",
            success=True,
            converted_file_path=result.converted_file_path,
            diagnosis=diagnosis,
        )
        logger.info(
            "cad_iges_conversion_completed",
            extra={
                **log_context,
                "conversion_attempted": True,
                "conversion_success": True,
                "conversion_time_ms": conversion_time_ms,
                "converted_step_path": result.converted_file_path,
                "iges_diagnosis": diagnosis,
            },
        )
        return conversion, output_path
    except CadConversionError as exc:
        error = str(exc)
    except Exception as exc:
        error = f"Falha inesperada ao converter IGES para STEP: {exc}"

    conversion_time_ms = round((time.perf_counter() - started_at) * 1000)
    conversion = CadConversionInfo(
        attempted=True,
        source_format="IGES",
        target_format="STEP",
        success=False,
        converted_file_path=None,
        error=error,
        diagnosis=diagnosis,
    )
    logger.warning(
        "cad_iges_conversion_failed",
        extra={
            **log_context,
            "conversion_attempted": True,
            "conversion_success": False,
            "conversion_time_ms": conversion_time_ms,
            "conversion_error": error,
            "iges_diagnosis": diagnosis,
        },
    )
    return conversion, source_path


def try_heal_iges_upload(
    source_path: Path,
    original_file_name: str,
    request_id: str,
    log_context: dict[str, str | None],
) -> tuple[GeometryHealingReport, GeometryConfidence, Path | None]:
    output_path = build_converted_step_path(
        request_id=f"{request_id}_healed",
        original_filename=original_file_name,
    )
    logger.info(
        "geometry_healing_started",
        extra={**log_context, "healed_step_path": str(output_path)},
    )
    result = attempt_geometry_healing(source_path, output_path)
    logger.info(
        "geometry_healing_completed",
        extra={
            **log_context,
            "geometry_healing_attempted": result.report.attempted,
            "geometry_healing_success": result.report.success,
            "geometry_healing_level": result.report.healing_level,
            "gaps_closed_count": result.report.gaps_closed_count,
            "total_gap_distance_mm": result.report.total_gap_distance_mm,
            "max_gap_mm": result.report.max_gap_mm,
            "modified_edges_ratio": result.report.modified_edges_ratio,
            "modified_faces_ratio": result.report.modified_faces_ratio,
            "solids_before_healing": result.report.solids_before_healing,
            "solids_after_healing": result.report.solids_after_healing,
            "geometry_confidence_score": result.confidence.score,
            "geometry_confidence_level": result.confidence.level,
            "healed_step_path": str(result.healed_step_path) if result.healed_step_path else None,
            "error": result.report.error,
        },
    )
    return result.report, result.confidence, result.healed_step_path


def apply_geometry_confidence_to_risk(
    manufacturing_risk: ManufacturingRisk,
    geometry_confidence: GeometryConfidence,
    healing_report: GeometryHealingReport | None,
) -> ManufacturingRisk:
    flags = list(manufacturing_risk.risk_flags)
    score_addition = 0.0

    if healing_report and healing_report.attempted:
        flags.extend(["geometry_healed", "surface_based_geometry"])
        if healing_report.success and healing_report.solids_before_healing == 0:
            flags.append("reconstructed_solid")
        if healing_report.healing_level in {"moderate", "aggressive", "forced"}:
            flags.append(f"{healing_report.healing_level}_geometry_reconstruction")
        score_addition += {
            "none": 0.0,
            "minimal": 0.04,
            "moderate": 0.10,
            "aggressive": 0.18,
            "forced": 0.25,
        }[healing_report.healing_level]

    if geometry_confidence.score < 0.75:
        flags.append("low_geometry_confidence")
        score_addition += 0.10

    risk_score = round(min(manufacturing_risk.risk_score + score_addition, 1.0), 4)
    breakdown = manufacturing_risk.risk_breakdown
    updated_breakdown = RiskBreakdown(
        geometric_risk=round(min(breakdown.geometric_risk + score_addition, 1.0), 4),
        machining_risk=breakdown.machining_risk,
        fixturing_risk=breakdown.fixturing_risk,
        commercial_risk=round(min(breakdown.commercial_risk + (score_addition * 0.8), 1.0), 4),
    )
    return ManufacturingRisk(
        risk_score=risk_score,
        risk_level=risk_level_from_score(risk_score),
        risk_breakdown=updated_breakdown,
        risk_flags=dedupe(flags),
    )


def apply_geometry_confidence_to_pricing(
    pricing_estimate,
    geometry_confidence: GeometryConfidence,
) -> None:
    pricing_estimate.confidence["geometry_confidence_score"] = geometry_confidence.score
    pricing_estimate.confidence["geometry_confidence_level"] = geometry_confidence.level
    pricing_estimate.confidence["geometry_commercial_warning"] = geometry_confidence.commercial_warning
    if geometry_confidence.score >= 0.75:
        return

    ceiling_addition = 1 + min((0.75 - geometry_confidence.score) * 0.8, 0.28)
    old_ceiling = float(pricing_estimate.commercial["price_ceiling_brl"])
    old_markup = float(pricing_estimate.commercial["markup_ceiling"])
    pricing_estimate.commercial["price_ceiling_brl"] = round(old_ceiling * ceiling_addition, 2)
    pricing_estimate.commercial["markup_ceiling"] = round(old_markup * ceiling_addition, 4)
    pricing_estimate.confidence["pricing_confidence"] = "low"
    pricing_estimate.confidence.setdefault("notes", []).append(
        "Faixa comercial ampliada por baixa confiança geométrica após healing/reconstrução."
    )


def risk_level_from_score(score: float) -> str:
    if score < 0.32:
        return "low"
    if score < 0.62:
        return "medium"
    return "high"


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def is_iges_file(extension: str) -> bool:
    return extension.lower().lstrip(".") in {"igs", "iges"}
