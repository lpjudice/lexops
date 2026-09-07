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
    """Responsável padrão pra informativos novos — lido de
    InformativoConfig.responsavel_padrao_id (editável na tela principal).
    Na primeira vez (config ainda sem valor), semeia buscando por nome
    (RESPONSAVEL_PADRAO_NOME) e já grava isso como o padrão daqui pra
    frente — depois disso, só muda se alguém trocar explicitamente."""
    cfg = obter_config(db)
    if cfg.responsavel_padrao_id:
        resp = db.get(Responsavel, cfg.responsavel_padrao_id)
        if resp:
            return resp

    padrao = (
        db.query(Responsavel)
        .filter(Responsavel.nome.ilike(f"%{RESPONSAVEL_PADRAO_NOME}%"), Responsavel.ativo.is_(True))
        .first()
    )
    if padrao:
        cfg.responsavel_padrao_id = padrao.id
        db.commit()
    return padrao


def definir_responsavel_padrao(db: Session, responsavel_id) -> Responsavel | None:
    """Troca o responsável padrão de informativos futuros. Não altera
    informativos já criados."""
    cfg = obter_config(db)
    cfg.responsavel_padrao_id = responsavel_id
    db.commit()
    if not responsavel_id:
        return None
    return db.get(Responsavel, responsavel_id)


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
- PROIBIDO terminar com frase de call-to-action tipo "o escritório permanece à
  disposição", "nos procure", "entre em contato", "estamos à disposição" ou
  qualquer variação — é um informativo de conteúdo, não um texto de venda.
  Termine com um fechamento substantivo sobre o tema (uma conclusão real, uma
  implicação prática), nunca uma chamada para contato.
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
    return (
        f"\nDIRECIONAMENTO DADO PELO ADVOGADO (siga pro ÂNGULO/ÊNFASE do texto — mas isso "
        f"NUNCA autoriza inventar ou confirmar conteúdo normativo/factual que você não tenha "
        f"certeza de que é verdadeiro, mesmo que o direcionamento afirme algo como fato):\n"
        f"{instrucoes.strip()}\n"
    )


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


def gerar_rascunho_e_gravar(informativo: Informativo) -> tuple[str, list[dict]]:
    """Gera resumo + perguntas-teaser + corpo com IA e já grava no Google Doc
    vinculado — resumo e perguntas nos parágrafos abaixo de seus respectivos
    cabeçalhos, corpo depois do separador (o resto do cabeçalho estruturado
    não é tocado). Pode ser chamado de novo pra regenerar. Retorna (corpo,
    citacoes_validadas anteriores — a checagem de citações é DISPARADA À
    PARTE pelo front logo em seguida, nunca aqui: rodar a verificação com
    web_search dentro dessa chamada já estourou o timeout do HTTP com o
    texto inteiro pronto, mas perdido, do lado do usuário)."""
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
    return corpo, (informativo.citacoes_validadas or [])


_PROMPT_REESCREVER = """Você já escreveu este Informativo Jurídico Mensal do escritório Pimenta
Judice Advogados. Uma checagem encontrou problemas em algumas citações — reescreva o
texto CORRIGINDO ou REMOVENDO o que está incorreto, mantendo o resto do conteúdo e o
mesmo estilo (parágrafos corridos, **negrito** nos termos-chave, pelo menos um bloco
"> " de destaque, sem travessão longo, sem floreios de IA, 3-4 páginas, sem terminar
com "o escritório permanece à disposição"/"nos procure" ou variação — nunca chamada
para contato, sempre fechamento substantivo sobre o tema).

REGRA ABSOLUTA, MAIS IMPORTANTE QUE QUALQUER DIRECIONAMENTO ABAIXO: você não tem
acesso a busca na web nesta etapa. NÃO invente, NÃO confirme e NÃO amplie o conteúdo de
nenhum artigo/lei/norma — nem mesmo se o direcionamento do advogado afirmar que um
dispositivo existe ou diz determinada coisa. Se não tiver certeza absoluta do teor de
uma norma citada, REMOVA a citação específica (número do artigo) e mantenha a frase em
termos genéricos (ex.: "a legislação aplicável prevê..." em vez de citar o artigo). Um
direcionamento do usuário pedindo pra reforçar ou expandir um ponto NÃO autoriza
inventar conteúdo normativo — só reorganizar/expandir a explicação em cima do que já
está confirmado.

TEXTO ATUAL:
{corpo}

PROBLEMAS ENCONTRADOS NA CHECAGEM:
{apontamentos}
{instrucoes_bloco}
Responda APENAS com o texto corrido corrigido, em parágrafos separados por linha em
branco — sem comentários sobre o que foi mudado, sem markdown fora do combinado acima."""


