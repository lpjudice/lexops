"""Classifica e-mails sincronizados (EmailCliente) em processual / comercial /
ruído, pra não contaminar o contexto que a IA usa sobre o cliente com spam,
newsletters e assuntos pessoais que nada têm a ver com o caso.

Classificação roda uma vez por e-mail (categoria fica persistida) — não se
repete a cada pergunta do chat.
"""
from __future__ import annotations

import json
import re

from app.config import settings

MODEL = "claude-haiku-4-5-20251001"

CATEGORIAS = ("processual", "comercial", "ruido")

_RUIDO_PADROES = re.compile(
    r"no-?reply|noreply|newsletter|do_not_reply|@mail\.|marketing@|notifications?@",
    re.IGNORECASE,
)

_SYSTEM = """Você classifica e-mails de um escritório de advocacia em 3 categorias, \
pra saber quais são relevantes sobre um cliente/processo jurídico e quais são ruído.

- "processual": sobre um processo, prazo, audiência, petição, documento jurídico, \
tratativa com cliente/parte/tribunal sobre o caso.
- "comercial": sobre honorários, contrato, proposta, financeiro, relacionamento \
comercial com o cliente — relevante mas não é sobre o mérito do caso.
- "ruido": pessoal, spam, newsletter, promoção, notificação de sistema não jurídica, \
ou qualquer coisa sem relação com o cliente como cliente do escritório.

Receberá uma lista de e-mails (remetente, assunto, trecho). Retorne SOMENTE um JSON \
com uma lista de categorias, uma por e-mail, na mesma ordem, ex: ["processual","ruido"]."""


def _provavel_ruido(remetente: str | None) -> bool:
    if not remetente:
        return False
    return bool(_RUIDO_PADROES.search(remetente))


def _parse_json_lista(raw: str) -> list[str]:
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if match:
        raw = match.group(1).strip()
    return json.loads(raw)


def classificar_lote(emails: list[dict]) -> list[str]:
    """Recebe [{remetente, assunto, snippet}] e retorna lista de categorias
    na mesma ordem. Aplica pré-filtro heurístico (sem custo de IA) antes de
    chamar o modelo só para o que sobrar."""
    categorias: list[str | None] = [
        "ruido" if _provavel_ruido(e.get("remetente")) else None
        for e in emails
    ]

    pendentes_idx = [i for i, c in enumerate(categorias) if c is None]
    if not pendentes_idx:
        return categorias  # type: ignore[return-value]

    if not settings.anthropic_api_key:
        # Sem IA disponível: não arrisca esconder e-mail real, marca como comercial (visível).
        for i in pendentes_idx:
            categorias[i] = "comercial"
        return categorias  # type: ignore[return-value]

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        lote = [
            {
                "remetente": emails[i].get("remetente") or "",
                "assunto": emails[i].get("assunto") or "",
                "trecho": (emails[i].get("snippet") or "")[:200],
            }
            for i in pendentes_idx
        ]
        msg = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(lote, ensure_ascii=False)}],
        )
        resultado = _parse_json_lista(msg.content[0].text.strip())
        for idx, cat in zip(pendentes_idx, resultado):
            categorias[idx] = cat if cat in CATEGORIAS else "comercial"
    except Exception:
        pass

    # Defensivo: se o modelo devolveu uma lista mais curta (ou falhou), garante
    # que nenhum índice fique sem categoria — melhor mostrar de mais do que
    # perder e-mail relevante silenciosamente.
    for i in pendentes_idx:
        if categorias[i] is None:
            categorias[i] = "comercial"

    return categorias  # type: ignore[return-value]
