from typing import Any


def analyze_cost_dominance(costs: dict[str, float]) -> dict[str, Any]:
    total = sum(max(value, 0.0) for value in costs.values())
    if total <= 0:
        return {
            "dominant_cost_driver": "unknown",
            "top_cost_components": [],
        }
    components = [
        {"component": key, "percent": round((value / total) * 100, 2), "cost_brl": round(value, 2)}
        for key, value in costs.items()
    ]
    components.sort(key=lambda item: item["percent"], reverse=True)
    return {
        "dominant_cost_driver": components[0]["component"],
        "top_cost_components": components[:5],
    }

