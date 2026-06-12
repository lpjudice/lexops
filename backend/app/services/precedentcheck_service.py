"""
PrecedentCheck — verificação reversa de citações de julgados em peças/decisões.

Fluxo:
  1. Extração: Claude lê a peça e lista todas as citações de julgados (structured output)
  2. Verificação: para cada citação, pesquisa nas fontes (STJ/STF APIs → Jusbrasil fallback)
     e produz um CitacaoVerificada com 7 dimensões.
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

# Modelo e limites dedicados ao PrecedentCheck.
_MODELO = "claude-sonnet-4-6"
_MAX_TOKENS = 8192

# Preços Sonnet 4.6 (USD por milhão de tokens) e web_search (USD por busca).
_PRECO_INPUT_PER_MTOK = 3.0
_PRECO_OUTPUT_PER_MTOK = 15.0
_PRECO_WEB_SEARCH = 0.01


def _calcular_custo(usage) -> float:
    """Custo real em USD a partir do objeto usage retornado pela API."""
    if usage is None:
        return 0.0
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    custo = (inp * _PRECO_INPUT_PER_MTOK + out * _PRECO_OUTPUT_PER_MTOK) / 1_000_000
    server_tool = getattr(usage, "server_tool_use", None)
    if server_tool is not None:
        buscas = getattr(server_tool, "web_search_requests", 0) or 0
        custo += buscas * _PRECO_WEB_SEARCH
    return round(custo, 4)


def _extrair_texto(content) -> str:
    """Concatena todos os blocos `text` da resposta (ignora server_tool_use)."""
    if not content:
        return ""
    partes = []
    for bloco in content:
        if getattr(bloco, "type", None) == "text":
            partes.append(getattr(bloco, "text", "") or "")
    return "\n".join(partes)


def _chamar_claude(prompt: str, com_web_search: bool = False) -> tuple[str, float]:
    """
    Chamada Claude dedicada ao PrecedentCheck, com retry para 429 (rate limit).
    Retorna (texto, custo_usd). com_web_search=True habilita o tool nativo
    `web_search` para a verificação buscar julgados reais em Jusbrasil/STJ/STF.
    """
    import time

    from app.config import settings

    if not settings.anthropic_api_key:
        logger.error("PrecedentCheck: ANTHROPIC_API_KEY não configurada")
        return "", 0.0

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    kwargs = {
        "model": _MODELO,
        "max_tokens": _MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    if com_web_search:
        kwargs["tools"] = [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
            "allowed_domains": [
                "jusbrasil.com.br",
                "stj.jus.br",
                "stf.jus.br",
                "cnj.jus.br",
                "trf1.jus.br", "trf2.jus.br", "trf3.jus.br",
                "trf4.jus.br", "trf5.jus.br", "trf6.jus.br",
            ],
        }]

    # Tier baixo da Anthropic estoura 30k tok/min e 50 req/min facilmente
    # com verificação em paralelo — retry com backoff resolve.
    delays = [3, 8, 20, 40]
    for tentativa, delay in enumerate([0] + delays):
        if delay:
            time.sleep(delay)
        try:
            msg = client.messages.create(**kwargs)
            texto = _extrair_texto(msg.content)
            custo = _calcular_custo(getattr(msg, "usage", None))
            logger.info(
                "PrecedentCheck: stop=%s, out=%d chars, custo=$%.4f%s",
                msg.stop_reason, len(texto), custo,
                f" (tentativa {tentativa + 1})" if tentativa else "",
            )
            return texto, custo
        except anthropic.RateLimitError as e:
            if tentativa < len(delays):
                logger.warning(
                    "PrecedentCheck: 429 rate limit — aguardando %ds (tentativa %d/%d)",
                    delays[tentativa] if tentativa < len(delays) else 0,
                    tentativa + 1, len(delays) + 1,
                )
                continue
            logger.error("PrecedentCheck: 429 após %d tentativas: %s", tentativa + 1, e)
            return "", 0.0
        except Exception as e:
            logger.error("PrecedentCheck: erro ao chamar Claude: %s", e)
            return "", 0.0
    return "", 0.0


def _limpar_fence(texto: str) -> str:
    """Remove fences markdown (```json ... ```) se presentes."""
    t = texto.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _parse_json_array(resposta: str) -> list[dict]:
    """
    Extrai um array JSON da resposta, tolerando truncamento.
    Se o JSON foi cortado (max_tokens), recupera os objetos completos
    fechando o array manualmente.
    """
    if not resposta:
        return []
    t = _limpar_fence(resposta)
    inicio = t.find("[")
    if inicio == -1:
        return []
    candidato = t[inicio:]

    # Tentativa direta
    try:
        return json.loads(candidato)
    except json.JSONDecodeError:
        pass

    # Recuperação de array truncado: pega até o último "}" e fecha o "]"
    ultimo = candidato.rfind("}")
    if ultimo != -1:
        recuperado = candidato[: ultimo + 1] + "]"
        try:
            dados = json.loads(recuperado)
            logger.warning("PrecedentCheck: JSON array truncado recuperado (%d itens)", len(dados))
            return dados
        except json.JSONDecodeError:
            pass
    logger.warning("PrecedentCheck: falha ao parsear array JSON")
    return []


def _parse_json_object(resposta: str) -> dict | None:
    """Extrai um objeto JSON da resposta, tolerando fence markdown."""
    if not resposta:
        return None
    t = _limpar_fence(resposta)
    inicio = t.find("{")
    fim = t.rfind("}")
    if inicio == -1 or fim == -1 or fim <= inicio:
        return None
    try:
        return json.loads(t[inicio : fim + 1])
    except json.JSONDecodeError:
        return None

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

PROMPT_EXTRAIR_CITACOES = """
Você é um especialista em análise de peças jurídicas. Leia o texto abaixo e extraia TODAS as citações de julgados (acórdãos, decisões, precedentes) mencionados.

