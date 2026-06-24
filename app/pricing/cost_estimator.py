from typing import Any


def build_service_costs(
    *,
    cnc: dict[str, Any],
    edm: dict[str, Any],
    engineering: dict[str, Any],
    treatments: dict[str, Any],
    bench: dict[str, Any],
    tryout: dict[str, Any],
) -> dict[str, float]:
    return {
        "cnc": float(cnc["total_cnc_cost_brl"]),
        "edm": float(edm["edm_total_cost_brl"]),
        "eletroerosao_edm": float(edm.get("eletroerosao_edm_cost_brl", edm.get("edm_total_cost_brl", 0.0))),
        "eletroerosao_wire_edm": float(edm.get("eletroerosao_wire_edm_cost_brl", 0.0)),
        "engineering": float(engineering["engineering_cost_brl"]),
        "treatments": float(treatments["total_treatments_cost_brl"]),
        "tratamento_termico": float(treatments["total_treatments_cost_brl"]),
        "polimento_molde": 0.0,
        "texturizacao": 0.0,
        "retifica": 0.0,
        "revestimento_coating": 0.0,
        "furacao_profunda": 0.0,
        "outros_servicos_tecnicos": 0.0,
        "bench_assembly": float(bench["bench_assembly_cost_brl"]),
        "tryout": float(tryout["tryout_cost_brl"]),
        "servicos_terceiros": 0.0,
    }


def build_industrial_cost_groups(
    *,
    material_costs: dict[str, Any],
    hardware_components: dict[str, Any],
    hot_runner: dict[str, Any],
    materials_sanity: dict[str, Any],
    service_costs: dict[str, float],
) -> dict[str, float]:
    return {
        "materia_prima_aco": float(material_costs.get("materia_prima_aco_brl", 0.0)),
        "porta_molde": float(material_costs.get("porta_molde_brl", 0.0)),
        "insertos": float(material_costs.get("insertos_brl", 0.0)),
        "componentes_normalizados": float(hardware_components.get("total_standard_components_cost_brl", 0.0)),
        "perifericos": float(hardware_components.get("total_peripherals_cost_brl", 0.0)),
        "camara_quente": float(hot_runner.get("total_hot_runner_cost_brl", 0.0)),
        "ajuste_piso_materiais": float(materials_sanity.get("materials_floor_adjustment_brl", 0.0)),
        **service_costs,
    }
