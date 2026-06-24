from typing import Any

from math import ceil

from app.schemas.mold_quote_schema import MoldTechnicalInput
from app.services.mold_calibration_service import load_mold_calibration


PLASTIC_MATERIAL_META: dict[str, dict[str, bool | str]] = {
    "PP_VIRGIN": {
        "label": "PP virgem",
        "shrinkage_risk": "medium",
        "abrasive": False,
        "polishing_risk": "low",
        "moldflow_recommended": False,
        "treatment_recommended": False,
    },
    "PP_COPOLYMER": {
        "label": "PP copolimero",
        "shrinkage_risk": "medium",
        "abrasive": False,
        "polishing_risk": "low",
        "moldflow_recommended": False,
        "treatment_recommended": False,
    },
    "PP_TALC_20": {
        "label": "PP + 20% talco",
        "shrinkage_risk": "medium",
        "abrasive": True,
        "polishing_risk": "medium",
        "moldflow_recommended": True,
        "treatment_recommended": True,
    },
    "PP_TALC_40": {
        "label": "PP + 40% talco",
        "shrinkage_risk": "medium",
        "abrasive": True,
        "polishing_risk": "medium",
        "moldflow_recommended": True,
        "treatment_recommended": True,
    },
    "PP_GLASS_FIBER": {
        "label": "PP com fibra",
        "shrinkage_risk": "high",
        "abrasive": True,
        "polishing_risk": "medium",
        "moldflow_recommended": True,
        "treatment_recommended": True,
    },
    "PEHD": {"label": "PEAD", "shrinkage_risk": "high", "abrasive": False, "polishing_risk": "low", "moldflow_recommended": False, "treatment_recommended": False},
    "PELD": {"label": "PEBD", "shrinkage_risk": "high", "abrasive": False, "polishing_risk": "low", "moldflow_recommended": False, "treatment_recommended": False},
    "ABS": {"label": "ABS", "shrinkage_risk": "low", "abrasive": False, "polishing_risk": "medium", "moldflow_recommended": False, "treatment_recommended": False},
    "PS_HIPS": {"label": "PS / PSAI", "shrinkage_risk": "low", "abrasive": False, "polishing_risk": "medium", "moldflow_recommended": False, "treatment_recommended": False},
    "POM": {"label": "POM", "shrinkage_risk": "medium", "abrasive": False, "polishing_risk": "medium", "moldflow_recommended": True, "treatment_recommended": False},
    "PA": {"label": "PA6 / PA66", "shrinkage_risk": "high", "abrasive": False, "polishing_risk": "medium", "moldflow_recommended": True, "treatment_recommended": False},
    "PA_GLASS_FIBER": {
        "label": "PA6 / PA66 com fibra",
        "shrinkage_risk": "high",
        "abrasive": True,
        "polishing_risk": "medium",
        "moldflow_recommended": True,
        "treatment_recommended": True,
    },
    "PC": {"label": "PC", "shrinkage_risk": "medium", "abrasive": False, "polishing_risk": "high", "moldflow_recommended": True, "treatment_recommended": False},
    "PC_ABS": {"label": "PC/ABS", "shrinkage_risk": "medium", "abrasive": False, "polishing_risk": "high", "moldflow_recommended": True, "treatment_recommended": False},
    "PMMA": {"label": "PMMA", "shrinkage_risk": "low", "abrasive": False, "polishing_risk": "high", "moldflow_recommended": True, "treatment_recommended": False},
    "PVC": {"label": "PVC", "shrinkage_risk": "medium", "abrasive": False, "polishing_risk": "medium", "moldflow_recommended": True, "treatment_recommended": True},
    "TPU_TPE": {"label": "TPU / TPE", "shrinkage_risk": "high", "abrasive": False, "polishing_risk": "medium", "moldflow_recommended": True, "treatment_recommended": False},
    "OTHER": {"label": "Material nao listado", "shrinkage_risk": "unknown", "abrasive": False, "polishing_risk": "unknown", "moldflow_recommended": True, "treatment_recommended": False},
}


