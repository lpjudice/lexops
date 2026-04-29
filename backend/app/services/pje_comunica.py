"""
Integração com a API do PJe Comunica (CNJ).
https://comunicaapi.pje.jus.br/api/v1

Permite ao advogado consultar comunicações processuais eletrônicas
(intimações, citações, etc.) recebidas no PJe.

Fluxo:
  1. POST /login   → recebe token JWT
  2. GET  /comunicacao/destinatario/listartodos?page=0&size=50  → lista comunicações
  3. GET  /comunicacao/destinatario/{id}  → detalhes
"""

import os
from typing import Any

import httpx

BASE_URL = "https://comunicaapi.pje.jus.br/api/v1"
_TIMEOUT = 20


def _headers(token: str | None = None) -> dict:
    h = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


# ── Autenticação ──────────────────────────────────────────────────────────────

def login(login_cpf: str, senha: str) -> str | None:
    """
    Autentica no PJe Comunica com CPF e senha.
    Retorna o token JWT ou None em caso de erro.
    """
    try:
        resp = httpx.post(
            f"{BASE_URL}/login",
            json={"login": login_cpf, "senha": senha},
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        if resp.is_success:
            data = resp.json()
            return data.get("token") or data.get("access_token")
    except Exception:
        pass
    return None


# ── Listar comunicações ───────────────────────────────────────────────────────

def listar_comunicacoes(
    token: str,
    page: int = 0,
    size: int = 50,
    termos: list[str] | None = None,
) -> list[dict]:
    """
    Retorna lista de comunicações processuais do destinatário autenticado.
    Se `termos` for fornecido, filtra client-side por nome de parte/processo.
    """
    try:
        resp = httpx.get(
            f"{BASE_URL}/comunicacao/destinatario/listartodos",
            params={"page": page, "size": size},
            headers=_headers(token),
            timeout=_TIMEOUT,
        )
        if not resp.is_success:
            return []
        data = resp.json()
        itens: list[dict] = data if isinstance(data, list) else data.get("content", data.get("data", []))

        # Filtro por termos (nome de parte, número de processo)
        if termos:
            filtrados = []
            for item in itens:
                texto = (
                    str(item.get("nomeDestinatario", "")).lower()
                    + str(item.get("numeroComunicacao", "")).lower()
                    + str(item.get("siglaTribunal", "")).lower()
                    + str(item.get("textoTeor", "")).lower()
                )
                if any(t.lower() in texto for t in termos if t):
                    filtrados.append(item)
            return filtrados
        return itens
    except Exception:
        return []


def obter_comunicacao(token: str, comunicacao_id: str) -> dict | None:
    """Retorna os detalhes de uma comunicação específica."""
    try:
        resp = httpx.get(
            f"{BASE_URL}/comunicacao/destinatario/{comunicacao_id}",
            headers=_headers(token),
            timeout=_TIMEOUT,
        )
        if resp.is_success:
            return resp.json()
    except Exception:
        pass
    return None


def comunicacoes_para_publicacoes(itens: list[dict]) -> list[dict]:
    """
    Converte a lista de comunicações do PJe para o formato de Publicacao
    compatível com o modelo da plataforma.
    """
    from datetime import date
    import re

    CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
    resultado = []

    for item in itens:
        # Extrai número CNJ do campo numeroComunicacao ou do texto
        numero_cnj = item.get("numeroComunicacao", "")
        if not CNJ_RE.match(numero_cnj):
            # Tenta extrair do texto
            texto = item.get("textoTeor", "") or ""
            match = CNJ_RE.search(texto)
            numero_cnj = match.group(0) if match else None

        data_str = item.get("dataDisponibilizacao") or item.get("dataCriacao", "")
        try:
            data_pub = date.fromisoformat(data_str[:10]) if data_str else date.today()
        except Exception:
            data_pub = date.today()

        texto_resumo = item.get("textoTeor", "") or item.get("descricao", "")
        tribunal = item.get("siglaTribunal", "DJEN")

        resultado.append({
            "fonte": "pje_comunica",
            "data_publicacao": data_pub,
            "numero_cnj": numero_cnj,
            "tipo_ato": "intimacao",
            "tribunal": tribunal,
            "texto_resumo": texto_resumo[:500] if texto_resumo else "Comunicação PJe",
            "texto_completo": texto_resumo[:5000] if texto_resumo else "",
            "email_message_id": None,
            "url_fonte": "https://comunica.pje.jus.br/",
        })

    return resultado
