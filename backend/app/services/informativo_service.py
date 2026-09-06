"""Informativo jurídico mensal — geração, sincronização com Google Docs,
validação de citações e publicação (PDF + Drive + rota pública do site).

Fluxo: cria-se um Google Doc em branco na pasta /Informativos/{AAAA-MM} do
Drive; o responsável escreve lá; "sincronizar" traz o texto para o sistema;
citações de lei/julgado são conferidas (PrecedentCheck, com fallback de
busca na web para citações de lei) antes de liberar; "publicar" renderiza o
HTML no layout padrão do escritório, converte em PDF, salva no Drive e
disponibiliza a versão pública (site → seção Informativos).
"""
from __future__ import annotations

import html as _html
import io
import logging
import re
from calendar import monthrange
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.informativo import RESPONSAVEL_PADRAO_NOME, Informativo
from app.models.responsavel import Responsavel

logger = logging.getLogger(__name__)

DRIVE_ROOT_SUBPASTA = "Informativos"
LIMITE_PAGINAS = 4
LIMITE_PAGINAS_PREFERIDO = 3


# ── Prazos internos ─────────────────────────────────────────────────────────
def calcular_prazos(mes_referencia: date) -> tuple[date, date]:
    """1º draft: 15 dias antes do fim do mês anterior. Versão revisada/final:
    7 dias antes do início do mês de referência."""
    primeiro_dia = mes_referencia.replace(day=1)
    from datetime import timedelta
    data_prazo_final = primeiro_dia - timedelta(days=7)
    fim_mes_anterior = primeiro_dia - timedelta(days=1)
    data_prazo_draft = fim_mes_anterior - timedelta(days=15)
    return data_prazo_draft, data_prazo_final


def resolver_responsavel_padrao(db: Session) -> Responsavel | None:
    return (
        db.query(Responsavel)
        .filter(Responsavel.nome.ilike(f"%{RESPONSAVEL_PADRAO_NOME}%"), Responsavel.ativo.is_(True))
        .first()
    )


def _mes_slug(mes_referencia: date) -> str:
    return mes_referencia.strftime("%Y-%m")


# ── Criação (Google Doc + pasta Drive) ──────────────────────────────────────
def criar_informativo(
    db: Session,
    mes_referencia: date,
    titulo: str,
    responsavel_id=None,
    tema_resumido: str | None = None,
    tema_sugestao_id=None,
) -> Informativo:
    mes_referencia = mes_referencia.replace(day=1)
    data_prazo_draft, data_prazo_final = calcular_prazos(mes_referencia)

    if responsavel_id is None:
        padrao = resolver_responsavel_padrao(db)
        responsavel_id = padrao.id if padrao else None

    informativo = Informativo(
        mes_referencia=mes_referencia,
        titulo=titulo or f"Informativo {mes_referencia.strftime('%m/%Y')}",
        tema_resumido=tema_resumido,
        tema_sugestao_id=tema_sugestao_id,
        responsavel_id=responsavel_id,
        data_prazo_draft=data_prazo_draft,
        data_prazo_final=data_prazo_final,
        status="rascunho",
    )
    db.add(informativo)
    db.commit()
    db.refresh(informativo)

    _provisionar_drive_e_doc(informativo)
    db.commit()
    db.refresh(informativo)
    return informativo


def _provisionar_drive_e_doc(informativo: Informativo) -> None:
    """Best-effort: cria a pasta do mês no Drive e um Google Doc em branco
    dentro dela. Falhas ficam em log — o usuário pode tentar de novo depois."""
    try:
        from app.services.google_drive import get_folder_link_raiz, resolver_pasta_id_raiz
        subpath = [DRIVE_ROOT_SUBPASTA, _mes_slug(informativo.mes_referencia)]
        informativo.drive_folder_link = get_folder_link_raiz(subpath)
        pasta_id = resolver_pasta_id_raiz(subpath)
    except Exception as exc:
        logger.warning("Informativo %s: falha ao preparar pasta no Drive: %s", informativo.id, exc)
        pasta_id = None

    try:
        from app.services.google_docs import criar_documento_em_branco
        doc = criar_documento_em_branco(f"Informativo {informativo.titulo}", parent_folder_id=pasta_id)
        if doc:
            informativo.google_doc_id = doc["id"]
            informativo.google_doc_link = doc["webViewLink"]
    except Exception as exc:
        logger.warning("Informativo %s: falha ao criar Google Doc: %s", informativo.id, exc)


