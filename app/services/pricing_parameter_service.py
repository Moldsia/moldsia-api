import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.settings import settings
from app.schemas.analysis_schema import PricingParameters, PricingParametersEnvelope


def get_default_pricing_parameters() -> PricingParameters:
    now = datetime.now(timezone.utc).isoformat()
    return PricingParameters(
        currency="BRL",
        minimum_order_value_brl=850.0,
        materials=[
            {
                "material_id": "steel_1045",
                "label": "Aço 1045",
                "density_g_cm3": 7.85,
                "material_price_brl_kg": 8.5,
                "machinability_factor": 1.0,
            },
            {
                "material_id": "steel_1020",
                "label": "Aço 1020",
                "density_g_cm3": 7.87,
                "material_price_brl_kg": 7.8,
                "machinability_factor": 0.95,
            },
            {
                "material_id": "steel_p20",
                "label": "Aço P20",
                "density_g_cm3": 7.8,
                "material_price_brl_kg": 18.0,
                "machinability_factor": 1.18,
            },
            {
                "material_id": "steel_h13",
                "label": "Aço H13",
                "density_g_cm3": 7.75,
                "material_price_brl_kg": 28.0,
                "machinability_factor": 1.35,
            },
            {
                "material_id": "stainless_420",
                "label": "Inox 420",
                "density_g_cm3": 7.74,
                "material_price_brl_kg": 32.0,
                "machinability_factor": 1.45,
            },
            {
                "material_id": "aluminum",
                "label": "Alumínio",
                "density_g_cm3": 2.7,
                "material_price_brl_kg": 24.0,
                "machinability_factor": 0.62,
            },
            {
                "material_id": "cast_iron",
                "label": "Ferro fundido",
                "density_g_cm3": 7.2,
                "material_price_brl_kg": 7.2,
                "machinability_factor": 0.9,
            },
            {
                "material_id": "copper",
                "label": "Cobre",
                "density_g_cm3": 8.96,
                "material_price_brl_kg": 55.0,
                "machinability_factor": 1.22,
            },
        ],
        base_mrr_by_material={
            "steel_1045": 1200.0,
            "steel_1020": 1350.0,
            "steel_p20": 850.0,
            "steel_h13": 450.0,
            "stainless_420": 420.0,
            "aluminum": 5000.0,
            "cast_iron": 1800.0,
            "copper": 700.0,
        },
        removal_rates={
            "bench_milling": {"removal_rate_cm3_hour": 70.0},
            "vertical_milling": {"removal_rate_cm3_hour": 120.0},
            "portal_milling": {"removal_rate_cm3_hour": 220.0},
            "complex_3_axis_milling": {"removal_rate_cm3_hour": 55.0},
            "precision_fixture_required": {"removal_rate_cm3_hour": 45.0},
            "engineering_review_required": {"removal_rate_cm3_hour": 35.0},
        },
        complexity_multipliers={"low": 1.0, "medium": 1.22, "high": 1.55},
        risk_multipliers={"low": 1.0, "medium": 1.12, "high": 1.32},
        finishing_multipliers={
            "low_feature_density_multiplier": 1.0,
            "medium_feature_density_multiplier": 1.12,
            "high_feature_density_multiplier": 1.28,
        },
        markup_tiers=[
            {"quantity_min": 1, "quantity_max": 5, "markup_floor": 1.6, "markup_ceiling": 1.8},
            {"quantity_min": 6, "quantity_max": 20, "markup_floor": 1.4, "markup_ceiling": 1.6},
            {"quantity_min": 21, "quantity_max": None, "markup_floor": 1.28, "markup_ceiling": 1.45},
        ],
        risk_markup_adjustment={
            "high_risk_ceiling_addition": 0.12,
            "engineering_review_ceiling_addition": 0.18,
        },
        default_stock_allowance_mm=5.0,
        default_supply_mode="moldsia_supplies",
        version=now,
        updated_at=None,
    )


def load_current_pricing_parameters() -> PricingParametersEnvelope:
    path = _current_parameters_path()
    if not path.exists():
        defaults = get_default_pricing_parameters()
        return PricingParametersEnvelope(
            parameters=defaults,
            parameters_source="default",
            parameters_updated_at=defaults.updated_at,
        )

    saved = PricingParameters.model_validate_json(path.read_text(encoding="utf-8"))
    merged = merge_with_defaults(saved)
    return PricingParametersEnvelope(
        parameters=merged,
        parameters_source="saved",
        parameters_updated_at=merged.updated_at,
    )


def save_current_pricing_parameters(parameters: PricingParameters) -> PricingParametersEnvelope:
    now = datetime.now(timezone.utc).isoformat()
    normalized = merge_with_defaults(parameters).model_copy(update={"version": now, "updated_at": now})
    path = _current_parameters_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalized.model_dump_json(indent=2), encoding="utf-8")
    save_pricing_parameter_history(normalized)
    return PricingParametersEnvelope(
        parameters=normalized,
        parameters_source="saved",
        parameters_updated_at=normalized.updated_at,
    )


def save_pricing_parameter_history(parameters: PricingParameters) -> Path:
    history_dir = settings.pricing_parameters_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _file_timestamp()
    output_path = history_dir / f"pricing-parameters-{timestamp}.json"
    output_path.write_text(parameters.model_dump_json(indent=2), encoding="utf-8")
    return output_path


def merge_with_defaults(parameters: PricingParameters) -> PricingParameters:
    defaults = get_default_pricing_parameters()
    default_payload = defaults.model_dump()
    saved_payload = parameters.model_dump(exclude_none=False)

    default_materials = {item["material_id"]: item for item in default_payload["materials"]}
    saved_materials = {item["material_id"]: item for item in saved_payload["materials"]}
    merged_materials = list((default_materials | saved_materials).values())

    merged_payload = {
        **default_payload,
        **saved_payload,
        "materials": merged_materials,
        "base_mrr_by_material": default_payload["base_mrr_by_material"]
        | saved_payload.get("base_mrr_by_material", {}),
        "removal_rates": default_payload["removal_rates"] | saved_payload["removal_rates"],
        "complexity_multipliers": default_payload["complexity_multipliers"]
        | saved_payload["complexity_multipliers"],
        "risk_multipliers": default_payload["risk_multipliers"] | saved_payload["risk_multipliers"],
    }
    return PricingParameters.model_validate(merged_payload)


def save_analysis_pricing_snapshot(payload: dict) -> Path:
    output_dir = settings.pricing_parameters_dir / "analysis_snapshots"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _file_timestamp()
    request_id = str(payload.get("request_id", "sem-request-id"))
    output_path = output_dir / f"pricing-analysis-{timestamp}-{request_id}.json"
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def _current_parameters_path() -> Path:
    return settings.pricing_parameters_dir / "current_parameters.json"


def _file_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