Para cada citação encontrada, retorne um JSON array com objetos no formato:
{{
  "tribunal": "STJ" | "STF" | "TJ..." | "TRF..." | "outro",
  "numero": "número completo do processo/recurso (ex: REsp 1.234.567/SP)",
  "relator": "nome do ministro/desembargador relator (se mencionado)",
  "data": "data do julgamento (se mencionada)",
  "trecho_citado": "trecho exato copiado da peça que representa a citação ou o que foi atribuído ao julgado",
  "contexto_na_peca": "em qual tese/argumento da peça esse julgado está sendo usado (uma frase)"
}}

Se não houver citações de julgados, retorne [].
Retorne APENAS o JSON array, sem texto antes ou depois.

Texto da peça:
{texto}
"""

PROMPT_VERIFICAR_CITACAO = """
Você é um verificador de precedentes jurídicos. Sua tarefa é verificar a autenticidade e o contexto de uma citação jurisprudencial.

**CITAÇÃO A VERIFICAR:**
- Tribunal: {tribunal}
- Número: {numero}
- Relator mencionado: {relator}
- Data mencionada: {data}
- Trecho citado na peça: "{trecho_citado}"
- Contexto de uso na peça: {contexto_na_peca}

**CONTEXTO GERAL DA PEÇA/TESE:**
{contexto_peca}

**INSTRUÇÕES DE PESQUISA:**
Use a ferramenta `web_search` para localizar o julgado em fontes oficiais e no Jusbrasil.
Tente buscas como:
  - "site:jusbrasil.com.br {tribunal} {numero}"
  - "site:stj.jus.br {numero}" (se STJ)
  - "site:stf.jus.br {numero}" (se STF)
  - "{tribunal} {numero} relator ementa"
