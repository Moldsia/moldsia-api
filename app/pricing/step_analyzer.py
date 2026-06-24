from typing import Any

from app.schemas.mold_quote_schema import MoldTechnicalInput


def analyze_step_geometry(analysis: dict[str, Any], calibration: dict[str, Any]) -> dict[str, Any]:
    geometry = analysis.get("geometry", {})
    derived = analysis.get("derived_metrics", {})
    complexity = analysis.get("complexity", {})
    xlen = float(geometry.get("xlen_mm", 0.0))
    ylen = float(geometry.get("ylen_mm", 0.0))
    zlen = float(geometry.get("zlen_mm", 0.0))
    real_volume_mm3 = float(geometry.get("real_volume_mm3", 0.0))
    occupancy = float(geometry.get("occupancy_ratio", 0.0))
    face_count = int(geometry.get("face_count", 0))
    rules = calibration["sizing_rules"]

    orientations = [
        ("XY", "Z", xlen, ylen, zlen),
        ("XZ", "Y", xlen, zlen, ylen),
        ("YZ", "X", ylen, zlen, xlen),
    ]
    projected_factor = max(
        float(rules["projected_area_min_factor"]),
        min(
            1.0,
            float(rules["projected_area_min_factor"])
            + occupancy * float(rules["projected_area_occupancy_weight"])
            + min(face_count / 6000, 0.12),
        ),
    )
    candidates = []
    for plane, opening_axis, width, length, depth in orientations:
        footprint = width * length
        projected_area = footprint * projected_factor
        aspect = max(width, length) / max(min(width, length), 1)
        depth_penalty = depth * depth * 4
        aspect_penalty = max(aspect - 2.2, 0) * footprint * 0.08
        score = projected_area + depth_penalty + aspect_penalty
        candidates.append(
            {
                "orientation_plane": plane,
                "opening_axis": opening_axis,
                "width_mm": round(width, 4),
                "length_mm": round(length, 4),
                "depth_mm": round(depth, 4),
                "projected_area_mm2": round(projected_area, 4),
                "orientation_score": round(score, 4),
            }
        )
    candidates.sort(key=lambda item: item["orientation_score"])
    selected = candidates[0]
    average_thickness = real_volume_mm3 / max(selected["projected_area_mm2"], 1)
    return {
        "original_x_mm": round(xlen, 4),
        "original_y_mm": round(ylen, 4),
        "original_z_mm": round(zlen, 4),
        "part_x_mm": round(xlen, 4),
        "part_y_mm": round(ylen, 4),
        "part_z_mm": round(zlen, 4),
        "part_volume_cm3": round(float(geometry.get("real_volume_cm3", 0.0)), 4),
        "part_volume_mm3": round(real_volume_mm3, 4),
        "projected_area_factor": round(projected_factor, 4),
        "projected_area_mm2": selected["projected_area_mm2"],
        "average_thickness_mm": round(average_thickness, 4),
        "suggested_orientation_plane": selected["orientation_plane"],
        "opening_axis": selected["opening_axis"],
        "oriented_width_mm": selected["width_mm"],
        "oriented_length_mm": selected["length_mm"],
        "oriented_depth_mm": selected["depth_mm"],
        "orientation_candidates": candidates,
        "complexity_score": complexity.get("complexity_score"),
        "complexity_level": complexity.get("complexity_level"),
        "feature_density_by_volume": derived.get("feature_density_by_volume"),
        "surface_complexity_signal": derived.get("surface_complexity_signal"),
        "risk_flags": analysis.get("manufacturing_risk", {}).get("risk_flags", []),
        "method": "step_analysis_response_projection_orientation_and_complexity",
    }


def apply_material_shrinkage(
    part_envelope: dict[str, Any],
    technical_input: MoldTechnicalInput,
    calibration: dict[str, Any],
) -> dict[str, Any]:
    material_meta = calibration["plastic_materials"].get(
        technical_input.plastic_material,
        calibration["plastic_materials"]["OTHER"],
    )
    shrinkage = float(material_meta["shrinkage_factor"])
    return {
        "x_mm": round(float(part_envelope["oriented_width_mm"]) * (1 + shrinkage), 4),
        "y_mm": round(float(part_envelope["oriented_length_mm"]) * (1 + shrinkage), 4),
        "z_mm": round(float(part_envelope["oriented_depth_mm"]) * (1 + shrinkage), 4),
        "shrinkage_factor": shrinkage,
        "plastic_material": technical_input.plastic_material,
        "plastic_label": material_meta["label"],
        "method": "corrected_part_envelope_from_plastic_shrinkage_table",
    }
