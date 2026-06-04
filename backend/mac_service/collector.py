"""Thin wrapper around lexops' existing collection logic.

Imports buscar_via_pdpj / buscar_via_datajud / baixar_documento_jusbr directly
from ../app/services/consulta_processual — same repo, no copy, no modification.
The PYTHONPATH injection below is only needed when running mac_service standalone
(launchd / python -m). Inside the repo the IDE already resolves it.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Add backend/ to sys.path so "from app.services..." works.
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.consulta_processual.cnj import inferir_tribunal_pelo_cnj  # noqa: E402
from app.services.consulta_processual.pdpj import (  # noqa: E402
    baixar_documento_jusbr,
    buscar_via_pdpj,
)

logger = logging.getLogger(__name__)

__all__ = [
    "inferir_tribunal_pelo_cnj",
    "buscar_via_pdpj",
    "baixar_documento_jusbr",
    "fetch_andamentos",
    "fetch_document",
]


async def fetch_andamentos(cnj: str, session_data: dict) -> list:
    """Return andamentos for a CNJ number via jus.br/PDPJ, newest first.

    Always requires a valid session — no DataJud fallback. The bot ensures
    the user authenticates before calling this function.
    Never writes to the lexops database — pure in-memory result.
    """
    tribunal = inferir_tribunal_pelo_cnj(cnj)
    if not tribunal:
        raise ValueError(f"Não foi possível inferir o tribunal pelo número CNJ: {cnj}")

    token = session_data.get("token")
    logger.info("Buscando via PDPJ (jus.br) — cnj=%s tribunal=%s", cnj, tribunal)
    andamentos = await buscar_via_pdpj(cnj, tribunal, token=token, session_data=session_data)

    # Sort newest first
    andamentos.sort(key=lambda a: a.data_andamento or __import__("datetime").date.min, reverse=True)
    return andamentos


async def fetch_document(url: str, session_data: dict | None) -> tuple[bytes, str] | None:
    """Download a single document. Returns (bytes, mimetype) or None."""
    token = session_data.get("token") if session_data else None
    return await baixar_documento_jusbr(url, token=token, session_data=session_data)
