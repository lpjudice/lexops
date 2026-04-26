"""PDPJ authenticated scraper — uses a Bearer token obtained from jus.br Network tab.

The token comes from the Authorization header of any authenticated request
visible in the Network tab of DevTools while browsing portaldeservicos.pdpj.jus.br.

NOTE: The PDPJ ecosystem uses multiple microservices. This module tries several
known endpoint patterns from the portal and the cabecalho-processual service.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from datetime import date, datetime

import httpx

from .base import Andamento
from .cnj import candidatos_tribunal, inferir_tribunal_pelo_cnj, normalizar_cnj, normalizar_tribunal

logger = logging.getLogger(__name__)

# Known PDPJ API bases to probe
_BASES = [
    "https://portaldeservicos.pdpj.jus.br/api/v2",
    "https://portaldeservicos.pdpj.jus.br/api",
    "https://portaldeservicos.pdpj.jus.br/api/v1",
    "https://gateway.cloud.pje.jus.br/cabecalho-processual/api/v1",
    "https://gateway.cloud.pje.jus.br/cabecalho-processual/api",
    "https://gateway.cloud.pje.jus.br/cabecalho-processual",
]


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


def _jwt_exp(token: str) -> datetime | None:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        exp = data.get("exp")
        if isinstance(exp, (int, float)):
            return datetime.fromtimestamp(exp)
    except Exception:
        return None
    return None


def _items_from_response(data: object) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("content", "processos", "data", "items", "resultado"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [data]
    return []


def _tribunal_matches(item: dict, tribunal: str | None) -> bool:
    if not tribunal:
        return True
    esperado = normalizar_tribunal(tribunal)
    candidatos = [
        item.get("tribunal"),
        item.get("siglaTribunal"),
        item.get("orgaoJulgador"),
        item.get("orgao"),
    ]
    return any(esperado in normalizar_tribunal(str(valor)) for valor in candidatos if valor)


def _extract_inline_movimentos(data: dict) -> list[dict]:
    for key in ("movimentos", "andamentos", "movements"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


async def buscar_via_pdpj(
    numero_cnj: str,
    tribunal: str,
    token: str | None = None,
    session_data: dict | None = None,
) -> list[Andamento]:
    """Fetch process movements from PDPJ using an authenticated Bearer token.

    Tries multiple known endpoint patterns. Raises PermissionError on 401/403.
    Returns [] if process not found after exhausting all patterns.
    """
    session_data = session_data or {}
    token = token or session_data.get("token") or ""
    if not token:
        raise PermissionError("Sessao do jus.br nao configurada.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://portaldeservicos.pdpj.jus.br",
        "Referer": session_data.get("referer") or "https://portaldeservicos.pdpj.jus.br/",
    }
    extra_headers = session_data.get("extra_headers") or {}
    if isinstance(extra_headers, dict):
        headers.update({str(k): str(v) for k, v in extra_headers.items()})
    if session_data.get("cookies"):
        headers["Cookie"] = str(session_data["cookies"])
    numero_norm = normalizar_cnj(numero_cnj)
    tribunal_norm = normalizar_tribunal(tribunal)
    tribunal_inferido = inferir_tribunal_pelo_cnj(numero_cnj)
    tribunais_candidatos = candidatos_tribunal(numero_cnj, tribunal)

    # ── Candidate search endpoints ────────────────────────────────────────────
    # Each tuple: (method, url, params, json_body)
    candidates = []
    seen_bases: list[str] = []
    for base in [*(session_data.get("api_bases") or []), *_BASES]:
        if base in seen_bases:
            continue
        seen_bases.append(base)
        candidates += [
            ("GET", f"{base}/processos",                   {"numeroProcesso": numero_cnj},  None),
            ("GET", f"{base}/processos",                   {"numeroProcesso": numero_norm}, None),
            ("GET", f"{base}/processos",                   {"numeroProcesso": numero_cnj, "retornarMovimentos": "true"},  None),
            ("GET", f"{base}/processos",                   {"numeroProcesso": numero_norm, "retornarMovimentos": "true"}, None),
            ("GET", f"{base}/processos",                   {"numeroProcesso": numero_norm, "incluirMovimentos": "true"}, None),
            ("GET", f"{base}/processos",                   {"numero": numero_cnj},          None),
            ("GET", f"{base}/processos",                   {"numero": numero_norm},         None),
            ("GET", f"{base}/processos/{numero_cnj}",      {},                              None),
            ("GET", f"{base}/processos/{numero_norm}",     {},                              None),
            ("GET", f"{base}/processo/{numero_cnj}",       {},                              None),
            ("GET", f"{base}/consulta/processos",          {"numeroProcesso": numero_cnj},  None),
            ("GET", f"{base}/consulta/processos",          {"numeroProcesso": numero_norm}, None),
        ]
        for candidato in tribunais_candidatos:
            candidates += [
                ("GET", f"{base}/processos", {"numeroProcesso": numero_norm, "tribunal": candidato}, None),
                ("GET", f"{base}/processos", {"numeroProcesso": numero_norm, "siglaTribunal": candidato}, None),
            ]

    async with httpx.AsyncClient(timeout=20) as client:
        processo_data: dict | None = None
        matched_base = ""
        inline_movimentos: list[dict] = []

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
                exp = _jwt_exp(token)
                extra = f" Token expira em {exp.strftime('%d/%m/%Y %H:%M:%S')}." if exp else ""
                raise PermissionError(
                    "Token expirado ou sem permissão. "
                    "Abra o portal jus.br, faça login e capture um novo token pela aba Network."
                    f"{extra}"
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
            items = _items_from_response(data)

            for item in items:
                n_raw = (item.get("numeroProcesso") or item.get("numero") or "")
                if re.sub(r"\D", "", n_raw) != numero_norm:
                    continue
                if tribunal_norm and not _tribunal_matches(item, tribunal_norm):
                    if tribunal_inferido and _tribunal_matches(item, tribunal_inferido):
                        pass
                    elif item.get("tribunal") or item.get("siglaTribunal"):
                        continue
                if re.sub(r"\D", "", n_raw) == numero_norm:
                    processo_data = item
                    matched_base = url.rsplit("/", 2)[0]  # strip /processos
                    inline_movimentos = _extract_inline_movimentos(item)
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

        if inline_movimentos:
            items = inline_movimentos
        else:
        # ── Fetch movimentos ──────────────────────────────────────────────────
            mov_candidates = [
                f"{matched_base}/processos/{processo_id}/movimentos",
                f"{matched_base}/processos/{numero_cnj}/movimentos",
                f"{matched_base}/processos/{numero_norm}/movimentos",
                f"{matched_base}/processos/{processo_id}/andamentos",
                f"{matched_base}/movimentos?processoId={processo_id}",
                f"{matched_base}/movimentos?numeroProcesso={numero_norm}",
            ]

            items = []
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

                items = _items_from_response(md)
                if not items and isinstance(md, dict):
                    items = _extract_inline_movimentos(md)
                if items:
                    break

        andamentos: list[Andamento] = []
        for m in items:
            dt = _parse_data(
                m.get("dataHora") or m.get("dataMovimento") or m.get("data") or m.get("datahora")
            )
            desc = _movimento_desc(m)
            tipo = m.get("nome") or m.get("tipo") or m.get("descricao")

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
