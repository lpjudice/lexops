"""
Converts plain text or simple markdown to a clean PDF using ReportLab.
Used for: IA analyses, jurisprudência analyses, atendimento notes.
"""
import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Accent colour
TEAL = colors.HexColor("#00b090")
DARK = colors.HexColor("#1d1e20")
GRAY = colors.HexColor("#6b7280")
LIGHT_BG = colors.HexColor("#f0fdf9")


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "titulo": ParagraphStyle(
            "titulo",
            parent=base["Title"],
            fontSize=18,
            leading=22,
            textColor=DARK,
            spaceAfter=4,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=GRAY,
            spaceAfter=6,
        ),
        "secao": ParagraphStyle(
            "secao",
            parent=base["Heading2"],
            fontSize=10,
            leading=13,
            textColor=TEAL,
            fontName="Helvetica-Bold",
            spaceBefore=14,
            spaceAfter=4,
            textTransform="uppercase",
        ),
        "corpo": ParagraphStyle(
            "corpo",
            parent=base["Normal"],
            fontSize=10,
            leading=15,
            textColor=DARK,
            spaceAfter=4,
        ),
        "item": ParagraphStyle(
            "item",
            parent=base["Normal"],
            fontSize=10,
            leading=15,
            textColor=DARK,
            leftIndent=14,
            spaceAfter=2,
            bulletIndent=0,
        ),
        "negrito": ParagraphStyle(
            "negrito",
            parent=base["Normal"],
            fontSize=10,
            leading=15,
            textColor=DARK,
            fontName="Helvetica-Bold",
            spaceAfter=4,
        ),
    }


def _escape(text: str) -> str:
    """Escape XML special chars for ReportLab Paragraph."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def texto_para_pdf(
    conteudo: str,
    titulo: str,
    subtitulo: str = "",
    cliente_nome: str = "",
    data: date | None = None,
) -> bytes:
    """
    Renders `conteudo` (markdown-ish text) to PDF bytes.

    Supported markup:
      **SECTION** (both sides)  → section heading
      **bold text**             → bold paragraph (one side only)
      - item / • item           → bullet list item
      blank line                → spacer
      plain text                → body paragraph
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title=titulo,
    )

    st = _styles()
    story = []

    # ── Header ────────────────────────────────────────────────────────────
    story.append(Paragraph(_escape(titulo), st["titulo"]))
    if subtitulo:
        story.append(Paragraph(_escape(subtitulo), st["meta"]))

    meta_parts = []
    if cliente_nome:
        meta_parts.append(f"Cliente: {cliente_nome}")
    if data:
        meta_parts.append(f"Data: {data.strftime('%d/%m/%Y')}")
    if meta_parts:
        story.append(Paragraph(" · ".join(meta_parts), st["meta"]))

    story.append(HRFlowable(width="100%", thickness=1, color=TEAL, spaceAfter=10))

    # ── Body ──────────────────────────────────────────────────────────────
    for raw_line in conteudo.splitlines():
        line = raw_line.strip()

        if not line:
            story.append(Spacer(1, 6))
            continue

        # Section heading: **ALL CAPS HEADING** on its own
        if line.startswith("**") and line.endswith("**") and len(line) > 4:
            inner = line[2:-2]
            story.append(Paragraph(_escape(inner), st["secao"]))
            continue

        # Bold line: starts with **
        if line.startswith("**"):
            inner = line.replace("**", "")
            story.append(Paragraph(f"<b>{_escape(inner)}</b>", st["corpo"]))
            continue

        # Bullet list
        if line.startswith("- ") or line.startswith("• "):
            inner = line[2:]
            story.append(Paragraph(f"• {_escape(inner)}", st["item"]))
            continue

        # Regular paragraph — handle inline **bold**
        if "**" in line:
            parts = line.split("**")
            html = ""
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    html += f"<b>{_escape(part)}</b>"
                else:
                    html += _escape(part)
            story.append(Paragraph(html, st["corpo"]))
        else:
            story.append(Paragraph(_escape(line), st["corpo"]))

    doc.build(story)
    return buf.getvalue()
