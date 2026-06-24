import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from OCP.IFSelect import IFSelect_RetDone
from OCP.IGESControl import IGESControl_Reader
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

from app.core.settings import settings
from app.schemas.analysis_schema import IgesDiagnostics
from app.utils.file_naming import build_converted_filename


class CadConversionError(RuntimeError):
    pass


@dataclass(frozen=True)
class CadConversionResult:
    success: bool
    converted_file_path: str | None = None
    error: str | None = None


def can_attempt_iges_conversion(iges_diagnostics: IgesDiagnostics | None) -> bool:
    if iges_diagnostics is None:
        return True

    return iges_diagnostics.has_brep_solid or iges_diagnostics.diagnosis == "unknown"


def convert_iges_to_step(input_path: Path, output_path: Path) -> CadConversionResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    reader = IGESControl_Reader()
    read_status = reader.ReadFile(str(input_path))
    if read_status != IFSelect_RetDone:
        raise CadConversionError("OpenCascade nao conseguiu ler o arquivo IGES para conversao STEP.")

    transferred_roots = reader.TransferRoots()
    if transferred_roots == 0:
        raise CadConversionError("Arquivo IGES nao possui geometrias transferiveis para conversao STEP.")

    shape = reader.OneShape()
    writer = STEPControl_Writer()
    transfer_status = writer.Transfer(shape, STEPControl_AsIs)
    if transfer_status != IFSelect_RetDone:
        raise CadConversionError("OpenCascade nao conseguiu transferir a geometria IGES para STEP.")

    write_status = writer.Write(str(output_path))
    if write_status != IFSelect_RetDone:
        raise CadConversionError("OpenCascade nao conseguiu gravar o arquivo STEP convertido.")

    return CadConversionResult(
        success=True,
        converted_file_path=_relative_to_backend(output_path),
    )


def build_converted_step_path(
    request_id: str,
    original_filename: str,
    timestamp: datetime | None = None,
) -> Path:
    created_at = timestamp or datetime.now()
    date_dir = created_at.strftime("%Y-%m-%d")
    file_name = build_converted_filename(original_filename, created_at)
    return settings.converted_cad_dir / date_dir / file_name


def _sanitize_filename(file_name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", file_name.strip())
    sanitized = sanitized.strip("._-")
    return sanitized[:120] or "uploaded_part"


def _relative_to_backend(path: Path) -> str:
    backend_root = Path(__file__).resolve().parents[2]
    return path.resolve().relative_to(backend_root).as_posix()
