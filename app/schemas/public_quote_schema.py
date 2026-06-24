from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.mold_quote_schema import MoldTechnicalInput


class PublicQuoteContact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    company: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=180)
    whatsapp: str = Field(min_length=8, max_length=40)
    city_state: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip()
        if "@" not in normalized or "." not in normalized.rsplit("@", 1)[-1]:
            raise ValueError("invalid_email")
        return normalized

    @field_validator("whatsapp")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        normalized = value.strip()
        digits = "".join(character for character in normalized if character.isdigit())
        if len(digits) < 8:
            raise ValueError("invalid_phone")
        return normalized


class PublicQuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: dict[str, Any]
    technical_input: MoldTechnicalInput
    contact: PublicQuoteContact
    estimated_annual_volume: str


class PublicQuoteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote_id: str
    status: Literal["awaiting_technical_review"]
    investment_range_brl: dict[str, float]
    estimated_lead_time_days: dict[str, int]
    cavities_considered: int
    injection_system_considered: str
    estimated_mold_type: str
    confidence_level: Literal["alta", "media", "baixa", "revisao_obrigatoria"]
    email_sent: bool = False
    email_status: str | None = None
    pdf_filename: str | None = None
    message: str
