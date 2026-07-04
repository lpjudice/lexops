"""Conselho Jurídico — várias IAs especialistas, cada uma numa área rotineira
do escritório, respondendo de forma independente sobre o mesmo cliente ou
processo. Todas partem do mesmo contexto (contexto_service) — a diferença
entre elas é o ângulo/especialidade, não o dado que cada uma enxerga.
"""
from __future__ import annotations

import asyncio

from app.config import settings

MODEL = "claude-haiku-4-5-20251001"

ESPECIALISTAS = [
    {
        "chave": "tributario",
        "nome": "Tributário",
        "prompt": (
            "Você é o especialista TRIBUTÁRIO do escritório — atua com ITCMD, ITBI, IPTU, "
            "mandados de segurança fiscais, PAF e teses de repetição de indébito. "
            "Responda com o olhar de quem avalia risco fiscal, teses aplicáveis e prazos tributários."
        ),
    },
    {
        "chave": "sucessoes_familia",
        "nome": "Sucessões e Família",
        "prompt": (
            "Você é o especialista em SUCESSÕES E FAMÍLIA do escritório — atua com inventários, "
            "arrolamentos, partilha, pacto antenupcial, doações e disputas entre herdeiros. "
            "Responda com o olhar de quem avalia direito de família/sucessório e a dinâmica entre as partes."
        ),
    },
    {
        "chave": "civel_contencioso",
        "nome": "Cível / Contencioso",
        "prompt": (
            "Você é o especialista em CÍVEL E CONTENCIOSO GERAL do escritório — atua com cumprimento "
            "de sentença, indenizações, cobrança, despejo e obrigações contratuais. "
            "Responda com o olhar de quem avalia mérito cível, provas e estratégia de cobrança/defesa."
        ),
    },
    {
        "chave": "recursal_processual",
        "nome": "Recursal / Processual",
        "prompt": (
            "Você é o especialista RECURSAL E PROCESSUAL do escritório — foca em prazos, cabimento de "
            "recursos (agravo, apelação, embargos), riscos processuais e questões de admissibilidade. "
            "Responda com o olhar de quem avalia prazo, forma e estratégia recursal."
        ),
    },
]

_INSTRUCAO_COMUM = (
    "\n\nVocê está no Conselho Jurídico do escritório: outros especialistas de áreas diferentes "
    "também vão opinar sobre a mesma pergunta, de forma independente. Dê sua opinião SÓ do ângulo "
    "da sua especialidade — se a pergunta não tiver nada a ver com sua área, diga isso em 1 frase e "
    "pare por aí, não force uma resposta genérica. Seja direto: 3-5 frases, sem preâmbulo."
)


def _consultar_um(especialista: dict, contexto: str, pergunta: str) -> dict:
    if not settings.anthropic_api_key:
        return {**_saida_base(especialista), "resposta": "❌ ANTHROPIC_API_KEY não configurada."}
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        system = especialista["prompt"] + _INSTRUCAO_COMUM + f"\n\nContexto do caso:\n{contexto[:8000]}"
        msg = client.messages.create(
            model=MODEL,
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": pergunta}],
        )
        return {**_saida_base(especialista), "resposta": msg.content[0].text.strip()}
    except Exception as e:
        return {**_saida_base(especialista), "resposta": f"❌ Erro: {e}"}


def _saida_base(especialista: dict) -> dict:
    return {"chave": especialista["chave"], "nome": especialista["nome"]}


async def consultar_conselho(contexto: str, pergunta: str) -> list[dict]:
    """Consulta todos os especialistas em paralelo. Retorna uma lista na
    mesma ordem de ESPECIALISTAS."""
    tarefas = [
        asyncio.to_thread(_consultar_um, especialista, contexto, pergunta)
        for especialista in ESPECIALISTAS
    ]
    return list(await asyncio.gather(*tarefas))
