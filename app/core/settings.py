import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "MOLDSIA Backend"
    app_version: str = "mvp-0.1"
    heuristics_version: str = "geometry-heuristics-v1"
    upload_temp_dir: Path = Field(default_factory=lambda: _backend_root() / "storage" / "tmp")
    upload_archive_dir: Path = Field(default_factory=lambda: _backend_root() / "storage" / "uploads")
    converted_cad_dir: Path = Field(default_factory=lambda: _backend_root() / "storage" / "converted")
    analysis_history_dir: Path = Field(
        default_factory=lambda: _backend_root() / "storage" / "analysis_history"
    )
    pricing_parameters_dir: Path = Field(
        default_factory=lambda: _backend_root() / "storage" / "pricing_parameters"
    )
    max_upload_size_mb: int = 250
    processing_timeout_seconds: int = 180
    quote_email_to: str = "moldsia@moldsia.com.br"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "https://moldsia.com.br",
            "https://www.moldsia.com.br",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def load_settings() -> Settings:
    return Settings(
        app_version=os.getenv("MOLDSIA_APP_VERSION", "mvp-0.1"),
        heuristics_version=os.getenv("MOLDSIA_HEURISTICS_VERSION", "geometry-heuristics-v1"),
        upload_temp_dir=Path(
            os.getenv("MOLDSIA_UPLOAD_TEMP_DIR", str(_backend_root() / "storage" / "tmp"))
        ),
        upload_archive_dir=Path(
            os.getenv("MOLDSIA_UPLOAD_ARCHIVE_DIR", str(_backend_root() / "storage" / "uploads"))
        ),
        converted_cad_dir=Path(
            os.getenv("MOLDSIA_CONVERTED_CAD_DIR", str(_backend_root() / "storage" / "converted"))
        ),
        analysis_history_dir=Path(
            os.getenv(
                "MOLDSIA_ANALYSIS_HISTORY_DIR",
                str(_backend_root() / "storage" / "analysis_history"),
            )
        ),
        pricing_parameters_dir=Path(
            os.getenv(
                "MOLDSIA_PRICING_PARAMETERS_DIR",
                str(_backend_root() / "storage" / "pricing_parameters"),
            )
        ),
        max_upload_size_mb=int(os.getenv("MOLDSIA_MAX_UPLOAD_SIZE_MB", "250")),
        processing_timeout_seconds=int(os.getenv("MOLDSIA_PROCESSING_TIMEOUT_SECONDS", "180")),
        quote_email_to=os.getenv("MOLDSIA_QUOTE_EMAIL_TO", "moldsia@moldsia.com.br"),
        smtp_host=os.getenv("MOLDSIA_SMTP_HOST") or None,
        smtp_port=int(os.getenv("MOLDSIA_SMTP_PORT", "587")),
        smtp_username=os.getenv("MOLDSIA_SMTP_USERNAME") or None,
        smtp_password=os.getenv("MOLDSIA_SMTP_PASSWORD") or None,
        smtp_from=os.getenv("MOLDSIA_SMTP_FROM") or os.getenv("MOLDSIA_SMTP_USERNAME") or None,
        smtp_use_tls=os.getenv("MOLDSIA_SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "sim"},
        smtp_use_ssl=os.getenv("MOLDSIA_SMTP_USE_SSL", "false").lower() in {"1", "true", "yes", "sim"},
        cors_allowed_origins=_parse_csv(
            os.getenv(
                "MOLDSIA_CORS_ALLOWED_ORIGINS",
                "https://moldsia.com.br,https://www.moldsia.com.br,http://127.0.0.1:5173,http://localhost:5173",
            )
        ),
    )


settings = load_settings()
