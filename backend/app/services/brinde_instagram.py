"""Brinde / isca (lead magnet) do módulo Instagram.

Gera um material rico (one-pager / slides / HTML) sobre o tema do post, na
identidade Pimenta Judice. Fonte de verdade = HTML; o PDF é derivado dele
(xhtml2pdf, puro Python — usa o reportlab que já está no requirements).
"""
from __future__ import annotations

import html as _html
import io
import json

from sqlalchemy.orm import Session

from app.models.instagram import InstagramSugestao
from app.services import ia_instagram

FORMATO_LABEL = {"one_pager": "one-pager", "slides": "guia em blocos", "html": "material completo"}


def _prompt(tema: str, formato: str, palavra: str | None) -> str:
    guia = {
        "one_pager": "3 a 5 seções CONCISAS (é uma folha única).",
        "slides": "5 a 8 seções CURTAS — cada seção vira um 'bloco/slide'.",
        "html": "4 a 6 seções com um pouco mais de texto (material completo).",
    }.get(formato, "3 a 5 seções concisas.")
    kw = f'\nA pessoa recebe este material comentando "{palavra}" no post.' if palavra else ""
    return f"""Você cria um material rico (brinde/isca de captação) para o Instagram
do @dr.lucasjudice (Pimenta Judice), advocacia patrimonialista (holding, sucessão,
societário, reforma tributária). Público: donos de patrimônio e empresas familiares.

TEMA: {tema}
FORMATO: {FORMATO_LABEL.get(formato, formato)} — {guia}{kw}

Tom acessível e confiável, juridicamente correto, SEM prometer resultado e SEM
consultoria específica. Conteúdo educativo e prático (checklists, passos, cuidados).

Responda APENAS com JSON válido (sem markdown):
{{
  "titulo": "título do material",
  "subtitulo": "1 linha de apoio",
  "secoes": [
    {{ "titulo": "título da seção", "paragrafos": ["parágrafo..."], "bullets": ["item..."] }}
  ],
  "cta": "chamada final curta (ex.: agende um diagnóstico)"
}}"""


def gerar_brinde(db: Session, sug: InstagramSugestao, formato: str) -> tuple[str, float, str]:
    """Gera o HTML do brinde. Retorna (html, custo_usd, titulo)."""
    tema = sug.tema or sug.titulo or "Planejamento patrimonial"
    data, custo = ia_instagram._call_llm_json(_prompt(tema, formato, sug.brinde_palavra_chave))
    if not isinstance(data, dict) or not data.get("secoes"):
        raise ValueError("A IA não retornou um brinde válido.")
    html = _render_html(data, formato)
    return html, custo, (data.get("titulo") or tema)[:255]


# ── Render HTML (print-friendly: CSS simples que o navegador E o xhtml2pdf entendem) ──
def _esc(t: str) -> str:
    return _html.escape(str(t or ""))


def _render_html(c: dict, formato: str) -> str:
    TEAL = "#1C5A4E"
    INK = "#123D34"
    secoes_html = ""
    for i, s in enumerate(c.get("secoes", []), start=1):
        paras = "".join(f'<p class="p">{_esc(p)}</p>' for p in (s.get("paragrafos") or []))
        bullets = "".join(f"<li>{_esc(b)}</li>" for b in (s.get("bullets") or []))
        bl = f'<ul class="bl">{bullets}</ul>' if bullets else ""
        quebra = ' style="page-break-before: always;"' if formato == "slides" and i > 1 else ""
        secoes_html += (
            f'<div class="sec"{quebra}>'
            f'<div class="sec-num">{i:02d}</div>'
            f'<h2>{_esc(s.get("titulo"))}</h2>{paras}{bl}</div>'
        )
    titulo = _esc(c.get("titulo"))
    subtitulo = _esc(c.get("subtitulo"))
    cta = _esc(c.get("cta"))
    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>{titulo} — Pimenta Judice</title>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
  @page {{ size: A4; margin: 1.4cm; }}
  body {{ font-family: 'Archivo', Helvetica, Arial, sans-serif; color: {INK}; margin: 0; padding: 0; }}
  .wrap {{ max-width: 760px; margin: 0 auto; padding: 28px; }}
  .cover {{ background: {TEAL}; color: #fff; padding: 40px 44px; border-radius: 10px; }}
  .kicker {{ font-size: 12px; letter-spacing: 3px; text-transform: uppercase; color: #cfe6e0; }}
  .cover h1 {{ font-size: 34px; margin: 8px 0 6px; line-height: 1.12; }}
  .cover .sub {{ font-size: 15px; color: #e7f2ef; }}
  .sec {{ margin: 26px 4px; }}
  .sec-num {{ color: {TEAL}; font-weight: 800; font-size: 14px; letter-spacing: 2px; }}
  .sec h2 {{ font-size: 21px; color: {INK}; margin: 4px 0 8px; border-left: 4px solid {TEAL}; padding-left: 12px; }}
  .p {{ font-size: 14px; line-height: 1.65; color: #34413c; margin: 6px 0; }}
  .bl {{ margin: 8px 0 8px 4px; padding-left: 18px; }}
  .bl li {{ font-size: 14px; line-height: 1.55; color: #34413c; margin: 4px 0; }}
  .cta {{ background: #f2f6f5; border: 1px solid #d8e6e2; border-radius: 10px; padding: 20px 24px; margin-top: 28px; }}
  .cta strong {{ color: {TEAL}; }}
  .foot {{ text-align: center; color: #8a9a95; font-size: 12px; margin-top: 26px; }}
  .foot b {{ color: {TEAL}; }}
</style></head>
<body><div class="wrap">
  <div class="cover">
    <div class="kicker">Pimenta Judice · Material Gratuito</div>
    <h1>{titulo}</h1>
    <div class="sub">{subtitulo}</div>
  </div>
  {secoes_html}
  <div class="cta"><strong>{cta}</strong></div>
  <div class="foot"><b>@dr.lucasjudice</b> · Advogado Patrimonialista · pimentajudice.com.br</div>
</div></body></html>"""


def html_para_pdf(html: str) -> bytes:
    """Converte o HTML do brinde em PDF (xhtml2pdf / pisa — puro Python)."""
    from xhtml2pdf import pisa

    buf = io.BytesIO()
    pisa.CreatePDF(src=html, dest=buf, encoding="utf-8")
    return buf.getvalue()
