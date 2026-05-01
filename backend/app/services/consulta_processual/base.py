"""Base class for process consultation scrapers."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date

import httpx

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}


@dataclass
class Andamento:
    data_andamento: date | None
    descricao: str
    tipo: str | None = None
    grau: str | None = None   # "1G", "2G"
    arquivo_nome: str | None = None
    arquivo_bytes: bytes | None = None
    arquivo_mimetype: str | None = None
    documento_detectado: bool = False


class BaseScraper:
    """Abstract base for tribunal scrapers."""

    tribunal: str = ""

    async def buscar_andamentos(self, numero_cnj: str) -> list[Andamento]:
        raise NotImplementedError

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict | None = None,
        retries: int = 3,
        delay: float = 2.0,
    ) -> httpx.Response:
        for attempt in range(retries):
            try:
                resp = await client.get(url, params=params, headers=HEADERS, timeout=30)
                resp.raise_for_status()
                return resp
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                if attempt < retries - 1:
                    await asyncio.sleep(delay * (attempt + 1))
                    continue
                raise exc
        raise RuntimeError("unreachable")

    async def _post(
        self,
        client: httpx.AsyncClient,
        url: str,
        data: dict | None = None,
        json: dict | None = None,
        retries: int = 3,
        delay: float = 2.0,
    ) -> httpx.Response:
        for attempt in range(retries):
            try:
                resp = await client.post(
                    url, data=data, json=json, headers=HEADERS, timeout=30
                )
                resp.raise_for_status()
                return resp
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                if attempt < retries - 1:
                    await asyncio.sleep(delay * (attempt + 1))
                    continue
                raise exc
        raise RuntimeError("unreachable")