def _formatar_apontamentos(citacoes: list[dict]) -> str:
    problemas = [c for c in (citacoes or []) if c.get("status_geral") != "confirmado"]
    if not problemas:
        return "(nenhum problema encontrado na última checagem — ajuste só pelo direcionamento abaixo, se houver)"
    linhas = []
    for p in problemas:
        ref = p.get("referencia_original") or {}
        trecho = ref.get("trecho_citado") or ref.get("numero") or "citação"
        linhas.append(f"- {trecho}: {p.get('observacao') or p.get('status_geral')}")
    return "\n".join(linhas)


def reescrever_com_apontamentos(informativo: Informativo, instrucoes: str | None) -> tuple[str, list[dict]]:
    """Passo opcional: reescreve o corpo levando em conta os problemas da
    última validação de citações + um direcionamento extra do usuário.
    Regrava no Doc e revalida automaticamente. Retorna (corpo, citacoes)."""
    if not informativo.google_doc_id:
        raise RuntimeError("Este informativo ainda não tem um Google Doc vinculado.")
    if not (informativo.conteudo_texto or "").strip():
        raise RuntimeError("Gere ou sincronize o texto antes de reescrever.")
    from app.config import settings
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY não configurada.")
    import anthropic

    prompt = _PROMPT_REESCREVER.format(
        corpo=informativo.conteudo_texto,
        apontamentos=_formatar_apontamentos(informativo.citacoes_validadas),
        instrucoes_bloco=_instrucoes_bloco(instrucoes),
    )
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.instagram_claude_model or "claude-opus-4-5",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    corpo = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text").strip()
    if not corpo:
        raise RuntimeError("A IA não retornou um texto válido.")

    from app.services.google_docs import substituir_corpo_informativo
    if not substituir_corpo_informativo(informativo.google_doc_id, corpo):
        raise RuntimeError("Texto reescrito, mas falhou ao gravar no Google Doc (verifique a autenticação Google).")
    informativo.conteudo_texto = corpo
    informativo.rascunho_gerado_em = datetime.now(timezone.utc)
    return corpo, (informativo.citacoes_validadas or [])


# ── Sincronização com o Google Doc ──────────────────────────────────────────
def sincronizar_do_doc(informativo: Informativo) -> tuple[str, list[dict]]:
    """Traz só o CORPO do Doc (texto depois do separador) pro sistema — útil
    quando o texto foi editado direto no Doc, sem passar pela IA. Não é
    necessário pra publicar: publicar exporta o Doc inteiro direto. A
    checagem de citações é disparada à parte pelo front (ver
    `_validar_citacoes_best_effort` — não roda mais aqui pra não estourar o
    timeout do HTTP). Retorna (texto, citacoes_validadas anteriores)."""
    if not informativo.google_doc_id:
        raise RuntimeError("Este informativo ainda não tem um Google Doc vinculado.")
    from app.services.google_docs import ler_corpo_documento

    texto = ler_corpo_documento(informativo.google_doc_id)
    if texto is None:
        raise RuntimeError("Não foi possível ler o Google Doc (verifique a autenticação Google).")
    informativo.conteudo_texto = texto.strip()
    if informativo.status == "rascunho" and informativo.conteudo_texto:
        informativo.status = "primeiro_draft"
    return informativo.conteudo_texto, (informativo.citacoes_validadas or [])


