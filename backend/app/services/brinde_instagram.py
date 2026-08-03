"""Brinde / isca (lead magnet) do módulo Instagram.

Gera o CONTEÚDO com a IA (Claude) e guarda o JSON; renderiza sob demanda em dois
estilos — "instagram" (teal) e "site" (bege/preto oficial) — e em HTML rico (para
navegador/Netlify) ou HTML pisa-friendly (para o PDF via xhtml2pdf). Logo embutida.
"""
from __future__ import annotations

import base64
import html as _html
import io
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

Responda APENAS com JSON válido (sem markdown):
{{
  "titulo": "título do material",
  "subtitulo": "1 linha de apoio forte",
  "secoes": [
    {{ "titulo": "título da seção", "paragrafos": ["parágrafo..."], "bullets": ["item..."] }}
  ],
  "cta": "chamada final curta (ex.: agende um diagnóstico com o escritório)"
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


def _bullets(items, cls="") -> str:
    if not items:
        return ""
    lis = "".join(f"<li>{_esc(b)}</li>" for b in items)
    return f'<ul class="{cls}">{lis}</ul>'


def _paras(items) -> str:
    return "".join(f'<p class="p">{_esc(p)}</p>' for p in (items or []))


# ---------- Estilo Instagram (teal) ----------
def _render_instagram(c: dict, formato: str, para_pdf: bool) -> str:
    TEAL, INK, CREAM = "#1C5A4E", "#123D34", "#F5F0E8"
    logo = _logo("logo_light.png")
    fonte = "Helvetica, Arial, sans-serif" if para_pdf else "'Archivo', Helvetica, Arial, sans-serif"
    gfont = "" if para_pdf else '<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;700;800;900&display=swap" rel="stylesheet">'
    # sombras/raios só no navegador (pisa ignora)
    card_sh = "" if para_pdf else "box-shadow:0 6px 22px rgba(18,61,52,.08); border-radius:12px;"
    cover_rad = "" if para_pdf else "border-radius:12px;"

    secoes = ""
    for i, s in enumerate(c.get("secoes", []), start=1):
        num = f'{i:02d}'
        if formato == "slides":
            # cada seção = um bloco/slide (quebra de página no PDF a partir do 2º)
            brk = 'style="page-break-before: always;"' if (para_pdf and i > 1) else ''
            secoes += f"""<div class="slide" {brk}>
              <div class="s-num">{num}</div>
              <h2 class="s-title">{_esc(s.get('titulo'))}</h2>
              <div class="s-card" style="{card_sh}">{_paras(s.get('paragrafos'))}{_bullets(s.get('bullets'),'bl')}</div>
            </div>"""
        else:
            # one_pager (compacto) e html (fluido)
            secoes += f"""<div class="sec">
              <div class="s-head"><span class="s-num">{num}</span><h2 class="s-title">{_esc(s.get('titulo'))}</h2></div>
              {_paras(s.get('paragrafos'))}{_bullets(s.get('bullets'),'bl')}
            </div>"""

    # densidade por formato
    if formato == "one_pager":
        pad, tsize, ptop = "26px", "26px", "14px"
    elif formato == "slides":
        pad, tsize, ptop = "34px", "30px", "20px"
    else:
        pad, tsize, ptop = "30px", "28px", "18px"

    logo_img = f'<img src="{logo}" width="150" style="margin-bottom:14px"/>' if logo else ''
    titulo, subtitulo, cta = _esc(c.get("titulo")), _esc(c.get("subtitulo")), _esc(c.get("cta"))
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<title>{titulo} — Pimenta Judice</title>{gfont}
<style>
  @page {{ size: A4; margin: 1.3cm; }}
  body {{ font-family: {fonte}; color: {INK}; margin: 0; background: #fff; }}
  .wrap {{ max-width: 760px; margin: 0 auto; padding: {pad}; }}
  .cover td {{ padding: 34px 38px; }}
  .cover .kick {{ color: {CREAM}; font-size: 12px; letter-spacing: 3px; }}
  .cover h1 {{ color: #fff; font-size: 32px; margin: 8px 0 6px; line-height: 1.14; font-weight: 800; }}
  .cover .sub {{ color: #e7f2ef; font-size: 15px; }}
  .sec {{ margin: {ptop} 0; }}
  .s-head {{ margin-bottom: 6px; }}
  .s-num {{ color: {TEAL}; font-weight: 800; font-size: 13px; letter-spacing: 2px; }}
  .s-title {{ display:inline; font-size: {tsize}; color: {INK}; margin: 0 0 0 10px; border-left: 4px solid {TEAL}; padding-left: 10px; }}
  .slide .s-title {{ display:block; margin: 4px 0 12px; padding-left: 12px; }}
  .slide {{ margin: 22px 0; }}
  .s-card {{ background: #f6faf9; border-left: 5px solid {TEAL}; padding: 18px 20px; }}
  .p {{ font-size: 14px; line-height: 1.6; color: #34413c; margin: {ptop} 0 6px; }}
  .bl {{ margin: 6px 0 6px 2px; padding-left: 18px; }}
  .bl li {{ font-size: 14px; line-height: 1.5; color: #34413c; margin: 3px 0; }}
  .cta {{ background: {CREAM}; border-left: 5px solid {TEAL}; padding: 18px 22px; margin-top: 22px; font-weight: 700; color: {TEAL}; {cover_rad} }}
  .foot {{ text-align: center; color: #8a9a95; font-size: 12px; margin-top: 22px; }}
  .foot b {{ color: {TEAL}; }}
</style></head><body><div class="wrap">
  <table class="cover" width="100%" cellpadding="0" cellspacing="0" style="{cover_rad}"><tr>
    <td bgcolor="{TEAL}" style="{cover_rad}">
      {logo_img}
      <div class="kick">MATERIAL GRATUITO</div>
      <h1>{titulo}</h1>
      <div class="sub">{subtitulo}</div>
    </td></tr></table>
  {secoes}
  <div class="cta">{cta}</div>
  <div class="foot"><b>@dr.lucasjudice</b> · Advogado Patrimonialista · pimentajudice.com.br</div>
</div></body></html>"""


# ---------- Estilo Site oficial (bege/preto, mais elaborado — landing page) ----------
def _render_site(c: dict, para_pdf: bool) -> str:
    BEGE, INK, TEAL, MUT = "#F1ECE1", "#1a1a1a", "#4a897c", "#6b655a"
    logo = _logo("logo_dark.png")
    serif = "Georgia, 'Times New Roman', serif" if para_pdf else "'Playfair Display', Georgia, serif"
    sans = "Helvetica, Arial, sans-serif" if para_pdf else "'Archivo', Helvetica, Arial, sans-serif"
    gfont = "" if para_pdf else '<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=Playfair+Display:wght@500;600;700;800&display=swap" rel="stylesheet">'

    secoes = ""
    for s in c.get("secoes", []):
        secoes += f"""<div class="sec">
          <h2>{_esc(s.get('titulo'))}</h2>
          {''.join(f'<p>{_esc(p)}</p>' for p in (s.get('paragrafos') or []))}
          {('<ul>' + ''.join(f'<li>{_esc(b)}</li>' for b in (s.get('bullets') or [])) + '</ul>') if s.get('bullets') else ''}
        </div>"""
    logo_img = f'<img src="{logo}" width="180" style="margin-bottom:26px"/>' if logo else ''
    titulo, subtitulo, cta = _esc(c.get("titulo")), _esc(c.get("subtitulo")), _esc(c.get("cta"))
    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<title>{titulo} — Pimenta Judice Advogados</title>{gfont}
<style>
  @page {{ size: A4; margin: 1.6cm; }}
  body {{ font-family: {sans}; color: {INK}; background: {BEGE}; margin: 0; }}
  .wrap {{ max-width: 820px; margin: 0 auto; padding: 56px 48px; background: {BEGE}; }}
  .hero {{ text-align: center; padding: 20px 0 36px; border-bottom: 1px solid #dcd4c5; margin-bottom: 40px; }}
  .hero .kick {{ font-size: 12px; letter-spacing: 5px; color: {TEAL}; text-transform: uppercase; }}
  .hero h1 {{ font-family: {serif}; font-weight: 700; font-size: 42px; line-height: 1.12; color: {INK}; margin: 16px 0 12px; }}
  .hero .sub {{ font-size: 17px; color: {MUT}; max-width: 620px; margin: 0 auto; line-height: 1.5; }}
  .sec {{ margin: 34px 0; }}
  .sec h2 {{ font-family: {serif}; font-weight: 600; font-size: 26px; color: {INK}; margin: 0 0 12px; }}
  .sec p {{ font-size: 16px; line-height: 1.75; color: #3a352c; margin: 10px 0; }}
  .sec ul {{ margin: 12px 0; padding-left: 20px; }}
  .sec li {{ font-size: 16px; line-height: 1.6; color: #3a352c; margin: 7px 0; }}
  .cta {{ text-align: center; border-top: 1px solid #dcd4c5; margin-top: 48px; padding-top: 40px; }}
  .cta .t {{ font-family: {serif}; font-size: 24px; color: {INK}; margin-bottom: 18px; }}
  .cta .btn {{ display: inline-block; background: {INK}; color: #fff; padding: 15px 34px; font-size: 14px; letter-spacing: 2px; text-transform: uppercase; text-decoration: none; }}
  .foot {{ text-align: center; color: {MUT}; font-size: 12px; margin-top: 40px; letter-spacing: 1px; }}
</style></head><body><div class="wrap">
  <div class="hero">{logo_img}<div class="kick">Pimenta Judice · Advogados Associados</div>
    <h1>{titulo}</h1><div class="sub">{subtitulo}</div></div>
  {secoes}
  <div class="cta"><div class="t">{cta}</div><a class="btn" href="https://www.pimentajudice.com.br">pimentajudice.com.br</a></div>
  <div class="foot">PIMENTA JUDICE ADVOGADOS ASSOCIADOS · PLANEJAMENTO PATRIMONIAL E SUCESSÓRIO</div>
</div></body></html>"""


def html_para_pdf(html: str) -> bytes:
    from xhtml2pdf import pisa
    buf = io.BytesIO()
    pisa.CreatePDF(src=html, dest=buf, encoding="utf-8")
    return buf.getvalue()
