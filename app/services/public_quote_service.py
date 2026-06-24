import json
import re
import smtplib
import textwrap
import unicodedata
from datetime import date, datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.settings import settings
from app.pricing.mold_pricing_engine import calculate_mold_pricing_estimate
from app.schemas.mold_quote_schema import MoldPricingEstimate
from app.schemas.public_quote_schema import PublicQuoteRequest, PublicQuoteResponse


PUBLIC_QUOTE_STORAGE = Path(__file__).resolve().parents[2] / "storage" / "public_quotes"


def create_public_quote(payload: PublicQuoteRequest) -> PublicQuoteResponse:
    estimate = calculate_mold_pricing_estimate(payload.analysis, payload.technical_input)
    quote_id = str(uuid4())
    commercial = estimate.commercial
    industrial_cost = float(commercial.get("cpv_total_brl") or 0)
    floor = industrial_cost * 1.10
    ceiling = industrial_cost * 1.20
    scale = str(estimate.steel_package.get("mold_scale", "medium_mold"))
    base_days = {"small_mold": 45, "medium_mold": 65, "large_mold": 90}.get(scale, 65)
    movement_days = min(payload.technical_input.number_of_movements * 3, 24)
    hot_runner_days = 8 if payload.technical_input.injection_type == "hot_runner" else 0
    lead_min = base_days + movement_days + hot_runner_days
    lead_max = int(round(lead_min * 1.25))
    construction = payload.technical_input.mold_construction_type or "monobloco"
    estimated_mold_type = {
        "monobloco": "Molde monobloco",
        "insertado_posticado": "Molde insertado / posticado",
        "hibrido": "Molde hibrido",
    }.get(construction, "Molde parametrico")
    internal_confidence = str(estimate.confidence.get("overall_level", "medium"))
    confidence_level = {
        "high": "alta",
        "medium": "media",
        "low": "baixa",
        "mandatory_review": "revisao_obrigatoria",
    }.get(internal_confidence, "media")

    folder = PUBLIC_QUOTE_STORAGE / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    pdf_filename = _quote_pdf_filename(payload)
    pdf_bytes = _build_quote_pdf(payload, estimate, quote_id)
    pdf_path = folder / f"{quote_id}-{_safe_filename(pdf_filename)}"
    pdf_path.write_bytes(pdf_bytes)
    email_delivery = _send_quote_email(
        payload=payload,
        quote_id=quote_id,
        estimate=estimate,
        pdf_bytes=pdf_bytes,
        pdf_filename=pdf_filename,
    )

    record = {
        "quote_id": quote_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contact": payload.contact.model_dump(mode="json"),
        "estimated_annual_volume": payload.estimated_annual_volume,
        "analysis": payload.analysis,
        "technical_input": payload.technical_input.model_dump(mode="json"),
        "internal_estimate": estimate.model_dump(mode="json"),
        "pdf_filename": pdf_filename,
        "pdf_path": str(pdf_path),
        "email_delivery": email_delivery,
        "status": "awaiting_technical_review",
    }
    (folder / f"{quote_id}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    return PublicQuoteResponse(
        quote_id=quote_id,
        status="awaiting_technical_review",
        investment_range_brl={"minimum": round(min(floor, ceiling), 2), "maximum": round(max(floor, ceiling), 2)},
        estimated_lead_time_days={"minimum": lead_min, "maximum": lead_max},
        cavities_considered=payload.technical_input.cavity_count,
        injection_system_considered=payload.technical_input.injection_type,
        estimated_mold_type=estimated_mold_type,
        confidence_level=confidence_level,
        email_sent=bool(email_delivery.get("sent")),
        email_status=str(email_delivery.get("status") or email_delivery.get("reason") or ""),
        pdf_filename=pdf_filename,
        message="Estimativa preliminar gerada. A proposta final depende de revisao tecnica.",
    )


def _quote_pdf_filename(payload: PublicQuoteRequest) -> str:
    piece_name = str(payload.analysis.get("file_name") or payload.analysis.get("product_name") or "peca")
    piece_name = Path(piece_name).stem or "peca"
    return f"Orcamento com BOM - {piece_name}.pdf"


def _safe_filename(filename: str) -> str:
    normalized = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^A-Za-z0-9._ -]+", "", normalized).strip()
    return normalized[:160] or "orcamento-com-bom.pdf"