# ── Validação de citações (lei/normativo e julgado) ─────────────────────────
def _extrair_trechos_normativos(texto: str) -> list[str]:
    """Detecção de citações de LEI/NORMA via IA — NÃO regex. Regex baseada em
    "art. X da lei/código/decreto" tem pontos cegos graves: não pega
    "Instrução CVM", "Resolução BACEN", "Regulamento X da CVM", "Portaria",
    Medida Provisória etc. Chamada barata (sem web_search, poucos tokens)."""
    from app.config import settings
    if not settings.anthropic_api_key or not (texto or "").strip():
        return []
    import anthropic
    import json as _json

    prompt = f"""Liste TODAS as citações de normas jurídicas mencionadas no texto abaixo —
lei, decreto, instrução normativa, instrução/resolução/deliberação de órgão regulador
(CVM, BACEN, Receita Federal, ANVISA etc.), portaria, medida provisória, código,
constituição, regulamento. Inclua o artigo/dispositivo específico quando houver.
NÃO avalie se a citação está certa — só extraia o que está citado, literalmente
como aparece no texto. Se não houver nenhuma citação normativa, responda [].

TEXTO:
{texto[:8000]}

Responda APENAS com um array JSON de strings (sem markdown), cada uma o trecho exato
da citação — ex.: ["art. 1.055 do Código Civil", "Instrução CVM nº 400/2003, art. 4º",
"Resolução CMN nº 4.557/2017"]."""

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        msg = client.messages.create(model="claude-sonnet-4-6", max_tokens=800,
                                      messages=[{"role": "user", "content": prompt}])
    except Exception as exc:
        logger.warning("Falha ao extrair citações normativas: %s", exc)
        return []
    texto_resp = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
    m = re.search(r"\[.*\]", texto_resp, re.DOTALL)
    if not m:
        return []
    try:
        lista = _json.loads(m.group(0))
        return [str(x).strip() for x in lista if str(x).strip()][:20]
    except Exception:
        return []


def detectar_citacoes(texto: str) -> tuple[list[dict], list[str]]:
    """Detecção BARATA (sem custo de web_search) — só pra saber se vale a
    pena rodar a verificação de verdade. Retorna (candidatos_julgado,
    trechos_normativos)."""
    if not (texto or "").strip():
        return [], []
    from app.services.precedentcheck_service import extrair_citacoes

    citacoes_julgado, _custo = extrair_citacoes(texto)
    trechos_normativos = _extrair_trechos_normativos(texto)
    return citacoes_julgado, trechos_normativos


def _verificar_citacao_lei(trecho: str, contexto: str) -> dict:
    """Confere um artigo/lei citado — chamada PRÓPRIA (não reaproveita o
    _chamar_claude do PrecedentCheck, que restringe a busca a domínios de
    jurisprudência (STJ/STF/Jusbrasil), errados pra achar o texto de uma
    LEI). NÃO restringe domínio — cobre lei federal (Planalto), estadual e
    municipal (cada uma no site oficial correspondente, que varia por
    estado/município). Custo baixo vem de max_tokens pequeno e no máx.
    2 buscas, não de restrição de domínio."""
    from app.config import settings
    if not settings.anthropic_api_key:
        return {"status_geral": "nao_encontrado", "observacao": "IA não configurada.",
                "referencia_original": {"tipo": "lei", "trecho_citado": trecho}, "custo_usd": 0.0}
    import anthropic

    prompt = f"""Você é um validador de citações jurídicas. Verifique se o dispositivo legal
abaixo existe e se o trecho citado corresponde ao teor real da norma. Use busca na web
pra confirmar no site oficial (Planalto pra lei federal; site oficial do estado/
município correspondente pra lei estadual/municipal). NÃO invente conteúdo — se não
achar a norma ou o dispositivo específico, diga que não encontrou.

DISPOSITIVO CITADO: {trecho}
CONTEXTO NO TEXTO: {contexto[:500]}

Responda APENAS com JSON (sem markdown):
{{
  "status_geral": "confirmado" | "divergente" | "nao_encontrado",
  "observacao": "explicação curta e objetiva da divergência (se houver) ou confirmação",
  "texto_integral": "o texto oficial completo do dispositivo (caput + parágrafos/incisos pertinentes), ou vazio se não encontrado",
  "url_oficial": "URL da norma no site oficial (Planalto ou o site oficial do estado/município), ou vazio se não encontrado"
}}"""

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 2,
            }],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        logger.warning("Falha ao verificar citação de lei: %s", exc)
        return {"status_geral": "nao_encontrado", "observacao": f"Falha na verificação: {exc}",
                "referencia_original": {"tipo": "lei", "trecho_citado": trecho}, "custo_usd": 0.0}

    texto_resp = "\n".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
    from app.services.precedentcheck_service import _parse_json_object
    verificacao = _parse_json_object(texto_resp) or {"status_geral": "nao_encontrado", "observacao": "Sem resposta válida"}

    usage = getattr(msg, "usage", None)
    tin = getattr(usage, "input_tokens", 0) or 0
    tout = getattr(usage, "output_tokens", 0) or 0
    custo = (tin * 3.0 + tout * 15.0) / 1_000_000
    server_tool = getattr(usage, "server_tool_use", None)
    buscas = getattr(server_tool, "web_search_requests", 0) or 0
    custo += buscas * 0.01

    verificacao["referencia_original"] = {"tipo": "lei", "trecho_citado": trecho}
    verificacao["custo_usd"] = round(custo, 4)
    return verificacao