def upload_arquivo_referencia(informativo: Informativo, conteudo: bytes, nome_arquivo: str, mimetype: str) -> None:
    """Sobe um arquivo de estudo (imagem/vídeo/PDF) pra pasta do mês no Drive
    e registra em `arquivos_referencia`."""
    from app.services.google_drive import upload_arquivo_raiz

    subpath = [DRIVE_ROOT_SUBPASTA, _mes_slug(informativo.mes_referencia), "Material de apoio"]
    link = upload_arquivo_raiz(conteudo, nome_arquivo, subpath, mimetype)
    if not link:
        raise RuntimeError("Falha ao subir o arquivo no Drive (verifique a autenticação Google).")
    atual = list(informativo.arquivos_referencia or [])
    atual.append({"nome": nome_arquivo, "link_drive": link, "tipo": mimetype})
    informativo.arquivos_referencia = atual


# ── Sincronização com o Google Doc ──────────────────────────────────────────
def sincronizar_do_doc(informativo: Informativo) -> str:
    if not informativo.google_doc_id:
        raise RuntimeError("Este informativo ainda não tem um Google Doc vinculado.")
    from app.services.google_docs import ler_texto_documento

    texto = ler_texto_documento(informativo.google_doc_id)
    if texto is None:
        raise RuntimeError("Não foi possível ler o Google Doc (verifique a autenticação Google).")
    informativo.conteudo_texto = texto.strip()
    if informativo.status == "rascunho" and informativo.conteudo_texto:
        informativo.status = "primeiro_draft"
    return informativo.conteudo_texto


# ── Validação de citações (lei e julgado) ───────────────────────────────────
_PADRAO_LEI = re.compile(
    r"(?:art(?:igo)?s?\.?\s*\d+[\wº°,.\s-]*(?:d[aoe]\s+(?:lei|c[oó]digo|constitui[cç][aã]o|decreto)[^.,;\n]{0,80})"
    r"|lei\s+(?:complementar\s+)?n?[ºo°]?\s*[\d./-]+)",
    re.IGNORECASE,
)


def _extrair_trechos_lei(texto: str) -> list[str]:
    achados = {m.group(0).strip() for m in _PADRAO_LEI.finditer(texto)}
    return list(achados)[:20]


def _verificar_citacao_lei(trecho: str, contexto: str) -> dict:
    """Confere um artigo/lei citado usando o mesmo mecanismo de web_search do
    PrecedentCheck, adaptado (sem tribunal/relator)."""
    from app.services.precedentcheck_service import _chamar_claude, _parse_json_object

    prompt = f"""Você é um validador de citações jurídicas. Verifique se o dispositivo legal
abaixo existe e se o trecho citado corresponde ao teor real da norma. Use busca na
web para confirmar no texto oficial (Planalto, sites de legislação confiáveis).
NÃO invente conteúdo — se não achar a norma, diga que não encontrou.

DISPOSITIVO CITADO: {trecho}
CONTEXTO NO TEXTO: {contexto[:500]}

Responda APENAS com JSON:
{{"status_geral": "confirmado" | "divergente" | "nao_encontrado", "observacao": "..."}}"""
    resposta, custo = _chamar_claude(prompt, com_web_search=True)
    verificacao = _parse_json_object(resposta) or {"status_geral": "nao_encontrado", "observacao": "Sem resposta válida"}
    verificacao["referencia_original"] = {"tipo": "lei", "trecho_citado": trecho}
    verificacao["custo_usd"] = custo
    return verificacao


def validar_citacoes(informativo: Informativo) -> list[dict]:
    texto = informativo.conteudo_texto or ""
    if not texto.strip():
        raise RuntimeError("Sincronize o texto do Doc antes de validar as citações.")

    from app.services.precedentcheck_service import extrair_citacoes, verificar_citacao

    resultados: list[dict] = []

    citacoes_julgado, _custo = extrair_citacoes(texto)
    for citacao in citacoes_julgado:
        resultados.append(verificar_citacao(citacao, texto))

    for trecho in _extrair_trechos_lei(texto):
        idx = texto.find(trecho)
        contexto = texto[max(0, idx - 200): idx + 200] if idx >= 0 else texto[:400]
        resultados.append(_verificar_citacao_lei(trecho, contexto))

    informativo.citacoes_validadas = resultados
    return resultados


# ── Render HTML (layout padrão) ─────────────────────────────────────────────
TEAL = "#1C5A4E"
INK = "#123D34"
CREAM = "#F5F0E8"


def _esc(t) -> str:
    return _html.escape(str(t or ""))


def _texto_para_paragrafos_html(texto: str) -> str:
    blocos = [b.strip() for b in re.split(r"\n{2,}", texto or "") if b.strip()]
    return "".join(f'<p class="corpo">{_esc(b)}</p>' for b in blocos)


