"""Sugestão de ação do "gestor jurídico" após uma publicação do Diário ser
confirmada como vinculada a um processo/cliente. Cruza o texto da publicação
com o contexto completo do processo (estratégia, andamentos, prazos, docs)
para sugerir o que fazer — nunca executa nada sozinho.
"""
import json
import re

from app.config import settings

MODEL = "claude-opus-4-5"

_SYSTEM = """Você é o gestor jurídico de um escritório de advocacia. Recebeu uma nova \
publicação do Diário Oficial já confirmada como sendo deste processo específico, e tem \
acesso ao contexto completo do processo (estratégia, andamentos, prazos, documentos).

Analise a publicação à luz desse contexto e retorne SOMENTE um JSON com este esquema:
{
  "resumo_raciocinio": "2-3 frases explicando o que a publicação significa NESTE processo específico, cruzando com o estágio atual",
  "requer_prazo": true ou false,
  "peca_necessaria": "contestacao" | "recurso" | "contrarrazoes" | "manifestacao" | "audiencia" | "pericia" | "outro" | null,
  "dias_prazo": número inteiro ou null,
  "tipo_contagem": "uteis" | "corridos",
  "tarefa_titulo": "título curto de tarefa pro responsável" ou null,
  "tarefa_responsavel": "nome se identificável no contexto (ex: quem já atua nesse processo)" ou null,
  "rascunho_sugerido": "um parágrafo inicial de rascunho da peça, se fizer sentido gerar algo" ou null
}
Sem markdown, sem explicações fora do JSON. Se a publicação não exigir ação (ex: mero andamento informativo), \
requer_prazo=false e os demais campos de ação ficam null, mas ainda preencha resumo_raciocinio."""


def _parse_json(raw: str) -> dict:
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if match:
        raw = match.group(1).strip()
    return json.loads(raw)


def sugerir_acao(contexto_processo: str, texto_publicacao: str) -> dict:
    if not settings.anthropic_api_key:
        return {"erro": "ANTHROPIC_API_KEY não configurada"}
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        mensagem = (
            f"CONTEXTO DO PROCESSO:\n{contexto_processo[:12000]}\n\n"
            f"PUBLICAÇÃO NOVA:\n{texto_publicacao[:4000]}"
        )
        msg = client.messages.create(
            model=MODEL,
            max_tokens=1536,
            system=_SYSTEM,
            messages=[{"role": "user", "content": mensagem}],
        )
        return _parse_json(msg.content[0].text.strip())
    except Exception as e:
        return {"erro": str(e)}
