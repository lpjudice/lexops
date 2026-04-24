"""
Analisa publicações do Diário de Justiça via Claude.
Extrai: cliente, CNJ, tribunal, vara, datas, tipo do ato,
        peça necessária, prazo em dias, resumo.
"""
import json
import re

from app.config import settings

SYSTEM_PROMPT = """Você é um assistente jurídico especializado em análise de publicações do \
Diário de Justiça Eletrônico (DJe) brasileiro.
Analise o texto fornecido e retorne SOMENTE um JSON válido com este esquema exato:
{
  "cliente_nome": "nome da parte ou advogado mencionado" ou null,
  "numero_cnj": "NNNNNNN-DD.AAAA.J.TT.OOOO" ou null,
  "tribunal": "TJSP" ou "TJES" ou "TJRJ" ou "TJAM" ou "STJ" ou "STF" ou "TRF1" ou "TRF2" ou "TRF3" ou "TRF4" ou null,
  "vara": "vara, câmara ou turma identificada" ou null,
  "data_publicacao": "YYYY-MM-DD" ou null,
  "data_disponibilizacao": "YYYY-MM-DD" ou null,
  "tipo_ato": "despacho" ou "decisao" ou "sentenca" ou "acordao" ou "intimacao" ou "citacao" ou "outro",
  "requer_resposta": true ou false,
  "peca_necessaria": "contestacao" ou "recurso" ou "contrarrazoes" ou "manifestacao" ou "audiencia" ou "pericia" ou "outro" ou null,
  "dias_prazo": número inteiro (ex: 15) ou null,
  "tipo_contagem": "uteis" ou "corridos",
  "resumo": "2-3 frases descrevendo o ato e o que precisa ser feito"
}
Prazos típicos (dias úteis): contestação=15, recurso=15, contrarrazões=15, manifestação=5, agravo=15, embargos=5.
Retorne APENAS o JSON. Sem explicações, sem blocos de código, sem markdown."""


def analisar_publicacao(texto: str) -> dict:
    if not settings.anthropic_api_key:
        return {"erro": "ANTHROPIC_API_KEY não configurada"}
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": texto[:8000]}],
        )
        raw = msg.content[0].text.strip()

        # Remove markdown code blocks se presentes
        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
        if match:
            raw = match.group(1).strip()

        return json.loads(raw)
    except json.JSONDecodeError as e:
        return {"erro": f"JSON inválido: {e}"}
    except Exception as e:
        return {"erro": str(e)}
