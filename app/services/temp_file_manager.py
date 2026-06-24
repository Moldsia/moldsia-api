import logging
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.settings import settings


ALLOWED_CAD_EXTENSIONS = {".step", ".stp", ".iges", ".igs"}
ALLOWED_MIME_TYPES = {
    "application/octet-stream",
    "application/iges",
    "application/step",
    "application/x-iges",
    "application/x-step",
    "model/iges",
    "model/step",
    "text/plain",
}
logger = logging.getLogger(__name__)


class FileValidationError(ValueError):
    pass


class UploadTooLargeError(ValueError):
    def __init__(self, limit_mb: int, received_bytes: int) -> None:
        self.limit_mb = limit_mb
        self.received_bytes = received_bytes
        self.received_mb = received_bytes / (1024 * 1024)
        super().__init__(
            "Arquivo excede o limite atual de "
            f"{limit_mb} MB. Tamanho recebido: {self.received_mb:.2f} MB. "
            "Arquivos CAD industriais complexos podem exigir processamento elevado. "
            "Reduza/simplifique o arquivo CAD ou aumente MOLDSIA_MAX_UPLOAD_SIZE_MB em ambiente controlado."
        )


class TempCadFileManager:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or settings.upload_temp_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, file: UploadFile) -> Path:
        self._validate_upload_metadata(file)

        original_name = Path(file.filename or "upload.step").name
        extension = Path(original_name).suffix.lower()
        temp_file_path = self.base_dir / f"{uuid4().hex}{extension}"
        total_bytes = 0

        try:
            with temp_file_path.open("wb") as output:
                while chunk := await file.read(1024 * 1024):
                    total_bytes += len(chunk)

                    if total_bytes > settings.max_upload_size_bytes:
                        raise UploadTooLargeError(settings.max_upload_size_mb, total_bytes)

                    output.write(chunk)
        except Exception:
            temp_file_path.unlink(missing_ok=True)
            raise

        return temp_file_path

    def delete(self, file_path: Path) -> None:
        try:
            file_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(
                "temp_file_delete_failed",
                extra={"temp_file_path": str(file_path), "error": str(exc)},
            )

    def _validate_upload_metadata(self, file: UploadFile) -> None:
        file_name = file.filename or ""
        extension = Path(file_name).suffix.lower()

        if extension not in ALLOWED_CAD_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_CAD_EXTENSIONS))
            raise FileValidationError(
                f"Extensao de arquivo invalida. Envie apenas arquivos: {allowed}."
            )

        if file.content_type and file.content_type.lower() not in ALLOWED_MIME_TYPES:
            allowed = ", ".join(sorted(ALLOWED_MIME_TYPES))
            raise FileValidationError(
                "MIME type invalido para arquivo CAD. "
                f"Recebido: {file.content_type}. Permitidos: {allowed}."
            )
