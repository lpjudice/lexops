"""
Geração de Proposta PDF em formato ReportLab.
Estrutura:
  Página 1 — Carta de apresentação (destinatário, data, parágrafo introdutório)
  Página 2+ — Resumo das Atividades + Detalhamento por bloco temático
  Última seção — Investimento
"""

import io
import os
from datetime import date
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Logo path — backend dir is mounted at /app in Docker
_LOGO_PATH = Path(__file__).parent.parent.parent / "logo.png"

# ── cores
DARK = colors.HexColor("#1d1e20")
TEAL = colors.HexColor("#00b090")
LIGHT_GRAY = colors.HexColor("#f3f4f6")
MID_GRAY = colors.HexColor("#6b7280")

# ── Blocos predefinidos por tipo de projeto
BLOCOS_PPS = {
    "Proteção Patrimonial": [
        "Estruturação de holding patrimonial para segregação de ativos",
        "Proteção de bens em face de riscos empresariais e pessoais",
        "Blindagem contratual e estatutária de participações societárias",
        "Análise de exposição e contingências patrimoniais",
    ],
    "Planejamento Patrimonial Sucessório & Familiar": [
        "Organização da estrutura societária para fins sucessórios",
        "Elaboração de cláusulas restritivas (inalienabilidade, impenhorabilidade, incomunicabilidade)",
        "Planejamento da transmissão de quotas e participações (doação em vida x inventário)",
        "Pacto antenupcial e regimes de bens — análise e orientação",
        "Constituição de holding familiar com governança definida",
    ],
    "Economia Tributária": [
        "Levantamento da carga tributária atual (IRPF, IRPJ, ITCMD, IOF)",
        "Análise de alternativas para redução lícita de tributos",
        "Remuneração sócios: pró-labore vs. distribuição de lucros — otimização",
        "Planejamento do ITCMD na transmissão patrimonial",
        "Reorganização societária com eficiência fiscal",
    ],
}

BLOCOS_PATRIMONIAL = {
    "Proteção Patrimonial": BLOCOS_PPS["Proteção Patrimonial"],
    "Estruturação Societária": [
        "Análise da estrutura societária atual e proposta de reorganização",
        "Constituição de SPE(s) para segregação de ativos imobiliários",
        "Revisão de contratos sociais e acordos de sócios",
        "Governança corporativa e mecanismos de decisão",
    ],
}

PROJETOS_BLOCOS: dict[str, dict[str, list[str]]] = {
    "PPS": BLOCOS_PPS,
    "Patrimonial": BLOCOS_PATRIMONIAL,
    "Personalizado": {},
}


def _estilos():
    base = getSampleStyleSheet()
    estilos = {
        "titulo": ParagraphStyle(
            "titulo",
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=DARK,
            spaceAfter=6,
            alignment=TA_LEFT,
        ),
        "subtitulo": ParagraphStyle(
            "subtitulo",
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=TEAL,
            spaceBefore=18,
            spaceAfter=6,
            letterSpacing=1.2,
        ),
        "corpo": ParagraphStyle(
            "corpo",
            fontName="Helvetica",
            fontSize=10.5,
            textColor=DARK,
            leading=15,
            spaceAfter=8,
            alignment=TA_JUSTIFY,
        ),
        "item": ParagraphStyle(
            "item",
            fontName="Helvetica",
            fontSize=10,
            textColor=colors.HexColor("#374151"),
            leading=14,
            spaceAfter=3,
            leftIndent=14,
            bulletIndent=6,
        ),
        "label": ParagraphStyle(
            "label",
            fontName="Helvetica-Bold",
            fontSize=9.5,
            textColor=MID_GRAY,
            spaceAfter=2,
        ),
        "secao": ParagraphStyle(
            "secao",
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=DARK,
            spaceBefore=14,
            spaceAfter=8,
        ),
        "rodape": ParagraphStyle(
            "rodape",
            fontName="Helvetica",
            fontSize=8,
            textColor=colors.HexColor("#9ca3af"),
            alignment=TA_CENTER,
        ),
        "investimento": ParagraphStyle(
            "investimento",
            fontName="Helvetica-Bold",
            fontSize=13,
            textColor=TEAL,
            spaceAfter=6,
        ),
    }
    return estilos


