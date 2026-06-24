import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.settings import settings
from app.schemas.analysis_schema import AnalysisResponse
from app.utils.file_naming import build_technical_log_filename


def build_analysis_log_text(analysis: AnalysisResponse, timestamp: str | None = None) -> str:
    created_at = timestamp or datetime.now(timezone.utc).isoformat()
    risk_flags = (
        "\n".join(f"- {flag}" for flag in analysis.manufacturing_risk.risk_flags)
        if analysis.manufacturing_risk.risk_flags
        else "- nenhuma flag registrada"
    )
    raw_response = json.dumps(analysis.model_dump(), ensure_ascii=False, indent=2)
    calculation_memory = analysis.pricing_estimate.calculation_memory or {}

    return "\n".join(
        [
            "MOLDSIA - LOG TÉCNICO DE ANÁLISE",
            "================================",
            "",
            "DADOS GERAIS",
            f"Request ID: {analysis.request_id}",
            f"Arquivo: {analysis.file_name}",
            f"Tempo de processamento: {analysis.processing_time_ms} ms",
            f"Exportado em: {created_at}",
            f"Versão backend: {settings.app_version}",
            "Origem do log: backend automático",
            f"SHA256: {analysis.metadata.file_hash_sha256}",
            f"Arquivo arquivado: {'sim' if analysis.upload_archive.stored else 'não'}",
            f"Caminho do arquivo arquivado: {analysis.upload_archive.archive_path}",
            "",
            "PRECHECK DO UPLOAD CAD",
            f"Tamanho do arquivo: {analysis.analysis_precheck.file_size_mb} MB",
            f"Extensão: {analysis.analysis_precheck.extension}",
            f"Entidades estimadas: {format_optional(analysis.analysis_precheck.estimated_entity_count)}",
            f"Risco de processamento: {analysis.analysis_precheck.estimated_processing_risk}",
            f"Modo recomendado: {analysis.analysis_precheck.recommended_analysis_mode}",
            "",
            "DIAGNOSTICO IGES",
            format_iges_diagnostics(analysis.iges_diagnostics),
            "",
            "CONVERSAO CAD",
            format_conversion(analysis.conversion),
            "",
            "HEALING GEOMETRICO",
            format_healing_report(analysis.geometry_healing),
            "",
            "CONFIANCA GEOMETRICA",
            format_geometry_confidence(analysis.geometry_confidence),
            "",
            "GEOMETRIA",
            f"X: {analysis.geometry.xlen_mm} mm",
            f"Y: {analysis.geometry.ylen_mm} mm",
            f"Z: {analysis.geometry.zlen_mm} mm",
            f"Volume bounding box: {analysis.geometry.bounding_box_volume_mm3} mm³",
            f"Volume real: {analysis.geometry.real_volume_cm3} cm³",
            f"Volume real: {analysis.geometry.real_volume_mm3} mm³",
            f"Occupancy Ratio: {analysis.geometry.occupancy_ratio}",
            f"Sólidos: {analysis.geometry.solid_count}",
            f"Cascas: {analysis.geometry.shell_count}",
            f"Faces: {analysis.geometry.face_count}",
            f"É assembly: {'sim' if analysis.geometry.is_assembly else 'não'}",
            "",
            "MÉTRICAS DERIVADAS",
            f"Thinness Ratio: {analysis.derived_metrics.thinness_ratio}",
            f"Slenderness Ratio: {analysis.derived_metrics.slenderness_ratio}",
            f"Densidade de features por volume real: {analysis.derived_metrics.feature_density_by_volume}",
            f"Densidade de features por bounding box: {analysis.derived_metrics.feature_density_by_bbox}",
            f"Occupancy Extremity Score: {analysis.derived_metrics.occupancy_extremity_score}",
            f"Processing Complexity Signal: {analysis.derived_metrics.processing_complexity_signal}",
            f"Surface Complexity Signal: {analysis.derived_metrics.surface_complexity_signal}",
            "",
            "COMPLEXIDADE",
            f"Score: {analysis.complexity.complexity_score}",
            f"Nível: {analysis.complexity.complexity_level}",
            f"Topology Complexity Score: {analysis.complexity.topology_complexity_score}",
            "Breakdown:",
            f"- Ocupacao: {analysis.complexity.complexity_breakdown.occupancy_component}",
            f"- Topologia: {analysis.complexity.complexity_breakdown.topology_component}",
            f"- Superficies: {analysis.complexity.complexity_breakdown.surface_component}",
            f"- Shape recognition: {analysis.complexity.complexity_breakdown.shape_component}",
            f"- Processamento: {analysis.complexity.complexity_breakdown.processing_component}",
            "Threshold diagnostics:",
            format_list(analysis.complexity.threshold_diagnostics),
            "",
            "PERFIL GEOMÉTRICO",
            f"Forma principal: {analysis.shape_profile.primary_shape}",
            f"Forma secundária: {analysis.shape_profile.secondary_shape or 'nenhuma'}",
            "",
            "PERFIL FABRIL",
            f"Porte da peça: {analysis.manufacturing_profile.piece_size}",
            f"Perfil de usinagem: {analysis.manufacturing_profile.machining_profile}",
            f"Máquina estimada: {analysis.manufacturing_profile.estimated_machine_type}",
            f"Setup: {analysis.manufacturing_profile.setup_hours} h",
            f"Taxa máquina: R$ {analysis.manufacturing_profile.machine_rate_brl_hour}/h",
            "",
            "RISCO",
            f"Score: {analysis.manufacturing_risk.risk_score}",
            f"Nível: {analysis.manufacturing_risk.risk_level}",
            "Breakdown:",
            f"- Risco geométrico: {analysis.manufacturing_risk.risk_breakdown.geometric_risk}",
            f"- Risco de usinagem: {analysis.manufacturing_risk.risk_breakdown.machining_risk}",
            f"- Risco de fixação: {analysis.manufacturing_risk.risk_breakdown.fixturing_risk}",
            f"- Risco comercial: {analysis.manufacturing_risk.risk_breakdown.commercial_risk}",
            "Flags:",
            risk_flags,
            "",
            "RECOMENDAÇÃO DE ENGENHARIA",
            f"Requer revisão: {'sim' if analysis.review_recommendation.requires_engineering_review else 'não'}",
            f"Confiança: {analysis.review_recommendation.confidence}",
            "Motivos:",
            format_list(analysis.review_recommendation.reason),
            "",
            "ESTIMATIVA DE PRICING",
            f"Moeda: {analysis.pricing_estimate.currency}",
            f"Versão dos parâmetros: {analysis.pricing_estimate.parameters_version}",
            f"Material: {analysis.pricing_estimate.material.get('label')}",
            f"Modo de fornecimento: {analysis.pricing_estimate.material.get('material_supply_mode')}",
            f"Quantidade: {analysis.pricing_estimate.commercial.get('quantity')}",
            f"Volume de tarugo ajustado: {analysis.pricing_estimate.material.get('adjusted_stock_volume_cm3')} cm³",
            f"Volume removido: {analysis.pricing_estimate.material.get('removed_volume_cm3')} cm³",
            f"Peso estimado do material: {analysis.pricing_estimate.material.get('material_weight_kg')} kg",
            f"Material efficiency factor: {analysis.pricing_estimate.material.get('material_efficiency_factor')}",
            f"Custo real material: R$ {analysis.pricing_estimate.material.get('real_material_cost_brl')}",
            f"Custo material: R$ {analysis.pricing_estimate.material.get('material_cost_brl')}",
            f"MRR efetivo: {analysis.pricing_estimate.machining.get('removal_rate_cm3_hour')} cm³/h",
            f"Horas máquina estimadas: {analysis.pricing_estimate.machining.get('estimated_machine_hours')}",
            f"CPV total: R$ {analysis.pricing_estimate.commercial.get('total_cpv_brl')}",
            f"CPV unitário: R$ {analysis.pricing_estimate.commercial.get('unit_cpv_brl')}",
            f"Preço piso: R$ {analysis.pricing_estimate.commercial.get('price_floor_brl')}",
            f"Preço teto: R$ {analysis.pricing_estimate.commercial.get('price_ceiling_brl')}",
            f"Pedido mínimo aplicado: {analysis.pricing_estimate.commercial.get('minimum_order_value_applied')}",
            f"Confiança de pricing: {analysis.pricing_estimate.confidence.get('pricing_confidence')}",
            "",
            "PARAMETRIZAÇÃO USADA",
            f"Fonte: {analysis.calibration.parameters_source}",
            f"Atualizada em: {analysis.calibration.parameters_updated_at or 'defaults não persistidos'}",
            f"Minimum order value: R$ {analysis.pricing_parameters_used.minimum_order_value_brl}",
            f"Stock allowance default: {analysis.pricing_parameters_used.default_stock_allowance_mm} mm",
            f"Supply mode default: {analysis.pricing_parameters_used.default_supply_mode}",
            "",
            "MEMÓRIA DE CÁLCULO DA ESTIMATIVA COMERCIAL",
            format_calculation_memory(calculation_memory),
            "",
            "MOLDE PRO - ESTIMATIVA MODULAR",
            format_mold_pricing_estimate(analysis.mold_pricing_estimate),
            "",
            "BENCHMARK",
            f"Horas estimadas: {format_optional(analysis.benchmark.estimated_hours)}",
            f"Horas reais: {format_optional(analysis.benchmark.real_hours)}",
            f"Custo estimado: {format_optional(analysis.benchmark.estimated_cost)}",
            f"Custo real: {format_optional(analysis.benchmark.real_cost)}",
            f"Orçamento ganho: {format_optional(analysis.benchmark.won_quote)}",
            "",
            "METADATA",
            f"Engine: {analysis.metadata.engine}",
            f"Kernel: {analysis.metadata.kernel}",
            f"Versão: {analysis.metadata.version}",
            f"Heuristics Version: {analysis.metadata.heuristics_version}",
            f"File SHA256: {analysis.metadata.file_hash_sha256}",
            "",
            "RAW RESPONSE",
            raw_response,
            "",
        ]
    )


