import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import ValidationError

from app.schemas.analysis_schema import (
    PricingParameters,
    PricingParametersEnvelope,
    PricingSnapshotRequest,
    PricingSnapshotResponse,
)
from app.schemas.mold_quote_schema import MoldPricingRequest, MoldPricingResponse
from app.pricing.mold_pricing_engine import calculate_mold_pricing_estimate, recalculate_quote_from_inputs
from app.services.pricing_parameter_service import (
    get_default_pricing_parameters,
    load_current_pricing_parameters,
    save_analysis_pricing_snapshot,
    save_current_pricing_parameters,
)
from app.services.mold_pricing_snapshot_writer import save_mold_pricing_snapshot


router = APIRouter(prefix="/pricing", tags=["pricing"])
logger = logging.getLogger(__name__)


@router.get("/parameters", response_model=PricingParametersEnvelope)
def get_pricing_parameters() -> PricingParametersEnvelope:
    return load_current_pricing_parameters()


@router.get("/parameters/defaults", response_model=PricingParametersEnvelope)
def get_pricing_parameter_defaults() -> PricingParametersEnvelope:
    defaults = get_default_pricing_parameters()
    return PricingParametersEnvelope(
        parameters=defaults,
        parameters_source="default",
        parameters_updated_at=defaults.updated_at,
    )


@router.put("/parameters", response_model=PricingParametersEnvelope)
def put_pricing_parameters(parameters: PricingParameters) -> PricingParametersEnvelope:
    try:
        saved = save_current_pricing_parameters(parameters)
        logger.info(
            "pricing_parameters_saved",
            extra={
                "pricing_parameters_version": saved.parameters.version,
                "pricing_parameters_updated_at": saved.parameters.updated_at,
            },
        )
        return saved
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.errors(),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/parameters/save-analysis-snapshot",
    response_model=PricingSnapshotResponse,
    status_code=status.HTTP_201_CREATED,
)
def save_analysis_snapshot(snapshot: PricingSnapshotRequest) -> PricingSnapshotResponse:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **snapshot.model_dump(),
        "raw_response": snapshot.analysis,
    }
    path = save_analysis_pricing_snapshot(payload)
    logger.info(
        "pricing_analysis_snapshot_saved",
        extra={
            "request_id": snapshot.request_id,
            "file_name": snapshot.file_name,
            "snapshot_path": str(path),
        },
    )
    return PricingSnapshotResponse(stored=True, snapshot_path=str(path))


@router.post("/mold/estimate", response_model=MoldPricingResponse)
def estimate_mold_pricing(payload: MoldPricingRequest) -> MoldPricingResponse:
    return _estimate_mold_pricing_response(payload)


@router.post("/mold/recalculate", response_model=MoldPricingResponse)
def recalculate_mold_pricing(payload: MoldPricingRequest) -> MoldPricingResponse:
    return _estimate_mold_pricing_response(payload, is_recalculation=True)


@router.post("/moldia/estimate", response_model=MoldPricingResponse)
def estimate_moldia_pricing(payload: MoldPricingRequest) -> MoldPricingResponse:
    return _estimate_mold_pricing_response(payload)


def _estimate_mold_pricing_response(
    payload: MoldPricingRequest,
    *,
    is_recalculation: bool = False,
) -> MoldPricingResponse:
    try:
        calculate = recalculate_quote_from_inputs if is_recalculation else calculate_mold_pricing_estimate
        estimate = calculate(payload.analysis, payload.technical_input)
        snapshot_paths = save_mold_pricing_snapshot(
            analysis=payload.analysis,
            technical_input=payload.technical_input,
            estimate=estimate,
        )
        estimate.confidence["snapshot_paths"] = snapshot_paths
        logger.info(
            "mold_pricing_estimate_completed",
            extra={
                "file_name": payload.analysis.get("file_name"),
                "mold_architecture": payload.technical_input.mold_architecture,
                "cavity_count": payload.technical_input.cavity_count,
                "cpv_total_brl": estimate.commercial.get("cpv_total_brl"),
                "price_floor_brl": estimate.commercial.get("price_floor_brl"),
                "price_ceiling_brl": estimate.commercial.get("price_ceiling_brl"),
                "dominant_cost_driver": estimate.cost_dominance.get("dominant_cost_driver"),
                "confidence_level": estimate.confidence.get("overall_level"),
                **snapshot_paths,
            },
        )
        return MoldPricingResponse(status="estimated", mold_pricing_estimate=estimate)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