def gerar_proposta(
    cliente_nome: str,
    projeto_tipo: str,
    valor: str,
    condicao_pagamento: str,
    intro_texto: str,
    anamnese_resumo: str,
    data_proposta: date | None = None,
    blocos_extras: dict[str, list[str]] | None = None,
) -> bytes:
    """Gera e retorna o PDF da proposta como bytes."""

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=3 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title=f"Proposta — {cliente_nome}",
    )

    st = _estilos()
    story = []
    data_str = (data_proposta or date.today()).strftime("%d de %B de %Y")
    blocos = blocos_extras or PROJETOS_BLOCOS.get(projeto_tipo, BLOCOS_PPS)

    # ──────────────────────────────────────────────────────────────
    # PÁGINA 1 — Carta de apresentação
    # ──────────────────────────────────────────────────────────────

    # Cabeçalho da carta — logo ou texto fallback
    if _LOGO_PATH.exists():
        img = Image(str(_LOGO_PATH))
        # Mantém proporção, limita altura a 2.5cm
        orig_w, orig_h = img.imageWidth, img.imageHeight
        max_h = 2.5 * cm
        ratio = max_h / orig_h
        img.drawWidth = orig_w * ratio
        img.drawHeight = max_h
        img.hAlign = "LEFT"
        story.append(img)
        story.append(Spacer(1, 0.2 * cm))
    else:
        story.append(Paragraph("PIMENTA JUDICE ADVOGADOS", ParagraphStyle(
            "hdr", fontName="Helvetica-Bold", fontSize=10, textColor=TEAL, spaceAfter=2, letterSpacing=2
        )))
    story.append(HRFlowable(width="100%", thickness=0.5, color=TEAL, spaceAfter=18))

    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph(f"Vitória, {data_str}", ParagraphStyle(
        "data", fontName="Helvetica", fontSize=10, textColor=MID_GRAY, spaceAfter=18
    )))

    story.append(Paragraph(f"<b>A/C {cliente_nome}</b>", st["corpo"]))
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph(
        f"Assunto: <b>Proposta de Serviços Jurídicos — {projeto_tipo}</b>",
        st["corpo"]
    ))
    story.append(HRFlowable(width="40%", thickness=0.5, color=LIGHT_GRAY, spaceAfter=14))

    story.append(Paragraph("Prezado(a) cliente,", st["corpo"]))
    story.append(Spacer(1, 0.3 * cm))

    intro = intro_texto or (
        f"É com satisfação que apresentamos nossa proposta de serviços jurídicos especializados em "
        f"{projeto_tipo}, elaborada com base nas informações compartilhadas em nossa reunião de "
        f"diagnóstico. Nossa equipe está preparada para estruturar, com segurança e eficiência, "
        f"as soluções jurídicas adequadas ao seu perfil patrimonial e familiar."
    )
    story.append(Paragraph(intro, st["corpo"]))
    story.append(Spacer(1, 0.5 * cm))

    if anamnese_resumo:
        story.append(Paragraph("Com base no levantamento realizado, identificamos:", st["corpo"]))
        for linha in anamnese_resumo.split("\n"):
            linha = linha.strip()
            if linha:
                story.append(Paragraph(f"• {linha}", st["item"]))
        story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph(
        "A presente proposta detalha o escopo dos serviços, metodologia e investimento para a "
        "implementação do projeto.",
        st["corpo"]
    ))

    story.append(PageBreak())

    # ──────────────────────────────────────────────────────────────
    # PÁGINA 2+ — Resumo + Detalhamento
    # ──────────────────────────────────────────────────────────────

    story.append(Paragraph(f"PROPOSTA DE SERVIÇOS — {projeto_tipo.upper()}", st["titulo"]))
    story.append(HRFlowable(width="100%", thickness=1, color=TEAL, spaceAfter=14))

    story.append(Paragraph("RESUMO DAS ATIVIDADES", st["subtitulo"]))
    story.append(HRFlowable(width="30%", thickness=0.5, color=LIGHT_GRAY, spaceAfter=10))

    for bloco_nome in blocos:
        story.append(Paragraph(f"• {bloco_nome}", st["item"]))
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph("DETALHAMENTO", st["subtitulo"]))
    story.append(HRFlowable(width="30%", thickness=0.5, color=LIGHT_GRAY, spaceAfter=10))

    for bloco_nome, itens in blocos.items():
        story.append(Paragraph(bloco_nome.upper(), st["secao"]))
        for item in itens:
            story.append(Paragraph(f"• {item}", st["item"]))
        story.append(Spacer(1, 0.3 * cm))

    # ──────────────────────────────────────────────────────────────
    # INVESTIMENTO
    # ──────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT_GRAY, spaceBefore=14, spaceAfter=14))
    story.append(Paragraph("INVESTIMENTO", st["subtitulo"]))

    inv_data = [
        ["Honorários", valor if valor else "A definir"],
        ["Condição de pagamento", condicao_pagamento if condicao_pagamento else "A definir"],
    ]
    inv_table = Table(inv_data, colWidths=[5 * cm, 10 * cm])
    inv_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GRAY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), DARK),
        ("TEXTCOLOR", (1, 0), (1, -1), DARK),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, LIGHT_GRAY]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(inv_table)

    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph(
        "Estes honorários são devidos exclusivamente pelos serviços de planejamento e estruturação "
        "jurídica descritos nesta proposta, não incluindo eventuais custos cartoriais, fiscais ou "
        "de terceiros.",
        st["corpo"]
    ))

    story.append(Spacer(1, 1.5 * cm))
    story.append(HRFlowable(width="40%", thickness=0.5, color=LIGHT_GRAY, spaceAfter=6))
    story.append(Paragraph("Pimenta Judice Advogados", ParagraphStyle(
        "ass", fontName="Helvetica-Bold", fontSize=10, textColor=DARK, alignment=TA_CENTER
    )))
    story.append(Paragraph("Lucas Judice — OAB/ES XXXXX", ParagraphStyle(
        "ass2", fontName="Helvetica", fontSize=9, textColor=MID_GRAY, alignment=TA_CENTER
    )))

    doc.build(story)
    buf.seek(0)
    return buf.read()