def save_analysis_log_txt(
    analysis: AnalysisResponse,
    base_dir: Path | None = None,
    timestamp: str | None = None,
) -> Path:
    output_dir = base_dir or settings.analysis_history_dir / "txt"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / build_technical_log_filename(analysis.file_name)
    output_path.write_text(
        build_analysis_log_text(analysis, timestamp=timestamp),
        encoding="utf-8",
    )
    return output_path


def format_optional(value: object) -> str:
    if value is None:
        return "indisponível"

    return str(value)


def format_list(values: list[str]) -> str:
    if not values:
        return "- nenhum motivo registrado"

    return "\n".join(f"- {value}" for value in values)


def format_iges_diagnostics(diagnostics: object) -> str:
    if diagnostics is None:
        return "Nao aplicavel para arquivo STEP/STP."

    return "\n".join(
        [
            f"Possui B-Rep solido: {'sim' if diagnostics.has_brep_solid else 'nao'}",
            f"Possui shells: {'sim' if diagnostics.has_shells else 'nao'}",
            f"Entidades Face (510): {diagnostics.face_entity_count}",
            f"Trimmed Surface (144): {diagnostics.trimmed_surface_count}",
            f"Rational B-Spline Surface (128): {diagnostics.bspline_surface_count}",
            f"Rational B-Spline Curve (126): {diagnostics.bspline_curve_count}",
            f"Diagnostico: {diagnostics.diagnosis}",
        ]
    )


