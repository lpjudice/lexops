"""Sincroniza andamentos de um ProcessoTelegramExtra (CNJ avulso) via PDPJ.

Independente de consulta_processual/pdpj.py (travado): replica APENAS o parsing
dos movimentos (descrição, data, tipo, documento) e persiste com dedup por hash.

Para CNJs do escritório (modelo Processo), a sincronização continua pela função
travada sincronizar_processo_jusbr — não usamos este módulo lá.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.andamento_telegram_extra import AndamentoTelegramExtra
from app.models.processo_telegram_extra import ProcessoTelegramExtra
from app.services.processo_partes_collector import fetch_processo

logger = logging.getLogger(__name__)


def _parse_data(raw: Any) -> date | None:
    if not raw:
        return None
    s = str(raw).strip().replace("Z", "")
    for chunk in (s, s[:10], s[:19], s[:23]):
        try:
            return datetime.fromisoformat(chunk).date()
        except Exception:
            continue
    digits = re.sub(r"\D", "", s)[:8]
    if len(digits) == 8:
        try:
            return datetime.strptime(digits, "%Y%m%d").date()
        except Exception:
            return None
    return None


def _movimentos_de(blob: dict) -> list[dict]:
    tram = blob.get("tramitacaoAtual") if isinstance(blob, dict) else {}
    if not isinstance(tram, dict):
        tram = {}
    candidatas = [tram.get("movimentos"), blob.get("movimentos")]
    for c in candidatas:
        if isinstance(c, list) and c:
            return c
    return []


def _documentos_de(blob: dict) -> list[dict]:
    tram = blob.get("tramitacaoAtual") if isinstance(blob, dict) else {}
    if not isinstance(tram, dict):
        tram = {}
    for c in (tram.get("documentos"), blob.get("documentos")):
        if isinstance(c, list) and c:
            return c
    return []


def _str_or_none(v: Any) -> str | None:
    if isinstance(v, str) and v.strip():
        return v.strip()
    if isinstance(v, dict):
        for k in ("descricao", "nome", "sigla"):
            x = v.get(k)
            if isinstance(x, str) and x.strip():
                return x.strip()
    return None


def _descricao_movimento(m: dict) -> str:
    return (
        _str_or_none(m.get("descricao"))
        or _str_or_none(m.get("nome"))
        or _str_or_none(m.get("tipo"))
        or _str_or_none(m.get("movimentoLocal"))
        or ""
    )


def _tipo_movimento(m: dict) -> str | None:
    return _str_or_none(m.get("tipo")) or _str_or_none(m.get("classe"))


def _href_doc(m: dict, todos_docs: list[dict]) -> tuple[str | None, str | None]:
    """Retorna (arquivo_nome, arquivo_url) se o movimento tem documento."""
    docs = m.get("documentos") if isinstance(m, dict) else None
    if not isinstance(docs, list) or not docs:
        # alguns layouts referenciam por id
        ids = m.get("documentoIds") if isinstance(m, dict) else None
        if isinstance(ids, list) and ids and todos_docs:
            achados = [d for d in todos_docs if d.get("id") in ids or d.get("idOrigem") in ids]
            docs = achados
    if not isinstance(docs, list) or not docs:
        return None, None
    d = docs[0]
    if not isinstance(d, dict):
        return None, None
    nome = _str_or_none(d.get("nome")) or _str_or_none(d.get("descricao"))
    url = d.get("hrefBinario") or d.get("href")
    return nome, (url if isinstance(url, str) else None)


def parse_movimentos(blob: dict) -> list[dict]:
    movs = _movimentos_de(blob)
    docs_all = _documentos_de(blob)
    out: list[dict] = []
    for m in movs:
        if not isinstance(m, dict):
            continue
        desc = _descricao_movimento(m)
        if not desc:
            continue
        nome, url = _href_doc(m, docs_all)
        out.append({
            "data_andamento": _parse_data(m.get("dataHora") or m.get("data") or m.get("dataMovimento")),
            "descricao": desc[:4000],
            "tipo": (_tipo_movimento(m) or "")[:240] or None,
            "arquivo_nome": (nome or "")[:480] or None,
            "arquivo_url": url,
        })
    return out


async def sincronizar_extra(
    db: Session, extra: ProcessoTelegramExtra, token: str
) -> int:
    """Coleta movimentos do PDPJ e insere os novos. Retorna quantos novos.

    Não toca em `notificado` dos existentes — só insere novos com False.
    """
    raw = await fetch_processo(extra.cnj, token)
    if not raw:
        logger.warning("sincronizar_extra %s: PDPJ retornou vazio", extra.cnj)
        return 0
    movs = parse_movimentos(raw)
    if not movs:
        return 0

    novos = 0
    for m in movs:
        h = AndamentoTelegramExtra.calcular_hash(
            str(extra.id),
            str(m["data_andamento"]) if m["data_andamento"] else None,
            m["descricao"],
        )
        if db.query(AndamentoTelegramExtra).filter(AndamentoTelegramExtra.hash_unico == h).first():
            continue
        db.add(AndamentoTelegramExtra(
            extra_id=extra.id,
            data_andamento=m["data_andamento"],
            descricao=m["descricao"],
            tipo=m["tipo"],
            arquivo_nome=m["arquivo_nome"],
            arquivo_url=m["arquivo_url"],
            hash_unico=h,
            notificado=False,
        ))
        novos += 1
    db.commit()
    return novos
