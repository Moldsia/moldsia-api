import math
from typing import Any

from app.pricing.cavity_layout_engine import calculate_cavity_layout
from app.pricing.moldbase_selector import select_standard_mold_base
from app.pricing.step_analyzer import analyze_step_geometry, apply_material_shrinkage
from app.schemas.mold_quote_schema import MoldTechnicalInput


def calculate_mold_sizing(
    analysis: dict[str, Any],
    technical_input: MoldTechnicalInput,
    calibration: dict[str, Any],
) -> dict[str, Any]:
    complexity = analysis.get("complexity", {})
    complexity_level = complexity.get("complexity_level", "medium")
    part_envelope = analyze_step_geometry(analysis, calibration)
    corrected = apply_material_shrinkage(part_envelope, technical_input, calibration)
    layout = calculate_cavity_layout(
        corrected_part_x_mm=corrected["x_mm"],
        corrected_part_y_mm=corrected["y_mm"],
        cavity_count=technical_input.cavity_count,
        complexity_level=complexity_level,
        technical_input=technical_input,
        calibration=calibration,
    )
    margins = _steel_margins(corrected, layout, complexity_level, technical_input, calibration)
    raw_width = layout["layout_width_mm"] + 2 * margins["side_steel_margin_mm"]
    raw_length = layout["layout_length_mm"] + 2 * margins["top_bottom_steel_margin_mm"]
    selected_base = select_standard_mold_base(raw_width, raw_length, calibration)
    base_override = technical_input.dimension_overrides.get("mold_base")
    if base_override:
        if base_override.width_mm is not None:
            selected_base["width_mm"] = round(float(base_override.width_mm), 4)
        if base_override.length_mm is not None:
            selected_base["length_mm"] = round(float(base_override.length_mm), 4)
        selected_base["area_mm2"] = round(
            float(selected_base["width_mm"]) * float(selected_base["length_mm"]), 4
        )
        selected_base["manual_override"] = True
        selected_base["is_locked"] = base_override.is_locked
        selected_base["source"] = "technical_input.dimension_overrides.mold_base"
    mold_scale = _mold_scale(selected_base["width_mm"], selected_base["length_mm"])
    height = _height_breakdown(
        corrected_depth_mm=corrected["z_mm"],
        mold_scale=mold_scale,
        complexity_level=complexity_level,
        technical_input=technical_input,
        calibration=calibration,
    )
    _apply_height_overrides(height, technical_input)
    alerts = _sizing_alerts(analysis, technical_input, corrected, layout, margins, selected_base, height)

    return {
        "part_envelope": part_envelope,
        "corrected_part_envelope": corrected,
        "cavity_layout": layout,
        "steel_margins": margins,
        "raw_mold_base": {
            "width_mm": round(raw_width, 4),
            "length_mm": round(raw_length, 4),
            "area_mm2": round(raw_width * raw_length, 4),
        },
        "selected_mold_base": selected_base,
        "height_breakdown": height,
        "mold_scale": mold_scale,
        "alerts": alerts,
        "method": "part_envelope_shrinkage_layout_margins_standard_moldbase",
        "calibration_version": calibration.get("version"),
    }


