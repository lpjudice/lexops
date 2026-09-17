"""
Gerador de Instrumento de Procuração em PDF.
Mesmo padrão visual do Contrato de Honorários (contrato_pdf.py).

Partes customizáveis:
  - Outorgante (nome, qualificação, CPF/CNPJ, endereço, email) — o cliente
  - Outorgado(s) — lista dinâmica de advogado(s): nome, OAB, CPF
  - Endereço profissional (do escritório) dos outorgados — pré-preenchido, editável
  - Finalidade específica (texto livre, opcional) — some à cláusula padrão ad judicia
  - Data da procuração
"""

import io
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)

_LOGO_PATH = Path(__file__).parent.parent.parent / "logo.png"

DARK = colors.HexColor("#1d1e20")
TEAL = colors.HexColor("#00b090")
MID_GRAY = colors.HexColor("#6b7280")

# Cláusula padrão "ad judicia et extra" — formulação genérica amplamente usada em
# procurações no Brasil (poderes gerais para o foro em geral).
PODERES_AD_JUDICIA = (
    "Pelo presente instrumento particular de mandato, o(a) OUTORGANTE nomeia e constitui "
    "seu(s) bastante procurador(es) o(s) OUTORGADO(S) acima qualificado(s), a quem confere "
    "amplos, gerais e ilimitados poderes para o foro em geral, com a cláusula \"ad judicia "
    "et extra\", em qualquer Juízo, Instância ou Tribunal, podendo propor contra quem de "
    "direito as ações competentes e defendê-lo(a) nas contrárias, seguindo umas e outras, "
    "até final decisão, usando os recursos legais e acompanhando-os, conferindo-lhe, ainda, "
    "poderes especiais para confessar, desistir, transigir, firmar compromissos ou acordos, "
    "receber e dar quitação, agindo em conjunto ou separadamente, podendo ainda "
    "substabelecer esta a outrem, com ou sem reserva de iguais poderes, dando tudo por bom, "
    "firme e valioso."
)

CLAUSULA_ASSINATURA = (
    "Por estarem assim justos, o(a) OUTORGANTE assina o presente instrumento, via "
    "assinatura eletrônica, nos moldes do art. 10 da MP 2.200/01 em vigor no Brasil, o "
    "\"De Acordo\" com a presente PROCURAÇÃO, redigida em {data_procuracao}."
)


_MESES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _data_por_extenso(d: date) -> str:
    """'%d de %B de %Y' depende do locale do processo (pode sair em inglês no
    servidor) — usa nomes de mês fixos em português para não depender disso."""
    return f"{d.day:02d} de {_MESES_PT[d.month - 1]} de {d.year}"


def _estilos():
    return {
        "titulo": ParagraphStyle(
            "titulo", fontName="Helvetica-Bold", fontSize=13, textColor=DARK,
            alignment=TA_CENTER, spaceAfter=4
        ),
        "secao_titulo": ParagraphStyle(
            "secao_titulo", fontName="Helvetica-Bold", fontSize=10.5, textColor=DARK,
            spaceBefore=16, spaceAfter=6, alignment=TA_CENTER
        ),
        "corpo": ParagraphStyle(
            "corpo", fontName="Helvetica", fontSize=10, textColor=DARK,
            leading=15, spaceAfter=6, alignment=TA_JUSTIFY
        ),
        "parte_label": ParagraphStyle(
            "parte_label", fontName="Helvetica-Bold", fontSize=10, textColor=DARK,
            spaceAfter=2, alignment=TA_LEFT
        ),
        "assinatura_label": ParagraphStyle(
            "assinatura_label", fontName="Helvetica-Bold", fontSize=9.5, textColor=DARK,
            alignment=TA_CENTER, spaceAfter=2
        ),
        "assinatura_sub": ParagraphStyle(
            "assinatura_sub", fontName="Helvetica", fontSize=9, textColor=MID_GRAY,
            alignment=TA_CENTER
        ),
    }


