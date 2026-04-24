"""PDPJ authenticated scraper — uses a Bearer token obtained from jus.br Network tab.

The token comes from the Authorization header of any authenticated request
visible in the Network tab of DevTools while browsing portaldeservicos.pdpj.jus.br.

NOTE: The PDPJ ecosystem uses multiple microservices. This module tries several
known endpoint patterns from the portal and the cabecalho-processual service.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

import httpx

from .base import Andamento

logger = logging.getLogger(__name__)

# Known PDPJ API bases to probe
_BASES = [
    "https://portaldeservicos.pdpj.jus.br/api",
    "https://portaldeservicos.pdpj.jus.br/api/v1",
    "https://gateway.cloud.pje.jus.br/cabecalho-processual/api/v1",
    "https://gateway.cloud.pje.jus.br/cabecalho-processual/api",
]


def _normalizar_cnj(numero: str) -> str:
    return re.sub(r"\D", "", numero)


def _parse_data(raw: str | None) -> date | None:
    if not raw:
        return None
    for prefix_len in (10, 19, 24, 27):
        try:
            chunk = raw[:prefix_len]
            return datetime.fromisoformat(chunk.replace("Z", "+00:00")).date()
        except Exception:
            pass
    return None


def _movimento_desc(m: dict) -> str:
    partes: list[str] = []
    for key in ("nome", "descricao", "tipo", "complemento", "tituloDocumento"):
        v = m.get(key)
        if v and isinstance(v, str):
            partes.append(v.strip())
    return " — ".join(dict.fromkeys(p for p in partes if p))


async def buscar_via_pdpj(numero_cnj: str, tribunal: str, token: str) -> list[Andamento]:
    """Fetch process movements from PDPJ using an authenticated Bearer token.

    Tries multiple known endpoint patterns. Raises PermissionError on 401/403.
    Returns [] if process not found after exhausting all patterns.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    numero_norm = _normalizar_cnj(numero_cnj)

    # ── Candidate search endpoints ────────────────────────────────────────────
    # Each tuple: (method, url, params, json_body)
    candidates = []
    for base in _BASES:
        candidates += [
            ("GET", f"{base}/processos",                   {"numeroProcesso": numero_cnj},  None),
            ("GET", f"{base}/processos",                   {"numeroProcesso": numero_norm}, None),
            ("GET", f"{base}/processos",                   {"numero": numero_cnj},          None),
            ("GET", f"{base}/processos",                   {"numero": numero_norm},         None),
            ("GET", f"{base}/processos/{numero_cnj}",      {},                              None),
            ("GET", f"{base}/processos/{numero_norm}",     {},                              None),
            ("GET", f"{base}/processo/{numero_cnj}",       {},                              None),
            ("GET", f"{base}/consulta/processos",          {"numeroProcesso": numero_cnj},  None),
            ("GET", f"{base}/consulta/processos",          {"numeroProcesso": numero_norm}, None),
        ]

    async with httpx.AsyncClient(timeout=20) as client:
        processo_data: dict | None = None
        matched_base = ""

        for method, url, params, body in candidates:
            try:
                resp = await client.request(
                    method, url,
                    headers=headers,
                    params=params or None,
                    json=body,
                )
            except httpx.RequestError as exc:
                logger.debug("PDPJ connection error %s: %s", url, exc)
                continue

            logger.info("PDPJ probe %s %s params=%s → %s", method, url, params, resp.status_code)

            if resp.status_code in (401, 403):
                raise PermissionError(
                    "Token expirado ou sem permissão. "
                    "Abra o portal jus.br, faça login e capture um novo token pela aba Network."
                )
            if resp.status_code == 404:
                continue
            if resp.status_code != 200:
                logger.debug("PDPJ %s → %s: %s", url, resp.status_code, resp.text[:200])
                continue

            try:
                data = resp.json()
            except Exception:
                continue

            # Unwrap paginated response
            items = (
                data if isinstance(data, list)
                else data.get("content")
                or data.get("processos")
                or data.get("data")
                or ([data] if isinstance(data, dict) and data else [])
            )

            for item in items:
                n_raw = (item.get("numeroProcesso") or item.get("numero") or "")
                if re.sub(r"\D", "", n_raw) == numero_norm:
                    processo_data = item
                    matched_base = url.rsplit("/", 2)[0]  # strip /processos
                    break

            if processo_data:
                break

        if not processo_data:
            logger.warning("PDPJ: process %s not found after probing all endpoints", numero_cnj)
            return []

        processo_id = str(
            processo_data.get("id")
            or processo_data.get("processoId")
            or numero_norm
        )

        # ── Fetch movimentos ──────────────────────────────────────────────────
        mov_candidates = [
            f"{matched_base}/processos/{processo_id}/movimentos",
            f"{matched_base}/processos/{numero_cnj}/movimentos",
            f"{matched_base}/processos/{numero_norm}/movimentos",
            f"{matched_base}/processos/{processo_id}/andamentos",
            f"{matched_base}/movimentos?processoId={processo_id}",
            f"{matched_base}/movimentos?numeroProcesso={numero_norm}",
        ]

        for url in mov_candidates:
            try:
                mr = await client.get(url, headers=headers)
            except Exception:
                continue

            logger.info("PDPJ movimentos probe %s → %s", url, mr.status_code)

            if mr.status_code in (401, 403):
                raise PermissionError("Token expirado ao buscar movimentos. Renove o token.")
            if mr.status_code != 200:
                continue

            try:
                md = mr.json()
            except Exception:
                continue

            items = md if isinstance(md, list) else (
                md.get("content")
                or md.get("movimentos")
                or md.get("andamentos")
                or md.get("data")
                or []
            )

            andamentos: list[Andamento] = []
            for m in items:
                dt = _parse_data(
                    m.get("dataHora") or m.get("dataMovimento") or m.get("data") or m.get("datahora")
                )
                desc = _movimento_desc(m)
                tipo = m.get("nome") or m.get("tipo") or m.get("descricao")

                # Enrich with document name if available
                for doc_key in ("documento", "doc", "arquivo"):
                    doc = m.get(doc_key)
                    if isinstance(doc, dict):
                        doc_nome = doc.get("nome") or doc.get("nomeArquivo") or doc.get("filename") or ""
                        if doc_nome:
                            desc = f"{desc} — {doc_nome}" if desc else doc_nome
                        break

                if desc:
                    andamentos.append(Andamento(
                        data_andamento=dt,
                        descricao=desc[:2000],
                        tipo=tipo,
                        grau=m.get("grau"),
                    ))

            if andamentos:
                return andamentos

    return []