def validar_citacoes(informativo: Informativo) -> list[dict]:
    """Detecta candidatos e, só se houver algum, roda a verificação de
    verdade (com custo de web_search). Chamado automaticamente depois de
    gerar/sincronizar o texto — mas pode ser rechamado manualmente."""
    texto = informativo.conteudo_texto or ""
    if not texto.strip():
        raise RuntimeError("Sincronize o texto do Doc antes de validar as citações.")

    from app.services.precedentcheck_service import verificar_citacao

    citacoes_julgado, trechos_lei = detectar_citacoes(texto)
    resultados: list[dict] = []

    for citacao in citacoes_julgado:
        resultados.append(verificar_citacao(citacao, texto))

    for trecho in trechos_lei:
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


# ── Distribuição (newsletter) ───────────────────────────────────────────────
def _link_publico(informativo: Informativo) -> str:
    """Link direto pro informativo na página pública (não a home)."""
    from app.config import settings
    base = (settings.frontend_url or "").rstrip("/")
    if not base or "localhost" in base or "127.0.0.1" in base:
        base = "https://lexops.fly.dev"
    return f"{base}/api/publico/informativos/{informativo.id}.html"


def listar_destinatarios_newsletter(db: Session) -> list[tuple[str, str]]:
    """Une Cliente.email + ConselhoContato.email + InformativoAssinante
    (inscrição pública), deduplicados por e-mail (case-insensitive), menos
    quem estiver na lista de opt-out. Retorna [(email, nome), ...]."""
    from app.models.cliente import Cliente
    from app.models.conselho import ConselhoContato
    from app.models.informativo import InformativoAssinante, InformativoOptOut

    optados_fora = {
        (e or "").strip().lower() for (e,) in db.query(InformativoOptOut.email).all()
    }

    vistos: dict[str, str] = {}

    for nome, email in db.query(Cliente.nome, Cliente.email).filter(Cliente.email.isnot(None)).all():
        chave = (email or "").strip().lower()
        if chave and "@" in chave and chave not in vistos and chave not in optados_fora:
            vistos[chave] = nome or ""

    for primeiro, sobre, email in (
        db.query(ConselhoContato.primeiro_nome, ConselhoContato.sobrenome, ConselhoContato.email)
        .filter(ConselhoContato.email.isnot(None)).all()
    ):
        chave = (email or "").strip().lower()
        if chave and "@" in chave and chave not in vistos and chave not in optados_fora:
            vistos[chave] = " ".join(p for p in [primeiro, sobre] if p)

    for nome, email in (
        db.query(InformativoAssinante.nome, InformativoAssinante.email)
        .filter(InformativoAssinante.ativo.is_(True)).all()
    ):
        chave = (email or "").strip().lower()
        if chave and chave not in vistos and chave not in optados_fora:
            vistos[chave] = nome or ""

    return list(vistos.items())


def _link_opt_out(email: str) -> str:
    from app.config import settings
    import urllib.parse
    base = (settings.frontend_url or "").rstrip("/")
    if not base or "localhost" in base or "127.0.0.1" in base:
        base = "https://lexops.fly.dev"
    return f"{base}/api/publico/informativos/opt-out?email={urllib.parse.quote(email)}"


