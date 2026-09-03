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
    pagamento: {"pix_chave", "pix_tipo", "favorecido", "contato_nome", "contato_email",
                "contato_whatsapp" (dígitos p/ wa.me), "contato_whatsapp_fmt"} — dados p/ pagamento.
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

    verde = colors.HexColor("#2f6f5e")   # acento sóbrio (paga)
    venc_bg = colors.HexColor("#fbeeee")  # vermelho MUITO suave (só vencida)
    venc_fg = colors.HexColor("#a2585e")

    el = []
    if os.path.exists(_LOGO_PATH):
        try:
            logo = Image(_LOGO_PATH, width=48 * mm, height=24 * mm, kind="proportional")
            logo.hAlign = "CENTER"
            el.append(logo)
            el.append(Spacer(1, 0.5 * cm))
        except Exception:
            pass
    # Sem repetir nome/CNPJ do escritório — a logo acima já identifica.
    el.append(Paragraph("LEMBRETE", ParagraphStyle(
        "t", fontName="Helvetica-Bold", fontSize=13, alignment=TA_CENTER,
        textColor=colors.HexColor("#374151"), spaceAfter=2)))
    el.append(Spacer(1, 0.4 * cm))

    el.append(Paragraph(f"<b>Cliente:</b> {cliente_nome}", label))
    el.append(Paragraph(f"<b>Referente a:</b> {descricao}", label))
    el.append(Paragraph(f"<b>Data:</b> {_fmt_data(date.today())}", label))
    el.append(Spacer(1, 0.4 * cm))

    # Tabela de parcelas
    dados = [["#", "Vencimento", "Valor", "Situação"]]
    for p in parcelas:
        sit = "Paga" if p.get("status") == "pago" else ("Vencida" if p.get("atrasada") else "A vencer")
        dados.append([str(p.get("numero", "")), _fmt_data(p.get("vencimento")), _brl(p.get("valor", 0)), sit])
    tab = Table(dados, colWidths=[1.2 * cm, 4 * cm, 4 * cm, 4 * cm])
    estilo = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9.5),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (2, 0), (3, -1), "CENTER"),
        ("ALIGN", (0, 0), (1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    # Vermelho suave só nas parcelas JÁ vencidas (nunca nas a vencer).
    for i, p in enumerate(parcelas, start=1):
        if p.get("status") != "pago" and p.get("atrasada"):
            estilo.append(("BACKGROUND", (0, i), (-1, i), venc_bg))
            estilo.append(("TEXTCOLOR", (3, i), (3, i), venc_fg))
            estilo.append(("FONT", (3, i), (3, i), "Helvetica-Bold", 9.5))
        elif p.get("status") == "pago":
            estilo.append(("TEXTCOLOR", (3, i), (3, i), verde))
    tab.setStyle(TableStyle(estilo))
    el.append(tab)
    el.append(Spacer(1, 0.5 * cm))

    n_pend = sum(1 for p in parcelas if p.get("status") != "pago")
    el.append(Paragraph(
        f"<b>Saldo a pagar:</b> {_brl(saldo)}"
        + (f" — em {n_pend} parcela(s)" if n_pend > 1 else ""), body))
    el.append(Spacer(1, 0.45 * cm))

    # ── Como pagar (caixa arredondada) ──────────────────────────────────────
    tem_contato = pagamento and (
        pagamento.get("contato_nome") or pagamento.get("contato_email") or pagamento.get("contato_whatsapp")
    )
    if pagamento and (pagamento.get("pix_chave") or tem_contato):
        cont = [Paragraph("Como pagar", ParagraphStyle(
            "hp", fontName="Helvetica-Bold", fontSize=10.5, textColor=colors.HexColor("#374151"), spaceAfter=5))]
        if pagamento.get("pix_chave"):
            tipo = pagamento.get("pix_tipo")
            cont.append(Paragraph(f"<b>PIX{(' (' + tipo + ')') if tipo else ''}:</b> {pagamento['pix_chave']}", body))
        if pagamento.get("favorecido"):
            cont.append(Paragraph(f"<b>Favorecido:</b> {pagamento['favorecido']}", body))
        if tem_contato:
            cont.append(Paragraph("<b>Contato:</b>", body))
            if pagamento.get("contato_nome"):
                cont.append(Paragraph(pagamento["contato_nome"], body))
            if pagamento.get("contato_email"):
                cont.append(Paragraph(pagamento["contato_email"], body))
            if pagamento.get("contato_whatsapp"):
                wa_url = f"https://wa.me/{pagamento['contato_whatsapp']}"
                wa_disp = pagamento.get("contato_whatsapp_fmt") or pagamento["contato_whatsapp"]
                cont.append(Paragraph(f'WhatsApp: <a href="{wa_url}" color="#2563eb">{wa_disp}</a>', body))
        caixa = Table([[cont]], colWidths=[doc.width])
        caixa.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#d8d8d8")),
            ("ROUNDEDCORNERS", [8, 8, 8, 8]),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafafa")),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        el.append(caixa)
        el.append(Spacer(1, 0.4 * cm))

    el.append(Paragraph(
        "Se o pagamento já tiver sido feito, é só desconsiderar — e, se puder, nos avise. Obrigado!",
        ParagraphStyle("f", parent=body, textColor=colors.HexColor("#6b7280"), fontSize=9.5)))

    doc.build(el)
    return buf.getvalue()
