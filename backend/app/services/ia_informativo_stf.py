"""Resumo estruturado (IA) dos verbetes do Informativo STF.

Roda em TODOS os itens (não só os destacados — "destacado" é só o sinal de
área/keyword de interesse do usuário). Mesmo contrato/padrão de
app/services/ia_informativo_stj.py: Gemini via app.services.ia_instagram,
JSON forçado por prompt, custo manual por token.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.informativo_stf import InformativoStfItem

logger = logging.getLogger(__name__)

SYSTEM_JSON = (
    "Você resume decisões do STF para um advogado que precisa ler rápido. Seu estilo é "
    "igual ao de um bom social media jurídico: tema_central é um GANCHO — uma pergunta ou "
    "afirmação curta e provocativa que já entrega o cerne da decisão e dá vontade de "
    "continuar lendo (ex.: 'Policial penal temporário sem concurso é inconstitucional?'). "
    "ratio_decidendi e resumo_leigo são PARÁGRAFOS CURTOS (3-4 linhas no máximo), nunca "
    "listas longas, nunca repetindo o texto oficial do STF. "
    "Responda SEMPRE E SOMENTE com JSON válido — sem markdown, sem crases, sem comentários."
)

JSON_CONTRATO = """Responda em JSON com exatamente este formato:
{"tema_central": "GANCHO curto (máx. 12 palavras) — pergunta ou afirmação direta", "ratio_decidendi": "parágrafo CURTO (3-4 linhas) explicando o fundamento jurídico, por que o STF decidiu assim — sem listas, sem repetir o texto oficial", "resumo_leigo": "parágrafo CURTO (2-3 linhas) explicando a decisão em português simples, sem juridiquês, pra quem não é advogado"}"""


def _montar_prompt(item: InformativoStfItem) -> str:
    legislacao = ", ".join(item.legislacao_citada or []) or "não identificada"
    return f"""JULGADO DO STF — {item.orgao_julgador} — {item.ramo_direito}

Tema/título: {item.titulo}

Destaque/tese oficial do STF: {item.destaque_oficial}

Texto explicativo completo (fundamentação):
{item.texto_explicativo or '(não disponível)'}

Notas de rodapé/legislação citada: {legislacao}

{JSON_CONTRATO}"""


def gerar_resumo_item(item: InformativoStfItem) -> tuple[dict, float]:
    from app.services.ia_instagram import _call_gemini_json

    prompt = f"{SYSTEM_JSON}\n\n{_montar_prompt(item)}"
    return _call_gemini_json(prompt)


def processar_item(item_id, db: Session, forcar: bool = False) -> InformativoStfItem:
    item = db.get(InformativoStfItem, item_id)
    if not item:
        raise ValueError(f"Item {item_id} não encontrado")
    if item.status_ia == "ok" and not forcar:
        return item

    item.status_ia = "processando"
    db.flush()
    try:
        resumo, custo = gerar_resumo_item(item)
        item.resumo_tema_central = resumo.get("tema_central")
        item.resumo_ratio_decidendi = resumo.get("ratio_decidendi")
        item.resumo_leigo = resumo.get("resumo_leigo")
        item.custo_ia_usd = (item.custo_ia_usd or 0.0) + custo
        item.ia_processado_em = datetime.now(timezone.utc)
        item.status_ia = "ok"
        item.erro_ia = None
    except Exception as exc:
        logger.warning("Informativo STF: erro ao gerar resumo IA do item %s", item_id, exc_info=True)
        item.status_ia = "erro"
        item.erro_ia = str(exc)
    db.commit()
    return item


def processar_pendentes(db: Session, limite: int = 50) -> dict:
    itens = db.scalars(
        select(InformativoStfItem)
        .where(InformativoStfItem.status_ia == "pendente")
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
            logger.warning("Informativo STF: falha ao processar item pendente %s", item.id, exc_info=True)
            erro += 1

    return {"total": len(itens), "ok": ok, "erro": erro}