def montar_email_newsletter(informativo: Informativo, destinatario_email: str | None = None) -> tuple[str, str]:
    """(assunto, html) do e-mail da newsletter — resumo do Doc + link direto
    pro informativo no site + aviso de que o PDF vai anexado + link de
    descadastro (opt-out) no rodapé. `destinatario_email` personaliza o link
    de opt-out; sem ele, o link fica genérico (usado em pré-visualização/teste)."""
    resumo = None
    if informativo.google_doc_id:
        from app.services.google_docs import ler_resumo_documento
        try:
            resumo = ler_resumo_documento(informativo.google_doc_id)
        except Exception:
            resumo = None

    mes_label = _mes_label(informativo.mes_referencia)
    link = _link_publico(informativo)
    assunto = f"Informativo Pimenta Judice — {informativo.titulo}"
    link_optout = _link_opt_out(destinatario_email or "")

    resumo_html = f'<p style="font-size:15px;line-height:1.6;color:#333;">{resumo}</p>' if resumo else ""
    html = f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
      <div style="background:#1C5A4E;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0;">
        <div style="font-size:11px;letter-spacing:2px;opacity:.85;text-transform:uppercase;">Informativo · {mes_label}</div>
        <h2 style="margin:8px 0 0;">{informativo.titulo}</h2>
      </div>
      <div style="padding:22px 24px;border:1px solid #e5e5e5;border-top:none;border-radius:0 0 8px 8px;">
        {resumo_html}
        <p style="font-size:14px;color:#555;">O PDF completo vai anexado neste e-mail. Você também pode ler direto no site:</p>
        <a href="{link}" style="display:inline-block;background:#1C5A4E;color:#fff;text-decoration:none;font-weight:700;padding:12px 24px;border-radius:999px;font-size:14px;">Ler no site →</a>
      </div>
      <p style="text-align:center;font-size:11px;color:#999;margin-top:14px;">
        Pimenta Judice Advogados — Planejamento Patrimonial e Sucessório<br>
        <a href="{link_optout}" style="color:#999;">Não quero mais receber estes e-mails</a>
      </p>
    </div>"""
    return assunto, html


def _baixar_pdf_informativo(informativo: Informativo) -> bytes:
    if informativo.status != "publicado" or not informativo.drive_pdf_link:
        raise RuntimeError("Publique o informativo antes de enviar a newsletter.")
    from app.services.google_drive import baixar_arquivo_por_id, extrair_file_id
    file_id = extrair_file_id(informativo.drive_pdf_link)
    pdf_bytes = baixar_arquivo_por_id(file_id) if file_id else None
    if not pdf_bytes:
        raise RuntimeError("Não consegui baixar o PDF do Drive pra anexar (verifique a autenticação Google).")
    return pdf_bytes


def enviar_newsletter_teste(informativo: Informativo, email: str) -> None:
    """Manda a newsletter (mesmo conteúdo real) só pra UM e-mail digitado na
    hora — pra conferir antes de disparar pra todo mundo. Não mexe na lista
    de destinatários real nem em nada persistido."""
    email = (email or "").strip()
    if not email or "@" not in email:
        raise RuntimeError("E-mail inválido.")
    pdf_bytes = _baixar_pdf_informativo(informativo)
    slug = re.sub(r"[^a-z0-9]+", "-", (informativo.titulo or "informativo").lower()).strip("-")[:60] or "informativo"
    assunto, html = montar_email_newsletter(informativo, destinatario_email=email)
    from app.services.email_service import _send_via_gmail_oauth
    _send_via_gmail_oauth(email, f"[TESTE] {assunto}", html, attachments=[(f"{slug}.pdf", pdf_bytes)])


def enviar_newsletter(db: Session, informativo: Informativo) -> dict:
    """Envia o e-mail da newsletter (resumo + link + PDF anexado) pra todos
    os destinatários únicos (Clientes + Contatos do Conselho + inscritos
    públicos, menos quem pediu opt-out). Só funciona pra informativo já
    publicado (precisa do PDF)."""
    pdf_bytes = _baixar_pdf_informativo(informativo)
    slug = re.sub(r"[^a-z0-9]+", "-", (informativo.titulo or "informativo").lower()).strip("-")[:60] or "informativo"
    destinatarios = listar_destinatarios_newsletter(db)

    from app.services.email_service import _send_via_gmail_oauth
    enviados = erros = 0
    for email, _nome in destinatarios:
        try:
            assunto, html = montar_email_newsletter(informativo, destinatario_email=email)
            _send_via_gmail_oauth(email, assunto, html, attachments=[(f"{slug}.pdf", pdf_bytes)])
            enviados += 1
        except Exception as exc:
            erros += 1
            logger.warning("Newsletter informativo %s: falha ao enviar pra %s: %s", informativo.id, email, exc)

    return {"enviados": enviados, "total": len(destinatarios), "erros": erros}
