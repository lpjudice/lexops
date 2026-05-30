"""PDPJ Portal de Serviços API v2 client — deterministic, single endpoint.

The whole process (metadata + movimentos + documentos) is returned by one call:

    GET https://portaldeservicos.pdpj.jus.br/api/v2/processos/{cnj_normalizado}

Headers: ``Authorization: Bearer <jwt>`` (token captured from jus.br), plus the
session cookies/referer when available. The response is a list; each item has
``tramitacaoAtual.movimentos[]`` and ``tramitacaoAtual.documentos[]`` (two
separate arrays — there is no explicit FK between a movimento and a documento).

Documents are downloaded by following each document's ``hrefBinario`` against the
same ``/api/v2`` base with the same Bearer token. We do NOT reconstruct gateway
URLs anymore.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from datetime import date, datetime

import httpx

from .base import Andamento
from .cnj import inferir_tribunal_pelo_cnj, normalizar_cnj, normalizar_tribunal

logger = logging.getLogger(__name__)

PORTAL_ROOT = "https://portaldeservicos.pdpj.jus.br"
PDPJ_API_BASE = f"{PORTAL_ROOT}/api/v2"

# Max time gap (seconds) for treating a documento as the attachment of a
# movimento. A "juntada" movimento and its bundled documents share (near-)
# identical timestamps (sub-second in practice); a few minutes of slack covers
# tribunals that register the movimento slightly after the juntada. Documents
# outside this window become their own row, so none is ever dropped.
_DOC_MATCH_TOLERANCE_SECONDS = 5 * 60


# ── Datetime parsing ──────────────────────────────────────────────────────────

def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip().replace("Z", "")
    for length in (None, 23, 19, 10):
        chunk = s if length is None else s[:length]
        try:
            return datetime.fromisoformat(chunk)
        except Exception:
            continue
    return None


def _parse_data(raw: str | None) -> date | None:
    dt = _parse_dt(raw)
    if dt:
        return dt.date()
    digits = re.sub(r"\D", "", str(raw or ""))[:8]
    if len(digits) == 8:
        try:
            return datetime.strptime(digits, "%Y%m%d").date()
        except Exception:
            return None
    return None


# ── JWT helpers ────────────────────────────────────────────────────────────────

def _jwt_payload(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _jwt_exp(token: str) -> datetime | None:
    exp = _jwt_payload(token).get("exp")
    if isinstance(exp, (int, float)):
        try:
            return datetime.fromtimestamp(exp)
        except Exception:
            return None
    return None


def _cpf_operador_from_token(token: str) -> str | None:
    payload = _jwt_payload(token)
    for key in ("preferred_username", "cpf", "cpfUsuario", "cpf_usuario", "sub"):
        digits = re.sub(r"\D", "", str(payload.get(key) or ""))
        if len(digits) == 11:
            return digits
    return None


# ── Headers ─────────────────────────────────────────────────────────────────────

def _build_headers(token: str, session_data: dict | None = None) -> dict[str, str]:
    session_data = session_data or {}
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Origin": PORTAL_ROOT,
        "Referer": session_data.get("referer") or f"{PORTAL_ROOT}/",
    }
    extra_headers = session_data.get("extra_headers") or {}
    if isinstance(extra_headers, dict):
        headers.update({str(k): str(v) for k, v in extra_headers.items()})
    if not any(k.lower() == "x-pdpj-cpf-usuario-operador" for k in headers):
        cpf_operador = _cpf_operador_from_token(token)
        if cpf_operador:
            headers["X-PDPJ-CPF-USUARIO-OPERADOR"] = cpf_operador
    if session_data.get("cookies"):
        headers["Cookie"] = str(session_data["cookies"])
    return headers


def _build_document_headers(headers: dict[str, str]) -> dict[str, str]:
    allowed = {
        "authorization",
        "accept-language",
        "origin",
        "referer",
        "cookie",
        "user-agent",
        "sec-ch-ua",
        "sec-ch-ua-mobile",
        "sec-ch-ua-platform",
        "sec-fetch-dest",
        "sec-fetch-mode",
        "sec-fetch-site",
        "x-pdpj-cpf-usuario-operador",
    }
    doc_headers = {key: value for key, value in headers.items() if key.lower() in allowed}
    doc_headers["Accept"] = "application/pdf,text/html,application/octet-stream,*/*"
    doc_headers.setdefault("Referer", f"{PORTAL_ROOT}/")
    return doc_headers


# ── Response shaping ──────────────────────────────────────────────────────────

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


def _selecionar_processo(data: object, numero_norm: str) -> dict | None:
    items = _items_from_response(data)
    for item in items:
        numero = re.sub(r"\D", "", str(item.get("numeroProcesso") or item.get("numero") or ""))
        if numero and numero != numero_norm:
            continue
        return item
    return items[0] if items else None


def _tramitacao(item: dict) -> dict:
    tram = item.get("tramitacaoAtual")
    if isinstance(tram, dict):
        return tram
    tramitacoes = item.get("tramitacoes")
    if isinstance(tramitacoes, list):
        for t in tramitacoes:
            if isinstance(t, dict) and (t.get("movimentos") or t.get("documentos")):
                return t
    # Some payloads expose movimentos/documentos directly on the item.
    if item.get("movimentos") or item.get("documentos"):
        return item
    return {}


# ── Field extraction ──────────────────────────────────────────────────────────

def _movimento_desc(m: dict) -> str:
    for key in ("descricao", "nome"):
        v = m.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    tipo = m.get("tipo")
    if isinstance(tipo, dict):
        nested = tipo.get("nome") or tipo.get("descricao")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    if isinstance(tipo, str) and tipo.strip():
        return tipo.strip()
    return ""


def _movimento_tipo(m: dict) -> str | None:
    tipo = m.get("tipo")
    if isinstance(tipo, dict):
        nested = tipo.get("nome") or tipo.get("descricao")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()[:255]
    if isinstance(tipo, str) and tipo.strip():
        return tipo.strip()[:255]
    nome = m.get("nome")
    if isinstance(nome, str) and nome.strip():
        return nome.strip()[:255]
    return None


def _doc_tipo_nome(doc: dict) -> str | None:
    tipo = doc.get("tipo")
    if isinstance(tipo, dict):
        nome = tipo.get("nome") or tipo.get("descricao")
        if isinstance(nome, str) and nome.strip():
            return nome.strip()[:255]
    if isinstance(tipo, str) and tipo.strip():
        return tipo.strip()[:255]
    return None


def _doc_descricao(doc: dict) -> str:
    nome = doc.get("nome")
    if isinstance(nome, str) and nome.strip():
        return nome.strip()
    tipo = _doc_tipo_nome(doc)
    seq = doc.get("sequencia")
    if tipo and seq is not None:
        return f"{tipo} (seq. {seq})"
    return tipo or "Documento"


def _nome_documento(doc: dict, fallback: str) -> str:
    nome = (
        doc.get("nome")
        or doc.get("nomeArquivo")
        or doc.get("filename")
        or doc.get("tituloDocumento")
        or fallback
    )
    if not isinstance(nome, str) or not nome.strip():
        nome = fallback
    nome = re.sub(r'[\\/:*?"<>|]+', "_", nome).strip()
    return nome or fallback


def _doc_mimetype(doc: dict) -> str | None:
    arquivo = doc.get("arquivo")
    if isinstance(arquivo, dict):
        tipo = arquivo.get("tipo") or arquivo.get("mimetype")
        if isinstance(tipo, str) and tipo.strip():
            return tipo.strip()
    mimetype = doc.get("mimetype")
    if isinstance(mimetype, str) and mimetype.strip():
        return mimetype.strip()
    return None


def _conteudo_documento_valido(content: bytes, content_type: str | None) -> bool:
    if not content:
        return False
    ct = (content_type or "").lower()
    prefix = content[:400].decode("utf-8", errors="ignore").lower()

    if "application/json" in ct:
        return False
    if "text/html" in ct and "portal de serviços do poder judiciário" in prefix:
        return False
    if '"code":500' in prefix or "503 service temporarily unavailable" in prefix:
        return False
    return True


# ── Movimento ↔ documento linkage ──────────────────────────────────────────────

def _agrupar_documentos_por_movimento(
    movimentos: list[dict],
    documentos: list[dict],
) -> tuple[dict[int, list[int]], list[int]]:
    """Many-to-one: assign each documento to its nearest movimento by timestamp.

    A "Juntada" movimento bundles several documents that share its timestamp, so
    multiple documents map to the same movimento. Returns ``(grupos, orfaos)``
    where ``grupos[mov_idx] = [doc_idx, ...]`` and ``orfaos`` lists documents with
    no movimento within ``_DOC_MATCH_TOLERANCE_SECONDS`` (never dropped).
    """
    mov_dts: list[tuple[datetime, int]] = []
    for mi, mov in enumerate(movimentos):
        dm = _parse_dt(mov.get("dataHora") or mov.get("dataMovimento") or mov.get("data"))
        if dm:
            mov_dts.append((dm, mi))

    grupos: dict[int, list[int]] = {}
    orfaos: list[int] = []
    for di, doc in enumerate(documentos):
        dj = _parse_dt(doc.get("dataHoraJuntada") or doc.get("dataHora"))
        best_mi: int | None = None
        best_delta: float | None = None
        if dj:
            for dm, mi in mov_dts:
                delta = abs((dj - dm).total_seconds())
                if best_delta is None or delta < best_delta:
                    best_delta = delta
                    best_mi = mi
        if best_mi is not None and best_delta is not None and best_delta <= _DOC_MATCH_TOLERANCE_SECONDS:
            grupos.setdefault(best_mi, []).append(di)
        else:
            orfaos.append(di)
    return grupos, orfaos


# ── Document download (called lazily by the orchestrator) ──────────────────────

def _documento_url_from_href(href: str | None) -> str | None:
    if not isinstance(href, str) or not href.strip():
        return None
    href = href.strip()
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if not href.startswith("/"):
        href = "/" + href
    return f"{PDPJ_API_BASE}{href}"


async def baixar_documento_jusbr(
    arquivo_url: str,
    token: str | None = None,
    session_data: dict | None = None,
) -> tuple[bytes, str | None] | None:
    """Download a single PDPJ document by its (already-resolved) binário URL.

    Returns ``(content, mimetype)`` or ``None`` (not found / no permission /
    invalid content). Called only for new or missing documents, so the full case
    file is never re-downloaded on every sync.
    """
    session_data = session_data or {}
    token = token or session_data.get("token") or ""
    if not token or not arquivo_url:
        return None

    headers = _build_document_headers(_build_headers(token, session_data))
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.get(arquivo_url, headers=headers)
    except Exception as exc:
        logger.info("PDPJ documento download falhou %s: %s", arquivo_url, exc)
        return None

    if resp.status_code in (401, 403):
        logger.info("PDPJ documento %s → %s (sem download)", arquivo_url, resp.status_code)
        return None
    if resp.status_code != 200 or not resp.content:
        return None

    content_type = resp.headers.get("content-type", "")
    if not _conteudo_documento_valido(resp.content, content_type):
        return None

    return resp.content, (content_type or None)


# ── Public API ──────────────────────────────────────────────────────────────────

def _raise_auth_error(status_code: int, token: str) -> None:
    exp = _jwt_exp(token)
    extra = f" Token expira em {exp.strftime('%d/%m/%Y %H:%M:%S')}." if exp else ""
    if status_code == 403:
        raise PermissionError(
            "Sessão do jus.br válida, mas sem permissão para este processo. "
            "Confirme se o processo abre no portal com o mesmo login." + extra
        )
    raise PermissionError(
        "Token do jus.br expirado ou inválido. Abra o portal, faça login e "
        "capture um novo token (JSON ou cURL)." + extra
    )


def _short_body(resp: httpx.Response, limit: int = 600) -> str:
    """Truncated, secret-safe snippet of a response body for diagnostics."""
    try:
        text = resp.text or ""
    except Exception:
        return ""
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._\-]+", "Bearer ***", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


async def _fetch_processo_v2(
    client: httpx.AsyncClient,
    numero_cnj: str,
    numero_norm: str,
    headers: dict[str, str],
    token: str,
) -> dict | None:
    """GET the process from PDPJ v2, tolerating the CNJ-format ambiguity.

    Tries the 20-digit form first, then the formatted CNJ on 403/404 (the
    document ``hrefBinario`` uses the formatted form, so the endpoint accepts it
    too). Raises ``PermissionError`` only when *every* attempt is 401/403,
    ``ConnectionError`` on 5xx. Logs status + masked body for each attempt so the
    real PDPJ error (e.g. "operador não informado") is visible in ``fly logs``.
    """
    cpf_op = next((v for k, v in headers.items() if k.lower() == "x-pdpj-cpf-usuario-operador"), None)
    logger.info(
        "PDPJ v2: consultando %s | cpf_operador=%s | cookies=%s",
        numero_cnj,
        (f"***{cpf_op[-2:]}" if cpf_op else "AUSENTE"),
        ("sim" if any(k.lower() == "cookie" for k in headers) else "nao"),
    )

    identificadores = [numero_norm]
    if numero_cnj and numero_cnj != numero_norm:
        identificadores.append(numero_cnj)

    last_auth_status: int | None = None
    for ident in identificadores:
        url = f"{PDPJ_API_BASE}/processos/{ident}"
        try:
            resp = await client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise ConnectionError(f"Falha ao conectar ao jus.br/PDPJ: {exc}") from exc

        if resp.status_code == 200:
            logger.info("PDPJ v2 GET %s -> 200", url)
            try:
                data = resp.json()
            except Exception:
                logger.warning("PDPJ v2 %s: 200 com corpo nao-JSON", url)
                return None
            item = _selecionar_processo(data, numero_norm)
            if not item:
                logger.warning("PDPJ v2 %s: 200 sem processo no corpo", url)
            return item

        body = _short_body(resp)
        logger.warning("PDPJ v2 GET %s -> %s | body=%s", url, resp.status_code, body)

        if resp.status_code in (401, 403):
            last_auth_status = resp.status_code
            continue
        if resp.status_code == 404:
            continue
        if resp.status_code >= 500:
            raise ConnectionError(
                f"O jus.br/PDPJ respondeu indisponível (HTTP {resp.status_code}). "
                "Tente novamente em instantes."
            )
        return None

    if last_auth_status is not None:
        _raise_auth_error(last_auth_status, token)
    return None


async def buscar_processo_pdpj_raw(
    numero_cnj: str,
    tribunal: str = "",
    token: str | None = None,
    session_data: dict | None = None,
) -> dict | None:
    """Return the raw PDPJ v2 process item (metadata + tramitacaoAtual).

    Used for prefilling a new process from jus.br. Raises ``PermissionError`` on
    401/403, returns ``None`` if the process is not found.
    """
    session_data = session_data or {}
    token = token or session_data.get("token") or ""
    if not token:
        raise PermissionError("Sessao do jus.br nao configurada.")

    headers = _build_headers(token, session_data)
    numero_norm = normalizar_cnj(numero_cnj)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        return await _fetch_processo_v2(client, numero_cnj, numero_norm, headers, token)


async def buscar_via_pdpj(
    numero_cnj: str,
    tribunal: str,
    token: str | None = None,
    session_data: dict | None = None,
) -> list[Andamento]:
    """Fetch process movements + documents from the deterministic PDPJ v2 API.

    Raises ``PermissionError`` on 401/403. Returns ``[]`` if the process is not
    found.
    """
    session_data = session_data or {}
    token = token or session_data.get("token") or ""
    if not token:
        raise PermissionError("Sessao do jus.br nao configurada.")

    headers = _build_headers(token, session_data)
    numero_norm = normalizar_cnj(numero_cnj)

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        item = await _fetch_processo_v2(client, numero_cnj, numero_norm, headers, token)

    if not item:
        logger.warning("PDPJ v2: processo %s nao retornado", numero_cnj)
        return []

    tram = _tramitacao(item)
    movimentos = [m for m in (tram.get("movimentos") or []) if isinstance(m, dict)]
    documentos = [d for d in (tram.get("documentos") or []) if isinstance(d, dict)]
    grau = tram.get("grau") if isinstance(tram.get("grau"), str) else None

    logger.info(
        "PDPJ v2 %s: tram_keys=%s movimentos=%d documentos=%d",
        numero_cnj, list(tram.keys())[:12], len(movimentos), len(documentos),
    )

    grupos, orfaos = _agrupar_documentos_por_movimento(movimentos, documentos)
    logger.info(
        "PDPJ v2 %s: grupos=%d docs_agrupados=%d orfaos=%d",
        numero_cnj, len(grupos), sum(len(v) for v in grupos.values()), len(orfaos),
    )

    andamentos: list[Andamento] = []

    # 1) Movimentos as rows. A juntada movimento bundling N documents yields N
    #    rows — one per document — so every file gets its own download button.
    #    The description is derived purely from metadata (movimento + document
    #    name), so the dedup hash is unique per document AND stable across syncs
    #    regardless of whether the binary download later succeeds.
    for mi, mov in enumerate(movimentos):
        desc = _movimento_desc(mov)
        if not desc:
            continue
        dt = _parse_data(mov.get("dataHora") or mov.get("dataMovimento") or mov.get("data"))
        mov_grau = mov.get("grau") if isinstance(mov.get("grau"), str) else grau
        docs_idx = grupos.get(mi, [])

        if not docs_idx:
            andamentos.append(Andamento(
                data_andamento=dt,
                descricao=desc[:2000],
                tipo=_movimento_tipo(mov),
                grau=mov_grau,
                documento_detectado=False,
            ))
            continue

        for di in docs_idx:
            doc = documentos[di]
            doc_nome = _nome_documento(doc, _doc_descricao(doc))
            row_desc = f"{desc} — {doc_nome}" if desc else doc_nome
            andamentos.append(Andamento(
                data_andamento=dt,
                descricao=row_desc[:2000],
                tipo=_doc_tipo_nome(doc) or _movimento_tipo(mov),
                grau=mov_grau,
                arquivo_nome=doc_nome,
                arquivo_mimetype=_doc_mimetype(doc),
                arquivo_url=_documento_url_from_href(doc.get("hrefBinario") or doc.get("hrefTexto")),
                documento_detectado=True,
            ))

    # 2) Documents that matched no movimento become their own rows (lossless).
    for di in orfaos:
        doc = documentos[di]
        doc_nome = _nome_documento(doc, _doc_descricao(doc))
        andamentos.append(Andamento(
            data_andamento=_parse_data(doc.get("dataHoraJuntada") or doc.get("dataHora")),
            descricao=_doc_descricao(doc)[:2000],
            tipo=_doc_tipo_nome(doc),
            grau=grau,
            arquivo_nome=doc_nome,
            arquivo_mimetype=_doc_mimetype(doc),
            arquivo_url=_documento_url_from_href(doc.get("hrefBinario") or doc.get("hrefTexto")),
            documento_detectado=True,
        ))

    return andamentos
