import json
from typing import Any

from app.core.settings import settings


def mold_calibration_path():
    return settings.pricing_parameters_dir / "mold_calibration" / "current_mold_calibration.json"


def load_mold_calibration() -> dict[str, Any]:
    path = mold_calibration_path()
    if not path.exists():
        raise ValueError(f"Mold calibration file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))
