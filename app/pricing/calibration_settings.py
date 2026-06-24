from typing import Any

from app.services.mold_calibration_service import load_mold_calibration


def load_calibration_settings() -> dict[str, Any]:
    return load_mold_calibration()


def calibration_section(calibration: dict[str, Any], section: str, default: Any | None = None) -> Any:
    if default is None:
        default = {}
    return calibration.get(section, default)
