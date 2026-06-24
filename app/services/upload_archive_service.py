import hashlib
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.core.settings import settings
from app.utils.file_naming import build_upload_filename


@dataclass(frozen=True)
class UploadArchiveResult:
    stored: bool
    archive_path: str | None
    file_hash_sha256: str
    file_size_bytes: int


def generate_file_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()

    with file_path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def archive_uploaded_file(
    source_path: Path,
    original_file_name: str,
    request_id: str,
    file_hash_sha256: str,
    timestamp: datetime | None = None,
) -> UploadArchiveResult:
    created_at = timestamp or datetime.now()
    archive_path = build_upload_storage_path(
        original_file_name=original_file_name,
        request_id=request_id,
        timestamp=created_at,
    )
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    final_archive_path = _avoid_overwrite(archive_path)
    shutil.copy2(source_path, final_archive_path)

    return UploadArchiveResult(
        stored=True,
        archive_path=_relative_to_backend(final_archive_path),
        file_hash_sha256=file_hash_sha256,
        file_size_bytes=source_path.stat().st_size,
    )


def build_upload_storage_path(
    original_file_name: str,
    request_id: str,
    timestamp: datetime | None = None,
) -> Path:
    created_at = timestamp or datetime.now()
    date_dir = created_at.strftime("%Y-%m-%d")
    file_name = build_upload_filename(original_file_name, created_at)

    return settings.upload_archive_dir / date_dir / "original_step_files" / file_name


def _sanitize_filename(file_name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", file_name.strip())
    sanitized = sanitized.strip("._-")
    return sanitized[:120] or "uploaded_part"


def _avoid_overwrite(path: Path) -> Path:
    if not path.exists():
        return path

    for index in range(1, 1000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate

    raise FileExistsError(f"Nao foi possivel gerar nome unico para {path}")


def _relative_to_backend(path: Path) -> str:
    backend_root = Path(__file__).resolve().parents[2]
    return path.resolve().relative_to(backend_root).as_posix()