MATERIAL_LIBRARY: dict[str, dict[str, float | str]] = {
    "steel_1045": {
        "label": "Aco 1045",
        "density_g_cm3": 7.85,
        "material_price_brl_kg": 8.5,
        "base_mrr_cm3_hour": 1200.0,
    },
    "steel_p20": {
        "label": "Aco P20",
        "density_g_cm3": 7.85,
        "material_price_brl_kg": 18.0,
        "base_mrr_cm3_hour": 850.0,
    },
    "steel_h13": {
        "label": "Aco H13",
        "density_g_cm3": 7.80,
        "material_price_brl_kg": 34.0,
        "base_mrr_cm3_hour": 450.0,
    },
    "stainless_420": {
        "label": "Inox 420",
        "density_g_cm3": 7.75,
        "material_price_brl_kg": 38.0,
        "base_mrr_cm3_hour": 520.0,
    },
    "aluminum": {
        "label": "Aluminio",
        "density_g_cm3": 2.70,
        "material_price_brl_kg": 32.0,
        "base_mrr_cm3_hour": 5000.0,
    },
}


def suggest_molding_steel(technical_input: MoldTechnicalInput) -> tuple[str, list[str]]:
    alerts: list[str] = []
    material_meta = plastic_material_meta(technical_input.plastic_material)
    high_lifetime = technical_input.mold_lifetime in {"HIGH_1M", "HEAVY_ABOVE_1M"}
    if material_meta["treatment_recommended"]:
        alerts.append("surface_treatment_recommended_by_plastic_material")
    if material_meta["abrasive"]:
        alerts.append("abrasive_plastic_material_detected")
    if high_lifetime:
        alerts.append("high_mold_lifetime_requires_more_robust_steel_package")
    if technical_input.plastic_material in {"PA_GLASS_FIBER", "PP_GLASS_FIBER"} and high_lifetime:
        alerts.append("hardened_steel_recommended_for_abrasive_high_lifetime_mold")
        return "steel_h13", alerts
    if material_meta["abrasive"]:
        return "steel_h13" if high_lifetime else "steel_p20_2738", alerts
    if high_lifetime:
        return "steel_p20_2738", alerts
    return "steel_p20_2711", alerts


def calculate_group_material_cost(group: dict[str, Any], calibration: dict[str, Any] | None = None) -> dict[str, Any]:
    calibration = calibration or _load_calibration_fallback()
    component_type = str(group.get("component_type") or group.get("group") or "default")
    material = str(group["material"])
    material_price = _material_price_record(material, calibration)
    stock = _stock_dimensions(group, component_type, calibration)
    density = float(material_price["density_g_cm3"])
    price = float(material_price["price_per_kg"])
    volume_cm3 = stock["volume_bruto_cm3"]
    weight_kg = volume_cm3 * density / 1000
    base_material_cost = weight_kg * price
    cutting_cost = float(material_price.get("cutting_cost", 0.0)) * max(int(group.get("quantity", 1)), 1)
    material_cost = (
        base_material_cost
        * float(material_price.get("scrap_factor", 1.0))
        * float(material_price.get("purchase_markup_factor", 1.0))
        * float(material_price.get("freight_factor", 1.0))
        * float(material_price.get("tax_factor", 1.0))
        + cutting_cost
    )
    theoretical_volume_cm3 = float(group.get("raw_volume_cm3") or group.get("volume_cm3") or 0.0)
    stock_over_theoretical_factor = volume_cm3 / theoretical_volume_cm3 if theoretical_volume_cm3 > 0 else 1.0
    return {
        **group,
        "final_dimensions_mm": {
            "width": group.get("width_mm"),
            "length": group.get("length_mm"),
            "thickness": group.get("thickness_mm"),
        },
        "stock_allowance_mm": stock["allowance_mm"],
        "stock_dimensions_mm": stock["dimensions_mm"],
        "largura_bruta_mm": stock["dimensions_mm"]["width"],
        "comprimento_bruto_mm": stock["dimensions_mm"]["length"],
        "espessura_bruta_mm": stock["dimensions_mm"]["thickness"],
        "volume_bruto_mm3": stock["volume_bruto_mm3"],
        "volume_bruto_cm3": stock["volume_bruto_cm3"],
        "volume_cm3": stock["volume_bruto_cm3"],
        "density_g_cm3": density,
        "material_price_brl_kg": price,
        "preco_kg": price,
        "material_purchase_factors": {
            "scrap_factor": material_price.get("scrap_factor", 1.0),
            "purchase_markup_factor": material_price.get("purchase_markup_factor", 1.0),
            "freight_factor": material_price.get("freight_factor", 1.0),
            "tax_factor": material_price.get("tax_factor", 1.0),
            "cutting_cost_brl": cutting_cost,
        },
        "estimated_weight_kg": round(weight_kg, 4),
        "peso_kg": round(weight_kg, 4),
        "raw_material_cost_brl": round(base_material_cost, 2),
        "base_material_cost_brl": round(base_material_cost, 2),
        "material_cost_brl": round(material_cost, 2),
        "custo_material": round(material_cost, 2),
        "stock_over_theoretical_factor": round(stock_over_theoretical_factor, 4),
        "cost_basis": "mold_physical_component_stock_dimensions",
    }


