from fastapi import APIRouter

from app.schemas.public_quote_schema import PublicQuoteRequest, PublicQuoteResponse
from app.services.public_quote_service import create_public_quote


router = APIRouter(prefix="/public-quotes", tags=["public-quotes"])


@router.post("/estimate", response_model=PublicQuoteResponse)
def estimate_public_quote(payload: PublicQuoteRequest) -> PublicQuoteResponse:
    return create_public_quote(payload)
