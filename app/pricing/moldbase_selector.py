from math import ceil
from typing import Any


def select_standard_mold_base(
    raw_width_mm: float,
    raw_length_mm: float,
    calibration: dict[str, Any],
) -> dict[str, Any]:
    standards = calibration["mold_base_standard_sizes_mm"]
    candidates = []
    for standard in standards:
        width = float(standard["width"])
        length = float(standard["length"])
        for rotated, candidate_width, candidate_length in (
            (False, width, length),
            (True, length, width),
        ):
            if candidate_width >= raw_width_mm and candidate_length >= raw_length_mm:
                area = candidate_width * candidate_length
                oversize = area - raw_width_mm * raw_length_mm
                candidates.append(
                    {
                        "width_mm": candidate_width,
                        "length_mm": candidate_length,
                        "area_mm2": area,
                        "oversize_area_mm2": oversize,
                        "rotated_standard": rotated,
                        "source": "standard_table",
                    }
                )
    if candidates:
        candidates.sort(key=lambda item: (item["area_mm2"], item["oversize_area_mm2"]))
        return _rounded_selection(candidates[0])

    snapped = snap_raw_dimensions_to_grid(raw_width_mm, raw_length_mm, calibration)
    width = snapped["width_mm"]
    length = snapped["length_mm"]
    return _rounded_selection(
        {
            "width_mm": width,
            "length_mm": length,
            "area_mm2": width * length,
            "oversize_area_mm2": width * length - raw_width_mm * raw_length_mm,
            "rotated_standard": False,
            "source": "snap_to_50mm_grid",
            "commercial_grid_increment_mm": snapped["commercial_grid_increment_mm"],
        }
    )


def snap_raw_dimensions_to_grid(
    raw_width_mm: float,
    raw_length_mm: float,
    calibration: dict[str, Any],
) -> dict[str, Any]:
    rules = calibration.get("moldbase_selector_rules", {})
    increment = int(rules.get("commercial_grid_increment_mm", 50))
    minimum = int(rules.get("minimum_commercial_dimension_mm", 150))
    return {
        "width_mm": snap_to_commercial_dimension(raw_width_mm, increment=increment, minimum=minimum),
        "length_mm": snap_to_commercial_dimension(raw_length_mm, increment=increment, minimum=minimum),
        "commercial_grid_increment_mm": increment,
        "minimum_commercial_dimension_mm": minimum,
    }


def snap_to_commercial_dimension(value_mm: float, *, increment: int = 50, minimum: int = 150) -> int:
    return max(minimum, int(ceil(value_mm / increment) * increment))


def _rounded_selection(selection: dict[str, Any]) -> dict[str, Any]:
    return {
        **selection,
        "width_mm": int(selection["width_mm"]),
        "length_mm": int(selection["length_mm"]),
        "area_mm2": round(float(selection["area_mm2"]), 4),
        "oversize_area_mm2": round(float(selection["oversize_area_mm2"]), 4),
    }