def _send_quote_email(
    *,
    payload: PublicQuoteRequest,
    quote_id: str,
    estimate: MoldPricingEstimate,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> dict[str, Any]:
    if not settings.smtp_host or not settings.smtp_from:
        return {"sent": False, "status": "smtp_not_configured", "reason": "missing_smtp_host_or_from"}
    if (settings.smtp_username and not settings.smtp_password) or (settings.smtp_password and not settings.smtp_username):
        return {"sent": False, "status": "smtp_not_configured", "reason": "missing_smtp_username_or_password"}

    subject = f"Orcamento foi gerado - {payload.contact.company} | {payload.contact.name}"
    body = _email_body(payload, estimate, quote_id)
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = settings.quote_email_to
    message["Subject"] = subject
    message.set_content(body)
    message.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=pdf_filename,
    )

    try:
        smtp_class = smtplib.SMTP_SSL if settings.smtp_use_ssl else smtplib.SMTP
        with smtp_class(settings.smtp_host, settings.smtp_port, timeout=25) as smtp:
            if not settings.smtp_use_ssl and settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except Exception as exc:  # pragma: no cover - depends on external SMTP.
        return {"sent": False, "status": "smtp_error", "reason": str(exc)[:300]}
    return {"sent": True, "status": "sent", "to": settings.quote_email_to}


def _email_body(payload: PublicQuoteRequest, estimate: MoldPricingEstimate, quote_id: str) -> str:
    commercial = estimate.commercial
    industrial_cost = float(commercial.get("cpv_total_brl") or 0)
    capex_min = industrial_cost * 1.10
    capex_max = industrial_cost * 1.20
    file_name = str(payload.analysis.get("file_name") or "arquivo STEP")
    return "\n".join(
        [
            "Orcamento foi gerado pelo modulo publico MOLDE PRO.",
            "",
            f"Protocolo: {quote_id}",
            f"Arquivo: {file_name}",
            f"Empresa: {payload.contact.company}",
            f"Contato: {payload.contact.name}",
            f"E-mail: {payload.contact.email}",
            f"Telefone: {payload.contact.whatsapp}",
            f"CAPEX preliminar: {_money(capex_min)} a {_money(capex_max)}",
            "",
            "O PDF anexo contem BOM, horas estimadas e custos tecnicos para revisao interna.",
            "",
            f"Observacoes: {payload.contact.notes or '-'}",
        ]
    )


def _build_quote_pdf(payload: PublicQuoteRequest, estimate: MoldPricingEstimate, quote_id: str) -> bytes:
    lines = _quote_pdf_lines(payload, estimate, quote_id)
    pages: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        wrapped = textwrap.wrap(str(line), width=108, replace_whitespace=False) or [""]
        for wrapped_line in wrapped:
            current.append(wrapped_line)
            if len(current) >= 55:
                pages.append(current)
                current = []
    if current:
        pages.append(current)
    return _simple_pdf(pages)


