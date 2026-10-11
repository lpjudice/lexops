"""Resumo estruturado (IA) de verbetes destacados do Informativo STJ.

Só roda em itens com destacado=True (área/keyword selecionada pelo usuário) —
gera tema central + ratio decidendi a partir do texto explicativo completo do
STJ. Mesmo contrato/padrão de app/services/ia_instagram.py (cliente Anthropic,
JSON forçado por prompt + strip de fences + json.loads, custo manual por token).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.informativo_stj import InformativoStjItem

logger = logging.getLogger(__name__)

_CLAUDE_IN_PER_MTOK = 5.00
_CLAUDE_OUT_PER_MTOK = 25.00

SYSTEM_JSON = (
    "Você resume decisões do STJ para um escritório de advocacia patrimonialista/"
    "societária. Foco: identificar com precisão o tema central do julgado e a "
    "ratio decidendi (o fundamento jurídico que sustenta a decisão, não só o resultado). "
    "Responda SEMPRE E SOMENTE com JSON válido — sem markdown, sem crases, sem comentários."
)

JSON_CONTRATO = """Responda em JSON com exatamente este formato:
{"tema_central": "1-2 frases identificando o que estava em discussão", "ratio_decidendi": "parágrafo explicando o fundamento jurídico da decisão, por que o STJ decidiu assim"}"""


def _strip_fences(txt: str) -> str:
    t = txt.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
    return t.strip()


def _montar_prompt(item: InformativoStjItem) -> str:
    legislacao = ", ".join(item.legislacao_citada or []) or "não identificada"
    return f"""JULGADO DO STJ — {item.orgao_julgador} — {item.ramo_direito}

Tema/título: {item.titulo}

Destaque oficial do STJ: {item.destaque_oficial}

Texto explicativo completo (fundamentação):
{item.texto_explicativo or '(não disponível)'}

Legislação citada: {legislacao}

{JSON_CONTRATO}"""


def gerar_resumo_item(item: InformativoStjItem) -> tuple[dict, float]:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY não configurada.")
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=getattr(settings, "instagram_claude_model", None) or "claude-opus-4-5",
        max_tokens=2000,
        system=SYSTEM_JSON,
        messages=[{"role": "user", "content": _montar_prompt(item)}],
    )
    txt = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
    usage = getattr(msg, "usage", None)
    tin = getattr(usage, "input_tokens", 0) or 0
    tout = getattr(usage, "output_tokens", 0) or 0
    custo = round((tin * _CLAUDE_IN_PER_MTOK + tout * _CLAUDE_OUT_PER_MTOK) / 1_000_000, 5)
    resumo = json.loads(_strip_fences(txt))
    return resumo, custo


def processar_item(item_id, db: Session, forcar: bool = False) -> InformativoStjItem:
    item = db.get(InformativoStjItem, item_id)
    if not item:
        raise ValueError(f"Item {item_id} não encontrado")
    if not item.destacado:
        raise ValueError("Item não está destacado — resumo de IA só roda em itens destacados")
    if item.status_ia == "ok" and not forcar:
        return item

    item.status_ia = "processando"
    db.flush()
    try:
        resumo, custo = gerar_resumo_item(item)
        item.resumo_tema_central = resumo.get("tema_central")
        item.resumo_ratio_decidendi = resumo.get("ratio_decidendi")
        item.custo_ia_usd = (item.custo_ia_usd or 0.0) + custo
        item.ia_processado_em = datetime.now(timezone.utc)
        item.status_ia = "ok"
        item.erro_ia = None
    except Exception as exc:
        logger.warning("Informativo STJ: erro ao gerar resumo IA do item %s", item_id, exc_info=True)
        item.status_ia = "erro"
        item.erro_ia = str(exc)
    db.commit()
    return item


def processar_pendentes(db: Session, limite: int = 50) -> dict:
    itens = db.scalars(
        select(InformativoStjItem)
        .where(InformativoStjItem.destacado.is_(True))
        .where(InformativoStjItem.status_ia == "pendente")
        .limit(limite)
    ).all()

    ok = erro = 0
    for item in itens:
        try:
            processar_item(item.id, db)
            if item.status_ia == "ok":
                ok += 1
            else:
                erro += 1
        except Exception:
            logger.warning("Informativo STJ: falha ao processar item pendente %s", item.id, exc_info=True)
            erro += 1

    return {"total": len(itens), "ok": ok, "erro": erro}


SYSTEM_RESUMO_EDICAO = (
    "Você resume uma edição do Informativo do STJ para um advogado que precisa decidir, "
    "em 1 olhada, se vale abrir a edição. Responda SEMPRE E SOMENTE com JSON válido."
)


def gerar_resumo_edicao(edicao_id, db: Session) -> str | None:
    """Resumo ultra-curto (1-2 frases) do que tem de mais relevante na edição.

    Roda sobre os títulos/destaques oficiais (não precisa esperar a IA por item).
    """
    from app.models.informativo_stj import InformativoStjEdicao

    edicao = db.get(InformativoStjEdicao, edicao_id)
    if not edicao:
        return None
    itens = db.scalars(
        select(InformativoStjItem).where(InformativoStjItem.edicao_id == edicao_id)
    ).all()
    if not itens:
        return None

    if not settings.anthropic_api_key:
        return None

    linhas = "\n".join(
        f"- [{i.ramo_direito}] {i.titulo}: {i.destaque_oficial}" for i in itens
    )
    prompt = f"""Edição nº {edicao.numero} do Informativo do STJ. Julgados desta edição:

{linhas}

Responda em JSON: {{"resumo": "1-2 frases citando os 2-3 julgados mais relevantes/impactantes desta edição, direto ao ponto"}}"""

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model=getattr(settings, "instagram_claude_model", None) or "claude-opus-4-5",
            max_tokens=400,
            system=SYSTEM_RESUMO_EDICAO,
            messages=[{"role": "user", "content": prompt}],
        )
        txt = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
        resumo = json.loads(_strip_fences(txt)).get("resumo")
        edicao.resumo_edicao = resumo
        db.commit()
        return resumo
    except Exception:
        logger.warning("Informativo STJ: falha ao gerar resumo da edição %s", edicao.numero, exc_info=True)
        return None
