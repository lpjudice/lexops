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
from urllib.parse import urljoin, urlparse

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
        if isinstance(v, str) and v:
            partes.append(v.strip())
        elif key == "tipo" and isinstance(v, dict):
            nested = v.get("nome") or v.get("descricao")
            if isinstance(nested, str) and nested:
                partes.append(nested.strip())
    return " — ".join(dict.fromkeys(p for p in partes if p))


def _movimento_tipo(m: dict) -> str | None:
    nome = m.get("nome")
    if isinstance(nome, str) and nome:
        return nome
    tipo = m.get("tipo")
    if isinstance(tipo, str) and tipo:
        return tipo
    if isinstance(tipo, dict):
        nested = tipo.get("nome") or tipo.get("descricao")
        if isinstance(nested, str) and nested:
            return nested.strip()[:255]
    descricao = m.get("descricao")
    if isinstance(descricao, str) and descricao:
        return descricao[:255]
    return None


def _normalizar_url_documento(raw: str, base: str) -> str | None:
    valor = (raw or "").strip()
    if not valor:
        return None
    if valor.startswith("http://") or valor.startswith("https://"):
        return valor
    if valor.startswith("/"):
        parsed = urlparse(base)
        return f"{parsed.scheme}://{parsed.netloc}{valor}"
    return urljoin(f"{base.rstrip('/')}/", valor.lstrip("/"))


def _coletar_urls_documento(obj: object, base: str, acc: list[str]) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str) and any(
                marker in key.lower() for marker in ("url", "href", "link", "download", "uri", "path")
            ):
                normalizada = _normalizar_url_documento(value, base)
                if normalizada and normalizada not in acc:
                    acc.append(normalizada)
            else:
                _coletar_urls_documento(value, base, acc)
    elif isinstance(obj, list):
        for item in obj:
            _coletar_urls_documento(item, base, acc)


def _coletar_bytes_embutidos(doc: dict) -> tuple[bytes, str | None] | None:
    for key in ("conteudoBase64", "arquivoBase64", "base64", "contentBase64", "pdfBase64"):
        raw = doc.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        payload = raw.strip()
        if "," in payload and payload.lower().startswith("data:"):
            header, payload = payload.split(",", 1)
            mimetype = header[5:].split(";", 1)[0] if header.startswith("data:") else None
        else:
            mimetype = doc.get("mimetype") if isinstance(doc.get("mimetype"), str) else None
        try:
            return base64.b64decode(payload), mimetype
        except Exception:
            continue
    return None


def _nome_documento(doc: dict, fallback: str) -> str:
    nome = (
        doc.get("nome")
        or doc.get("nomeArquivo")
        or doc.get("filename")
        or doc.get("tituloDocumento")
        or fallback
    )
    if not isinstance(nome, str) or not nome.strip():
        return fallback
    nome = re.sub(r'[\\/:*?"<>|]+', "_", nome).strip()
    return nome or fallback


async def _baixar_documento_movimento(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    matched_base: str,
    processo_id: str,
    movimento: dict,
) -> tuple[str, bytes, str | None] | None:
    doc = next(
        (movimento.get(key) for key in ("documento", "doc", "arquivo") if isinstance(movimento.get(key), dict)),
        None,
    )
    if not isinstance(doc, dict):
        return None

    embutido = _coletar_bytes_embutidos(doc)
    fallback_nome = f"documento_{movimento.get('id') or processo_id}.pdf"
    if embutido:
        nome = _nome_documento(doc, fallback_nome)
        mimetype = embutido[1] or "application/pdf"
        if mimetype == "application/pdf" and not nome.lower().endswith(".pdf"):
            nome = f"{nome}.pdf"
        return nome, embutido[0], mimetype

    candidatos: list[str] = []
    _coletar_urls_documento(doc, matched_base, candidatos)
    _coletar_urls_documento(movimento, matched_base, candidatos)

    doc_id = next(
        (
            str(doc.get(key)).strip()
            for key in ("id", "documentoId", "idDocumento", "uuid", "chave", "key")
            if doc.get(key)
        ),
        "",
    )
    if doc_id:
        for url in (
            f"{matched_base}/documentos/{doc_id}",
            f"{matched_base}/documentos/{doc_id}/download",
            f"{matched_base}/documentos/{doc_id}/arquivo",
            f"{matched_base}/processos/{processo_id}/documentos/{doc_id}",
            f"{matched_base}/processos/{processo_id}/documentos/{doc_id}/download",
        ):
            if url not in candidatos:
                candidatos.append(url)

    for url in candidatos:
        try:
            resp = await client.get(url, headers=headers)
        except Exception:
            continue
        if resp.status_code in (401, 403):
            raise PermissionError("Token expirado ao baixar documento do jus.br. Renove a sessão.")
        if resp.status_code != 200 or not resp.content:
            continue

        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                payload = resp.json()
            except Exception:
                continue
            if isinstance(payload, dict):
                _coletar_urls_documento(payload, matched_base, candidatos)
                nested_doc = payload.get("documento") if isinstance(payload.get("documento"), dict) else payload
                embutido_payload = _coletar_bytes_embutidos(nested_doc if isinstance(nested_doc, dict) else {})
                if embutido_payload:
                    nome = _nome_documento(doc, fallback_nome)
                    return nome, embutido_payload[0], embutido_payload[1] or "application/pdf"
            continue

        nome = _nome_documento(doc, fallback_nome)
        if "application/pdf" in content_type and not nome.lower().endswith(".pdf"):
            nome = f"{nome}.pdf"
        return nome, resp.content, content_type or None

    return None


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
    tramitacoes = item.get("tramitacoes")
    if isinstance(tramitacoes, list):
        for tram in tramitacoes:
            if not isinstance(tram, dict):
                continue
            tribunal_obj = tram.get("tribunal")
            if isinstance(tribunal_obj, dict):
                candidatos.extend([tribunal_obj.get("sigla"), tribunal_obj.get("nome")])
            candidatos.append(tram.get("orgaoJulgador"))
    return any(esperado in normalizar_tribunal(str(valor)) for valor in candidatos if valor)


