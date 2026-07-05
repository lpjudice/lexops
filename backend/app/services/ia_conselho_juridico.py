"""Conselho Jurídico — 4 especialistas independentes, cada um numa área
rotineira do escritório E num provedor de IA diferente (diversidade real de
modelo, não só de prompt). Todos partem do mesmo contexto (contexto_service)
— a diferença entre eles é o ângulo/especialidade e o "cérebro" por trás.
"""
from __future__ import annotations

import asyncio

from app.services.ia_cliente import chat_claude, chat_gemini, chat_gpt

ESPECIALISTAS = [
    {
        "chave": "tributario",
        "nome": "Tributário",
        "fn": chat_claude,
        "model": "claude-sonnet-4-5",
        "prompt": (
            "Você é o especialista TRIBUTÁRIO do escritório — atua com ITCMD, ITBI, IPTU, "
            "mandados de segurança fiscais, PAF e teses de repetição de indébito. "
            "Responda com o olhar de quem avalia risco fiscal, teses aplicáveis e prazos tributários."
        ),
    },
    {
        "chave": "sucessoes_familia",
        "nome": "Sucessões e Família",
        "fn": chat_claude,
        "model": "claude-haiku-4-5-20251001",
        "prompt": (
            "Você é o especialista em SUCESSÕES E FAMÍLIA do escritório — atua com inventários, "
            "arrolamentos, partilha, pacto antenupcial, doações e disputas entre herdeiros. "
            "Responda com o olhar de quem avalia direito de família/sucessório e a dinâmica entre as partes."
        ),
    },
    {
        "chave": "civel_contencioso",
        "nome": "Cível / Contencioso",
        "fn": chat_gpt,
        "model": "gpt-4o",
        "prompt": (
            "Você é o especialista em CÍVEL E CONTENCIOSO GERAL do escritório — atua com cumprimento "
            "de sentença, indenizações, cobrança, despejo e obrigações contratuais. "
            "Responda com o olhar de quem avalia mérito cível, provas e estratégia de cobrança/defesa."
        ),
    },
    {
        "chave": "recursal_processual",
        "nome": "Recursal / Processual",
        "fn": chat_gemini,
        "model": "gemini-2.5-flash",
        "prompt": (
            "Você é o especialista RECURSAL E PROCESSUAL do escritório — foca em prazos, cabimento de "
            "recursos (agravo, apelação, embargos), riscos processuais e questões de admissibilidade. "
            "Responda com o olhar de quem avalia prazo, forma e estratégia recursal."
        ),
    },
]

_INSTRUCAO_COMUM = (
    "\nVocê está no Conselho Jurídico do escritório: outros especialistas de áreas diferentes "
    "também vão opinar sobre a mesma pergunta, de forma independente. Dê sua opinião SÓ do ângulo "
    "da sua especialidade — se a pergunta não tiver nada a ver com sua área, diga isso em 1 frase e "
    "pare por aí, não force uma resposta genérica. Seja direto: 3-5 frases, sem preâmbulo."
)


def _por_chave(chave: str) -> dict | None:
    return next((e for e in ESPECIALISTAS if e["chave"] == chave), None)


def _consultar_um_sync(especialista: dict, contexto: str, pergunta: str, historico: list[dict]) -> dict:
    resposta = especialista["fn"](
        pergunta, historico, "", contexto, "",
        pdf_paths=[], model=especialista["model"],
        instrucao_extra=especialista["prompt"] + _INSTRUCAO_COMUM,
    )
    return {"chave": especialista["chave"], "nome": especialista["nome"], "resposta": resposta}


async def consultar_conselho(contexto: str, pergunta: str) -> list[dict]:
    """Consulta todos os especialistas em paralelo (primeira pergunta,
    broadcast). Retorna na mesma ordem de ESPECIALISTAS."""
    tarefas = [
        asyncio.to_thread(_consultar_um_sync, especialista, contexto, pergunta, [])
        for especialista in ESPECIALISTAS
    ]
    return list(await asyncio.gather(*tarefas))


async def consultar_um(chave: str, contexto: str, pergunta: str, historico: list[dict]) -> dict:
    """Pergunta de aprofundamento pra UM especialista específico, mantendo
    o histórico isolado daquele card (não afeta os outros)."""
    especialista = _por_chave(chave)
    if not especialista:
        return {"chave": chave, "nome": chave, "resposta": f"❌ Especialista desconhecido: {chave}"}
    return await asyncio.to_thread(_consultar_um_sync, especialista, contexto, pergunta, historico)