def consolidate_material_costs(groups: list[dict[str, Any]], material_alerts: list[str]) -> dict[str, Any]:
    by_material: dict[str, dict[str, Any]] = {}
    by_cost_group: dict[str, float] = {
        "materia_prima_aco": 0.0,
        "porta_molde": 0.0,
        "insertos": 0.0,
    }
    total_weight = 0.0
    bottom_up_total = 0.0
    applied_total = 0.0
    total_waste = 0.0

    for group in groups:
        material = str(group["material"])
        cost_group = str(group.get("material_cost_group", "materia_prima_aco"))
        applied_cost = float(group.get("material_cost_applied_brl", group["material_cost_brl"]))
        bottom_up_cost = float(group["material_cost_brl"])
        item = by_material.setdefault(
            material,
            {
                "material": material,
                "label": group["material_label"],
                "estimated_weight_kg": 0.0,
                "material_cost_brl": 0.0,
                "material_cost_applied_brl": 0.0,
            },
        )
        item["estimated_weight_kg"] += float(group["estimated_weight_kg"])
        item["material_cost_brl"] += bottom_up_cost
        item["material_cost_applied_brl"] += applied_cost
        by_cost_group[cost_group] = by_cost_group.get(cost_group, 0.0) + applied_cost
        total_weight += float(group["estimated_weight_kg"])
        bottom_up_total += bottom_up_cost
        applied_total += applied_cost
        total_waste += max(bottom_up_cost - float(group["raw_material_cost_brl"]), 0.0)

    for item in by_material.values():
        item["estimated_weight_kg"] = round(item["estimated_weight_kg"], 4)
        item["material_cost_brl"] = round(item["material_cost_brl"], 2)
        item["material_cost_applied_brl"] = round(item["material_cost_applied_brl"], 2)

    for key, value in list(by_cost_group.items()):
        by_cost_group[key] = round(value, 2)

    return {
        "total_weight_kg": round(total_weight, 4),
        "peso_total_aco_kg": round(total_weight, 4),
        "bottom_up_steel_material_cost_brl": round(bottom_up_total, 2),
        "total_material_cost_brl": round(applied_total, 2),
        "custo_total_aco": round(applied_total, 2),
        "materia_prima_aco_brl": by_cost_group.get("materia_prima_aco", 0.0),
        "porta_molde_brl": by_cost_group.get("porta_molde", 0.0),
        "insertos_brl": by_cost_group.get("insertos", 0.0),
        "material_cost_groups": by_cost_group,
        "estimated_waste_cost_brl": round(total_waste, 2),
        "by_material": list(by_material.values()),
        "steel_component_breakdown": groups,
        "material_alerts": material_alerts,
        "method": "physical_mold_components_stock_dimensions_density_price_kg",
    }