def _quote_pdf_lines(payload: PublicQuoteRequest, estimate: MoldPricingEstimate, quote_id: str) -> list[str]:
    technical = estimate.technical_breakdown or {}
    material_breakdown = technical.get("material_breakdown", {})
    components = technical.get("components", {})
    fabricated = list(components.get("fabricated", []))
    material_items = list(material_breakdown.get("steel_component_breakdown", []))
    cnc_hours = _aggregate_cnc_hours(technical.get("mrr_application", []), estimate)
    commercial = estimate.commercial
    industrial_cost = float(commercial.get("cpv_total_brl") or 0)
    capex_min = industrial_cost * 1.10
    capex_max = industrial_cost * 1.20
    step_name = str(payload.analysis.get("file_name") or "arquivo STEP")
    hot_runner = estimate.hot_runner
    edm = estimate.edm
    treatments = estimate.treatments
    bench = estimate.bench_assembly
    tryout = estimate.tryout
    hardware = estimate.hardware_components
    material_costs = estimate.material_costs
    electrode_fab_cost = max(
        float(edm.get("edm_total_cost_brl", 0.0))
        - float(edm.get("eletroerosao_edm_cost_brl", 0.0))
        - float(edm.get("eletroerosao_wire_edm_cost_brl", 0.0))
        - float(edm.get("electrode_material_cost_brl", 0.0)),
        0.0,
    )

    lines = [
        "ORCAMENTO COM BOM - MOLDSIA",
        f"Protocolo: {quote_id}",
        f"Gerado em: {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}",
        "",
        "Dados do contato",
        f"Empresa: {payload.contact.company}",
        f"Contato: {payload.contact.name}",
        f"E-mail: {payload.contact.email}",
        f"Telefone: {payload.contact.whatsapp}",
        f"Observacoes: {payload.contact.notes or '-'}",
        "",
        "Resumo da peca e premissas",
        f"Arquivo: {step_name}",
        f"Cavidades: {payload.technical_input.cavity_count}",
        f"Material plastico: {payload.technical_input.plastic_material}",
        f"Sistema de injecao: {payload.technical_input.injection_type}",
        f"Tipo construtivo: {payload.technical_input.mold_construction_type or payload.technical_input.cavity_type}",
        f"CAPEX preliminar: {_money(capex_min)} a {_money(capex_max)}",
        "",
        "Horas estimadas por centro/operacao",
    ]
    for label in [
        "Desbaste 2,5 eixos",
        "Desbaste 3 eixos",
        "Acabamento",
        "Torneamento",
        "Furacao",
        "Retifica",
        "Bancada",
        "Setups",
        "Outras horas CNC",
    ]:
        lines.append(f"- {label}: {_num(cnc_hours.get(label, 0.0))} h")
    lines.extend(
        [
            f"- EDM: {_num(float(edm.get('eletroerosao_edm_hours', 0.0)))} h",
            f"- Wire EDM: {_num(float(edm.get('eletroerosao_wire_edm_hours', 0.0)))} h",
            f"- Fabricacao de eletrodos: {_num(float(edm.get('electrode_machining_hours', 0.0)))} h",
            "",
            "Custos tecnicos principais",
            f"Materia-prima / aco: {_money(material_costs.get('materia_prima_aco_brl', 0.0))}",
            f"Porta-molde: {_money(material_costs.get('porta_molde_brl', 0.0))}",
            f"Insertos: {_money(material_costs.get('insertos_brl', 0.0))}",
            f"Componentes normalizados: {_money(hardware.get('total_standard_components_cost_brl', 0.0))}",
            f"Itens perifericos: {_money(hardware.get('total_peripherals_cost_brl', 0.0))}",
            f"Camara quente: {_money(hot_runner.get('total_hot_runner_cost_brl', 0.0))}",
            f"EDM: {_money(edm.get('eletroerosao_edm_cost_brl', 0.0))}",
            f"Wire EDM: {_money(edm.get('eletroerosao_wire_edm_cost_brl', 0.0))}",
            f"Fabricacao de eletrodos: {_money(electrode_fab_cost)}",
            f"Material dos eletrodos: {_money(edm.get('electrode_material_cost_brl', 0.0))}",
            f"Polimento: {_money(treatments.get('mirror_polishing_cost_brl', 0.0))}",
            f"Tratamento termico: {_money(treatments.get('heat_treatment_cost_brl', 0.0))}",
            f"Tratamento superficial: {_money(float(treatments.get('nitriding_cost_brl', 0.0)) + float(treatments.get('hard_chrome_cost_brl', 0.0)) + float(treatments.get('special_coating_cost_brl', 0.0)))}",
            f"Texturizacao: {_money(treatments.get('texture_cost_brl', 0.0))}",
            f"Montagem / bancada: {_money(bench.get('bench_assembly_cost_brl', 0.0))}",
            f"Try-out: {_money(tryout.get('tryout_cost_brl', 0.0))}",
            "",
            "BOM por componente fabricado",
        ]
    )
    component_map = {item.get("component_id"): item for item in material_items}
    for component in fabricated[:80]:
        material_item = component_map.get(component.get("component_id"), {})
        dims = component.get("dimensions_mm") or {}
        stock_dims = component.get("stock_dimensions_mm") or material_item.get("stock_dimensions_mm") or {}
        lines.append(
            " | ".join(
                [
                    str(component.get("component_type") or component.get("component_id") or "componente"),
                    f"role={component.get('component_role') or '-'}",
                    f"mat={component.get('material') or material_item.get('material') or '-'}",
                    f"dim={_num(dims.get('width'))}x{_num(dims.get('length'))}x{_num(dims.get('thickness'))} mm",
                    f"bruto={_num(stock_dims.get('width'))}x{_num(stock_dims.get('length'))}x{_num(stock_dims.get('thickness'))} mm",
                    f"kg={_num(component.get('estimated_weight_kg') or material_item.get('peso_kg'))}",
                    f"aco={_money(component.get('material_cost_applied_brl') or component.get('material_cost_brl') or material_item.get('material_cost_applied_brl') or 0)}",
                    f"CNC={_money(component.get('machining_cost_brl') or 0)}",
                    f"h={_num(component.get('machining_hours') or 0)}",
                ]
            )
        )

    lines.extend(["", "Operacoes CNC/MRR por componente"])
    for component in fabricated[:60]:
        operations = component.get("operations") or []
        if not operations:
            continue
        lines.append(str(component.get("component_type") or component.get("component_id") or "componente"))
        for operation in operations[:8]:
            lines.append(
                f"  - {operation.get('operation_type')}: {_num(operation.get('estimated_hours'))} h | {_money(operation.get('machining_cost_brl', 0.0))} | MRR {_num(operation.get('effective_mrr_cm3_min'))} cm3/min"
            )
    lines.extend(["", "Este documento e preliminar e deve ser revisado pela engenharia MOLDSIA antes da proposta final."])
    return lines