Use no máximo 3 buscas. Se nem o Jusbrasil tiver o julgado, marque como `nao_encontrado` com sinceridade — NÃO invente dados nem use "conhecimento do modelo" sem confirmação.

Com base no que você encontrar via web_search, responda em JSON:

{{
  "numero_existe": {{
    "resultado": "ok" | "divergencia" | "nao_encontrado",
    "detalhe": "explicação breve"
  }},
  "relator_correto": {{
    "resultado": "ok" | "divergencia" | "nao_encontrado",
    "detalhe": "nome real do relator se diferente"
  }},
  "data_procede": {{
    "resultado": "ok" | "divergencia" | "nao_encontrado",
    "detalhe": "data real do julgamento se diferente"
  }},
  "trecho_literal": {{
    "resultado": "ok" | "divergencia" | "nao_encontrado",
    "detalhe": "o trecho existe literalmente? adaptado? inventado?"
  }},
  "voto_vencedor": {{
    "resultado": "ok" | "divergencia" | "nao_encontrado" | "inconclusivo",
    "detalhe": "trecho pertence ao voto vencedor, vencido, ou não identificado"
  }},
  "contexto_compativel": {{
    "resultado": "ok" | "divergencia" | "nao_encontrado",
    "detalhe": "a ratio decidendi do julgado é compatível com o uso feito na peça?"
  }},
  "ratio_fit": {{
    "resultado": "ok" | "divergencia" | "adequado_com_ressalvas",
    "detalhe": "síntese: o julgado de fato suporta a tese da peça?"
  }},
  "ementa_real": "ementa ou síntese real do julgado (se encontrado), ou null",
  "link_inteiro_teor": "URL direta do PDF ou página do inteiro teor (não URL de busca), ou null se não encontrado",
  "status_geral": "verificado" | "divergencia" | "nao_encontrado" | "parcial",
  "decisoes_mesmo_sentido": [
    {{"referencia": "ex: STJ — REsp 1.234.567/SP", "ementa": "súmula de 1 frase do entendimento", "link": null}}
  ],
  "decisoes_sentido_contrario": [
    {{"referencia": "ex: STJ — AgRg no REsp 987.654/RJ", "ementa": "súmula de 1 frase do entendimento contrário", "link": null}}
  ]
}}

IMPORTANTE sobre decisoes_mesmo_sentido e decisoes_sentido_contrario:
- Liste 2 a 4 julgados REAIS de STJ ou STF no mesmo sentido (que corroboram a tese da peça).
- Liste 1 a 2 julgados REAIS de STJ ou STF em sentido contrário (se existirem).
- Se não souber julgados reais com certeza, retorne [] (não invente números de processos).
- Não repita o julgado principal que está sendo verificado.