def _apply_height_overrides(height: dict[str, Any], technical_input: MoldTechnicalInput) -> None:
    mappings = {
        "placa_superior": "top_clamping_plate_mm",
        "placa_porta_manifold": "manifold_support_plate_mm",
        "placa_cavidade": "cavity_plate_mm",
        "placa_macho": "core_plate_mm",
        "placa_suporte": "support_plate_mm",
        "paralelas": "spacer_block_height_mm",
        "placa_extratora_1": "ejector_plate_1_mm",
        "placa_extratora_2": "ejector_plate_2_mm",
        "placa_inferior": "bottom_clamping_plate_mm",
        "inserto_cavidade": "inserto_cavidade_thickness_mm",
        "inserto_macho": "inserto_macho_thickness_mm",
    }
    applied: list[str] = []
    for component_key, height_key in mappings.items():
        override = technical_input.dimension_overrides.get(component_key)
        if override is None or override.thickness_mm is None:
            continue
        height[height_key] = round(float(override.thickness_mm), 4)
        if component_key == "placa_cavidade" and "porta_inserto_cavidade_thickness_mm" in height:
            height["porta_inserto_cavidade_thickness_mm"] = height[height_key]
        if component_key == "placa_macho" and "porta_inserto_macho_thickness_mm" in height:
            height["porta_inserto_macho_thickness_mm"] = height[height_key]
        applied.append(component_key)

    plate_stack = float(height.get("ejector_plate_1_mm", 0)) + float(height.get("ejector_plate_2_mm", 0))
    clearance = float(height.get("required_ejection_clearance_mm", 0))
    spacer = float(height.get("spacer_block_height_mm", 0))
    ejector_box = max(spacer, plate_stack + clearance)
    height["ejector_plate_stack_height_mm"] = round(plate_stack, 4)
    height["ejector_box_height_mm"] = round(ejector_box, 4)
    height["spacer_block_height_mm"] = round(ejector_box, 4)
    physical_stack_keys = (
        "top_clamping_plate_mm",
        "manifold_support_plate_mm",
        "cavity_plate_mm",
        "core_plate_mm",
        "support_plate_mm",
        "spacer_block_height_mm",
        "bottom_clamping_plate_mm",
    )
    height["total_mold_height_mm"] = round(sum(float(height.get(key, 0)) for key in physical_stack_keys), 4)
    total_override = technical_input.dimension_overrides.get("mold_total_height")
    if total_override and total_override.thickness_mm is not None:
        height["total_mold_height_mm"] = round(float(total_override.thickness_mm), 4)
        applied.append("mold_total_height")
    if applied:
        height["manual_overrides_applied"] = applied
        height["method"] = "physical_plate_stack_with_manual_dimension_overrides"


def _steel_margins(
    corrected: dict[str, Any],
    layout: dict[str, Any],
    complexity_level: str,
    technical_input: MoldTechnicalInput,
    calibration: dict[str, Any],
) -> dict[str, Any]:
    rules = calibration["sizing_rules"]
    max_dim = max(float(corrected["x_mm"]), float(corrected["y_mm"]))
    side = max(float(rules["side_margin_min_mm"]), max_dim * float(rules["side_margin_dim_factor"]))
    top_bottom = max(float(rules["depth_margin_min_mm"]), float(corrected["z_mm"]) * float(rules["depth_margin_factor"]))
    factor = float(rules["complexity_margin_factors"].get(complexity_level, 1.08))
    if max_dim >= float(rules["large_part_threshold_mm"]):
        factor *= float(rules["large_part_margin_factor"])
    if technical_input.has_movements:
        factor *= float(rules["movement_margin_factor"])
    if technical_input.injection_type == "hot_runner":
        factor *= float(rules["hot_runner_margin_factor"])
    if technical_input.cavity_type == "inserted":
        factor *= 1.05
    return {
        "side_steel_margin_mm": round(side * factor, 4),
        "center_steel_between_cavities_mm": layout["center_margin_between_cavities_mm"],
        "top_bottom_steel_margin_mm": round(max(top_bottom, side * 0.86) * factor, 4),
        "margin_factor_applied": round(factor, 4),
    }


