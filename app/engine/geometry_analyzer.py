import logging
from pathlib import Path

import cadquery as cq
from OCP.IFSelect import IFSelect_RetDone
from OCP.IGESControl import IGESControl_Reader

from app.schemas.analysis_schema import GeometryMetrics

logger = logging.getLogger(__name__)


class CadReadError(RuntimeError):
    pass


class IgesCadReadError(CadReadError):
    pass


class GeometryAnalysisError(RuntimeError):
    pass


def analyze_cad_geometry(file_path: Path) -> GeometryMetrics:
    extension = file_path.suffix.lower()
    shape = load_cad_file(str(file_path), extension)
    solids = _extract_solids(shape)
    shells = _extract_shells(shape)
    faces = _extract_faces(shape)

    if not solids:
        logger.warning(
            "cad_geometry_without_valid_solid",
            extra={
                "cad_format": extension,
                "solid_count": 0,
                "shell_count": len(shells),
                "face_count": len(faces),
                "volume_available": False,
            },
        )
        raise GeometryAnalysisError(_build_no_solid_message(extension, shells, faces))

    compound = cq.Compound.makeCompound(solids)
    bounding_box = compound.BoundingBox()
    real_volume_mm3 = float(compound.Volume())
    bounding_box_volume_mm3 = float(bounding_box.xlen * bounding_box.ylen * bounding_box.zlen)

    if real_volume_mm3 <= 0:
        logger.warning(
            "cad_geometry_without_positive_volume",
            extra={
                "cad_format": extension,
                "solid_count": len(solids),
                "shell_count": len(shells),
                "face_count": len(faces),
                "real_volume_mm3": real_volume_mm3,
                "volume_available": False,
            },
        )
        raise GeometryAnalysisError(_build_no_solid_message(extension, shells, faces))

    occupancy_ratio = (
        real_volume_mm3 / bounding_box_volume_mm3
        if bounding_box_volume_mm3 > 0
        else 0.0
    )

    logger.info(
        "cad_geometry_loaded",
        extra={
            "cad_format": extension,
            "solid_count": len(solids),
            "shell_count": len(shells),
            "face_count": len(faces),
            "real_volume_mm3": real_volume_mm3,
            "occupancy_ratio": round(occupancy_ratio, 6),
        },
    )

    return GeometryMetrics(
        xlen_mm=round(float(bounding_box.xlen), 4),
        ylen_mm=round(float(bounding_box.ylen), 4),
        zlen_mm=round(float(bounding_box.zlen), 4),
        bounding_box_volume_mm3=round(bounding_box_volume_mm3, 4),
        real_volume_mm3=round(real_volume_mm3, 4),
        real_volume_cm3=round(real_volume_mm3 / 1000, 4),
        occupancy_ratio=round(occupancy_ratio, 6),
        solid_count=len(solids),
        shell_count=len(shells),
        face_count=len(faces),
        is_assembly=len(solids) > 1,
    )


def load_cad_file(file_path: str, extension: str) -> cq.Shape | cq.Workplane:
    normalized_extension = extension.lower()
    path = Path(file_path)

    try:
        if normalized_extension in {".step", ".stp"}:
            logger.info(
                "cad_file_loader_selected",
                extra={"cad_format": normalized_extension, "cad_importer": "cadquery.importStep"},
            )
            return cq.importers.importStep(str(path))

        if normalized_extension in {".iges", ".igs"}:
            logger.info(
                "cad_file_loader_selected",
                extra={"cad_format": normalized_extension, "cad_importer": "IGES"},
            )
            return _load_iges_file(path)
    except IgesCadReadError:
        raise
    except Exception as exc:
        if normalized_extension in {".iges", ".igs"}:
            logger.exception(
                "cad_iges_read_failed",
                extra={"cad_format": normalized_extension, "cad_importer": "OCP.IGESControl_Reader"},
            )
            raise IgesCadReadError(
                "Falha ao ler arquivo IGES. O arquivo pode estar corrompido, conter superfícies "
                "sem sólido fechado ou o importador IGES não está disponível no ambiente atual."
            ) from exc

        logger.exception(
            "cad_read_failed",
            extra={"cad_format": normalized_extension, "cad_importer": "cadquery.importStep"},
        )
        raise CadReadError(str(exc)) from exc

    raise CadReadError(f"Formato CAD nao suportado: {normalized_extension}")


def _load_iges_file(file_path: Path) -> cq.Shape | cq.Workplane:
    cadquery_iges_importer = (
        getattr(cq.importers, "importIges", None)
        or getattr(cq.importers, "importIGES", None)
        or getattr(cq.importers, "importIgesFile", None)
    )

    if cadquery_iges_importer is not None:
        logger.info(
            "cad_iges_importer_selected",
            extra={"cad_format": file_path.suffix.lower(), "cad_importer": cadquery_iges_importer.__name__},
        )
        return cadquery_iges_importer(str(file_path))

    logger.info(
        "cad_iges_importer_selected",
        extra={"cad_format": file_path.suffix.lower(), "cad_importer": "OCP.IGESControl_Reader"},
    )
    return _load_iges_with_ocp(file_path)


def _load_iges_with_ocp(file_path: Path) -> cq.Shape:
    reader = IGESControl_Reader()
    read_status = reader.ReadFile(str(file_path))

    if read_status != IFSelect_RetDone:
        raise IgesCadReadError(
            "Falha ao ler arquivo IGES. O arquivo pode estar corrompido, conter superfícies "
            "sem sólido fechado ou o importador IGES não está disponível no ambiente atual."
        )

    transferred_roots = reader.TransferRoots()
    if transferred_roots == 0:
        raise IgesCadReadError(
            "Falha ao ler arquivo IGES. O arquivo pode estar corrompido, conter superfícies "
            "sem sólido fechado ou o importador IGES não está disponível no ambiente atual."
        )

    shape = cq.Shape.cast(reader.OneShape())
    logger.info(
        "cad_iges_read_succeeded",
        extra={"cad_format": ".iges", "cad_importer": "OCP.IGESControl_Reader"},
    )
    return shape


def _extract_solids(imported_shape: cq.Shape | cq.Workplane) -> list[cq.Solid]:
    if isinstance(imported_shape, cq.Workplane):
        solids = imported_shape.solids().vals()
        if solids:
            return [solid for solid in solids if solid.Volume() > 0]

        imported_shape = imported_shape.val()

    solids = imported_shape.Solids()
    return [solid for solid in solids if solid.Volume() > 0]


def _extract_shells(imported_shape: cq.Shape | cq.Workplane) -> list[cq.Shell]:
    if isinstance(imported_shape, cq.Workplane):
        shape = imported_shape.val()
    else:
        shape = imported_shape

    return list(shape.Shells())


def _extract_faces(imported_shape: cq.Shape | cq.Workplane) -> list[cq.Face]:
    if isinstance(imported_shape, cq.Workplane):
        shape = imported_shape.val()
    else:
        shape = imported_shape

    return list(shape.Faces())


def _build_no_solid_message(
    extension: str,
    shells: list[cq.Shell],
    faces: list[cq.Face],
) -> str:
    if extension in {".iges", ".igs"}:
        if shells or faces:
            return (
                "Arquivo IGES contém superfícies, mas não sólido volumétrico. "
                "Volume real não pode ser calculado com segurança."
            )

        return "Arquivo IGES lido, mas não contém sólido fechado válido para cálculo de volume."

    return "Geometria sem solido valido para calculo de volume."