def _aggregate_cnc_hours(mrr_rows: list[dict[str, Any]], estimate: MoldPricingEstimate) -> dict[str, float]:
    totals = {
        "Desbaste 2,5 eixos": 0.0,
        "Desbaste 3 eixos": 0.0,
        "Acabamento": 0.0,
        "Torneamento": 0.0,
        "Furacao": 0.0,
        "Retifica": 0.0,
        "Bancada": float(estimate.bench_assembly.get("total_bench_hours", 0.0)),
        "Setups": 0.0,
        "Outras horas CNC": 0.0,
    }
    for row in mrr_rows:
        operation = str(row.get("operation_type", "")).lower()
        hours = float(row.get("estimated_hours", 0.0) or 0.0)
        if "setup" in operation:
            key = "Setups"
        elif "2.5" in operation or "25" in operation or "face" in operation or "esquad" in operation:
            key = "Desbaste 2,5 eixos"
        elif "3d" in operation or "3_d" in operation or "figura" in operation or "roughing_3" in operation:
            key = "Desbaste 3 eixos"
        elif "acab" in operation or "finish" in operation or "polish" in operation:
            key = "Acabamento"
        elif "torne" in operation or "turn" in operation:
            key = "Torneamento"
        elif "fura" in operation or "drill" in operation or "rosca" in operation or "thread" in operation:
            key = "Furacao"
        elif "retifica" in operation or "grind" in operation:
            key = "Retifica"
        else:
            key = "Outras horas CNC"
        totals[key] += hours
    if not any(totals[key] for key in totals if key not in {"Bancada"}):
        totals["Outras horas CNC"] = float(estimate.cnc_machining.get("total_cnc_hours", 0.0) or 0.0)
    return {key: round(value, 4) for key, value in totals.items()}


def _simple_pdf(pages: list[list[str]]) -> bytes:
    page_count = len(pages)
    font_object_number = 3 + page_count * 2
    objects: list[bytes] = []

    def add_object(content: str | bytes) -> int:
        payload = content if isinstance(content, bytes) else content.encode("latin-1", "replace")
        objects.append(payload)
        return len(objects)

    kids = " ".join(f"{3 + index * 2} 0 R" for index in range(page_count))
    add_object("<< /Type /Catalog /Pages 2 0 R >>")
    add_object(f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>")
    for index, page_lines in enumerate(pages):
        page_object_number = 3 + index * 2
        content_object_number = page_object_number + 1
        add_object(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_object_number} 0 R >> >> /Contents {content_object_number} 0 R >>"
        )
        stream = _pdf_page_stream(page_lines)
        add_object(f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream")
    add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_number, content in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_number} 0 obj\n".encode("latin-1"))
        output.extend(content)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin-1")
    )
    return bytes(output)


def _pdf_page_stream(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 9 Tf", "42 810 Td", "13 TL"]
    for line in lines:
        commands.append(f"({_pdf_escape(line)}) Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1", "replace")


def _pdf_escape(value: Any) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = text.encode("latin-1", "replace").decode("latin-1")
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _money(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def _num(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    if amount == int(amount):
        return str(int(amount))
    return f"{amount:.2f}".replace(".", ",")
