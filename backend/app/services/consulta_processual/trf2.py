"""TRF2 scraper — eProc system.

Public consultation:
  https://eproc.trf2.jus.br/eproc2trf2/controlador.php?acao=processo_consulta_publica
"""
from __future__ import annotations

import logging
from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup

from .base import Andamento, BaseScraper

logger = logging.getLogger(__name__)


def _parse_data(txt: str) -> date | None:
    txt = txt.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            pass
    return None


class TRF2Scraper(BaseScraper):
    tribunal = "TRF2"

    BASE = "https://eproc.trf2.jus.br/eproc2trf2/controlador.php"

    async def buscar_andamentos(self, numero_cnj: str) -> list[Andamento]:  # type: ignore[override]
        async with httpx.AsyncClient(follow_redirects=True) as client:
            try:
                return await self._eproc(client, numero_cnj)
            except Exception as exc:
                logger.warning("TRF2 falhou (%s): %s", numero_cnj, exc)
                return []

    async def _eproc(self, client: httpx.AsyncClient, numero_cnj: str) -> list[Andamento]:
        # Step 1: submit search form
        params = {
            "acao": "processo_consulta_publica",
            "num_processo": numero_cnj,
        }
        resp = await self._get(client, self.BASE, params=params)
        return self._parse_eproc(resp.text)

    def _parse_eproc(self, html: str) -> list[Andamento]:
        soup = BeautifulSoup(html, "lxml")
        andamentos: list[Andamento] = []

        # eProc renders events in a <table> with class "infraTable" or similar
        for table in soup.find_all("table", class_=lambda c: c and "infra" in c.lower()):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
            if not any(kw in " ".join(headers) for kw in ("data", "evento", "moviment", "andamento")):
                continue
            for row in rows[1:]:
                cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]
                if len(cells) < 2:
                    continue
                dt = _parse_data(cells[0])
                desc = " — ".join(cells[1:]) if len(cells) > 1 else cells[0]
                if desc:
                    andamentos.append(
                        Andamento(data_andamento=dt, descricao=desc[:2000], grau=None)
                    )

        # Fallback: any table that has date-like values
        if not andamentos:
            for table in soup.find_all("table"):
                rows = table.find_all("tr")
                for row in rows[1:]:
                    cells = [td.get_text(" ", strip=True) for td in row.find_all("td")]
                    if len(cells) >= 2:
                        dt = _parse_data(cells[0])
                        if dt:
                            desc = " — ".join(cells[1:])
                            if desc:
                                andamentos.append(
                                    Andamento(data_andamento=dt, descricao=desc[:2000], grau=None)
                                )
                if andamentos:
                    break

        return andamentos
