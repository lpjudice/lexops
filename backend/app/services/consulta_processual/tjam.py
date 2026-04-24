"""TJAM scraper — two systems:
  1. LIBRA  (1G/2G): https://consultaprocessual.tjam.jus.br/consultaProcessual/consulta
  2. PJe    (1G/2G): https://pje.tjam.jus.br/pjekz/  (JSON API)
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup

from .base import Andamento, BaseScraper

logger = logging.getLogger(__name__)


def _parse_data(txt: str) -> date | None:
    txt = txt.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            pass
    return None


class TJAMScraper(BaseScraper):
    tribunal = "TJAM"

    async def buscar_andamentos(self, numero_cnj: str) -> list[Andamento]:  # type: ignore[override]
        andamentos: list[Andamento] = []
        async with httpx.AsyncClient(follow_redirects=True) as client:
            try:
                andamentos += await self._libra(client, numero_cnj)
            except Exception as exc:
                logger.warning("TJAM LIBRA falhou (%s): %s", numero_cnj, exc)
            try:
                andamentos += await self._pje(client, numero_cnj)
            except Exception as exc:
                logger.warning("TJAM PJe falhou (%s): %s", numero_cnj, exc)
        return andamentos

    # ── LIBRA ─────────────────────────────────────────────────────────────────

    async def _libra(self, client: httpx.AsyncClient, numero_cnj: str) -> list[Andamento]:
        url = "https://consultaprocessual.tjam.jus.br/consultaProcessual/consulta"
        params = {"numProcesso": numero_cnj}
        resp = await self._get(client, url, params=params)
        return self._parse_libra(resp.text)

    def _parse_libra(self, html: str) -> list[Andamento]:
        soup = BeautifulSoup(html, "lxml")
        andamentos: list[Andamento] = []
        # LIBRA renders a table with class "table" or "tablesorter"
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
            if not any("data" in h or "moviment" in h or "andamento" in h for h in headers):
                continue
            for row in rows[1:]:
                cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]
                if len(cells) < 2:
                    continue
                dt = _parse_data(cells[0])
                desc = cells[-1] if len(cells) > 1 else cells[0]
                if desc:
                    andamentos.append(
                        Andamento(data_andamento=dt, descricao=desc[:2000], grau=None)
                    )
        return andamentos

    # ── PJe ───────────────────────────────────────────────────────────────────

    async def _pje(self, client: httpx.AsyncClient, numero_cnj: str) -> list[Andamento]:
        # PJe exposes a JSON endpoint for public consultation
        url = "https://pje.tjam.jus.br/pjekz/api/public/processo/consultaPublica"
        params = {"numeroProcesso": numero_cnj}
        try:
            resp = await self._get(client, url, params=params)
            data = resp.json()
        except Exception:
            # PJe may not have the process; return empty
            return []

        andamentos: list[Andamento] = []
        # Navigate typical PJe JSON structure
        movimentos = []
        if isinstance(data, dict):
            movimentos = (
                data.get("movimentos")
                or data.get("andamentos")
                or data.get("items")
                or []
            )
        for m in movimentos:
            if not isinstance(m, dict):
                continue
            desc = m.get("descricao") or m.get("complemento") or m.get("nome") or ""
            raw_data = m.get("dataHora") or m.get("data") or m.get("dtMovimento") or ""
            dt = _parse_data(str(raw_data)[:10]) if raw_data else None
            tipo = m.get("tipo") or m.get("tipoMovimento") or None
            if desc:
                andamentos.append(
                    Andamento(data_andamento=dt, descricao=str(desc)[:2000], tipo=tipo, grau=None)
                )
        return andamentos