def material_record(material_id: str) -> dict[str, Any]:
    library = _material_library()
    material = library.get(material_id, library.get("steel_1045", MATERIAL_LIBRARY["steel_1045"]))
    return {
        "material": material_id,
        "material_label": material["label"],
        "density_g_cm3": material["density_g_cm3"],
        "material_price_brl_kg": material["material_price_brl_kg"],
        "base_mrr_cm3_hour": material.get("base_mrr_cm3_hour", 0.0),
        "machinability_factor": material.get("machinability_factor", 1.0),
    }


def plastic_material_meta(plastic_material: str) -> dict[str, bool | str]:
    return PLASTIC_MATERIAL_META.get(plastic_material, PLASTIC_MATERIAL_META["OTHER"])


def _material_library() -> dict[str, dict[str, Any]]:
    try:
        calibration = load_mold_calibration()
    except Exception:
        return MATERIAL_LIBRARY
    calibrated = {
        key: {
            **value,
            "base_mrr_cm3_hour": value.get("base_mrr_cm3_hour", 0.0),
        }
        for key, value in calibration.get("steel_materials", {}).items()
    }
    return MATERIAL_LIBRARY | calibrated


def _load_calibration_fallback() -> dict[str, Any]:
    try:
        return load_mold_calibration()
    except Exception:
        return {}


def _material_price_record(material_id: str, calibration: dict[str, Any]) -> dict[str, Any]:
    price_library = calibration.get("material_price_library", {})
    if material_id in price_library:
        return price_library[material_id]
    steel = calibration.get("steel_materials", {}).get(material_id) or _material_library().get(
        material_id,
        MATERIAL_LIBRARY["steel_1045"],
    )
    return {
        "label": steel.get("label", material_id),
        "density_g_cm3": steel.get("density_g_cm3", 7.85),
        "price_per_kg": steel.get("material_price_brl_kg", 10.0),
        "scrap_factor": 1.0,
        "purchase_markup_factor": 1.0,
        "cutting_cost": 0.0,
        "freight_factor": 1.0,
        "tax_factor": 1.0,
    }


def _stock_dimensions(group: dict[str, Any], component_type: str, calibration: dict[str, Any]) -> dict[str, Any]:
    rules = calibration.get("stock_purchase_rules", {})
    increments = rules.get("rounding_increment_mm", {"x": 10, "y": 10, "z": 5})
    allowances = rules.get("component_allowances", {})
    allowance = allowances.get(component_type, allowances.get("default", {}))
    width = _round_up_stock(
        float(group.get("width_mm", 0.0)) + float(allowance.get("sobremetal_x_mm", 0.0)),
        float(increments.get("x", 10)),
    )
    length = _round_up_stock(
        float(group.get("length_mm", 0.0)) + float(allowance.get("sobremetal_y_mm", 0.0)),
        float(increments.get("y", 10)),
    )
    thickness = _round_up_stock(
        float(group.get("thickness_mm", 0.0)) + float(allowance.get("sobremetal_z_mm", 0.0)),
        float(increments.get("z", 5)),
    )
    quantity = max(int(group.get("quantity", 1)), 1)
    volume_mm3 = width * length * thickness * quantity
    return {
        "allowance_mm": {
            "x": float(allowance.get("sobremetal_x_mm", 0.0)),
            "y": float(allowance.get("sobremetal_y_mm", 0.0)),
            "z": float(allowance.get("sobremetal_z_mm", 0.0)),
        },
        "dimensions_mm": {
            "width": round(width, 4),
            "length": round(length, 4),
            "thickness": round(thickness, 4),
        },
        "volume_bruto_mm3": round(volume_mm3, 4),
        "volume_bruto_cm3": round(volume_mm3 / 1000, 4),
    }


def _round_up_stock(value: float, increment: float) -> float:
    if increment <= 0:
        return value
    return ceil(value / increment) * increment


