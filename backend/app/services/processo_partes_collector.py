"""Coleta metadados + partes de um processo via jus.br/PDPJ.

Módulo INDEPENDENTE do consulta_processual/pdpj.py (travado): chama o mesmo
endpoint v2/processos/{cnj} mas extrai SÓ o que precisamos para o bot de
andamentos (cabeçalho do processo + partes do polo ativo/passivo/outros).

Não escreve no banco — devolve um dict que o caller (router /add ou /lista)
persiste em ProcessoTelegramExtra / ProcessoParte conforme o caso.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_PDPJ_BASE = "https://portaldeservicos.pdpj.jus.br/api/v2"

# O portal fica atrás de um WAF que devolve um "<html>403 Forbidden" genérico
# (não é erro do PDPJ) pra requisição que não pareça vir de um navegador — o
# gatilho mais comum é o User-Agent padrão do httpx. Mesmo contorno usado em
# consulta_processual/pdpj.py (travado), duplicado aqui de propósito: este
# módulo é independente daquele por design (ver docstring acima).
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


# ── Coleta HTTP ───────────────────────────────────────────────────────────────

async def fetch_processo(cnj: str, token: str) -> dict | None:
    """Retorna o JSON cru do PDPJ ou None se não achar / não autorizado."""
    ident = _digits(cnj)
    url = f"{_PDPJ_BASE}/processos/{ident}"
    headers = {
        **_BROWSER_HEADERS,
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Referer": "https://portaldeservicos.pdpj.jus.br/home",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        logger.warning("PDPJ partes %s: erro de rede: %s", ident, exc)
        return None

    if resp.status_code != 200:
        logger.warning("PDPJ partes %s: HTTP %s body=%s", ident, resp.status_code, resp.text[:200])
        return None
    try:
        data = resp.json()
    except Exception:
        logger.warning("PDPJ partes %s: corpo não-JSON", ident)
        return None
    # API às vezes devolve lista, às vezes objeto.
    if isinstance(data, list):
        return data[0] if data else None
    return data


# ── Parsing ───────────────────────────────────────────────────────────────────

_POLO_MAP = {
    "ATIVO": "ATIVO",
    "PASSIVO": "PASSIVO",
    "AUTOR": "ATIVO",
    "REU": "PASSIVO",
    "RÉU": "PASSIVO",
    "REQUERENTE": "ATIVO",
    "REQUERIDO": "PASSIVO",
    "RECORRENTE": "ATIVO",
    "RECORRIDO": "PASSIVO",
    "EXEQUENTE": "ATIVO",
    "EXECUTADO": "PASSIVO",
}


def _norm_polo(raw: Any) -> str:
    s = str(raw or "").upper().strip()
    return _POLO_MAP.get(s, "OUTROS")


def _coerce_partes(blob: Any) -> list[dict]:
    """O PDPJ tem variações na chave/estrutura. Cobre os layouts conhecidos.

    Layouts vistos:
      - tramitacaoAtual.partes: [ {polo, nome, tipoPessoa, documento, ...} ]
      - tramitacaoAtual.poloAtivo: [...]  / poloPassivo: [...]
      - partes: [...] no nível raiz
    Retorna lista normalizada com polo, nome, tipo_pessoa, documento.
    """
    out: list[dict] = []
    if not blob:
        return out
    tram = blob.get("tramitacaoAtual") if isinstance(blob, dict) else None
    candidatos = [tram, blob]

    for root in candidatos:
        if not isinstance(root, dict):
            continue

        # (a) lista única com campo "polo"
        partes = root.get("partes")
        if isinstance(partes, list) and partes:
            for p in partes:
                if not isinstance(p, dict):
                    continue
                nome = (p.get("nome") or p.get("nomeParte") or "").strip()
                if not nome:
                    continue
                out.append({
                    "polo": _norm_polo(p.get("polo") or p.get("tipoPolo")),
                    "nome": nome,
                    "tipo_pessoa": str(p.get("tipoPessoa") or p.get("tipo") or "").upper() or None,
                    "documento": str(p.get("documento") or p.get("cpfCnpj") or "").strip() or None,
                })
            if out:
                return out

        # (b) polo por chave separada
        for chave, polo in (("poloAtivo", "ATIVO"), ("poloPassivo", "PASSIVO"), ("outros", "OUTROS")):
            lista = root.get(chave)
            if isinstance(lista, list):
                for p in lista:
                    if not isinstance(p, dict):
                        continue
                    nome = (p.get("nome") or p.get("nomeParte") or "").strip()
                    if not nome:
                        continue
                    out.append({
                        "polo": polo,
                        "nome": nome,
                        "tipo_pessoa": str(p.get("tipoPessoa") or "").upper() or None,
                        "documento": str(p.get("documento") or p.get("cpfCnpj") or "").strip() or None,
                    })
        if out:
            return out

    return out


def _str_or_none(*candidates: Any) -> str | None:
    for c in candidates:
        if isinstance(c, str) and c.strip():
            return c.strip()
        if isinstance(c, dict):
            for k in ("nome", "descricao", "sigla"):
                v = c.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
    return None


def parse_processo(blob: dict) -> dict:
    """Resume o JSON do PDPJ no que interessa pro bot/lexops.

    Retorna:
      {
        "numero_cnj": str | None,
        "tribunal": str | None,
        "orgao_julgador": str | None,
        "vara": str | None,
        "comarca": str | None,
        "classe": str | None,
        "assunto": str | None,
        "partes": [{polo, nome, tipo_pessoa, documento}, ...],
      }
    """
    tram = blob.get("tramitacaoAtual") if isinstance(blob, dict) else {}
    if not isinstance(tram, dict):
        tram = {}

    tribunal = _str_or_none(
        tram.get("tribunal"), blob.get("tribunal"), tram.get("siglaTribunal"), blob.get("siglaTribunal")
    )
    orgao = _str_or_none(
        tram.get("orgaoJulgador"), blob.get("orgaoJulgador"),
        tram.get("orgaoJulgadorTipo"), tram.get("orgao"),
    )
    classe = _str_or_none(
        tram.get("classe"), blob.get("classe"),
        (tram.get("classeProcessual") if isinstance(tram, dict) else None),
    )
    assunto_raw = tram.get("assuntos") or blob.get("assuntos")
    if isinstance(assunto_raw, list) and assunto_raw:
        assunto = _str_or_none(assunto_raw[0])
    else:
        assunto = _str_or_none(tram.get("assunto"), blob.get("assunto"))

    return {
        "numero_cnj": _str_or_none(blob.get("numeroProcesso"), blob.get("numero"), tram.get("numeroProcesso")),
        "tribunal": tribunal,
        "orgao_julgador": orgao,
        "vara": _str_or_none(tram.get("vara"), tram.get("orgaoJulgador")),
        "comarca": _str_or_none(tram.get("comarca"), tram.get("municipio")),
        "classe": classe,
        "assunto": assunto,
        "partes": _coerce_partes(blob),
    }


async def fetch_resumo(cnj: str, token: str) -> dict | None:
    """Atalho: baixa e parseia. Retorna dict pronto ou None."""
    raw = await fetch_processo(cnj, token)
    if not raw:
        return None
    return parse_processo(raw)
