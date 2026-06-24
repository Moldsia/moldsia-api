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
    processing_timeout_seconds: int = 60
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
        processing_timeout_seconds=int(os.getenv("MOLDSIA_PROCESSING_TIMEOUT_SECONDS", "60")),
        cors_allowed_origins=_parse_csv(
            os.getenv(
                "MOLDSIA_CORS_ALLOWED_ORIGINS",
                "https://moldsia.com.br,https://www.moldsia.com.br,http://127.0.0.1:5173,http://localhost:5173",
            )
        ),
    )


settings = load_settings()
