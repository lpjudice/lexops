"""Informativo jurídico mensal — geração, sincronização com Google Docs,
validação de citações e publicação (PDF + Drive + rota pública do site).

Fluxo: cria-se um Google Doc a partir do MODELO de informativo (copiado uma
vez do timbrado do escritório, com cabeçalho estruturado — número, mês,
tema/subtema, resumo, separador, corpo) na pasta /Informativos/{AAAA-MM} do
Drive; opcionalmente a IA lê os arquivos de referência enviados e grava um
primeiro rascunho no corpo do Doc; o responsável edita lá; "sincronizar"
traz o corpo para o sistema; citações de lei/julgado são conferidas
(PrecedentCheck, com fallback de busca na web para citações de lei) antes
de liberar; "publicar" EXPORTA o próprio Google Doc (PDF e HTML) — o PDF
final é sempre o Doc timbrado tal como está, nunca um layout à parte.
"""
from __future__ import annotations

import base64
import io
import logging
import re
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models.informativo import RESPONSAVEL_PADRAO_NOME, Informativo, InformativoConfig
from app.models.responsavel import Responsavel

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def _mes_label(mes_referencia: date) -> str:
    return f"{MESES_PT[mes_referencia.month]}/{mes_referencia.year}"

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

    _provisionar_drive_e_doc(db, informativo)
    db.commit()
    db.refresh(informativo)
    return informativo


def obter_config(db: Session) -> InformativoConfig:
    cfg = db.get(InformativoConfig, 1)
    if not cfg:
        cfg = InformativoConfig(id=1)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def _garantir_template(db: Session) -> str | None:
    """Retorna o id do Google Doc-modelo dos informativos, criando-o (uma
    vez só) se ainda não existir."""
    cfg = obter_config(db)
    if cfg.template_doc_id:
        return cfg.template_doc_id

    try:
        from app.services.google_drive import resolver_pasta_id_raiz
        from app.services.google_docs import provisionar_template_informativo

        pasta_templates_id = resolver_pasta_id_raiz([DRIVE_ROOT_SUBPASTA, "Templates"])
        template = provisionar_template_informativo(parent_folder_id=pasta_templates_id)
    except Exception as exc:
        logger.warning("Falha ao provisionar o modelo de Informativo: %s", exc)
        template = None

    if not template:
        return None
    cfg.template_doc_id = template["id"]
    cfg.template_doc_link = template["webViewLink"]
    db.commit()
    return cfg.template_doc_id


def _provisionar_drive_e_doc(db: Session, informativo: Informativo) -> None:
    """Best-effort: cria a pasta do mês no Drive e, dentro dela, um Google
    Doc a partir do MODELO de informativo (com cabeçalho já preenchido).
    Resolve a pasta UMA VEZ só (id) e deriva o link dela do mesmo id — evita
    qualquer divergência entre o link mostrado e a pasta onde o Doc/PDF
    realmente vão parar. Falhas ficam em log — o usuário pode tentar de novo
    depois (ou escrever manualmente e vincular)."""
    pasta_id = None
    try:
        from app.services.google_drive import resolver_pasta_id_raiz
        subpath = [DRIVE_ROOT_SUBPASTA, _mes_slug(informativo.mes_referencia)]
        pasta_id = resolver_pasta_id_raiz(subpath)
        if pasta_id:
            informativo.drive_folder_link = f"https://drive.google.com/drive/folders/{pasta_id}"
    except Exception as exc:
        logger.warning("Informativo %s: falha ao preparar pasta no Drive: %s", informativo.id, exc)

    template_doc_id = _garantir_template(db)
    if not template_doc_id:
        logger.warning("Informativo %s: sem modelo disponível, Doc não criado.", informativo.id)
        return

    try:
        from app.services.google_docs import preencher_cabecalho_informativo
        from app.services.google_drive import copiar_arquivo_por_id

        cfg = obter_config(db)
        numero = cfg.proximo_numero
        cfg.proximo_numero = numero + 1
        db.commit()

        copia = copiar_arquivo_por_id(
            template_doc_id, f"Informativo nº {numero} — {informativo.titulo}", parent_folder_id=pasta_id
        )
        if copia:
            informativo.google_doc_id = copia["id"]
            informativo.google_doc_link = copia.get("webViewLink")
            informativo.numero = numero
            preencher_cabecalho_informativo(
                copia["id"], numero, _mes_label(informativo.mes_referencia),
                informativo.titulo, informativo.tema_resumido or "",
            )
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