def _height_breakdown(
    *,
    corrected_depth_mm: float,
    mold_scale: str,
    complexity_level: str,
    technical_input: MoldTechnicalInput,
    calibration: dict[str, Any],
) -> dict[str, Any]:
    rules = calibration["height_rules"]
    standards = calibration["standard_thickness_mm"]
    material_meta = calibration["plastic_materials"].get(
        technical_input.plastic_material,
        calibration["plastic_materials"]["OTHER"],
    )
    complexity_extra = {"low": 0, "medium": 8, "high": 18}.get(complexity_level, 8)
    pressure_extra = 8 if material_meta.get("pressure_class") == "high" else 0
    hot_runner_extra = float(rules["hot_runner_extra_mm"]) if technical_input.injection_type == "hot_runner" else 0
    movement_extra = float(rules["movement_extra_mm"]) if technical_input.has_movements else 0
    cooling_extra = float(rules["cooling_extra_mm"]) * float(material_meta.get("cooling_factor", 1.0))
    inserted = getattr(technical_input, "mold_construction_type", None) in {"insertado_posticado", "hibrido"} or technical_input.cavity_type == "inserted"
    hot_runner = technical_input.injection_type == "hot_runner"

    if inserted:
        insert_cavity = _round_up_standard(
            max(
                float(rules.get("min_insert_cavity_mm", rules["min_cavity_plate_mm"])),
                corrected_depth_mm * float(rules.get("insert_cavity_depth_factor", 0.9)) + 20 + complexity_extra * 0.45,
            ),
            standards,
        )
        insert_core = _round_up_standard(
            max(
                float(rules.get("min_insert_core_mm", rules["min_core_plate_mm"])),
                corrected_depth_mm * float(rules.get("insert_core_depth_factor", 0.85)) + 20 + complexity_extra * 0.40,
            ),
            standards,
        )
        cavity_plate = _holder_plate_thickness(
            rules=rules,
            standards=standards,
            mold_scale=mold_scale,
            insert_thickness_mm=insert_cavity,
            cooling_extra_mm=cooling_extra,
            pressure_extra_mm=pressure_extra,
            complexity_extra_mm=complexity_extra,
            side="cavity",
        )
        core_plate = _holder_plate_thickness(
            rules=rules,
            standards=standards,
            mold_scale=mold_scale,
            insert_thickness_mm=insert_core,
            cooling_extra_mm=cooling_extra,
            pressure_extra_mm=0,
            complexity_extra_mm=complexity_extra + movement_extra,
            side="core",
        )
        thickness_rules = {
            "porta_inserto_cavidade_thickness_mm": cavity_plate,
            "porta_inserto_macho_thickness_mm": core_plate,
            "inserto_cavidade_thickness_mm": insert_cavity,
            "inserto_macho_thickness_mm": insert_core,
            "holder_plate_thickness_rule": "holder_plate_thickness_logic_by_scale_insert_depth_cooling_pressure_and_complexity",
            "insert_thickness_rule": "insert_thickness_logic_by_corrected_part_depth",
        }
    else:
        cavity_plate = _round_up_standard(
            max(
                float(rules["min_cavity_plate_mm"]),
                corrected_depth_mm * float(rules["cavity_depth_factor"]) + cooling_extra + hot_runner_extra + complexity_extra + pressure_extra,
            ),
            standards,
        )
        core_plate = _round_up_standard(
            max(
                float(rules["min_core_plate_mm"]),
                corrected_depth_mm * float(rules["core_depth_factor"]) + cooling_extra + movement_extra + complexity_extra,
            ),
            standards,
        )
        thickness_rules = {
            "holder_plate_thickness_rule": None,
            "insert_thickness_rule": None,
        }
    ejection = _ejection_stroke(
        corrected_depth_mm=corrected_depth_mm,
        rules=rules,
        standards=standards,
        technical_input=technical_input,
    )
    ejector_1, ejector_2 = _ejector_plate_thicknesses(
        rules=rules,
        standards=standards,
        mold_scale=mold_scale,
        technical_input=technical_input,
        ejection_stroke_mm=ejection["ejection_stroke_mm"],
        complexity_level=complexity_level,
    )
    ejector_box = _ejector_box_height(
        rules=rules,
        standards=standards,
        mold_scale=mold_scale,
        technical_input=technical_input,
        ejection_stroke_mm=ejection["ejection_stroke_mm"],
        ejector_plate_1_mm=ejector_1,
        ejector_plate_2_mm=ejector_2,
    )
    manifold_support_plate, manifold_internal_pocket = _hot_runner_stack(
        rules=rules,
        standards=standards,
        mold_scale=mold_scale,
        technical_input=technical_input,
        pressure_extra_mm=pressure_extra,
    )
    items = {
        "top_clamping_plate_mm": float(rules["top_clamping_by_scale_mm"][mold_scale]),
        "manifold_support_plate_mm": manifold_support_plate,
        "cavity_plate_mm": cavity_plate,
        "core_plate_mm": core_plate,
        "support_plate_mm": float(rules["support_plate_by_scale_mm"][mold_scale]),
        "spacer_block_height_mm": ejector_box["ejector_box_height_mm"],
        "bottom_clamping_plate_mm": float(rules["bottom_clamping_by_scale_mm"][mold_scale]),
    }
    total = sum(items.values())
    return {
        **{key: round(value, 4) for key, value in items.items()},
        "manifold_internal_pocket_height_mm": round(manifold_internal_pocket, 4),
        "manifold_functional_space_mm": round(manifold_internal_pocket, 4),
        "ejector_plate_1_mm": round(ejector_1, 4),
        "ejector_plate_2_mm": round(ejector_2, 4),
        **{key: round(value, 4) for key, value in ejector_box.items()},
        **{key: round(value, 4) if isinstance(value, (int, float)) else value for key, value in thickness_rules.items()},
        "include_manifold_support_plate": hot_runner and bool(rules.get("include_manifold_support_plate", True)),
        "injection_system_type": technical_input.injection_type,
        **{key: round(value, 4) if isinstance(value, (int, float)) else value for key, value in ejection.items()},
        "total_mold_height_mm": round(total, 4),
        "method": "physical_plate_stack_with_internal_hot_runner_and_nested_ejector_box",
    }