Retorne APENAS o JSON, sem texto antes ou depois.
"""


# ---------------------------------------------------------------------------
# Serviço principal
# ---------------------------------------------------------------------------

# Tipos de recurso comuns — usados pra normalizar variantes ("Recurso Especial"
# vs "REsp", "Agravo Regimental" vs "AgRg") na chave de dedup.
_NORMALIZE_RECURSOS = [
    (r"RECURSO\s+ESPECIAL", "RESP"),
    (r"RECURSO\s+EXTRAORDIN[ÁA]RIO", "RE"),
    (r"AGRAVO\s+REGIMENTAL", "AGRG"),
    (r"AGRAVO\s+INTERNO", "AGINT"),
    (r"EMBARGOS\s+DE\s+DECLARA[ÇC][ÃA]O", "EDCL"),
    (r"EMBARGOS\s+DE\s+DIVERG[ÊE]NCIA", "ERESP"),
    (r"A[ÇC][ÃA]O\s+DIRETA\s+DE\s+INCONSTITUCIONALIDADE", "ADI"),
    (r"A[ÇC][ÃA]O\s+DECLARAT[ÓO]RIA\s+DE\s+CONSTITUCIONALIDADE", "ADC"),
    (r"ARGUI[ÇC][ÃA]O\s+DE\s+DESCUMPRIMENTO", "ADPF"),
    (r"MANDADO\s+DE\s+SEGURAN[ÇC]A", "MS"),
    (r"HABEAS\s+CORPUS", "HC"),
]


def _chave_dedup(numero: str) -> str:
    """
    Normaliza o número da citação para deduplicar variantes textuais.
    Ex.: "REsp 1.234.567/SP", "Recurso Especial nº 1234567 - SP" → "RESP1234567SP".
    """
    if not numero:
        return ""
    s = numero.upper()
    s = s.replace("Nº", "").replace("N.", "").replace("N°", "")
    for padrao, sigla in _NORMALIZE_RECURSOS:
        s = re.sub(padrao, sigla, s)
    # Remove tudo que não seja letra ou dígito (espaços, pontos, hífens, barras)
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s


def _extrair_citacoes_chunk(texto: str) -> tuple[list[dict], float]:
    """Extrai citações de um chunk de texto via Claude. Retorna (citações, custo)."""
    prompt = PROMPT_EXTRAIR_CITACOES.format(texto=texto)
    resposta, custo = _chamar_claude(prompt)
    citacoes = _parse_json_array(resposta)
    logger.info("PrecedentCheck: chunk de %d chars → %d citações ($%.4f)", len(texto), len(citacoes), custo)
    return citacoes, custo


def extrair_citacoes(texto_peca: str) -> tuple[list[dict], float]:
    """
    Etapa 1: extrai citações da peça via Claude. Retorna (citações_unicas, custo_total).
    Divide em chunks de 80k chars com 2k de sobreposição e deduplica com chave
    normalizada (REsp vs Recurso Especial, com/sem pontuação, etc.).
    """
    CHUNK = 80_000
    OVERLAP = 2_000

    todas: list[dict] = []
    custo_total = 0.0

    if len(texto_peca) <= CHUNK:
        todas, custo_total = _extrair_citacoes_chunk(texto_peca)
    else:
        pos = 0
        while pos < len(texto_peca):
            chunk = texto_peca[pos: pos + CHUNK]
            cits, custo = _extrair_citacoes_chunk(chunk)
            todas.extend(cits)
            custo_total += custo
            pos += CHUNK - OVERLAP

    # Dedup com chave normalizada
    vistos: set[str] = set()
    unicas: list[dict] = []
    for c in todas:
        chave = _chave_dedup(c.get("numero", ""))
        if chave and chave not in vistos:
            vistos.add(chave)
            unicas.append(c)

    logger.info(
        "PrecedentCheck: extração total %d brutas → %d únicas (custo $%.4f)",
        len(todas), len(unicas), custo_total,
    )
    return unicas, round(custo_total, 4)


def verificar_citacao(citacao: dict, contexto_peca: str) -> dict:
    """Etapa 2: verifica uma citação individual usando web_search nativo."""
    prompt = PROMPT_VERIFICAR_CITACAO.format(
        tribunal=citacao.get("tribunal", ""),
        numero=citacao.get("numero", ""),
        relator=citacao.get("relator", "não informado"),
        data=citacao.get("data", "não informada"),
        trecho_citado=citacao.get("trecho_citado", ""),
        contexto_na_peca=citacao.get("contexto_na_peca", ""),
        contexto_peca=contexto_peca[:3000],
    )

    resposta, custo = _chamar_claude(prompt, com_web_search=True)

    verificacao = _parse_json_object(resposta)
    if verificacao is None:
        logger.warning("PrecedentCheck: verificação sem JSON válido (%d chars)", len(resposta))
        return {
            "status_geral": "nao_encontrado",
            "erro": "Não foi possível processar a verificação",
            "custo_usd": custo,
        }
    verificacao["referencia_original"] = citacao
    verificacao["custo_usd"] = custo
    return verificacao
