"""
PrecedentCheck — verificação reversa de citações de julgados em peças/decisões.

Fluxo:
  1. Extração: Claude lê a peça e lista todas as citações de julgados (structured output)
  2. Verificação: para cada citação, pesquisa nas fontes (STJ/STF APIs → Jusbrasil fallback)
     e produz um CitacaoVerificada com 7 dimensões.
"""

import json
import re
from typing import Any

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

**RESULTADO DA BUSCA NAS FONTES:**
{resultado_busca}

Com base nas informações acima, responda as seguintes dimensões em JSON:

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
# Funções de busca nas fontes oficiais
# ---------------------------------------------------------------------------

def _buscar_stj(numero: str) -> dict[str, Any]:
    """Tenta localizar o julgado no portal STJ."""
    try:
        import httpx
        # Normaliza o número para a API do STJ
        numero_limpo = re.sub(r"[^\w/]", "", numero.replace(".", "").replace("-", ""))
        url = f"https://jurisprudencia.stj.jus.br/SCON/pesquisa.jsp?tipo_visualizacao=RESUMO&b=ACOR&livre={numero_limpo}"
        r = httpx.get(url, timeout=10, follow_redirects=True)
        return {"fonte": "STJ", "url": url, "encontrado": r.status_code == 200, "conteudo": r.text[:3000]}
    except Exception as e:
        return {"fonte": "STJ", "encontrado": False, "erro": str(e)}


def _buscar_stf(numero: str) -> dict[str, Any]:
    """Tenta localizar o julgado no portal STF."""
    try:
        import httpx
        url = f"https://jurisprudencia.stf.jus.br/pages/search?base=acordaos&sinonimo=true&plural=true&page=1&pageSize=5&queryString={numero}&sort=_score&sortBy=desc"
        r = httpx.get(url, timeout=10, follow_redirects=True, headers={"Accept": "application/json"})
        if r.status_code == 200:
            return {"fonte": "STF", "url": url, "encontrado": True, "conteudo": r.text[:3000]}
        return {"fonte": "STF", "encontrado": False}
    except Exception as e:
        return {"fonte": "STF", "encontrado": False, "erro": str(e)}


def _buscar_jusbrasil(numero: str, tribunal: str) -> dict[str, Any]:
    """Fallback: busca no Jusbrasil via web search (sem scraping direto)."""
    return {
        "fonte": "Jusbrasil",
        "encontrado": False,
        "nota": "Busca Jusbrasil requer pesquisa web — será delegada ao modelo de IA com tool web_search.",
        "query_sugerida": f"site:jusbrasil.com.br {tribunal} {numero}",
    }


def buscar_julgado(tribunal: str, numero: str) -> str:
    """Busca o julgado nas fontes disponíveis e retorna texto consolidado."""
    resultados = []

    tribunal_upper = tribunal.upper()
    if "STJ" in tribunal_upper:
        resultados.append(_buscar_stj(numero))
    elif "STF" in tribunal_upper:
        resultados.append(_buscar_stf(numero))

    # Fallback Jusbrasil sempre
    resultados.append(_buscar_jusbrasil(numero, tribunal))

    return json.dumps(resultados, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Serviço principal
# ---------------------------------------------------------------------------

def extrair_citacoes(texto_peca: str) -> list[dict]:
    """Etapa 1: extrai citações de julgados da peça via Claude."""
    from app.services.ia_cliente import chat_claude

    prompt = PROMPT_EXTRAIR_CITACOES.format(texto=texto_peca[:20000])
    resposta = chat_claude(pergunta=prompt, historico=[], cliente_id="", contexto="")

    # Extrai o JSON da resposta
    match = re.search(r"\[.*\]", resposta, re.DOTALL)
    if not match:
        return []
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return []


def verificar_citacao(citacao: dict, contexto_peca: str) -> dict:
    """Etapa 2: verifica uma citação individual."""
    from app.services.ia_cliente import chat_claude

    resultado_busca = buscar_julgado(
        tribunal=citacao.get("tribunal", ""),
        numero=citacao.get("numero", ""),
    )

    prompt = PROMPT_VERIFICAR_CITACAO.format(
        tribunal=citacao.get("tribunal", ""),
        numero=citacao.get("numero", ""),
        relator=citacao.get("relator", "não informado"),
        data=citacao.get("data", "não informada"),
        trecho_citado=citacao.get("trecho_citado", ""),
        contexto_na_peca=citacao.get("contexto_na_peca", ""),
        contexto_peca=contexto_peca[:3000],
        resultado_busca=resultado_busca,
    )

    resposta = chat_claude(pergunta=prompt, historico=[], cliente_id="", contexto="")

    match = re.search(r"\{.*\}", resposta, re.DOTALL)
    if not match:
        return {
            "status_geral": "nao_encontrado",
            "erro": "Não foi possível processar a verificação",
        }
    try:
        verificacao = json.loads(match.group(0))
        # Injeta metadados da citação original
        verificacao["referencia_original"] = citacao
        return verificacao
    except json.JSONDecodeError:
        return {"status_geral": "nao_encontrado", "erro": "JSON inválido na resposta"}