# ── Rascunho inicial via IA (a partir dos arquivos de referência) ──────────
_PROMPT_RASCUNHO = """Você escreve o Informativo Jurídico Mensal do escritório Pimenta Judice
Advogados (planejamento patrimonial e sucessório, holdings, societário, reforma tributária).

TEMA DO MÊS: {tema}
{instrucoes_bloco}
Use os materiais anexados (se houver) como base de estudo — não invente fatos, números
ou julgados que não estejam no material ou que você não tenha certeza de que existem.
Se for citar lei ou julgado, cite de forma precisa (número, tribunal/artigo) só quando
tiver certeza; senão, escreva de forma genérica sem citar número específico.

REGRAS DE ESTILO (importantes, não quebre nenhuma):
- Texto corrido em parágrafos, quase sem listas com marcadores (no máximo uma, se for
  realmente necessária).
- Linguagem técnica mas acessível — não é uma petição, é um informativo para clientes.
- PROIBIDO usar travessão longo (—) ou meia-risca como pontuação de pausa — se precisar
  desse tipo de aposto, use parênteses.
- Nada de floreios típicos de texto gerado por IA (evite "é importante ressaltar",
  "em suma", "dito isso", frases de efeito genéricas).
- Extensão: para caber em 3-4 páginas de PDF (aproximadamente 900-1400 palavras).
- Comece direto com um parágrafo de abertura contextualizando o tema — sem título
  (o título já aparece no cabeçalho do documento).
- Use **negrito** (dois asteriscos) nos 3-6 termos ou trechos mais importantes do
  texto — não exagere, só o que realmente merece destaque.
- Inclua OBRIGATORIAMENTE pelo menos um bloco de destaque: um parágrafo iniciado
  por "> " (maior que, espaço) com uma citação literal de lei/julgado relevante ou
  uma frase-síntese do ponto central do informativo. Esse bloco quebra o visual de
  texto corrido — não coloque mais de dois no total.

Responda EXATAMENTE neste formato (sem markdown fora do combinado acima, sem
títulos de seção, sem numeração):

RESUMO: <1 a 2 frases curtas, ou só palavras-chave separadas por vírgula — isso
vai aparecer sozinho, resumido mesmo, no cabeçalho do informativo>
PERGUNTAS: <2 a 3 perguntas bem curtas e diretas, separadas por " | ", do tipo
"o que você vai encontrar neste informativo" — precisam despertar interesse
de continuar lendo (ex.: "O IVA Dual muda o seu contrato de locação?")>
---CORPO---
<o texto corrido do informativo, em parágrafos separados por linha em branco>"""


def _instrucoes_bloco(instrucoes: str | None) -> str:
    if not (instrucoes or "").strip():
        return ""
    return f"\nDIRECIONAMENTO DADO PELO ADVOGADO (siga à risca): {instrucoes.strip()}\n"


def gerar_rascunho_ia(informativo: Informativo) -> tuple[str, list[str], str, float]:
    """Lê os arquivos de referência (Drive) e escreve, com Claude, um
    resumo estruturado curto + perguntas-teaser + o corpo do informativo.
    Retorna (resumo, perguntas, corpo, custo_usd)."""
    from app.config import settings
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY não configurada.")
    import anthropic

    from app.services.google_drive import baixar_arquivo_por_id, extrair_file_id

    blocos: list[dict] = []
    for arquivo in (informativo.arquivos_referencia or [])[:8]:
        link = arquivo.get("link_drive")
        tipo = (arquivo.get("tipo") or "").lower()
        file_id = extrair_file_id(link) if link else None
        if not file_id:
            continue
        conteudo = baixar_arquivo_por_id(file_id)
        if not conteudo:
            continue
        b64 = base64.b64encode(conteudo).decode()
        if "pdf" in tipo:
            blocos.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}})
        elif "image" in tipo:
            blocos.append({"type": "image", "source": {"type": "base64", "media_type": tipo or "image/png", "data": b64}})
        # vídeo: sem suporte nativo no Claude — ignorado aqui (best-effort)

    tema = informativo.tema_resumido or informativo.titulo
    prompt = _PROMPT_RASCUNHO.format(tema=tema, instrucoes_bloco=_instrucoes_bloco(informativo.instrucoes_ia))
    conteudo_msg = blocos + [{"type": "text", "text": prompt}]

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.instagram_claude_model or "claude-opus-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": conteudo_msg}],
    )
    resposta = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text").strip()
    if not resposta:
        raise RuntimeError("A IA não retornou um rascunho válido.")

    resumo, perguntas, corpo = "", [], resposta
    if "---CORPO---" in resposta:
        cabeca, corpo = resposta.split("---CORPO---", 1)
        corpo = corpo.strip()
        for linha in cabeca.strip().splitlines():
            if linha.upper().startswith("RESUMO:"):
                resumo = linha.split(":", 1)[1].strip()
            elif linha.upper().startswith("PERGUNTAS:"):
                perguntas = [p.strip() for p in linha.split(":", 1)[1].split("|") if p.strip()]

    usage = getattr(msg, "usage", None)
    tin = getattr(usage, "input_tokens", 0) or 0
    tout = getattr(usage, "output_tokens", 0) or 0
    custo = round((tin * 5 + tout * 25) / 1_000_000, 5)  # estimativa (preço Opus)
    return resumo, perguntas, corpo, custo