def format_conversion(conversion: object) -> str:
    if conversion is None:
        return "Nao aplicavel para arquivo STEP/STP."

    return "\n".join(
        [
            f"Tentada: {'sim' if conversion.attempted else 'nao'}",
            f"Origem: {conversion.source_format}",
            f"Destino: {conversion.target_format}",
            f"Sucesso: {'sim' if conversion.success else 'nao'}",
            f"Caminho STEP convertido: {conversion.converted_file_path or 'indisponivel'}",
            f"Diagnostico: {conversion.diagnosis or 'indisponivel'}",
            f"Erro: {conversion.error or 'nenhum'}",
        ]
    )


def format_healing_report(report: object) -> str:
    if report is None:
        return "Nao aplicado."

    return "\n".join(
        [
            f"Tentado: {'sim' if report.attempted else 'nao'}",
            f"Sucesso: {'sim' if report.success else 'nao'}",
            f"Nivel: {report.healing_level}",
            f"Gaps fechados: {report.gaps_closed_count}",
            f"Distancia total costurada: {report.total_gap_distance_mm} mm",
            f"Maior gap: {report.max_gap_mm} mm",
            f"Ratio edges modificadas: {report.modified_edges_ratio}",
            f"Ratio faces modificadas: {report.modified_faces_ratio}",
            f"Shells antes/depois: {report.shells_before_healing}/{report.shells_after_healing}",
            f"Solidos antes/depois: {report.solids_before_healing}/{report.solids_after_healing}",
            f"Tempo healing: {report.healing_processing_time_ms} ms",
            f"Erro: {report.error or 'nenhum'}",
        ]
    )


