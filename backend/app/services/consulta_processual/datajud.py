"""DataJud scraper — CNJ public API.

Faz consulta por processo tentando:
- tribunal informado no cadastro;
- tribunal inferido a partir do numero CNJ;
- variantes de query para reduzir falsos negativos.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

import httpx

from app.config import settings

from .base import Andamento
from .cnj import candidatos_tribunal, normalizar_cnj

logger = logging.getLogger(__name__)

DATAJUD_BASE = "https://api-publica.datajud.cnj.jus.br"


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


def _build_payloads(numero_norm: str) -> list[dict]:
    source_fields = [
        "numeroProcesso",
        "movimentos",
        "dataHoraUltimaAtualizacao",
        "tribunal",
        "orgaoJulgador",
    ]
    return [
        {
            "query": {"term": {"numeroProcesso.keyword": numero_norm}},
            "_source": source_fields,
            "size": 3,
        },
        {
            "query": {"term": {"numeroProcesso": numero_norm}},
            "_source": source_fields,
            "size": 3,
        },
        {
            "query": {"match_phrase": {"numeroProcesso": numero_norm}},
            "_source": source_fields,
            "size": 3,
        },
        {
            "query": {"match": {"numeroProcesso": {"query": numero_norm, "operator": "and"}}},
            "_source": source_fields,
            "size": 3,
        },
    ]


def _hit_matches_numero(hit: dict, numero_norm: str) -> bool:
    source = hit.get("_source", {})
    numero_hit = normalizar_cnj(source.get("numeroProcesso", ""))
    return numero_hit == numero_norm


def _parse_hit(hit: dict) -> list[Andamento]:
    source = hit.get("_source", {})
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


async def buscar_via_datajud(numero_cnj: str, tribunal: str) -> list[Andamento]:
    """Query DataJud and return list of Andamento objects."""
    api_key = settings.datajud_api_key
    if not api_key:
        raise ValueError(
            "DATAJUD_API_KEY não configurada. "
            "Adicione a chave pública do DataJud/CNJ no arquivo .env como DATAJUD_API_KEY=suachave"
        )

    numero_norm = normalizar_cnj(numero_cnj)
    tribunais = candidatos_tribunal(numero_cnj, tribunal)
    if not tribunais:
        tribunais = [tribunal]

    headers = {
        "Authorization": f"ApiKey {api_key}",
        "Content-Type": "application/json",
    }

    last_exc: Exception | None = None
    payloads = _build_payloads(numero_norm)

    async with httpx.AsyncClient(timeout=45) as client:
        for tribunal_sigla in tribunais:
            index = _tribunal_to_index(tribunal_sigla)
            url = f"{DATAJUD_BASE}/{index}/_search"

            for payload in payloads:
                for attempt in range(3):
                    if attempt:
                        await asyncio.sleep(2 ** attempt)
                    try:
                        resp = await client.post(url, json=payload, headers=headers)
                        last_exc = None
                        break
                    except httpx.RequestError as exc:
                        last_exc = exc
                        logger.warning(
                            "DataJud tentativa %d falhou para %s: %s",
                            attempt + 1,
                            tribunal_sigla,
                            exc,
                        )
                else:
                    continue

                if resp.status_code == 401:
                    raise PermissionError(
                        "Chave de API do DataJud inválida ou expirada. "
                        "Verifique DATAJUD_API_KEY no .env."
                    )
                if resp.status_code == 404:
                    logger.info("Indice DataJud nao encontrado para %s", tribunal_sigla)
                    break
                if resp.status_code != 200:
                    logger.info(
                        "DataJud %s respondeu %s para %s",
                        tribunal_sigla,
                        resp.status_code,
                        numero_cnj,
                    )
                    continue

                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])
                for hit in hits:
                    if not _hit_matches_numero(hit, numero_norm):
                        continue
                    andamentos = _parse_hit(hit)
                    if andamentos:
                        return andamentos

    if last_exc is not None:
        raise ConnectionError(
            f"DataJud não respondeu após múltiplas tentativas. "
            f"Verifique sua conexão ou tente novamente em instantes. ({last_exc})"
        )

    return []