def gerar_rascunho_e_gravar(informativo: Informativo) -> str:
    """Gera resumo + perguntas-teaser + corpo com IA e já grava no Google Doc
    vinculado — resumo e perguntas nos parágrafos abaixo de seus respectivos
    cabeçalhos, corpo depois do separador (o resto do cabeçalho estruturado
    não é tocado). Pode ser chamado de novo pra regenerar."""
    if not informativo.google_doc_id:
        raise RuntimeError("Este informativo ainda não tem um Google Doc vinculado.")
    resumo, perguntas, corpo, _custo = gerar_rascunho_ia(informativo)
    from app.services.google_docs import (
        substituir_corpo_informativo,
        substituir_perguntas_informativo,
        substituir_resumo_informativo,
    )
    if not substituir_corpo_informativo(informativo.google_doc_id, corpo):
        raise RuntimeError("Rascunho gerado, mas falhou ao gravar no Google Doc (verifique a autenticação Google).")
    if resumo:
        substituir_resumo_informativo(informativo.google_doc_id, resumo)
    if perguntas:
        substituir_perguntas_informativo(informativo.google_doc_id, perguntas)
    informativo.conteudo_texto = corpo
    informativo.rascunho_gerado_em = datetime.now(timezone.utc)
    if informativo.status == "rascunho":
        informativo.status = "primeiro_draft"
    return corpo


# ── Sincronização com o Google Doc ──────────────────────────────────────────
def sincronizar_do_doc(informativo: Informativo) -> str:
    """Traz só o CORPO do Doc (texto depois do separador) pro sistema —
    usado antes de validar citações. Não é necessário pra publicar: publicar
    exporta o Doc inteiro direto."""
    if not informativo.google_doc_id:
        raise RuntimeError("Este informativo ainda não tem um Google Doc vinculado.")
    from app.services.google_docs import ler_corpo_documento

    texto = ler_corpo_documento(informativo.google_doc_id)
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


# ── Exportação do Doc (fonte única de verdade — sem layout à parte) ────────
def preview_doc_html(informativo: Informativo) -> str:
    """HTML do Doc AGORA MESMO, exportado direto do Google Docs — reflete
    exatamente o que está no Doc (timbrado, formatação), sem precisar
    sincronizar antes."""
    if not informativo.google_doc_id:
        raise RuntimeError("Este informativo ainda não tem um Google Doc vinculado.")
    from app.services.google_drive import exportar_arquivo

    html_bytes = exportar_arquivo(informativo.google_doc_id, "text/html")
    if not html_bytes:
        raise RuntimeError("Não foi possível exportar o Doc (verifique a autenticação Google).")
    return html_bytes.decode("utf-8", errors="ignore")


def contar_paginas(pdf_bytes: bytes) -> int:
    from pypdf import PdfReader
    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


# ── Publicação ───────────────────────────────────────────────────────────────
def publicar(db: Session, informativo: Informativo) -> dict:
    """Exporta o PRÓPRIO Google Doc (timbrado + tudo que está escrito nele)
    como PDF e HTML, salva o PDF na pasta do mês no Drive e disponibiliza a
    versão pública. Não depende de ter sincronizado antes — publica o que
    estiver no Doc neste momento."""
    if not informativo.google_doc_id:
        raise RuntimeError("Este informativo ainda não tem um Google Doc vinculado.")

    from app.services.google_drive import exportar_arquivo, upload_arquivo_raiz

    pdf_bytes = exportar_arquivo(informativo.google_doc_id, "application/pdf")
    if not pdf_bytes:
        raise RuntimeError("Falha ao exportar o PDF do Google Doc (verifique a autenticação Google).")
    html_bytes = exportar_arquivo(informativo.google_doc_id, "text/html")
    html = html_bytes.decode("utf-8", errors="ignore") if html_bytes else (informativo.conteudo_html or "")

    paginas = contar_paginas(pdf_bytes)

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
