"""DataJud scraper — CNJ public API.

Covers all tribunais in a single API:
  https://api-publica.datajud.cnj.jus.br/api_publica_{sigla}/_search

The process number must be submitted WITHOUT dashes/dots (pure digits).
e.g. "5026724-11.2025.8.08.0024" → "50267241120258080024"

Tribunal index mapping (lowercase sigla):
  TJES  → api_publica_tjes
  TJSP  → api_publica_tjsp
  TJAM  → api_publica_tjam
  TRF2  → api_publica_trf2
  TJRJ  → api_publica_tjrj
  TJMG  → api_publica_tjmg
  (any tribunal: lowercase and prepend api_publica_)
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime

import httpx

from app.config import settings

from .base import Andamento

logger = logging.getLogger(__name__)

DATAJUD_BASE = "https://api-publica.datajud.cnj.jus.br"


def _normalizar_cnj(numero: str) -> str:
    """Strip all non-digits from CNJ number for DataJud query."""
    return re.sub(r"\D", "", numero)


def _tribunal_to_index(tribunal: str) -> str:
    """Convert tribunal sigla to DataJud index name."""
    return f"api_publica_{tribunal.lower()}"


def _parse_data(raw: str | None) -> date | None:
    if not raw:
        return None
    # "2025-07-14T23:43:52.000Z"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:len(fmt.replace('%Y','0000').replace('%m','00').replace('%d','00').replace('%H','00').replace('%M','00').replace('%S','00').replace('%f','000000').replace('%Z','Z').replace('T','T'))], fmt).date()
        except Exception:
            pass
    # Last resort: take first 10 chars and try YYYY-MM-DD
    try:
        return date.fromisoformat(raw[:10])
    except Exception:
        pass
    return None


def _parse_data_v2(raw: str | None) -> date | None:
    """Robust date parser for DataJud timestamps."""
    if not raw:
        return None
    # Try ISO variants
    for prefix_len in (10, 19, 24, 27):
        try:
            chunk = raw[:prefix_len]
            return datetime.fromisoformat(chunk.replace("Z", "+00:00")).date()
        except Exception:
            pass
    return None


def _movimento_descricao(m: dict) -> str:
    """Build a human-readable description from a DataJud movimento."""
    partes = [m.get("nome", "")]
    if m.get("complemento"):
        partes.append(m["complemento"])
    # Structured complements
    for ct in m.get("complementosTabelados", []):
        nome_ct = ct.get("nome") or ct.get("descricao") or ""
        valor_ct = ct.get("valor") or ""
        if nome_ct:
            partes.append(f"{nome_ct}: {valor_ct}" if valor_ct else nome_ct)
    return " — ".join(p for p in partes if p).strip()


async def buscar_via_datajud(numero_cnj: str, tribunal: str) -> list[Andamento]:
    """Query DataJud and return list of Andamento objects."""
    api_key = settings.datajud_api_key
    if not api_key:
        raise ValueError(
            "DATAJUD_API_KEY não configurada. "
            "Adicione a chave pública do DataJud/CNJ no arquivo .env como DATAJUD_API_KEY=suachave"
        )

    numero_norm = _normalizar_cnj(numero_cnj)
    index = _tribunal_to_index(tribunal)
    url = f"{DATAJUD_BASE}/{index}/_search"

    payload = {
        "query": {"match": {"numeroProcesso": numero_norm}},
        "_source": ["numeroProcesso", "movimentos", "dataHoraUltimaAtualizacao"],
        "size": 1,
    }

    headers = {
        "Authorization": f"ApiKey {api_key}",
        "Content-Type": "application/json",
    }

    last_exc: Exception | None = None
    for attempt in range(3):
        if attempt:
            await asyncio.sleep(2 ** attempt)   # 2s, 4s
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                resp = await client.post(url, json=payload, headers=headers)
            last_exc = None
            break
        except httpx.RequestError as exc:
            last_exc = exc
            logger.warning("DataJud tentativa %d falhou: %s", attempt + 1, exc)
    else:
        raise ConnectionError(
            f"DataJud não respondeu após 3 tentativas. "
            f"Verifique sua conexão ou tente novamente em instantes. ({last_exc})"
        )

    if resp.status_code == 401:
        raise PermissionError(
            "Chave de API do DataJud inválida ou expirada. "
            "Verifique DATAJUD_API_KEY no .env."
        )
    if resp.status_code == 404:
        raise ValueError(
            f"Índice '{index}' não encontrado no DataJud. "
            f"Verifique se o tribunal '{tribunal}' está correto."
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"DataJud retornou status {resp.status_code}: {resp.text[:200]}"
        )

    data = resp.json()
    hits = data.get("hits", {}).get("hits", [])
    if not hits:
        return []

    source = hits[0].get("_source", {})
    movimentos_raw = source.get("movimentos", [])

    andamentos: list[Andamento] = []
    for m in movimentos_raw:
        dt = _parse_data_v2(m.get("dataHora"))
        desc = _movimento_descricao(m)
        tipo = m.get("nome")
        if desc:
            andamentos.append(
                Andamento(
                    data_andamento=dt,
                    descricao=desc[:2000],
                    tipo=tipo,
                    grau=None,
                )
            )

    return andamentos
