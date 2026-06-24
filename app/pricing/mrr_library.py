from typing import Any


def lookup_mrr_entry(
    calibration: dict[str, Any],
    *,
    material: str,
    component_type: str,
    operation_type: str,
) -> dict[str, Any]:
    entries = calibration.get("mrr_library", [])
    exact = _find(entries, material, component_type, operation_type)
    if exact:
        return _normalize_entry({**exact, "lookup_level": "exact"}, operation_type)
    material_default = _find(entries, material, "default", operation_type)
    if material_default:
        return _normalize_entry({**material_default, "lookup_level": "material_operation_default"}, operation_type)
    component_default = _find(entries, "default", component_type, operation_type)
    if component_default:
        return _normalize_entry({**component_default, "lookup_level": "component_operation_default"}, operation_type)
    operation_default = _find(entries, "default", "default", operation_type)
    if operation_default:
        return _normalize_entry({**operation_default, "lookup_level": "operation_default"}, operation_type)
    return _normalize_entry({
        "material": "default",
        "component_type": "default",
        "operation_type": operation_type,
        "base_mrr_cm3_min": 1.0,
        "machine_factor": 0.7,
        "complexity_factor": 0.75,
        "finishing_factor": 0.85,
        "tolerance_factor": 0.85,
        "lookup_level": "emergency_fallback",
    }, operation_type)


def calculate_effective_mrr_cm3_min(
    calibration: dict[str, Any],
    *,
    material: str,
    component_type: str,
    operation_type: str,
    machine_id: str | None = None,
    extra_factors: dict[str, float] | None = None,
) -> dict[str, Any]:
    entry = lookup_mrr_entry(
        calibration,
        material=material,
        component_type=component_type,
        operation_type=operation_type,
    )
    machine_factor = _machine_factor(entry, machine_id)
    factors = {
        "machine_factor": machine_factor,
        "material_factor": material_machinability_factor(calibration, material),
        "complexity_factor": float(entry.get("complexity_factor", 1.0)),
        "finishing_factor": float(entry.get("finishing_factor", 1.0)),
        "tolerance_factor": float(entry.get("tolerance_factor", 1.0)),
    }
    for key, value in (extra_factors or {}).items():
        factors[key] = float(value)
    effective = float(entry["base_mrr_cm3_min"])
    for value in factors.values():
        effective *= value
    return {
        "mrr_entry": entry,
        "base_mrr_cm3_min": round(float(entry["base_mrr_cm3_min"]), 4),
        "effective_mrr_cm3_min": round(max(effective, 0.05), 4),
        "factors": {key: round(value, 4) for key, value in factors.items()},
        "unit": "cm3/min",
        "formula": "base_mrr_cm3_min * product(factors)",
    }


def estimate_machining_time_from_mrr(
    *,
    removed_volume_cm3: float,
    effective_mrr_cm3_min: float,
) -> dict[str, float | str]:
    minutes = removed_volume_cm3 / effective_mrr_cm3_min if removed_volume_cm3 > 0 and effective_mrr_cm3_min > 0 else 0.0
    return {
        "machining_time_minutes": round(minutes, 4),
        "machining_time_hours": round(minutes / 60, 4),
        "formula": "removed_volume_cm3 / effective_mrr_cm3_min",
    }


def material_machinability_factor(calibration: dict[str, Any], material: str) -> float:
    material_record = calibration.get("steel_materials", {}).get(material, {})
    return float(material_record.get("machinability_factor", 1.0))


def _find(
    entries: list[dict[str, Any]],
    material: str,
    component_type: str,
    operation_type: str,
) -> dict[str, Any] | None:
    for entry in entries:
        entry_operation = entry.get("operation_type", entry.get("operation"))
        if (
            entry.get("material") == material
            and entry.get("component_type") == component_type
            and entry_operation == operation_type
        ):
            return entry
    return None


def _normalize_entry(entry: dict[str, Any], operation_type: str) -> dict[str, Any]:
    base = float(entry.get("base_mrr_cm3_min", entry.get("mrr_cm3_min", 1.0)))
    return {
        **entry,
        "operation_type": entry.get("operation_type", entry.get("operation", operation_type)),
        "operation": entry.get("operation", entry.get("operation_type", operation_type)),
        "base_mrr_cm3_min": base,
        "mrr_cm3_min": base,
    }


def _machine_factor(entry: dict[str, Any], machine_id: str | None) -> float:
    if machine_id:
        specific_key = f"machine_factor_{machine_id}"
        if specific_key in entry:
            return float(entry[specific_key])
    return float(entry.get("machine_factor", 1.0))
