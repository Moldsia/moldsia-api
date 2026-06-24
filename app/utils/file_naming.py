import re
from datetime import datetime
from pathlib import Path


def sanitize_filename(filename: str, max_length: int = 120) -> str:
    path = Path(filename)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", (path.stem or "arquivo").strip()).strip("._-")
    suffix = re.sub(r"[^A-Za-z0-9.]+", "", path.suffix.lower())
    safe = (stem[: max_length - len(suffix)] or "arquivo") + suffix
    return safe


def build_timestamp_prefix(timestamp: datetime | None = None) -> str:
    return (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")


def build_upload_filename(original_filename: str, timestamp: datetime | None = None) -> str:
    return f"{build_timestamp_prefix(timestamp)}_{sanitize_filename(original_filename)}"


def build_log_filename(original_filename: str, extension: str, timestamp: datetime | None = None) -> str:
    stem = Path(sanitize_filename(original_filename)).stem
    return f"{build_timestamp_prefix(timestamp)}_{stem}_analysis{extension}"


def build_technical_log_filename(original_filename: str, timestamp: datetime | None = None) -> str:
    stem = Path(sanitize_filename(original_filename)).stem
    return f"{build_timestamp_prefix(timestamp)}_{stem}_technical_log.txt"


def build_converted_filename(original_filename: str, timestamp: datetime | None = None) -> str:
    stem = Path(sanitize_filename(original_filename)).stem
    return f"{build_timestamp_prefix(timestamp)}_{stem}.step"
