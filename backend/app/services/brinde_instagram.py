"""Brinde / isca (lead magnet) do módulo Instagram.

Gera o CONTEÚDO com a IA (Claude) e guarda o JSON; renderiza sob demanda em dois
estilos — "instagram" (teal) e "site" (bege/preto oficial) — e em HTML rico (para
navegador/Netlify) ou HTML pisa-friendly (para o PDF via xhtml2pdf). Logo embutida.
"""
from __future__ import annotations

import base64
import html as _html
import json
import pathlib

from sqlalchemy.orm import Session

from app.models.instagram import InstagramSugestao
from app.services import ia_instagram

_ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"
_LOGO_CACHE: dict[str, str] = {}

FORMATO_LABEL = {"one_pager": "one-pager", "slides": "guia em blocos", "html": "material completo"}


def _logo(nome: str) -> str:
    """Retorna a logo como data-URI base64 (cacheado)."""
    if nome not in _LOGO_CACHE:
        try:
            data = (_ASSETS / nome).read_bytes()
            _LOGO_CACHE[nome] = "data:image/png;base64," + base64.b64encode(data).decode()
        except Exception:
            _LOGO_CACHE[nome] = ""
    return _LOGO_CACHE[nome]


def _esc(t) -> str:
    return _html.escape(str(t or ""))


# ── Geração de conteúdo (Claude) ──────────────────────────────────────────────
def _prompt(tema: str, formato: str, estilo: str, palavra: str | None) -> str:
    if estilo == "site":
        guia = "4 a 6 seções com boa profundidade (vira uma landing page do site)."
    else:
        guia = {
            "one_pager": "EXATAMENTE 3 seções bem concisas — cabe em 1 folha. Bullets curtíssimos.",
            "slides": "6 a 8 seções CURTAS e diretas — cada uma é um bloco/slide independente e escaneável.",
            "html": "4 a 6 seções com mais texto e explicação (material completo tipo mini-ebook).",
        }.get(formato, "3 a 5 seções concisas.")
    kw = f'\nA pessoa recebe este material comentando "{palavra}" no post.' if palavra else ""
    return f"""Você cria um material rico (brinde/isca de captação) para o Pimenta Judice,
advocacia patrimonialista (holding, sucessão, societário, reforma tributária).
Público: donos de patrimônio e empresas familiares.

TEMA: {tema}
ESTRUTURA: {guia}{kw}

Tom acessível e confiável, juridicamente correto, SEM prometer resultado e SEM
consultoria específica. Conteúdo prático (passos, cuidados, checklists).

O material é PURAMENTE INFORMATIVO — não é peça de venda. NÃO inclua call-to-action
comercial (nada de "agende", "contrate", "fale com o escritório"). O fechamento é
institucional: uma frase de encerramento que amarra o tema, sem convite para ação.

Responda APENAS com JSON válido (sem markdown):
{{
  "titulo": "título do material",
  "subtitulo": "1 linha de apoio forte",
  "secoes": [
    {{ "titulo": "título da seção", "paragrafos": ["parágrafo..."], "bullets": ["item..."] }}
  ],
  "cta": "frase de encerramento institucional (SEM call-to-action de venda)"
}}"""


def gerar_conteudo(sug: InstagramSugestao, formato: str, estilo: str) -> tuple[dict, float, str]:
    """Gera o conteúdo do brinde. Retorna (conteudo, custo_usd, titulo)."""
    tema = sug.tema or sug.titulo or "Planejamento patrimonial"
    data, custo = ia_instagram._call_llm_json(_prompt(tema, formato, estilo, sug.brinde_palavra_chave))
    if not isinstance(data, dict) or not data.get("secoes"):
        raise ValueError("A IA não retornou um brinde válido.")
    return data, custo, (data.get("titulo") or tema)[:255]


# ── Render ────────────────────────────────────────────────────────────────────
def render(conteudo: dict, formato: str, estilo: str, para_pdf: bool = False) -> str:
    if estilo == "site":
        return _render_site(conteudo, para_pdf)
    return _render_instagram(conteudo, formato or "one_pager", para_pdf)


def _paras(items) -> str:
    return "".join(f'<p class="p">{_esc(p)}</p>' for p in (items or []))


