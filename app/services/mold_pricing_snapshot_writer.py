import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.settings import settings
from app.schemas.mold_quote_schema import MoldPricingEstimate, MoldTechnicalInput
from app.utils.file_naming import build_log_filename, build_technical_log_filename


def save_mold_pricing_snapshot(
    *,
    analysis: dict[str, Any],
    technical_input: MoldTechnicalInput,
    estimate: MoldPricingEstimate,
    timestamp: str | None = None,
) -> dict[str, str]:
    created_at = datetime.now(timezone.utc)
    file_name = str(analysis.get("file_name") or "mold_quote.step")
    payload = {
        "timestamp": timestamp or created_at.isoformat(),
        "file_name": file_name,
        "technical_input": technical_input.model_dump(),
        "mold_pricing_estimate": estimate.model_dump(),
        "raw_analysis": analysis,
    }
    json_dir = settings.analysis_history_dir / "mold_pricing" / "json"
    txt_dir = settings.analysis_history_dir / "mold_pricing" / "txt"
    json_dir.mkdir(parents=True, exist_ok=True)
    txt_dir.mkdir(parents=True, exist_ok=True)

    json_path = json_dir / build_log_filename(file_name, ".json", created_at)
    txt_path = txt_dir / build_technical_log_filename(file_name, created_at)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(build_mold_pricing_log_text(payload), encoding="utf-8")
    return {
        "mold_pricing_json_snapshot": _relative_to_backend(json_path),
        "mold_pricing_txt_snapshot": _relative_to_backend(txt_path),
    }


def build_mold_pricing_log_text(payload: dict[str, Any]) -> str:
    estimate = payload["mold_pricing_estimate"]
    commercial = estimate["commercial"]
    cnc = estimate["cnc_machining"]
    dominance = estimate["cost_dominance"]
    steel = estimate["steel_package"]
    confidence = estimate["confidence"]
    return "\n".join(
        [
            "MOLDSIA PRO - LOG TECNICO DE COTACAO DE MOLDE",
            "================================================",
            "",
            "DADOS GERAIS",
            f"Arquivo: {payload['file_name']}",
            f"Timestamp: {payload['timestamp']}",
            "",
            "INPUT TECNICO",
            json.dumps(payload["technical_input"], ensure_ascii=False, indent=2),
            "",
            "PACOTE DE ACO",
            f"Escala: {steel.get('mold_scale')}",
            f"Volume total estimado: {steel.get('estimated_total_volume_cm3')} cm3",
            "Grupos:",
            _format_steel_groups(steel.get("groups", [])),
            "",
            "MRR FRACIONADO",
            f"Horas CNC totais: {cnc.get('total_cnc_hours')}",
            f"Custo CNC total: R$ {cnc.get('total_cnc_cost_brl')}",
            _format_mrr_groups(cnc.get("groups", [])),
            "",
            "EDM",
            json.dumps(estimate["edm"], ensure_ascii=False, indent=2),
            "",
            "CPV E COMERCIAL",
            f"CPV total: R$ {commercial.get('cpv_total_brl')}",
            f"Preco piso: R$ {commercial.get('price_floor_brl')}",
            f"Preco teto: R$ {commercial.get('price_ceiling_brl')}",
            "",
            "CUSTO DOMINANTE",
            f"Driver dominante: {dominance.get('dominant_cost_driver')}",
            json.dumps(dominance.get("top_cost_components", []), ensure_ascii=False, indent=2),
            "",
            "PREMISSAS",
            "\n".join(f"- {item}" for item in estimate.get("assumptions", [])),
            "",
            "CONFIANCA",
            json.dumps(confidence, ensure_ascii=False, indent=2),
            "",
            "RAW MOLD PRICING ESTIMATE",
            json.dumps(estimate, ensure_ascii=False, indent=2),
            "",
        ]
    )


def _format_steel_groups(groups: list[dict[str, Any]]) -> str:
    if not groups:
        return "- nenhum grupo registrado"
    return "\n".join(
        (
            f"- {group.get('group')}: {group.get('material')} | "
            f"{group.get('estimated_weight_kg')} kg | R$ {group.get('material_cost_brl')}"
        )
        for group in groups
    )


def _format_mrr_groups(groups: list[dict[str, Any]]) -> str:
    if not groups:
        return "- nenhum grupo registrado"
    return "\n".join(
        (
            f"- {group.get('group')}: {group.get('estimated_hours')} h | "
            f"{group.get('effective_mrr_cm3_hour')} cm3/h | "
            f"rota {group.get('machine_route')}"
        )
        for group in groups
    )


def _relative_to_backend(path: Path) -> str:
    backend_root = Path(__file__).resolve().parents[2]
    return path.resolve().relative_to(backend_root).as_posix()