def gerar_procuracao(
    outorgante_nome: str,
    outorgante_qualificacao: str,
    outorgante_cpf_cnpj: str,
    outorgante_endereco: str,
    outorgante_email: str,
    outorgados: list[dict],
    endereco_escritorio: str,
    finalidade: str = "",
    data_procuracao: date | None = None,
) -> bytes:
    """
    Gera o PDF do instrumento de procuração. Retorna bytes.
    `outorgados`: lista de {"nome": str, "oab": str, "cpf": str}.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=3 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title=f"Procuração — {outorgante_nome}",
    )

    st = _estilos()
    story = []
    data_str = _data_por_extenso(data_procuracao or date.today())

    # ── Cabeçalho com logo ────────────────────────────────────────────────────
    if _LOGO_PATH.exists():
        img = Image(str(_LOGO_PATH))
        orig_w, orig_h = img.imageWidth, img.imageHeight
        max_h = 2.2 * cm
        ratio = max_h / orig_h
        img.drawWidth = orig_w * ratio
        img.drawHeight = max_h
        img.hAlign = "CENTER"
        story.append(img)
        story.append(Spacer(1, 0.3 * cm))
    else:
        story.append(Paragraph("PIMENTA JÚDICE ADVOGADOS", ParagraphStyle(
            "hdr", fontName="Helvetica-Bold", fontSize=10, textColor=TEAL,
            spaceAfter=4, alignment=TA_CENTER, letterSpacing=2
        )))

    story.append(HRFlowable(width="100%", thickness=0.5, color=TEAL, spaceAfter=14))

    story.append(Paragraph("PROCURAÇÃO", st["titulo"]))
    story.append(HRFlowable(width="50%", thickness=0.5, color=colors.HexColor("#e5e7eb"),
                             spaceAfter=14, hAlign="CENTER"))

    # ── OUTORGANTE ────────────────────────────────────────────────────────────
    story.append(Paragraph("<b>OUTORGANTE:</b>", st["parte_label"]))
    story.append(Paragraph(
        f"{outorgante_nome}, {outorgante_qualificacao}, "
        f"com {outorgante_cpf_cnpj}, "
        f"residente/domiciliado em {outorgante_endereco}"
        f"{', e-mail ' + outorgante_email if outorgante_email else ''}, "
        "doravante denominado(a) <b>OUTORGANTE</b>;",
        st["corpo"]
    ))
    story.append(Spacer(1, 0.2 * cm))

    # ── OUTORGADO(S) — dinâmico, um ou mais advogados ───────────────────────────
    story.append(Paragraph("<b>OUTORGADO(S):</b>", st["parte_label"]))
    for adv in outorgados:
        nome = (adv.get("nome") or "").strip()
        oab = (adv.get("oab") or "").strip()
        cpf = (adv.get("cpf") or "").strip()
        if not nome:
            continue
        partes = [f"<b>{nome}</b>, advogado(a)"]
        if oab:
            partes.append(f"inscrito(a) na OAB sob o n.º {oab}")
        if cpf:
            partes.append(f"portador(a) do CPF n.º {cpf}")
        partes.append(f"com endereço profissional em {endereco_escritorio}")
        story.append(Paragraph(", ".join(partes) + ";", st["corpo"]))

    story.append(Spacer(1, 0.3 * cm))

    # ── PODERES ───────────────────────────────────────────────────────────────
    story.append(Paragraph("DOS PODERES", st["secao_titulo"]))
    story.append(Paragraph(PODERES_AD_JUDICIA, st["corpo"]))

    if finalidade.strip():
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("DA FINALIDADE ESPECÍFICA", st["secao_titulo"]))
        for paragrafo in finalidade.strip().split("\n\n"):
            paragrafo = paragrafo.strip()
            if paragrafo:
                story.append(Paragraph(paragrafo.replace("\n", " "), st["corpo"]))

    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        CLAUSULA_ASSINATURA.format(data_procuracao=data_str),
        st["corpo"]
    ))

    # ── ASSINATURA (só o outorgante — mandato unilateral) ───────────────────────
    story.append(Spacer(1, 1.5 * cm))
    story.append(HRFlowable(width="100%", thickness=0.3, color=colors.HexColor("#e5e7eb"),
                             spaceAfter=12))

    assinatura_data = [[_bloco_assinatura(st, outorgante_nome.upper(), "OUTORGANTE")]]
    tabela_ass = Table(assinatura_data, colWidths=[16 * cm])
    tabela_ass.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether([tabela_ass]))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def _bloco_assinatura(st: dict, nome: str, papel: str):
    return [
        Paragraph("_" * 38, ParagraphStyle(
            "linha", fontName="Helvetica", fontSize=10, textColor=DARK, alignment=TA_CENTER, spaceAfter=4
        )),
        Paragraph(nome, st["assinatura_label"]),
        Paragraph(papel, st["assinatura_sub"]),
    ]
