"""
Relatório PDF de leitura em lote de andamentos.

Lista os processos que tiveram andamento novo no lote, com os 10 últimos
andamentos de cada, destacando os novos e oferecendo hyperlink para o arquivo
de cada andamento (quando há link no Drive).

Segue o padrão Platypus usado em `proposta_pdf.py`.
"""
from __future__ import annotations

import io
from datetime import datetime
from html import escape
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

# Paleta alinhada ao app (teal/verde para "novo")
VERDE = colors.HexColor("#00875a")
VERDE_FUNDO = colors.HexColor("#e6f7f1")
CINZA = colors.HexColor("#6b7280")
ESCURO = colors.HexColor("#1d1e20")


def _estilos() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle(
            "titulo", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=18, textColor=ESCURO, spaceAfter=2, alignment=TA_LEFT,
        ),
        "resumo": ParagraphStyle(
            "resumo", parent=base["Normal"], fontName="Helvetica",
            fontSize=10, textColor=CINZA, spaceAfter=10,
        ),
        "processo": ParagraphStyle(
            "processo", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12, textColor=ESCURO, spaceBefore=12, spaceAfter=1,
        ),
        "processoSub": ParagraphStyle(
            "processoSub", parent=base["Normal"], fontName="Helvetica",
            fontSize=8.5, textColor=CINZA, spaceAfter=6,
        ),
        "andHeader": ParagraphStyle(
            "andHeader", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9.5, textColor=ESCURO, spaceAfter=0,
        ),
        "andHeaderNovo": ParagraphStyle(
            "andHeaderNovo", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=9.5, textColor=VERDE, spaceAfter=0, backColor=VERDE_FUNDO,
            borderPadding=(3, 4, 3, 4), leftIndent=2,
        ),
        "andCorpo": ParagraphStyle(
            "andCorpo", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, textColor=colors.HexColor("#374151"), spaceAfter=7,
            leading=12, leftIndent=2,
        ),
        "rodape": ParagraphStyle(
            "rodape", parent=base["Normal"], fontName="Helvetica-Oblique",
            fontSize=8, textColor=CINZA,
        ),
    }


def _fmt_data(d: Any) -> str:
    if not d:
        return "s/ data"
    try:
        return d.strftime("%d/%m/%Y")
    except AttributeError:
        s = str(d)
        if "-" in s:
            y, m, day = s.split("T")[0].split("-")[:3]
            return f"{day}/{m}/{y}"
        return s


def gerar_relatorio_lote(processos: list[dict[str, Any]], gerado_em: datetime | None = None) -> bytes:
    """
    `processos`: lista de
      {
        "cnj": str, "cliente": str, "tribunal": str | None,
        "andamentos": [
          {"data": date|None, "tipo": str|None, "descricao": str,
           "arquivo_nome": str|None, "arquivo_drive_link": str|None, "novo": bool},
          ...
        ]
      }
    Retorna os bytes do PDF.
    """
    gerado_em = gerado_em or datetime.now()
    st = _estilos()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.6 * cm, bottomMargin=1.6 * cm,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        title="Andamentos em Lote",
    )

    flow: list[Any] = []
    flow.append(Paragraph("Andamentos em Lote", st["titulo"]))
    total_novos = sum(
        sum(1 for a in p["andamentos"] if a.get("novo")) for p in processos
    )
    flow.append(Paragraph(
        f"Gerado em {gerado_em.strftime('%d/%m/%Y %H:%M')} · "
        f"{len(processos)} processo(s) com novidade · {total_novos} andamento(s) novo(s)",
        st["resumo"],
    ))
    flow.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e5e7eb")))

    for p in processos:
        bloco: list[Any] = []
        sub = " · ".join(
            [x for x in [p.get("tribunal"), f"{len(p['andamentos'])} andamento(s) listado(s)"] if x]
        )
        bloco.append(Paragraph(
            f"{escape(p['cnj'])} &nbsp;—&nbsp; {escape(p.get('cliente') or 'Cliente não informado')}",
            st["processo"],
        ))
        if sub:
            bloco.append(Paragraph(escape(sub), st["processoSub"]))

        for a in p["andamentos"]:
            novo = bool(a.get("novo"))
            tag = '<font color="#00875a"><b>● NOVO</b></font> &nbsp;' if novo else ""
            tipo = f" &nbsp;·&nbsp; {escape(a['tipo'])}" if a.get("tipo") else ""
            cabec = f"{tag}{escape(_fmt_data(a.get('data')))}{tipo}"
            bloco.append(Paragraph(cabec, st["andHeaderNovo"] if novo else st["andHeader"]))

            desc = escape((a.get("descricao") or "").strip()) or "—"
            link = a.get("arquivo_drive_link")
            nome = a.get("arquivo_nome")
            if link and nome:
                desc += (
                    f'<br/><a href="{escape(link)}" color="#0b6bcb">'
                    f'<u>&#8595; {escape(nome)}</u></a>'
                )
            elif nome:
                desc += f"<br/><font color='#6b7280'>&#8595; {escape(nome)}</font>"
            bloco.append(Paragraph(desc, st["andCorpo"]))

        if not p["andamentos"]:
            bloco.append(Paragraph("Sem andamentos registrados.", st["andCorpo"]))

        # Mantém o cabeçalho do processo junto do 1º andamento quando possível.
        flow.append(KeepTogether(bloco[:2]))
        flow.extend(bloco[2:])
        flow.append(Spacer(1, 4))

    flow.append(Spacer(1, 10))
    flow.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e5e7eb")))
    flow.append(Paragraph(
        "Sui — Pimenta Judice · Relatório de andamentos em lote.", st["rodape"]
    ))

    doc.build(flow)
    return buf.getvalue()
