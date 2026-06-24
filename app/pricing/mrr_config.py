from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


MachiningOperation = Literal[
    "PLATE_ROUGHING",
    "PLATE_FINISHING",
    "CAVITY_ROUGHING",
    "CAVITY_SEMI_FINISHING",
    "CAVITY_FINISHING",
    "CORE_ROUGHING",
    "CORE_SEMI_FINISHING",
    "CORE_FINISHING",
    "ELECTRODE_MACHINING",
    "DRILLING",
    "DEEP_DRILLING",
    "EDM",
    "BENCHWORK",
    "POLISHING",
]

SteelMaterial = Literal["P20", "H13", "H13_HARDENED", "420", "420_HARDENED", "1045", "4140", "ALUMINUM", "OTHER"]

MRR_CONFIG_VERSION = "mrr-default-v1"


class MrrConfigItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: MachiningOperation
    steel_material: SteelMaterial
    effective_mrr_cm3_hour: float | None = Field(default=None, gt=0)
    area_rate_cm2_hour: float | None = Field(default=None, gt=0)
    fixed_setup_hours: float = Field(default=0, ge=0)
    complexity_factor: float = Field(default=1.0, gt=0)
    conservative_factor: float = Field(default=1.3, gt=0)
    machine_hour_rate: float | None = Field(default=None, gt=0)
    notes: str | None = None
    version: str = MRR_CONFIG_VERSION


class MachiningCalibrationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    mold_id: str | None = None
    part_name: str | None = None
    operation: MachiningOperation
    steel_material: SteelMaterial
    estimated_removed_volume_cm3: float | None = None
    estimated_finishing_area_cm2: float | None = None
    estimated_hours: float
    real_hours: float | None = None
    machine: str | None = None
    operator_notes: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


DEFAULT_MRR_CONFIG: list[MrrConfigItem] = [
    MrrConfigItem(operation="PLATE_ROUGHING", steel_material="P20", effective_mrr_cm3_hour=20000, fixed_setup_hours=1.5, complexity_factor=1.0, conservative_factor=1.2, machine_hour_rate=180, notes="Initial estimate. Calibrate with real mold history."),
    MrrConfigItem(operation="PLATE_ROUGHING", steel_material="1045", effective_mrr_cm3_hour=24000, fixed_setup_hours=1.2, complexity_factor=1.0, conservative_factor=1.15, machine_hour_rate=170, notes="Initial base plate roughing value."),
    MrrConfigItem(operation="PLATE_FINISHING", steel_material="P20", effective_mrr_cm3_hour=8500, fixed_setup_hours=1.0, complexity_factor=1.05, conservative_factor=1.2, machine_hour_rate=180),
    MrrConfigItem(operation="PLATE_FINISHING", steel_material="1045", effective_mrr_cm3_hour=10000, fixed_setup_hours=0.8, complexity_factor=1.0, conservative_factor=1.15, machine_hour_rate=170),
    MrrConfigItem(operation="CAVITY_ROUGHING", steel_material="P20", effective_mrr_cm3_hour=8000, fixed_setup_hours=2.5, complexity_factor=1.3, conservative_factor=1.25, machine_hour_rate=220, notes="Initial cavity roughing value. Adjust after real hour comparison."),
    MrrConfigItem(operation="CAVITY_ROUGHING", steel_material="H13", effective_mrr_cm3_hour=4200, fixed_setup_hours=2.8, complexity_factor=1.35, conservative_factor=1.3, machine_hour_rate=230),
    MrrConfigItem(operation="CAVITY_SEMI_FINISHING", steel_material="P20", effective_mrr_cm3_hour=3200, fixed_setup_hours=2.0, complexity_factor=1.35, conservative_factor=1.25, machine_hour_rate=220),
    MrrConfigItem(operation="CAVITY_SEMI_FINISHING", steel_material="H13", effective_mrr_cm3_hour=1800, fixed_setup_hours=2.2, complexity_factor=1.4, conservative_factor=1.35, machine_hour_rate=230),
    MrrConfigItem(operation="CAVITY_FINISHING", steel_material="P20", area_rate_cm2_hour=120, fixed_setup_hours=2.0, complexity_factor=1.4, conservative_factor=1.3, machine_hour_rate=220, notes="Finishing should be estimated by area when available."),
    MrrConfigItem(operation="CAVITY_FINISHING", steel_material="H13", area_rate_cm2_hour=80, fixed_setup_hours=2.4, complexity_factor=1.45, conservative_factor=1.35, machine_hour_rate=230),
    MrrConfigItem(operation="CORE_ROUGHING", steel_material="P20", effective_mrr_cm3_hour=6500, fixed_setup_hours=2.0, complexity_factor=1.25, conservative_factor=1.25, machine_hour_rate=220),
    MrrConfigItem(operation="CORE_ROUGHING", steel_material="H13", effective_mrr_cm3_hour=3600, fixed_setup_hours=2.4, complexity_factor=1.35, conservative_factor=1.3, machine_hour_rate=230),
    MrrConfigItem(operation="CORE_SEMI_FINISHING", steel_material="P20", effective_mrr_cm3_hour=2800, fixed_setup_hours=1.8, complexity_factor=1.35, conservative_factor=1.25, machine_hour_rate=220),
    MrrConfigItem(operation="CORE_SEMI_FINISHING", steel_material="H13", effective_mrr_cm3_hour=1600, fixed_setup_hours=2.0, complexity_factor=1.4, conservative_factor=1.35, machine_hour_rate=230),
    MrrConfigItem(operation="CORE_FINISHING", steel_material="P20", area_rate_cm2_hour=95, fixed_setup_hours=1.5, complexity_factor=1.45, conservative_factor=1.3, machine_hour_rate=220),
    MrrConfigItem(operation="CORE_FINISHING", steel_material="H13", area_rate_cm2_hour=65, fixed_setup_hours=1.8, complexity_factor=1.5, conservative_factor=1.35, machine_hour_rate=230),
    MrrConfigItem(operation="ELECTRODE_MACHINING", steel_material="P20", effective_mrr_cm3_hour=4500, fixed_setup_hours=1.0, complexity_factor=1.2, conservative_factor=1.2, machine_hour_rate=150),
    MrrConfigItem(operation="DRILLING", steel_material="P20", effective_mrr_cm3_hour=12000, fixed_setup_hours=0.8, complexity_factor=1.0, conservative_factor=1.15, machine_hour_rate=160),
    MrrConfigItem(operation="DEEP_DRILLING", steel_material="P20", effective_mrr_cm3_hour=3000, fixed_setup_hours=1.5, complexity_factor=1.25, conservative_factor=1.35, machine_hour_rate=190),
    MrrConfigItem(operation="POLISHING", steel_material="P20", area_rate_cm2_hour=55, fixed_setup_hours=1.0, complexity_factor=1.4, conservative_factor=1.35, machine_hour_rate=120),
]