def gerar_html(informativo: Informativo, para_pdf: bool = False) -> str:
    """Layout do Informativo Pimenta Judice: capa teal com título + mês,
    corpo em Georgia/serif (título)/Archivo (texto), rodapé com marca."""
    from app.services import brinde_instagram
    logo = brinde_instagram._logo("logo_light.png")

    fonte_serif = "Georgia, 'Times New Roman', serif" if para_pdf else "'Playfair Display', Georgia, serif"
    fonte_sans = "Helvetica, Arial, sans-serif" if para_pdf else "'Archivo', Helvetica, Arial, sans-serif"
    gfont = "" if para_pdf else (
        '<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700'
        '&family=Playfair+Display:wght@600;700;800&display=swap" rel="stylesheet">'
    )
    logo_img = f'<img src="{logo}" width="150" style="margin-bottom:16px"/>' if logo else ""
    mes_label = informativo.mes_referencia.strftime("%m.%Y")
    corpo_html = _texto_para_paragrafos_html(informativo.conteudo_texto or "")

    return f"""<!DOCTYPE html><html lang="pt-BR"><head><meta charset="utf-8">
<title>{_esc(informativo.titulo)} — Pimenta Judice</title>{gfont}
<style>
  @page {{ size: A4; margin: 1.8cm 2cm; }}
  body {{ font-family: {fonte_sans}; color: #262b28; margin: 0; background: #fff; }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  .capa {{ background: {TEAL}; color: #fff; padding: 40px 44px; margin-bottom: 30px; }}
  .capa .kick {{ font-size: 12px; letter-spacing: 3px; color: {CREAM}; text-transform: uppercase; }}
  .capa h1 {{ font-family: {fonte_serif}; font-weight: 700; font-size: 30px; line-height: 1.2; margin: 10px 0 4px; }}
  .capa .num {{ font-size: 13px; color: #e7f2ef; margin-top: 6px; }}
  .corpo {{ font-size: 14.5px; line-height: 1.75; text-align: justify; color: #262b28; margin: 0 0 14px; }}
  .foot {{ text-align: center; color: #8a9a95; font-size: 11px; margin-top: 34px; padding-top: 14px; border-top: 1px solid #e5e5e5; }}
  .foot b {{ color: {TEAL}; }}
</style></head><body><div class="wrap">
  <div class="capa">
    {logo_img}
    <div class="kick">Informativo Mensal</div>
    <h1>{_esc(informativo.titulo)}</h1>
    <div class="num">Edição {mes_label}</div>
  </div>
  {corpo_html}
  <div class="foot"><b>Pimenta Judice Advogados</b> · Planejamento Patrimonial e Sucessório · pimentajudice.com.br</div>
</div></body></html>"""


def html_para_pdf(html: str) -> bytes:
    from xhtml2pdf import pisa
    buf = io.BytesIO()
    pisa.CreatePDF(src=html, dest=buf, encoding="utf-8")
    return buf.getvalue()


def contar_paginas(pdf_bytes: bytes) -> int:
    from pypdf import PdfReader
    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


# ── Publicação ───────────────────────────────────────────────────────────────
def publicar(db: Session, informativo: Informativo) -> dict:
    if not (informativo.conteudo_texto or "").strip():
        raise RuntimeError("Sincronize o texto do Doc antes de publicar.")

    html = gerar_html(informativo, para_pdf=False)
    pdf_html = gerar_html(informativo, para_pdf=True)
    pdf_bytes = html_para_pdf(pdf_html)
    paginas = contar_paginas(pdf_bytes)

    from app.services.google_drive import upload_arquivo_raiz
    slug = re.sub(r"[^a-z0-9]+", "-", (informativo.titulo or "informativo").lower()).strip("-")[:60] or "informativo"
    subpath = [DRIVE_ROOT_SUBPASTA, _mes_slug(informativo.mes_referencia)]
    pdf_link = upload_arquivo_raiz(pdf_bytes, f"{slug}.pdf", subpath, "application/pdf")

    informativo.conteudo_html = html
    informativo.paginas_estimadas = paginas
    informativo.drive_pdf_link = pdf_link
    informativo.status = "publicado"
    informativo.publicado_em = datetime.now(timezone.utc)

    aviso = None
    if paginas > LIMITE_PAGINAS:
        aviso = f"O PDF ficou com {paginas} páginas (limite recomendado: {LIMITE_PAGINAS_PREFERIDO}-{LIMITE_PAGINAS})."
    elif paginas > LIMITE_PAGINAS_PREFERIDO:
        aviso = f"O PDF ficou com {paginas} páginas (preferência: até {LIMITE_PAGINAS_PREFERIDO})."

    return {"paginas": paginas, "aviso": aviso, "pdf_link": pdf_link}
