"""Datas de disponibilização e publicação escritas no corpo do diário.

O Recorte Digital traz as duas datas no texto do e-mail ("Data de
Disponibilização: dd/mm/aaaa"). O DJEN não traz rótulo nenhum — ele entrega a
disponibilização como campo estruturado, e a publicação é derivada dela
(CPC, art. 224, §2º).

Regex própria, sem depender do parser do router `diario2`: aquele import
arrasta httpx e a árvore de dependências do router para dentro de jobs de
e-mail e de rotinas de importação. São duas linhas de texto.
"""
from __future__ import annotations

import re
from datetime import date, datetime

_RE_DISPONIBILIZACAO = re.compile(
    r"Data\s+de\s+Disponibiliza(?:ç|c)[aã]o\s*:?\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE
)
_RE_PUBLICACAO = re.compile(
    r"Data\s+de\s+Publica(?:ç|c)[aã]o\s*:?\s*(\d{2}/\d{2}/\d{4})", re.IGNORECASE
)


def _para_date(txt: str | None) -> date | None:
    if not txt:
        return None
    try:
        return datetime.strptime(txt, "%d/%m/%Y").date()
    except ValueError:
        return None


def extrair_datas(texto: str | None) -> tuple[date | None, date | None]:
    """(disponibilização, publicação) lidas do texto, ou (None, None)."""
    if not texto:
        return None, None
    m_disp = _RE_DISPONIBILIZACAO.search(texto)
    m_publ = _RE_PUBLICACAO.search(texto)
    return _para_date(m_disp.group(1) if m_disp else None), _para_date(
        m_publ.group(1) if m_publ else None
    )