def _callout(items, cor_bg: str, cor_borda: str) -> str:
    """Bullets viram UM único bloco destacado (fundo + barra lateral) — usado só
    para a lista de pontos-chave, não para cada parágrafo."""
    if not items:
        return ""
    lis = "".join(f"<li>{_esc(b)}</li>" for b in items)
    return f'<ul class="callout" style="background:{cor_bg}; border-left-color:{cor_borda};">{lis}</ul>'


# ---------- Estilo Instagram (teal, fundo branco, sotaques coloridos) ----------
def _render_instagram(c: dict, formato: str, para_pdf: bool) -> str:
    TEAL, INK, MUT, TINT = "#1C5A4E", "#16211d", "#5c6b66", "#EAF3F0"
    logo = _logo("logo_dark.png")
    fonte = "Helvetica, Arial, sans-serif" if para_pdf else "'Archivo', Helvetica, Arial, sans-serif"
    gfont = "" if para_pdf else '<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">'

    secoes = ""
    for i, s in enumerate(c.get("secoes", []), start=1):
        num = f'{i:02d}'
        brk = 'style="page-break-before: always;"' if (para_pdf and formato == "slides" and i > 1) else ''
        secoes += f"""<div class="sec" {brk}>
          <div class="s-head"><span class="s-num">{num}</span><h2 class="s-title">{_esc(s.get('titulo'))}</h2></div>
          {_paras(s.get('paragrafos'))}{_callout(s.get('bullets'), TINT, TEAL)}
        </div>"""

    if formato == "one_pager":
        tsize = "24px"
    elif formato == "slides":
        tsize = "26px"
    else:
        tsize = "25px"

    logo_img = f'<img src="{logo}" style="width:130px; margin-bottom:22px"/>' if logo else ''
    titulo, subtitulo, cta = _esc(c.get("titulo")), _esc(c.get("subtitulo")), _esc(c.get("cta"))
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<title>{titulo} — Pimenta Judice</title>{gfont}
<style>
  @page {{ size: A4; margin: 1.6cm; }}
  body {{ font-family: {fonte}; color: {INK}; margin: 0; background: #fff; }}
  .wrap {{ max-width: 720px; margin: 0 auto; padding: 8px; }}
  .hero {{ position: relative; }}
  .kick {{ color: {TEAL}; font-size: 12px; font-weight: 800; letter-spacing: 4px; margin-bottom: 14px; }}
  h1 {{ font-size: 34px; line-height: 1.16; font-weight: 900; color: {INK}; margin: 0 0 14px; max-width: 90%; }}
  .quote {{ font-size: 110px; color: {TEAL}; opacity: .14; font-weight: 900; font-family: Georgia, serif; position: absolute; right: 0; top: -18px; }}
  .sub {{ font-size: 16px; color: {MUT}; line-height: 1.55; max-width: 560px; margin: 0 0 8px; }}
  .rule {{ border: none; border-top: 3px solid {TEAL}; width: 56px; margin: 26px 0 6px; }}
  .sec {{ margin: 30px 0; }}
  .s-head {{ display: flex; align-items: baseline; gap: 12px; margin-bottom: 10px; }}
  .s-num {{ color: {TEAL}; font-weight: 900; font-size: 15px; letter-spacing: 1px; }}
  .s-title {{ font-size: {tsize}; font-weight: 800; color: {INK}; margin: 0; }}
  .p {{ font-size: 15px; line-height: 1.7; color: #333d39; margin: 0 0 10px; }}
  ul.callout {{ list-style: none; margin: 14px 0 4px; padding: 16px 20px; border-left: 4px solid; border-radius: 0 8px 8px 0; }}
  ul.callout li {{ font-size: 14.5px; line-height: 1.55; color: {INK}; margin: 7px 0; font-weight: 500; }}
  ul.callout li::before {{ content: "→ "; color: {TEAL}; font-weight: 800; }}
  .fechamento {{ margin-top: 26px; padding-top: 22px; border-top: 1px solid #e4e9e7; text-align: center; font-style: italic; font-size: 15px; color: #4a5450; }}
  .foot {{ text-align: center; color: #9aa6a1; font-size: 11.5px; margin-top: 20px; letter-spacing: .5px; }}
  .foot b {{ color: {TEAL}; }}
</style></head><body><div class="wrap">
  {logo_img}
  <div class="hero">
    <div class="quote">&ldquo;</div>
    <div class="kick">MATERIAL INFORMATIVO</div>
    <h1>{titulo}</h1>
    <div class="sub">{subtitulo}</div>
  </div>
  <hr class="rule">
  {secoes}
  <div class="fechamento">{cta}</div>
  <div class="foot"><b>@dr.lucasjudice</b> · Advogado Patrimonialista · pimentajudice.com.br</div>
</div></body></html>"""


# ---------- Estilo Site oficial (fundo branco, serifado, sotaque bege/teal) ----------
def _render_site(c: dict, para_pdf: bool) -> str:
    INK, TEAL, MUT, TINT = "#1a1a1a", "#4a897c", "#6b655a", "#F1ECE1"
    logo = _logo("logo_dark.png")
    serif = "Georgia, 'Times New Roman', serif" if para_pdf else "'Playfair Display', Georgia, serif"
    sans = "Helvetica, Arial, sans-serif" if para_pdf else "'Archivo', Helvetica, Arial, sans-serif"
    gfont = "" if para_pdf else '<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=Playfair+Display:wght@500;600;700;800&display=swap" rel="stylesheet">'

    secoes = ""
    for s in c.get("secoes", []):
        secoes += f"""<div class="sec">
          <h2>{_esc(s.get('titulo'))}</h2>
          {''.join(f'<p>{_esc(p)}</p>' for p in (s.get('paragrafos') or []))}
          {_callout(s.get('bullets'), TINT, TEAL)}
        </div>"""
    logo_img = f'<img src="{logo}" style="width:160px; margin-bottom:30px"/>' if logo else ''
    titulo, subtitulo, cta = _esc(c.get("titulo")), _esc(c.get("subtitulo")), _esc(c.get("cta"))
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<title>{titulo} — Pimenta Judice Advogados</title>{gfont}
<style>
  @page {{ size: A4; margin: 2cm; }}
  body {{ font-family: {sans}; color: {INK}; background: #fff; margin: 0; }}
  .wrap {{ max-width: 720px; margin: 0 auto; }}
  .hero {{ padding: 0 0 30px; border-bottom: 1px solid #e4dfd2; margin-bottom: 36px; position: relative; }}
  .hero .kick {{ font-size: 11.5px; letter-spacing: 4px; color: {TEAL}; text-transform: uppercase; font-weight: 600; }}
  .hero h1 {{ font-family: {serif}; font-weight: 700; font-size: 38px; line-height: 1.16; color: {INK}; margin: 14px 0 14px; }}
  .quote {{ font-size: 100px; line-height: 0; color: {TEAL}; opacity: .15; font-family: {serif}; position: absolute; right: 0; top: 10px; }}
  .hero .sub {{ font-size: 16.5px; color: {MUT}; max-width: 560px; line-height: 1.55; font-style: italic; }}
  .sec {{ margin: 30px 0; }}
  .sec h2 {{ font-family: {serif}; font-weight: 600; font-size: 23px; color: {INK}; margin: 0 0 10px; }}
  .sec p {{ font-size: 15.5px; line-height: 1.75; color: #3a352c; margin: 8px 0; }}
  ul.callout {{ list-style: none; margin: 14px 0 4px; padding: 16px 22px; border-left: 3px solid; }}
  ul.callout li {{ font-size: 15px; line-height: 1.6; color: {INK}; margin: 7px 0; }}
  ul.callout li::before {{ content: "— "; color: {TEAL}; font-weight: 700; }}
  .fechamento {{ text-align: center; border-top: 1px solid #e4dfd2; margin-top: 44px; padding-top: 32px; font-family: {serif}; font-style: italic; font-size: 19px; color: {INK}; }}
  .foot {{ text-align: center; color: {MUT}; font-size: 11.5px; margin-top: 28px; letter-spacing: 1px; }}
</style></head><body><div class="wrap">
  <div class="hero">{logo_img}<div class="kick">Pimenta Judice · Advogados Associados</div>
    <h1>{titulo}</h1><div class="quote">&rdquo;</div><div class="sub">{subtitulo}</div></div>
  {secoes}
  <div class="fechamento">{cta}</div>
  <div class="foot">PIMENTA JUDICE ADVOGADOS ASSOCIADOS · PLANEJAMENTO PATRIMONIAL E SUCESSÓRIO · pimentajudice.com.br</div>
</div></body></html>"""


def html_para_pdf(html: str) -> bytes:
    """Renderiza o HTML em PDF via WeasyPrint (motor com suporte real a CSS —
    xhtml2pdf/pisa quebrava o fundo contínuo em uma caixa por parágrafo/bullet)."""
    from weasyprint import HTML
    return HTML(string=html).write_pdf()
