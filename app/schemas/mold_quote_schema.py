from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


MoldArchitecture = Literal["2_plate", "3_plate", "stack_mold"]
CavityType = Literal["monoblock", "inserted"]
MoldConstructionType = Literal["monobloco", "insertado_posticado", "hibrido"]
MoldLifetime = Literal["PROTOTYPE_10K", "LOW_50K", "MEDIUM_250K", "HIGH_1M", "HEAVY_ABOVE_1M"]
PlasticMaterial = Literal[
    "PP_VIRGIN",
    "PP_COPOLYMER",
    "PP_TALC_20",
    "PP_TALC_40",
    "PP_GLASS_FIBER",
    "PEHD",
    "PELD",
    "ABS",
    "PS_HIPS",
    "POM",
    "PA",
    "PA_GLASS_FIBER",
    "PC",
    "PC_ABS",
    "PMMA",
    "PVC",
    "TPU_TPE",
    "OTHER",
]
MovementType = Literal[
    "NONE",
    "SIDE_SLIDER",
    "ANGLED_SLIDER",
    "UNSCREWING_CORE",
    "FORCED_EJECTION",
    "HYDRAULIC_MOVEMENT",
    "MECHANICAL_MOVEMENT",
    "OTHER",
]
InjectionType = Literal["cold_runner", "hot_runner"]
GateStrategy = Literal["direct_to_part", "to_runner", "unknown_schematic"]
ExtractionType = Literal[
    "automatic",
    "ejector_pins",
    "ejector_plate",
    "air",
    "forced_ejection",
    "rotary_core",
    "robot",
    "none",
]
SurfaceTreatment = Literal[
    "NOT_DEFINED",
    "ENGINEERING_RECOMMENDED",
    "NONE",
    "NITRIDING",
    "HARD_CHROME",
    "SPECIAL_COATING",
]
MainFinish = Literal[
    "MACHINED_TECHNICAL",
    "SIMPLE_POLISHED",
    "HIGH_GLOSS",
    "MIRROR_POLISH",
    "TEXTURED",
    "MIXED",
]
PartClass = Literal[
    "TECHNICAL",
    "APPEARANCE",
    "HIGH_PRECISION",
    "PACKAGING",
    "AUTOMOTIVE",
    "ELECTRONICS",
    "CONSTRUCTION",
    "MEDICAL_PHARMA",
    "OTHER",
]
DimensionalRequirement = Literal["NORMAL", "MEDIUM_PRECISION", "HIGH_PRECISION", "CRITICAL"]
VisualRequirement = Literal[
    "NO_VISUAL_REQUIREMENT",
    "SIMPLE_APPEARANCE",
    "CRITICAL_APPEARANCE",
    "HIGH_GLOSS",
    "SPECIFIED_TEXTURE",
]
SpecialMovementType = Literal[
    "SIMPLE_SIDE_SLIDER",
    "ANGLED_PIN_SLIDER",
    "HYDRAULIC_SLIDER",
    "SPECIAL_MECHANICAL_SLIDER",
    "COLLAPSIBLE_CORE",
    "NEGATIVE_JAW",
    "ROTARY_CORE",
    "FORCED_EJECTION",
    "LIFTER",
    "MOVABLE_CORE",
    "MOVABLE_INSERT",
    "RETRACTABLE_CORE",
    "CUSTOM",
    "UNKNOWN",
]
MovementPosition = Literal[
    "AUTO",
    "LEFT",
    "RIGHT",
    "TOP",
    "BOTTOM",
    "FRONT",
    "BACK",
    "MULTIPLE",
    "UNKNOWN",
]
MovementActuation = Literal[
    "AUTO",
    "MECHANICAL",
    "ANGLED_PIN",
    "HYDRAULIC",
    "PNEUMATIC",
    "CAM",
    "COLLAPSIBLE",
    "ROTARY",
    "FORCED",
    "MANUAL",
    "OTHER",
    "UNKNOWN",
]
MovementComplexity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"]


class SpecialMovementInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    movement_type: SpecialMovementType
    technical_definition: Literal["AUTO", "MANUAL"] = "AUTO"
    quantity: int = Field(default=1, ge=1, le=32)
    position: MovementPosition = "AUTO"
    width_mm: float | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, gt=0)
    height_mm: float | None = Field(default=None, gt=0)
    stroke_mm: float | None = Field(default=None, ge=0)
    actuation: MovementActuation = "MECHANICAL"
    material: str = "steel_h13"
    complexity: MovementComplexity = "MEDIUM"
    uses_edm: bool = False
    uses_treatment: bool = False
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def preserve_explicit_technical_dimensions(self) -> "SpecialMovementInput":
        if any(value is not None for value in (self.width_mm, self.length_mm, self.height_mm, self.stroke_mm)):
            self.technical_definition = "MANUAL"
        return self


class ComponentDimensionOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width_mm: float | None = Field(default=None, gt=0)
    length_mm: float | None = Field(default=None, gt=0)
    thickness_mm: float | None = Field(default=None, gt=0)
    material: str | None = None
    is_manual_override: bool = True
    is_locked: bool = False


class MoldExtras(BaseModel):
    model_config = ConfigDict(extra="forbid")

    moldflow: bool = False
    dfm: bool = False


class RealQuoteCalibrationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preco_real_referencia: float | None = Field(default=None, gt=0)
    horas_reais_referencia: float | None = Field(default=None, gt=0)
    apply_global_factor_to_current_quote: bool = False


class MoldTechnicalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mold_architecture: MoldArchitecture = "2_plate"
    cavity_count: int = Field(default=1, ge=1)
    cavity_type: CavityType = "monoblock"
    mold_construction_type: MoldConstructionType | None = None
    mold_lifetime: MoldLifetime = "LOW_50K"
    plastic_material: PlasticMaterial = "PP_VIRGIN"
    other_plastic_material: str | None = None
    injection_type: InjectionType = "cold_runner"
    hot_runner_drops: int = Field(default=0, ge=0)
    gate_strategy: GateStrategy = "unknown_schematic"
    extraction_type: ExtractionType = "ejector_pins"
    has_movements: bool = False
    number_of_movements: int = Field(default=0, ge=0)
    movement_type: MovementType = "NONE"
    special_movements: list[SpecialMovementInput] = Field(default_factory=list)
    dimension_overrides: dict[str, ComponentDimensionOverride] = Field(default_factory=dict)
    part_class: PartClass = "TECHNICAL"
    dimensional_requirement: DimensionalRequirement = "NORMAL"
    visual_requirement: VisualRequirement = "NO_VISUAL_REQUIREMENT"
    surface_treatment: SurfaceTreatment = "NOT_DEFINED"
    main_finish: MainFinish = "MACHINED_TECHNICAL"
    has_mirror_polish_areas: bool = False
    has_textured_areas: bool = False
    cad_movement_warning: bool = False
    cad_movement_warning_message: str | None = None
    mrr_config_version: str = "mrr-default-v1"
    extras: MoldExtras = Field(default_factory=MoldExtras)
    real_quote_calibration: RealQuoteCalibrationInput = Field(default_factory=RealQuoteCalibrationInput)

    @model_validator(mode="after")
    def validate_mold_input(self) -> "MoldTechnicalInput":
        if self.mold_construction_type is None:
            self.mold_construction_type = (
                "insertado_posticado" if self.cavity_type == "inserted" else "monobloco"
            )
        if self.mold_construction_type in {"insertado_posticado", "hibrido"}:
            self.cavity_type = "inserted"
        elif self.mold_construction_type == "monobloco":
            self.cavity_type = "monoblock"
        if self.injection_type == "hot_runner" and self.hot_runner_drops <= 0:
            raise ValueError("hot_runner_drops must be at least 1 for hot_runner.")
        if self.injection_type != "hot_runner":
            self.gate_strategy = "unknown_schematic"
        if self.special_movements:
            self.has_movements = True
            self.number_of_movements = sum(item.quantity for item in self.special_movements)
            self.movement_type = _legacy_movement_type(self.special_movements[0].movement_type)
        if not self.has_movements:
            self.number_of_movements = 0
            self.movement_type = "NONE"
        if self.has_movements and self.number_of_movements == 0:
            raise ValueError("number_of_movements must be greater than 0 when has_movements is true.")
        if self.number_of_movements == 0 and self.movement_type != "NONE":
            raise ValueError("movement_type must be NONE when no movements are present.")
        if self.main_finish != "MIXED":
            self.has_mirror_polish_areas = False
            self.has_textured_areas = False
        if self.plastic_material == "OTHER" and not self.other_plastic_material:
            raise ValueError("other_plastic_material is required when plastic_material is OTHER.")
        return self

    @property
    def production_volume(self) -> str:
        if self.mold_lifetime == "PROTOTYPE_10K":
            return "prototype"
        if self.mold_lifetime in {"HIGH_1M", "HEAVY_ABOVE_1M"}:
            return "high"
        return "low"

    @property
    def has_sliders(self) -> bool:
        return self.has_movements

    @property
    def slider_count(self) -> int:
        return self.number_of_movements

    @property
    def slider_motion_type(self) -> str:
        return {
            "NONE": "none",
            "SIDE_SLIDER": "cams",
            "ANGLED_SLIDER": "inclined_pins",
            "UNSCREWING_CORE": "cams",
            "FORCED_EJECTION": "cams",
            "HYDRAULIC_MOVEMENT": "hydraulic_cylinders",
            "MECHANICAL_MOVEMENT": "cams",
            "OTHER": "cams",
        }[self.movement_type]


def _legacy_movement_type(movement_type: SpecialMovementType) -> MovementType:
    return {
        "SIMPLE_SIDE_SLIDER": "SIDE_SLIDER",
        "ANGLED_PIN_SLIDER": "ANGLED_SLIDER",
        "HYDRAULIC_SLIDER": "HYDRAULIC_MOVEMENT",
        "SPECIAL_MECHANICAL_SLIDER": "MECHANICAL_MOVEMENT",
        "COLLAPSIBLE_CORE": "MECHANICAL_MOVEMENT",
        "NEGATIVE_JAW": "SIDE_SLIDER",
        "ROTARY_CORE": "UNSCREWING_CORE",
        "FORCED_EJECTION": "FORCED_EJECTION",
        "LIFTER": "ANGLED_SLIDER",
        "MOVABLE_CORE": "MECHANICAL_MOVEMENT",
        "MOVABLE_INSERT": "MECHANICAL_MOVEMENT",
        "RETRACTABLE_CORE": "HYDRAULIC_MOVEMENT",
        "CUSTOM": "OTHER",
        "UNKNOWN": "OTHER",
    }[movement_type]


class MoldPricingEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steel_package: dict[str, Any]
    material_costs: dict[str, Any]
    hardware_components: dict[str, Any]
    hot_runner: dict[str, Any]
    cnc_machining: dict[str, Any]
    edm: dict[str, Any]
    engineering: dict[str, Any]
    treatments: dict[str, Any]
    bench_assembly: dict[str, Any]
    tryout: dict[str, Any]
    commercial: dict[str, Any]
    assumptions: list[str]
    cost_dominance: dict[str, Any]
    confidence: dict[str, Any]
    technical_breakdown: dict[str, Any]


class MoldPricingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: dict[str, Any]
    technical_input: MoldTechnicalInput


class MoldPricingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["estimated"]
    mold_pricing_estimate: MoldPricingEstimate
