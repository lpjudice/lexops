"""
Processa transcrições de reuniões Google Meet via Claude.
Gera: TLDR, tarefas sugeridas, rascunho de contrato, anotação.
"""
import json
import re
from datetime import date

from app.config import settings

SYSTEM_PROMPT = """Você é um assistente jurídico especializado em análise de reuniões.
Analise a transcrição fornecida e retorne SOMENTE um JSON válido com este esquema exato:
{
  "resumo": "Resumo executivo em 3-5 frases do que foi discutido e decidido",
  "tarefas": [
    {
      "titulo": "Título da tarefa",
      "descricao": "Descrição detalhada do que precisa ser feito",
      "data_sugerida": "YYYY-MM-DD ou null se não mencionado"
    }
  ],
  "contratos": [
    {
      "titulo": "Título do contrato/proposta",
      "descricao": "Descrição do escopo, valor e condições mencionados",
      "valor_mencionado": 5000.00 ou null
    }
  ],
  "anotacao": "Texto completo da anotação a ser salva no cliente — inclua pontos importantes, decisões, próximos passos"
}

Regras:
- Datas relativas (ex: "semana que vem", "em 15 dias") devem ser convertidas para datas absolutas com base na data atual fornecida no início da transcrição.
- Só inclua tarefas se houver comprometimento claro ("vou enviar", "preciso verificar", "deve ser feito até").
- Só inclua contratos se houver negociação de honorários, escopo ou algum tipo de acordo comercial.
- Se não houver tarefas, retorne "tarefas": [].
- Se não houver contratos, retorne "contratos": [].
- Retorne APENAS o JSON. Sem explicações, sem blocos de código, sem markdown."""


MATCH_PROMPT = """Você é um assistente jurídico. Dado o título de uma reunião e uma lista de clientes,
identifique qual cliente é o mais provável para essa reunião.
Retorne APENAS um JSON com este esquema:
{
  "cliente_id": "UUID do cliente ou null",
  "confianca": 0.0 a 1.0,
  "motivo": "explicação em uma frase"
}
Retorne APENAS o JSON. Sem explicações, sem blocos de código, sem markdown."""


def processar_transcricao(transcricao: str, data_reuniao: date | None = None) -> dict:
    """Processa transcrição com Claude e retorna resumo + ações sugeridas."""
    if not settings.anthropic_api_key:
        return {"erro": "ANTHROPIC_API_KEY não configurada"}

    data_str = data_reuniao.isoformat() if data_reuniao else date.today().isoformat()
    texto_completo = f"[Data da reunião: {data_str}]\n\n{transcricao}"

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": texto_completo[:20000]}],
        )
        raw = msg.content[0].text.strip()

        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
        if match:
            raw = match.group(1).strip()

        return json.loads(raw)
    except json.JSONDecodeError as e:
        return {"erro": f"JSON inválido: {e}"}
    except Exception as e:
        return {"erro": str(e)}


def match_cliente(titulo_reuniao: str, clientes: list[dict]) -> dict:
    """Tenta identificar automaticamente o cliente pela IA com base no título da reunião."""
    if not settings.anthropic_api_key or not clientes:
        return {"cliente_id": None, "confianca": 0.0, "motivo": "sem dados"}

    lista = "\n".join(f"- ID: {c['id']} | Nome: {c['nome']}" for c in clientes[:50])
    user_msg = f"Título da reunião: {titulo_reuniao}\n\nClientes cadastrados:\n{lista}"

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=MATCH_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = msg.content[0].text.strip()

        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
        if match:
            raw = match.group(1).strip()

        return json.loads(raw)
    except Exception:
        return {"cliente_id": None, "confianca": 0.0, "motivo": "erro no matching"}
