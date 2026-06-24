from typing import Any


def _template(
    component_type: str,
    cnc_factor: float,
    edm_ratio: float,
    bench_hours: float,
    engineering_hours: float,
    tryout_factor: float,
    purchased_components: dict[str, float],
) -> dict[str, Any]:
    return {
        "component_type": component_type,
        "default_material": "steel_h13",
        "cnc_factor": cnc_factor,
        "edm_removed_volume_ratio": edm_ratio,
        "bench_hours_per_unit": bench_hours,
        "engineering_hours_per_unit": engineering_hours,
        "assembly_factor": 1.0 + bench_hours / 40,
        "tryout_factor": tryout_factor,
        "risk_factor": max(tryout_factor - 0.9, 0.1),
        "purchased_components": purchased_components,
    }


# Editable industrial defaults. Values are deliberately explicit so calibration can
# later move to the admin settings store without changing the pricing engine contract.
MOVEMENT_COST_TEMPLATES: dict[str, dict[str, Any]] = {
    "SIMPLE_SIDE_SLIDER": _template("gaveta", 1.00, 0.35, 5.0, 3.0, 1.05, {"guias_travas_gaveta": 1800}),
    "ANGLED_PIN_SLIDER": _template("gaveta", 1.12, 0.45, 7.0, 4.0, 1.12, {"pino_inclinado_guias": 2400}),
    "HYDRAULIC_SLIDER": _template("gaveta", 1.18, 0.40, 9.0, 5.0, 1.18, {"cilindro_hidraulico_conexoes": 5200}),
    "SPECIAL_MECHANICAL_SLIDER": _template("gaveta", 1.28, 0.55, 10.0, 6.0, 1.22, {"acionamento_mecanico_especial": 4200}),
    "COLLAPSIBLE_CORE": _template("macho_movel", 1.65, 0.85, 18.0, 12.0, 1.45, {"sistema_colapsivel": 14500}),
    "NEGATIVE_JAW": _template("gaveta", 1.35, 0.75, 12.0, 7.0, 1.30, {"guias_mandibula": 4800}),
    "ROTARY_CORE": _template("macho_movel", 1.48, 0.65, 15.0, 10.0, 1.38, {"acionamento_macho_rotativo": 9500}),
    "FORCED_EJECTION": _template("lifter", 1.05, 0.20, 9.0, 4.0, 1.32, {"componentes_extracao_forcada": 2200}),
    "LIFTER": _template("lifter", 1.20, 0.55, 8.0, 5.0, 1.18, {"guias_lifter": 2600}),
    "MOVABLE_CORE": _template("macho_movel", 1.30, 0.60, 11.0, 7.0, 1.25, {"guias_macho_movel": 3900}),
    "MOVABLE_INSERT": _template("postico", 1.18, 0.45, 7.0, 5.0, 1.15, {"retencao_postico_movel": 2100}),
    "RETRACTABLE_CORE": _template("macho_movel", 1.42, 0.65, 13.0, 8.0, 1.34, {"acionamento_nucleo_retratil": 7200}),
    "CUSTOM": _template("gaveta", 1.40, 0.65, 14.0, 9.0, 1.35, {"componentes_movimento_customizado": 6500}),
    "UNKNOWN": _template("gaveta", 1.32, 0.55, 11.0, 7.0, 1.28, {"provisao_movimento_a_definir": 4800}),
}


def movement_template(movement_type: str) -> dict[str, Any]:
    return MOVEMENT_COST_TEMPLATES.get(movement_type, MOVEMENT_COST_TEMPLATES["CUSTOM"])


def movement_totals(technical_input: Any) -> dict[str, float]:
    engineering_hours = 0.0
    bench_hours = 0.0
    tryout_shots = 0.0
    risk = 0.0
    for movement in getattr(technical_input, "special_movements", []):
        template = movement_template(str(movement.movement_type))
        quantity = max(int(movement.quantity), 1)
        complexity = {"LOW": 0.85, "MEDIUM": 1.0, "HIGH": 1.25, "CRITICAL": 1.55, "UNKNOWN": 1.12}.get(
            str(movement.complexity), 1.0
        )
        engineering_hours += float(template["engineering_hours_per_unit"]) * quantity * complexity
        bench_hours += float(template["bench_hours_per_unit"]) * quantity * complexity
        tryout_shots += 20 * float(template["tryout_factor"]) * quantity
        risk += float(template["risk_factor"]) * quantity
    return {
        "engineering_hours": engineering_hours,
        "bench_hours": bench_hours,
        "tryout_shots": tryout_shots,
        "risk": risk,
    }