def get_mrr_config(operation: MachiningOperation, steel_material: SteelMaterial) -> MrrConfigItem:
    for item in DEFAULT_MRR_CONFIG:
        if item.operation == operation and item.steel_material == steel_material:
            return item
    return MrrConfigItem(
        operation=operation,
        steel_material=steel_material,
        fixed_setup_hours=0,
        complexity_factor=1.0,
        conservative_factor=1.3,
        notes="Configuration not found. Use conservative fallback or require technical review.",
    )


def estimate_machining_time_by_volume(
    *,
    removed_volume_cm3: float,
    operation: MachiningOperation,
    steel_material: SteelMaterial,
) -> dict[str, Any]:
    config = get_mrr_config(operation, steel_material)
    if not config.effective_mrr_cm3_hour:
        return {
            "estimated_hours": None,
            "requires_manual_review": True,
            "reason": "MRR not configured for this operation/material.",
            "config_used": config.model_dump(),
        }
    cutting_hours = max(removed_volume_cm3, 0) / config.effective_mrr_cm3_hour
    estimated_hours = (cutting_hours + config.fixed_setup_hours) * config.complexity_factor * config.conservative_factor
    return {
        "estimated_hours": round(estimated_hours, 4),
        "cutting_hours": round(cutting_hours, 4),
        "requires_manual_review": False,
        "config_used": config.model_dump(),
    }


def estimate_machining_time_by_area(
    *,
    finishing_area_cm2: float,
    operation: MachiningOperation,
    steel_material: SteelMaterial,
) -> dict[str, Any]:
    config = get_mrr_config(operation, steel_material)
    if not config.area_rate_cm2_hour:
        return {
            "estimated_hours": None,
            "requires_manual_review": True,
            "reason": "Area finishing rate not configured for this operation/material.",
            "config_used": config.model_dump(),
        }
    finishing_hours = max(finishing_area_cm2, 0) / config.area_rate_cm2_hour
    estimated_hours = (finishing_hours + config.fixed_setup_hours) * config.complexity_factor * config.conservative_factor
    return {
        "estimated_hours": round(estimated_hours, 4),
        "finishing_hours": round(finishing_hours, 4),
        "requires_manual_review": False,
        "config_used": config.model_dump(),
    }


def calculate_calibration_deviation(record: MachiningCalibrationRecord) -> dict[str, Any] | None:
    if record.real_hours is None or record.estimated_hours <= 0:
        return None
    deviation_percent = ((record.real_hours - record.estimated_hours) / record.estimated_hours) * 100
    return {
        "deviation_percent": round(deviation_percent, 4),
        "underestimated": record.real_hours > record.estimated_hours,
        "overestimated": record.real_hours < record.estimated_hours,
    }


def steel_material_from_internal(material: str) -> SteelMaterial:
    return {
        "steel_p20": "P20",
        "steel_p20_2711": "P20",
        "steel_p20_2738": "P20",
        "steel_h13": "H13",
        "stainless_420": "420",
        "steel_1045": "1045",
        "aluminum": "ALUMINUM",
    }.get(material, "OTHER")