def _holder_plate_thickness(
    *,
    rules: dict[str, Any],
    standards: list[int | float],
    mold_scale: str,
    insert_thickness_mm: float,
    cooling_extra_mm: float,
    pressure_extra_mm: float,
    complexity_extra_mm: float,
    side: str,
) -> float:
    minimum_by_scale = rules.get("holder_plate_min_by_scale_mm", {})
    maximum_by_scale = rules.get("holder_plate_max_by_scale_mm", {})
    minimum = float(minimum_by_scale.get(mold_scale, rules.get("min_cavity_plate_mm", 35)))
    maximum = float(maximum_by_scale.get(mold_scale, 180))
    insert_factor = float(rules.get("holder_plate_insert_thickness_factor", 0.42))
    side_extra = float(rules.get("holder_plate_core_extra_mm", 0 if side == "cavity" else 6))
    calculated = (
        insert_thickness_mm * insert_factor
        + cooling_extra_mm
        + pressure_extra_mm
        + complexity_extra_mm * 0.35
        + side_extra
        + float(rules.get("holder_plate_base_extra_mm", 18))
    )
    return _round_up_standard(min(max(calculated, minimum), maximum), standards)


def _hot_runner_stack(
    *,
    rules: dict[str, Any],
    standards: list[int | float],
    mold_scale: str,
    technical_input: MoldTechnicalInput,
    pressure_extra_mm: float,
) -> tuple[float, float]:
    if technical_input.injection_type != "hot_runner" or not bool(rules.get("include_manifold_support_plate", True)):
        return 0.0, 0.0

    drops = max(int(getattr(technical_input, "hot_runner_drops", 0) or 0), int(getattr(technical_input, "cavity_count", 1) or 1), 1)
    drop_extra = drops * float(rules.get("hot_runner_drop_clearance_factor_mm", 2.0))
    support_base = float(rules.get("manifold_support_plate_by_scale_mm", {}).get(mold_scale, 45))
    functional_base = float(rules.get("manifold_functional_space_by_scale_mm", {}).get(mold_scale, 38))
    pressure_extra = float(rules.get("hot_runner_plate_pressure_extra_mm", 5)) if pressure_extra_mm else 0.0
    support = _round_up_standard(support_base + drop_extra + pressure_extra, standards)
    internal_pocket = _round_up_standard(functional_base + drop_extra * 0.8, standards)
    return support, min(internal_pocket, support)


