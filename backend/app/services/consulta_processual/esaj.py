"""ESAJ/SAJ scraper — TJSP (1G + 2G) and TJES (1G + 2G).

TJSP  1G: https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo=...
TJSP  2G: https://esaj.tjsp.jus.br/cposg/show.do
TJES  1G: https://sistemas.tjes.jus.br/efront/php/sistemas/consulta-processual/...
TJES  2G: https://sistemas.tjes.jus.br/esaj/portal.do?servico=780000

The SAJ system is the same across tribunais, so we share parsing logic.
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
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            pass
    return None


def _parse_esaj_movimentos(html: str, grau: str) -> list[Andamento]:
    """Parse andamentos from ESAJ HTML (SAJ system used by TJSP and TJES)."""
    soup = BeautifulSoup(html, "lxml")
    andamentos: list[Andamento] = []

    # ESAJ movement table: <tbody id="tabelaTodasMovimentacoes"> or <table class="secaoFormBody">
    tbody = soup.find("tbody", id="tabelaTodasMovimentacoes") or soup.find(
        "tbody", id="tabelaUltimasMovimentacoes"
    )
    if not tbody:
        # fallback: any table with 'Movimentações' in a heading nearby
        tables = soup.find_all("table")
        for t in tables:
            rows = t.find_all("tr")
            if len(rows) > 1:
                # Check headers
                ths = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
                if any("data" in h.lower() or "moviment" in h.lower() for h in ths):
                    tbody = t
                    break

    if not tbody:
        return andamentos

    rows = tbody.find_all("tr") if tbody.name in ("tbody", "table") else []
    # Skip header row if tbody is actually a table
    start = 0
    for i, row in enumerate(rows):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        raw_data = cells[0].get_text(strip=True)
        raw_desc = cells[-1].get_text(" ", strip=True)
        dt = _parse_data(raw_data)
        if raw_desc:
            andamentos.append(
                Andamento(
                    data_andamento=dt,
                    descricao=raw_desc[:2000],
                    tipo=None,
                    grau=grau,
                )
            )

    return andamentos


class ESAJScraper(BaseScraper):
    """Handles TJSP and TJES (both use SAJ/ESAJ)."""

    # Subclasses or callers set tribunal
    tribunal = "ESAJ"

    async def buscar_andamentos(self, numero_cnj: str, tribunal: str = "TJSP") -> list[Andamento]:  # type: ignore[override]
        andamentos: list[Andamento] = []
        async with httpx.AsyncClient(follow_redirects=True) as client:
            if tribunal == "TJSP":
                andamentos += await self._tjsp(client, numero_cnj)
            elif tribunal == "TJES":
                andamentos += await self._tjes(client, numero_cnj)
        return andamentos

    # ── TJSP ──────────────────────────────────────────────────────────────────

    async def _tjsp(self, client: httpx.AsyncClient, numero_cnj: str) -> list[Andamento]:
        resultado: list[Andamento] = []
        # 1G
        try:
            resultado += await self._tjsp_grau(client, numero_cnj, "1G")
        except Exception as exc:
            logger.warning("TJSP 1G falhou (%s): %s", numero_cnj, exc)
        # 2G
        try:
            resultado += await self._tjsp_grau(client, numero_cnj, "2G")
        except Exception as exc:
            logger.warning("TJSP 2G falhou (%s): %s", numero_cnj, exc)
        return resultado

    async def _tjsp_grau(
        self, client: httpx.AsyncClient, numero_cnj: str, grau: str
    ) -> list[Andamento]:
        base = "cpopg" if grau == "1G" else "cposg"
        url = f"https://esaj.tjsp.jus.br/{base}/search.do"
        params = {
            "conversationId": "",
            "cbPesquisa": "NUMPROC",
            "numeroDigitoAnoUnificado": "",
            "foroNumeroUnificado": "",
            "dadosConsulta.valorConsultaNuUnificado": numero_cnj,
            "dadosConsulta.valorConsulta": "",
            "dadosConsulta.tipoNuProcesso": "UNIFICADO",
        }
        resp = await self._get(client, url, params=params)
        html = resp.text
        andamentos = _parse_esaj_movimentos(html, grau)
        # If no results on search page, try show.do from redirect
        if not andamentos and "show.do" in resp.url.path:
            andamentos = _parse_esaj_movimentos(html, grau)
        return andamentos

    # ── TJES ──────────────────────────────────────────────────────────────────

    async def _tjes(self, client: httpx.AsyncClient, numero_cnj: str) -> list[Andamento]:
        resultado: list[Andamento] = []
        # TJES 1G via SAJ
        try:
            resultado += await self._tjes_grau(client, numero_cnj, "1G")
        except Exception as exc:
            logger.warning("TJES 1G falhou (%s): %s", numero_cnj, exc)
        # TJES 2G via SAJ
        try:
            resultado += await self._tjes_grau(client, numero_cnj, "2G")
        except Exception as exc:
            logger.warning("TJES 2G falhou (%s): %s", numero_cnj, exc)
        return resultado

    async def _tjes_grau(
        self, client: httpx.AsyncClient, numero_cnj: str, grau: str
    ) -> list[Andamento]:
        # TJES uses a SAJ portal similar to TJSP
        if grau == "1G":
            url = "https://sistemas.tjes.jus.br/efront/php/sistemas/consulta-processual/consulta_todos.php"
        else:
            url = "https://sistemas.tjes.jus.br/esaj/portal.do"
        params = {
            "servico": "190010" if grau == "1G" else "780000",
            "cbPesquisa": "NUMPROC",
            "dadosConsulta.valorConsultaNuUnificado": numero_cnj,
            "dadosConsulta.tipoNuProcesso": "UNIFICADO",
        }
        resp = await self._get(client, url, params=params)
        return _parse_esaj_movimentos(resp.text, grau)
