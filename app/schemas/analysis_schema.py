from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.mold_quote_schema import MoldPricingEstimate


ComplexityLevel = Literal["low", "medium", "high"]
PieceSize = Literal["small", "large"]
MachiningProfile = Literal[
    "bench_milling",
    "vertical_milling",
    "portal_milling",
    "lathe_candidate",
    "mold_base_candidate",
    "complex_3_axis_milling",
    "precision_fixture_required",
    "engineering_review_required",
]
EstimatedMachineType = Literal[
    "bench_3_axis",
    "vertical_3_axis",
    "gantry_3_axis",
    "cnc_lathe",
    "mold_base_machining_center",
    "high_precision_3_axis",
    "fixture_assisted_3_axis",
    "engineering_review",
]
RiskLevel = Literal["low", "medium", "high"]
ShapeKind = Literal[
    "block_like",
    "cylindrical_like",
    "plate_like",
    "shaft_like",
    "thin_wall_like",
    "unknown",
    "unknown_complex",
    "compact_complex",
    "sparse_geometry",
    "thin_featured_geometry",
]
ReviewConfidence = Literal["low", "medium", "high"]
MaterialSupplyMode = Literal["customer_supplies", "moldsia_supplies"]
ParametersSource = Literal["saved", "default"]
ProcessingRisk = Literal["low", "medium", "high"]
AnalysisMode = Literal["standard", "heavy", "enterprise"]
IgesDiagnosis = Literal["solid_brep", "surface_model", "wireframe_or_curves", "unknown"]
HealingLevel = Literal["none", "minimal", "moderate", "aggressive", "forced"]
GeometryConfidenceLevel = Literal["very_high", "high", "medium", "low", "very_low"]



class GeometryMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    xlen_mm: float = Field(..., ge=0)
    ylen_mm: float = Field(..., ge=0)
    zlen_mm: float = Field(..., ge=0)
    bounding_box_volume_mm3: float = Field(..., ge=0)
    real_volume_mm3: float = Field(..., ge=0)
    real_volume_cm3: float = Field(..., ge=0)
    occupancy_ratio: float = Field(..., ge=0)
    solid_count: int = Field(..., ge=0)
    shell_count: int = Field(..., ge=0)
    face_count: int = Field(..., ge=0)
    is_assembly: bool


class ComplexityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    complexity_score: float = Field(..., ge=0, le=1)
    complexity_level: ComplexityLevel
    topology_complexity_score: float = Field(..., ge=0, le=1)
    complexity_breakdown: "ComplexityBreakdown"
    threshold_diagnostics: list[str] = Field(default_factory=list)


class ComplexityBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occupancy_component: float = Field(..., ge=0, le=1)
    topology_component: float = Field(..., ge=0, le=1)
    surface_component: float = Field(..., ge=0, le=1)
    shape_component: float = Field(..., ge=0, le=1)
    processing_component: float = Field(..., ge=0, le=1)


class DerivedMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thinness_ratio: float = Field(..., ge=0)
    slenderness_ratio: float = Field(..., ge=0)
    feature_density_by_volume: float = Field(..., ge=0)
    feature_density_by_bbox: float = Field(..., ge=0)
    occupancy_extremity_score: float = Field(..., ge=0, le=1)
    processing_complexity_signal: float = Field(..., ge=0, le=1)
    surface_complexity_signal: float = Field(..., ge=0, le=1)


class ShapeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_shape: ShapeKind
    secondary_shape: ShapeKind | None = None


class ManufacturingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    piece_size: PieceSize
    machining_profile: MachiningProfile
    estimated_machine_type: EstimatedMachineType
    setup_hours: float
    machine_rate_brl_hour: int


class ManufacturingRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_score: float = Field(..., ge=0, le=1)
    risk_level: RiskLevel
    risk_breakdown: "RiskBreakdown"
    risk_flags: list[str]


class RiskBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geometric_risk: float = Field(..., ge=0, le=1)
    machining_risk: float = Field(..., ge=0, le=1)
    fixturing_risk: float = Field(..., ge=0, le=1)
    commercial_risk: float = Field(..., ge=0, le=1)


class ReviewRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requires_engineering_review: bool
    reason: list[str]
    confidence: ReviewConfidence


class BenchmarkMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimated_hours: float | None = None
    real_hours: float | None = None
    estimated_cost: float | None = None
    real_cost: float | None = None
    won_quote: bool | None = None


class MaterialPricingParameter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: str
    label: str
    density_g_cm3: float = Field(..., gt=0)
    material_price_brl_kg: float = Field(..., ge=0)
    machinability_factor: float = Field(..., gt=0)


class RemovalRateParameter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    removal_rate_cm3_hour: float = Field(..., gt=0)


class FinishingMultipliers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low_feature_density_multiplier: float = Field(..., gt=0)
    medium_feature_density_multiplier: float = Field(..., gt=0)
    high_feature_density_multiplier: float = Field(..., gt=0)


class QuantityMarkupTier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity_min: int = Field(..., ge=1)
    quantity_max: int | None = Field(default=None, ge=1)
    markup_floor: float = Field(..., gt=0)
    markup_ceiling: float = Field(..., gt=0)

    @model_validator(mode="after")
    def validate_tier(self) -> "QuantityMarkupTier":
        if self.quantity_max is not None and self.quantity_min > self.quantity_max:
            raise ValueError("quantity_min deve ser menor ou igual a quantity_max.")
        if self.markup_ceiling < self.markup_floor:
            raise ValueError("markup_ceiling deve ser maior ou igual a markup_floor.")
        return self


class RiskMarkupAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    high_risk_ceiling_addition: float = Field(..., ge=0)
    engineering_review_ceiling_addition: float = Field(..., ge=0)


class PricingParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: Literal["BRL"] = "BRL"
    minimum_order_value_brl: float = Field(..., ge=0)
    materials: list[MaterialPricingParameter]
    base_mrr_by_material: dict[str, float] = Field(default_factory=dict)
    removal_rates: dict[str, RemovalRateParameter]
    complexity_multipliers: dict[ComplexityLevel, float]
    risk_multipliers: dict[RiskLevel, float]
    finishing_multipliers: FinishingMultipliers
    markup_tiers: list[QuantityMarkupTier]
    risk_markup_adjustment: RiskMarkupAdjustment
    default_stock_allowance_mm: float = Field(..., ge=0)
    default_supply_mode: MaterialSupplyMode
    version: str
    updated_at: str | None = None

    @model_validator(mode="after")
    def validate_parameters(self) -> "PricingParameters":
        if not self.materials:
            raise ValueError("A parametrizaÃ§Ã£o deve ter ao menos um material.")
        if not self.markup_tiers:
            raise ValueError("A parametrizaÃ§Ã£o deve ter ao menos uma faixa de markup.")
        for key, value in self.complexity_multipliers.items():
            if value <= 0:
                raise ValueError(f"Multiplicador de complexidade invÃ¡lido para {key}.")
        for key, value in self.risk_multipliers.items():
            if value <= 0:
                raise ValueError(f"Multiplicador de risco invÃ¡lido para {key}.")
        for key, value in self.base_mrr_by_material.items():
            if value <= 0:
                raise ValueError(f"Base MRR invÃ¡lido para {key}.")
        return self


class PricingParametersEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameters: PricingParameters
    parameters_source: ParametersSource
    parameters_updated_at: str | None = None


class PricingEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: Literal["BRL"]
    parameters_version: str
    material: dict[str, Any]
    machining: dict[str, Any]
    commercial: dict[str, Any]
    confidence: dict[str, Any]
    calculation_memory: dict[str, Any] | None = None


class CalibrationInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameters_source: ParametersSource
    parameters_updated_at: str | None = None
    can_save_snapshot: bool


class AnalysisPrecheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_size_mb: float = Field(..., ge=0)
    extension: str
    estimated_entity_count: int | None = Field(default=None, ge=0)
    estimated_processing_risk: ProcessingRisk
    recommended_analysis_mode: AnalysisMode
    iges_diagnostics: "IgesDiagnostics | None" = None


class IgesDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    has_brep_solid: bool
    has_shells: bool
    face_entity_count: int = Field(..., ge=0)
    trimmed_surface_count: int = Field(..., ge=0)
    bspline_surface_count: int = Field(..., ge=0)
    bspline_curve_count: int = Field(..., ge=0)
    diagnosis: IgesDiagnosis


class CadConversionInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempted: bool
    source_format: Literal["IGES"]
    target_format: Literal["STEP"]
    success: bool
    converted_file_path: str | None = None
    error: str | None = None
    diagnosis: IgesDiagnosis | None = None


class GeometryHealingReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempted: bool
    success: bool
    healing_level: HealingLevel
    gaps_closed_count: int = Field(..., ge=0)
    total_gap_distance_mm: float = Field(..., ge=0)
    max_gap_mm: float = Field(..., ge=0)
    modified_edges_ratio: float = Field(..., ge=0, le=1)
    modified_faces_ratio: float = Field(..., ge=0, le=1)
    shells_before_healing: int = Field(..., ge=0)
    shells_after_healing: int = Field(..., ge=0)
    solids_before_healing: int = Field(..., ge=0)
    solids_after_healing: int = Field(..., ge=0)
    healing_processing_time_ms: int = Field(..., ge=0)
    error: str | None = None


class GeometryConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(..., ge=0, le=1)
    level: GeometryConfidenceLevel
    healing_impact: HealingLevel
    commercial_warning: bool


class PricingSnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    file_name: str
    analysis: dict[str, Any]
    pricing_parameters_used: PricingParameters
    pricing_estimate: PricingEstimate


class PricingSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stored: bool
    snapshot_path: str


class UploadArchive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stored: bool
    archive_path: str | None = None
    file_hash_sha256: str


class AnalysisMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["CadQuery"]
    kernel: Literal["OpenCascade"]
    version: str
    heuristics_version: str
    file_hash_sha256: str


class AnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    status: Literal["analyzed"]
    processing_time_ms: int = Field(..., ge=0)
    file_name: str
    geometry: GeometryMetrics
    derived_metrics: DerivedMetrics
    complexity: ComplexityProfile
    shape_profile: ShapeProfile
    manufacturing_profile: ManufacturingProfile
    manufacturing_risk: ManufacturingRisk
    review_recommendation: ReviewRecommendation
    analysis_precheck: AnalysisPrecheck
    iges_diagnostics: IgesDiagnostics | None = None
    conversion: CadConversionInfo | None = None
    geometry_healing: GeometryHealingReport | None = None
    geometry_confidence: GeometryConfidence
    pricing_estimate: PricingEstimate
    mold_pricing_estimate: MoldPricingEstimate | None = None
    pricing_parameters_used: PricingParameters
    calibration: CalibrationInfo
    benchmark: BenchmarkMetrics
    upload_archive: UploadArchive
    metadata: AnalysisMetadata