def _ejection_stroke(
    *,
    corrected_depth_mm: float,
    rules: dict[str, Any],
    standards: list[int | float],
    technical_input: MoldTechnicalInput,
) -> dict[str, Any]:
    extraction_type = str(technical_input.extraction_type or "automatic")
    factor_by_extraction = {
        "automatic": 0.72,
        "ejector_pins": 0.70,
        "ejector_plate": 0.76,
        "air": 0.62,
        "forced_ejection": 0.84,
        "rotary_core": 0.88,
        "robot": 0.58,
        "none": 0.55,
        **rules.get("ejection_stroke_factor_by_extraction", {}),
    }
    extra_by_extraction = {
        "automatic": 14.0,
        "ejector_pins": 14.0,
        "ejector_plate": 16.0,
        "air": 10.0,
        "forced_ejection": 18.0,
        "rotary_core": 18.0,
        "robot": 8.0,
        "none": 8.0,
        **rules.get("ejection_stroke_extra_by_extraction_mm", {}),
    }
    min_by_extraction = {
        "automatic": 25.0,
        "ejector_pins": 25.0,
        "ejector_plate": 30.0,
        "air": 20.0,
        "forced_ejection": 35.0,
        "rotary_core": 35.0,
        "robot": 20.0,
        "none": 18.0,
        **rules.get("ejection_stroke_min_by_extraction_mm", {}),
    }
    fallback_factor = float(rules.get("ejection_stroke_factor", 1.0))
    fallback_extra = float(rules.get("ejection_stroke_extra_mm", 0.0))
    factor = float(factor_by_extraction.get(extraction_type, fallback_factor))
    extra = float(extra_by_extraction.get(extraction_type, fallback_extra))
    minimum = float(min_by_extraction.get(extraction_type, 25.0))
    raw_stroke = max(minimum, corrected_depth_mm * factor + extra)
    ejection_stroke = _round_up_standard(raw_stroke, standards)

    opening_factor_by_extraction = {
        "automatic": 1.20,
        "ejector_pins": 1.25,
        "ejector_plate": 1.25,
        "air": 1.10,
        "forced_ejection": 1.35,
        "rotary_core": 1.40,
        "robot": 1.75,
        "none": 1.10,
        **rules.get("mold_opening_factor_by_extraction", {}),
    }
    opening_extra_by_extraction = {
        "robot": 60.0,
        "forced_ejection": 35.0,
        "rotary_core": 40.0,
        **rules.get("mold_opening_extra_by_extraction_mm", {}),
    }
    opening_raw = max(
        corrected_depth_mm * float(opening_factor_by_extraction.get(extraction_type, 1.2))
        + float(opening_extra_by_extraction.get(extraction_type, 30.0)),
        ejection_stroke + corrected_depth_mm * 0.35,
    )
    return {
        "ejection_stroke_mm": ejection_stroke,
        "ejection_stroke_raw_mm": raw_stroke,
        "ejection_stroke_factor_applied": factor,
        "ejection_stroke_extra_applied_mm": extra,
        "ejection_stroke_method": f"depth_based_by_extraction_{extraction_type}",
        "mold_opening_stroke_mm": _round_up_standard(opening_raw, standards),
        "mold_opening_stroke_method": f"part_fall_or_robot_access_by_extraction_{extraction_type}",
    }


def _ejector_box_height(
    *,
    rules: dict[str, Any],
    standards: list[int | float],
    mold_scale: str,
    technical_input: MoldTechnicalInput,
    ejection_stroke_mm: float,
    ejector_plate_1_mm: float,
    ejector_plate_2_mm: float,
) -> dict[str, float]:
    plate_stack = ejector_plate_1_mm + ejector_plate_2_mm
    running_clearance = float(rules.get("ejector_running_clearance_mm", 12))
    movement_extra = (
        float(rules.get("ejector_box_movement_extra_mm", 10))
        if technical_input.has_movements or technical_input.extraction_type in {"forced_ejection", "rotary_core", "robot"}
        else 0.0
    )
    required_clearance = ejection_stroke_mm + running_clearance + movement_extra
    minimum = float(rules.get("ejector_box_min_by_scale_mm", {}).get(mold_scale, 70))
    required_height = max(minimum, plate_stack + required_clearance)
    ejector_box_height = _round_up_standard(required_height, standards)
    if ejector_box_height < required_height:
        increment = float(rules.get("ejector_box_rounding_increment_mm", 10))
        ejector_box_height = math.ceil(required_height / increment) * increment
    default_max_by_scale = {
        "small_mold": 130,
        "medium_mold": 180,
        "large_mold": 240,
        "extra_large_mold": 300,
    }
    maximum = float(rules.get("ejector_box_max_by_scale_mm", {}).get(mold_scale, default_max_by_scale.get(mold_scale, 180)))
    clamped = ejector_box_height > maximum
    ejector_box_height = min(ejector_box_height, maximum)
    return {
        "ejector_box_height_mm": ejector_box_height,
        "ejector_plate_stack_height_mm": plate_stack,
        "required_ejection_clearance_mm": required_clearance,
        "ejector_box_max_by_scale_mm": maximum,
        "ejector_box_clamped_to_scale_max": clamped,
    }