def _extract_inline_movimentos(data: dict) -> list[dict]:
    for key in ("movimentos", "andamentos", "movements"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    tramitacoes = data.get("tramitacoes")
    if isinstance(tramitacoes, list):
        for tram in tramitacoes:
            if not isinstance(tram, dict):
                continue
            for key in ("movimentos", "andamentos", "movements"):
                value = tram.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
    return []


def _build_headers(token: str, session_data: dict | None = None) -> dict[str, str]:
    session_data = session_data or {}
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
    return headers


def _build_candidate_requests(numero_cnj: str, tribunal: str, session_data: dict | None = None) -> tuple[str, str, list[tuple[str, str, dict, None]]]:
    session_data = session_data or {}
    numero_norm = normalizar_cnj(numero_cnj)
    tribunal_norm = normalizar_tribunal(tribunal)
    tribunais_candidatos = candidatos_tribunal(numero_cnj, tribunal)

    candidates: list[tuple[str, str, dict, None]] = []
    seen_bases: list[str] = []
    for base in [*(session_data.get("api_bases") or []), *_BASES]:
        if base in seen_bases:
            continue
        seen_bases.append(base)
        candidates += [
            ("GET", f"{base}/processos", {"numeroProcesso": numero_cnj}, None),
            ("GET", f"{base}/processos", {"numeroProcesso": numero_norm}, None),
            ("GET", f"{base}/processos", {"numeroProcesso": numero_cnj, "retornarMovimentos": "true"}, None),
            ("GET", f"{base}/processos", {"numeroProcesso": numero_norm, "retornarMovimentos": "true"}, None),
            ("GET", f"{base}/processos", {"numeroProcesso": numero_norm, "incluirMovimentos": "true"}, None),
            ("GET", f"{base}/processos", {"numero": numero_cnj}, None),
            ("GET", f"{base}/processos", {"numero": numero_norm}, None),
            ("GET", f"{base}/processos/{numero_cnj}", {}, None),
            ("GET", f"{base}/processos/{numero_norm}", {}, None),
            ("GET", f"{base}/processo/{numero_cnj}", {}, None),
            ("GET", f"{base}/consulta/processos", {"numeroProcesso": numero_cnj}, None),
            ("GET", f"{base}/consulta/processos", {"numeroProcesso": numero_norm}, None),
        ]
        for candidato in tribunais_candidatos:
            candidates += [
                ("GET", f"{base}/processos", {"numeroProcesso": numero_norm, "tribunal": candidato}, None),
                ("GET", f"{base}/processos", {"numeroProcesso": numero_norm, "siglaTribunal": candidato}, None),
            ]
    return numero_norm, tribunal_norm, candidates


async def buscar_processo_pdpj_raw(
    numero_cnj: str,
    tribunal: str,
    token: str | None = None,
    session_data: dict | None = None,
) -> dict | None:
    session_data = session_data or {}
    token = token or session_data.get("token") or ""
    if not token:
        raise PermissionError("Sessao do jus.br nao configurada.")

    headers = _build_headers(token, session_data)
    numero_norm, tribunal_norm, candidates = _build_candidate_requests(numero_cnj, tribunal, session_data)
    tribunal_inferido = inferir_tribunal_pelo_cnj(numero_cnj)

    async with httpx.AsyncClient(timeout=20) as client:
        for method, url, params, body in candidates:
            try:
                resp = await client.request(method, url, headers=headers, params=params or None, json=body)
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
            if resp.status_code == 404 or resp.status_code != 200:
                continue

            try:
                data = resp.json()
            except Exception:
                continue

            items = _items_from_response(data)
            for item in items:
                n_raw = (item.get("numeroProcesso") or item.get("numero") or "")
                if re.sub(r"\D", "", n_raw) != numero_norm:
                    continue
                if tribunal_norm and not _tribunal_matches(item, tribunal_norm):
                    if tribunal_inferido and _tribunal_matches(item, tribunal_inferido):
                        pass
                    elif item.get("tribunal") or item.get("siglaTribunal") or item.get("tramitacoes"):
                        continue
                return item
    return None


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

    headers = _build_headers(token, session_data)
    numero_norm = normalizar_cnj(numero_cnj)

    processo_data = await buscar_processo_pdpj_raw(
        numero_cnj,
        tribunal,
        token=token,
        session_data=session_data,
    )

    async with httpx.AsyncClient(timeout=20) as client:
        matched_base = next(iter(session_data.get("api_bases") or []), _BASES[0])
        inline_movimentos: list[dict] = _extract_inline_movimentos(processo_data) if processo_data else []

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
            tipo = _movimento_tipo(m)
            arquivo = await _baixar_documento_movimento(client, headers, matched_base, processo_id, m)

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
                    arquivo_nome=arquivo[0] if arquivo else None,
                    arquivo_bytes=arquivo[1] if arquivo else None,
                    arquivo_mimetype=arquivo[2] if arquivo else None,
                ))

        if andamentos:
            return andamentos

    return []
