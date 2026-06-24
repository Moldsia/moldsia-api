import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.settings import settings
from app.schemas.analysis_schema import AnalysisResponse
from app.utils.file_naming import build_log_filename


class AnalysisHistoryWriter:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or settings.analysis_history_dir / "json"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, analysis: AnalysisResponse, timestamp: str | None = None) -> Path:
        created_at = datetime.now(timezone.utc)
        output_path = self.base_dir / build_log_filename(analysis.file_name, ".json", created_at)
        payload = {
            "timestamp": timestamp or created_at.isoformat(),
            **analysis.model_dump(),
        }

        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return output_path
