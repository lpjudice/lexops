"""
PDF de cobrança (aviso de vencimento) de um recebível parcelado.

Recebe dados já montados (desacoplado da ORM) e devolve os bytes do PDF, no
mesmo ferramental (reportlab/platypus) do contrato_pdf. Destaca a parcela em
cobrança e lista o cronograma para o cliente.
"""
import io
import os
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# Mesma logo usada no DANFSe (raiz do backend).
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "logo.png")


def _brl(v: float) -> str:
    s = f"{float(v):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_data(d) -> str:
    if not d:
        return "—"
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d[:10])
        except Exception:
            return d
    return d.strftime("%d/%m/%Y")


def gerar_pdf_cobranca(
    *,
    escritorio: dict,
    cliente_nome: str,
    descricao: str,
    parcelas: list[dict],
    total: float,
    saldo: float,
    destaque_numero: int | None = None,
    pagamento: dict | None = None,
) -> bytes:
    """
    escritorio: {"razao_social", "cnpj", "endereco"}
    parcelas: [{"numero", "valor", "vencimento", "status", "atrasada"(bool)}]
    pagamento: {"pix_chave", "pix_tipo", "favorecido", "contato"} — dados p/ pagamento.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
    )
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, alignment=TA_CENTER, spaceAfter=2)
    small = ParagraphStyle("small", fontName="Helvetica", fontSize=8.5, alignment=TA_CENTER, textColor=colors.HexColor("#555555"))
    label = ParagraphStyle("label", fontName="Helvetica", fontSize=10, alignment=TA_LEFT, spaceAfter=2)
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=10, alignment=TA_LEFT, spaceAfter=6, leading=14)

    el = []
    if os.path.exists(_LOGO_PATH):
        try:
            logo = Image(_LOGO_PATH, width=45 * mm, height=22 * mm, kind="proportional")
            logo.hAlign = "CENTER"
            el.append(logo)
            el.append(Spacer(1, 0.3 * cm))
        except Exception:
            pass
    el.append(Paragraph(escritorio.get("razao_social") or "Pimenta Júdice Advogados", h1))
    linha2 = " · ".join(x for x in [escritorio.get("cnpj"), escritorio.get("endereco")] if x)
    if linha2:
        el.append(Paragraph(linha2, small))
    el.append(Spacer(1, 0.5 * cm))
    el.append(Paragraph("AVISO DE COBRANÇA", ParagraphStyle("t", parent=h1, fontSize=13)))
    el.append(Spacer(1, 0.3 * cm))

    el.append(Paragraph(f"<b>Cliente:</b> {cliente_nome}", label))
    el.append(Paragraph(f"<b>Referente a:</b> {descricao}", label))
    el.append(Paragraph(f"<b>Emitido em:</b> {_fmt_data(date.today())}", label))
    el.append(Spacer(1, 0.4 * cm))

    # Tabela de parcelas
    dados = [["#", "Vencimento", "Valor", "Situação"]]
    for p in parcelas:
        sit = "PAGA" if p.get("status") == "pago" else ("VENCIDA" if p.get("atrasada") else "A vencer")
        dados.append([str(p.get("numero", "")), _fmt_data(p.get("vencimento")), _brl(p.get("valor", 0)), sit])
    tab = Table(dados, colWidths=[1.2 * cm, 4 * cm, 4 * cm, 4 * cm])
    estilo = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9.5),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (2, 0), (3, -1), "CENTER"),
        ("ALIGN", (0, 0), (1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    # Destaca a linha da parcela em cobrança
    if destaque_numero is not None:
        for i, p in enumerate(parcelas, start=1):
            if p.get("numero") == destaque_numero:
                estilo.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fee2e2")))
                estilo.append(("FONT", (0, i), (-1, i), "Helvetica-Bold", 9.5))
    tab.setStyle(TableStyle(estilo))
    el.append(tab)
    el.append(Spacer(1, 0.5 * cm))

    el.append(Paragraph(f"<b>Total do recebível:</b> {_brl(total)}", body))
    el.append(Paragraph(f"<b>Saldo em aberto:</b> {_brl(saldo)}", body))
    el.append(Spacer(1, 0.4 * cm))

    # ── Como pagar (PIX + contato) ──────────────────────────────────────────
    if pagamento and (pagamento.get("pix_chave") or pagamento.get("contato")):
        el.append(Paragraph("Como pagar", ParagraphStyle("hp", fontName="Helvetica-Bold", fontSize=11, spaceAfter=4)))
        if pagamento.get("pix_chave"):
            tipo = pagamento.get("pix_tipo")
            el.append(Paragraph(
                f"<b>PIX{(' (' + tipo + ')') if tipo else ''}:</b> {pagamento['pix_chave']}", body))
        if pagamento.get("favorecido"):
            el.append(Paragraph(f"<b>Favorecido:</b> {pagamento['favorecido']}", body))
        if pagamento.get("contato"):
            el.append(Paragraph(
                f"<b>Dúvidas e envio de comprovante:</b> {pagamento['contato']}", body))
        el.append(Spacer(1, 0.3 * cm))

    el.append(Paragraph(
        "Caso o pagamento já tenha sido realizado, por favor desconsidere este aviso.", body))

    doc.build(el)
    return buf.getvalue()