def format_geometry_confidence(confidence: object) -> str:
    return "\n".join(
        [
            f"Score: {confidence.score}",
            f"Nivel: {confidence.level}",
            f"Impacto healing: {confidence.healing_impact}",
            f"Alerta comercial: {'sim' if confidence.commercial_warning else 'nao'}",
        ]
    )


def format_calculation_memory(memory: dict) -> str:
    if not memory:
        return "indisponível"

    lines: list[str] = []
    section_titles = {
        "inputs": "ENTRADAS DO CÁLCULO",
        "volumes": "VOLUMES",
        "material": "MATERIAL",
        "machining": "USINAGEM",
        "setup": "SETUP",
        "cpv": "CPV",
        "sale": "VENDA",
    }
    for section_key, title in section_titles.items():
        section = memory.get(section_key, {})
        lines.append(title)
        for field_name, payload in section.items():
            value = payload.get("value")
            unit = payload.get("unit")
            formula = payload.get("formula")
            line = f"- {field_name}: {value} [{unit}]"
            if formula:
                line += f" | fórmula: {formula}"
            lines.append(line)
        lines.append("")

    diagnostics = memory.get("diagnostics", [])
    lines.append("DIAGNOSTICS")
    if diagnostics:
        lines.extend(f"- {item.get('level')}: {item.get('code')} - {item.get('message')}" for item in diagnostics)
    else:
        lines.append("- nenhum alerta diagnóstico")

    return "\n".join(lines)


def format_mold_pricing_estimate(estimate: object) -> str:
    if estimate is None:
        return "Nao calculado para esta analise."

    commercial = estimate.commercial
    dominance = estimate.cost_dominance
    confidence = estimate.confidence
    cnc = estimate.cnc_machining
    steel = estimate.steel_package
    return "\n".join(
        [
            f"CPV total: R$ {commercial.get('cpv_total_brl')}",
            f"Preco piso: R$ {commercial.get('price_floor_brl')}",
            f"Preco teto: R$ {commercial.get('price_ceiling_brl')}",
            f"Margem piso/teto: {commercial.get('margin_range')}",
            f"Pacote de aco - escala: {steel.get('mold_scale')}",
            f"Pacote de aco - volume total estimado: {steel.get('estimated_total_volume_cm3')} cm3",
            f"CNC total: {cnc.get('total_cnc_hours')} h",
            f"Custo CNC: R$ {cnc.get('total_cnc_cost_brl')}",
            f"Driver dominante: {dominance.get('dominant_cost_driver')}",
            f"Confianca: {confidence.get('overall_level')} ({confidence.get('overall_score')})",
            "Premissas:",
            format_list(estimate.assumptions),
            "Top cost components:",
            "\n".join(
                f"- {item.get('component')}: {item.get('percent')}% | R$ {item.get('cost_brl')}"
                for item in dominance.get("top_cost_components", [])
            )
            or "- nenhum componente registrado",
            "MRR por grupo:",
            "\n".join(
                (
                    f"- {group.get('group')}: {group.get('estimated_hours')} h | "
                    f"{group.get('effective_mrr_cm3_hour')} cm3/h | R$ {group.get('machining_cost_brl')}"
                )
                for group in cnc.get("groups", [])
            )
            or "- nenhum grupo CNC registrado",
        ]
    )
