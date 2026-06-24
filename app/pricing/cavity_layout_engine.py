from math import ceil
from typing import Any

from app.schemas.mold_quote_schema import MoldTechnicalInput


def calculate_cavity_layout(
    *,
    corrected_part_x_mm: float,
    corrected_part_y_mm: float,
    cavity_count: int,
    complexity_level: str,
    technical_input: MoldTechnicalInput,
    calibration: dict[str, Any],
) -> dict[str, Any]:
    rules = calibration["sizing_rules"]
    material_meta = calibration["plastic_materials"].get(
        technical_input.plastic_material,
        calibration["plastic_materials"]["OTHER"],
    )
    max_part_dim = max(corrected_part_x_mm, corrected_part_y_mm)
    clearance = max(
        float(rules["part_clearance_min_mm"]),
        max_part_dim * float(rules["part_clearance_dim_factor"]),
    )
    clearance *= 1 + min(max(cavity_count - 1, 0) * 0.015, 0.12)
    clearance *= float(material_meta.get("cooling_factor", 1.0))
    if technical_input.injection_type == "hot_runner":
        clearance += 8 + max(technical_input.hot_runner_drops - 1, 0) * 2
    if technical_input.has_movements:
        clearance += 10
    if complexity_level == "high":
        clearance += 6

    center_margin = max(
        float(rules["center_margin_min_mm"]),
        max_part_dim * float(rules["center_margin_dim_factor"]),
    )
    if technical_input.injection_type == "hot_runner":
        center_margin *= 1.12
    if technical_input.has_movements:
        center_margin *= 1.10

    candidates = []
    for layout_x, layout_y in _layout_factor_pairs(cavity_count):
        cavity_envelope_x = corrected_part_x_mm + clearance
        cavity_envelope_y = corrected_part_y_mm + clearance
        width = layout_x * cavity_envelope_x + max(layout_x - 1, 0) * center_margin
        length = layout_y * cavity_envelope_y + max(layout_y - 1, 0) * center_margin
        area = width * length
        aspect = max(width, length) / max(min(width, length), 1)
        aspect_penalty = max(aspect - float(rules["layout_aspect_target"]), 0)
        score = area * (1 + aspect_penalty * float(rules["layout_aspect_penalty"]))
        candidates.append(
            {
                "layout_x": layout_x,
                "layout_y": layout_y,
                "cavity_envelope_x_mm": round(cavity_envelope_x, 4),
                "cavity_envelope_y_mm": round(cavity_envelope_y, 4),
                "cavity_clearance_mm": round(clearance, 4),
                "center_margin_between_cavities_mm": round(center_margin, 4),
                "layout_width_mm": round(width, 4),
                "layout_length_mm": round(length, 4),
                "layout_area_mm2": round(area, 4),
                "aspect_ratio": round(aspect, 4),
                "layout_score": round(score, 4),
            }
        )

    candidates.sort(key=lambda item: (item["layout_score"], item["layout_area_mm2"]))
    selected = candidates[0]
    return {
        **selected,
        "cavity_count": cavity_count,
        "evaluated_layouts": candidates[:8],
        "selection_method": "compact_area_with_aspect_penalty",
    }


def _layout_factor_pairs(cavity_count: int) -> list[tuple[int, int]]:
    count = max(int(cavity_count), 1)
    pairs: set[tuple[int, int]] = set()
    for x in range(1, int(ceil(count ** 0.5)) + 2):
        y = int(ceil(count / x))
        if x * y >= count:
            pairs.add((x, y))
            pairs.add((y, x))
    pairs.add((1, count))
    pairs.add((count, 1))
    return sorted(pairs)