def _ejector_plate_thicknesses(
    *,
    rules: dict[str, Any],
    standards: list[int | float],
    mold_scale: str,
    technical_input: MoldTechnicalInput,
    ejection_stroke_mm: float,
    complexity_level: str,
) -> tuple[float, float]:
    base_1 = max(
        float(rules.get("ejector_plate_1_mm", 20)),
        float(rules.get("ejector_plate_1_min_by_scale_mm", {}).get(mold_scale, 20)),
    )
    base_2 = max(
        float(rules.get("ejector_plate_2_mm", 25)),
        float(rules.get("ejector_plate_2_min_by_scale_mm", {}).get(mold_scale, 25)),
    )
    cavity_extra = max(int(technical_input.cavity_count) - 1, 0) * float(rules.get("ejector_plate_cavity_factor_mm", 1.2))
    stroke_extra = ejection_stroke_mm * float(rules.get("ejector_plate_stroke_factor", 0.055))
    pins_per_cavity = int(rules.get("ejector_pins_per_cavity_by_complexity", {}).get(complexity_level, 6))
    estimated_pin_count = max(int(technical_input.cavity_count), 1) * pins_per_cavity
    pin_count_extra = max(estimated_pin_count - 4, 0) * float(rules.get("ejector_pin_count_factor_mm", 0.12))
    estimated_pin_diameter = float(rules.get("ejector_pin_diameter_by_scale_mm", {}).get(mold_scale, 8))
    pin_diameter_extra = max(estimated_pin_diameter - 5, 0) * float(rules.get("ejector_pin_diameter_factor_mm", 0.35))
    complex_extraction = technical_input.extraction_type in {"ejector_plate", "forced_ejection", "rotary_core", "robot"}
    extraction_extra = float(rules.get("ejector_plate_complex_extraction_extra_mm", 5)) if complex_extraction else 0.0
    movement_extra = float(rules.get("ejector_plate_movement_extra_mm", 5)) if technical_input.has_movements else 0.0
    complexity_extra = {"low": 0.0, "medium": 2.0, "high": 5.0}.get(complexity_level, 2.0)

    plate_1 = _round_up_standard(base_1 + cavity_extra + stroke_extra + pin_count_extra + pin_diameter_extra + extraction_extra + movement_extra + complexity_extra, standards)
    plate_2 = _round_up_standard(base_2 + cavity_extra * 0.8 + stroke_extra * 0.8 + pin_count_extra * 0.7 + pin_diameter_extra + extraction_extra + movement_extra * 0.5 + complexity_extra, standards)
    return plate_1, plate_2


def _round_up_standard(value: float, standards: list[int | float]) -> float:
    for standard in sorted(float(item) for item in standards):
        if standard >= value:
            return standard
    return sorted(float(item) for item in standards)[-1]


def _mold_scale(width_mm: float, length_mm: float) -> str:
    max_dim = max(width_mm, length_mm)
    if max_dim <= 450:
        return "small_mold"
    if max_dim <= 950:
        return "medium_mold"
    return "large_mold"


def _sizing_alerts(
    analysis: dict[str, Any],
    technical_input: MoldTechnicalInput,
    corrected: dict[str, Any],
    layout: dict[str, Any],
    margins: dict[str, Any],
    selected_base: dict[str, Any],
    height: dict[str, Any],
) -> list[str]:
    alerts: list[str] = []
    complexity_level = analysis.get("complexity", {}).get("complexity_level")
    risk_flags = set(analysis.get("manufacturing_risk", {}).get("risk_flags", []))
    if complexity_level == "high" and not technical_input.has_movements:
        alerts.append("high_geometry_complexity_but_simple_mold_input_selected")
    if "possible_thin_wall" in risk_flags or "extreme_low_occupancy" in risk_flags:
        alerts.append("step_geometry_suggests_internal_or_sparse_features_review_layout")
    if layout["aspect_ratio"] > 2.2:
        alerts.append("cavity_layout_aspect_ratio_is_high")
    if selected_base["source"] in {"extrapolated_100mm_increment", "snap_to_50mm_grid"}:
        alerts.append("mold_base_snapped_beyond_catalog_table")
    if margins["margin_factor_applied"] > 1.35:
        alerts.append("large_margin_factor_applied_due_to_complexity_or_special_features")
    if corrected["z_mm"] > max(corrected["x_mm"], corrected["y_mm"]):
        alerts.append("part_depth_exceeds_plan_dimensions_review_opening_direction")
    if height.get("ejector_box_clamped_to_scale_max"):
        alerts.append("ejector_box_height_limited_by_mold_size_class_review_extraction")
    return alerts
