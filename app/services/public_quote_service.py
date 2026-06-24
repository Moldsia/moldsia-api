import json
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.pricing.mold_pricing_engine import calculate_mold_pricing_estimate
from app.schemas.public_quote_schema import PublicQuoteRequest, PublicQuoteResponse


PUBLIC_QUOTE_STORAGE = Path(__file__).resolve().parents[2] / "storage" / "public_quotes"


def create_public_quote(payload: PublicQuoteRequest) -> PublicQuoteResponse:
    estimate = calculate_mold_pricing_estimate(payload.analysis, payload.technical_input)
    quote_id = str(uuid4())
    commercial = estimate.commercial
    industrial_cost = float(commercial.get("cpv_total_brl") or 0)
    floor = industrial_cost * 1.10
    ceiling = industrial_cost * 1.20
    scale = str(estimate.steel_package.get("mold_scale", "medium_mold"))
    base_days = {"small_mold": 45, "medium_mold": 65, "large_mold": 90}.get(scale, 65)
    movement_days = min(payload.technical_input.number_of_movements * 3, 24)
    hot_runner_days = 8 if payload.technical_input.injection_type == "hot_runner" else 0
    lead_min = base_days + movement_days + hot_runner_days
    lead_max = int(round(lead_min * 1.25))
    construction = payload.technical_input.mold_construction_type or "monobloco"
    estimated_mold_type = {
        "monobloco": "Molde monobloco",
        "insertado_posticado": "Molde insertado / posticado",
        "hibrido": "Molde hibrido",
    }.get(construction, "Molde parametrico")
    internal_confidence = str(estimate.confidence.get("overall_level", "medium"))
    confidence_level = {
        "high": "alta",
        "medium": "media",
        "low": "baixa",
        "mandatory_review": "revisao_obrigatoria",
    }.get(internal_confidence, "media")

    record = {
        "quote_id": quote_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contact": payload.contact.model_dump(mode="json"),
        "estimated_annual_volume": payload.estimated_annual_volume,
        "analysis": payload.analysis,
        "technical_input": payload.technical_input.model_dump(mode="json"),
        "internal_estimate": estimate.model_dump(mode="json"),
        "status": "awaiting_technical_review",
    }
    folder = PUBLIC_QUOTE_STORAGE / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{quote_id}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    return PublicQuoteResponse(
        quote_id=quote_id,
        status="awaiting_technical_review",
        investment_range_brl={"minimum": round(min(floor, ceiling), 2), "maximum": round(max(floor, ceiling), 2)},
        estimated_lead_time_days={"minimum": lead_min, "maximum": lead_max},
        cavities_considered=payload.technical_input.cavity_count,
        injection_system_considered=payload.technical_input.injection_type,
        estimated_mold_type=estimated_mold_type,
        confidence_level=confidence_level,
        message="Estimativa preliminar gerada. A proposta final depende de revisao tecnica.",
    )
