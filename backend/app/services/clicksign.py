"""
Integração com ClickSign API v1.

Fluxo:
  1. Upload do PDF → retorna document_key
  2. Criar signatário → retorna signer_key
  3. Vincular signer ao documento (POST /api/v1/lists) → retorna request_signature_key
     ↳ O ClickSign envia o email de assinatura automaticamente neste passo.
  4. (Opcional) Re-enviar notificação → POST /api/v1/notifications
  5. Cancelar → PATCH /api/v1/documents/{key}/cancel
  6. /finish fecha o documento permanentemente após todas as assinaturas (auto_close já faz isso).

Docs: https://developers.clicksign.com/docs/api-de-integracoes
"""

import base64
import os
from pathlib import Path

import httpx

BASE_URL = os.getenv("CLICKSIGN_BASE_URL", "https://app.clicksign.com")
API_KEY  = os.getenv("CLICKSIGN_API_KEY", "")


def _url(path: str) -> str:
    return f"{BASE_URL}{path}?access_token={API_KEY}"


def _h() -> dict:
    return {"Content-Type": "application/json", "Accept": "application/json"}


# ── 1. Upload do documento ────────────────────────────────────────────────────

def upload_documento(arquivo_path: str, nome_arquivo: str) -> str | None:
    """
    Faz upload do PDF para o ClickSign.
    Retorna o document_key ou None em caso de erro.
    Lança ValueError com a mensagem de erro do ClickSign para facilitar debug.
    """
    conteudo = Path(arquivo_path).read_bytes()
    b64 = base64.b64encode(conteudo).decode()

    payload = {
        "document": {
            "path": f"/{nome_arquivo}",
            "content_base64": f"data:application/pdf;base64,{b64}",
            "deadline_at": None,
            "auto_close": True,
            "locale": "pt-BR",
            "sequence_enabled": False,
        }
    }

    resp = httpx.post(_url("/api/v1/documents"), json=payload, headers=_h(), timeout=60)

    if resp.is_success:
        return resp.json().get("document", {}).get("key")

    raise ValueError(f"ClickSign upload falhou ({resp.status_code}): {resp.text[:300]}")


# ── 2. Criar signatário ───────────────────────────────────────────────────────

def criar_signatario(nome: str, email: str) -> str | None:
    """
    Cria um signatário no ClickSign e retorna seu signer_key.
    Autenticação por e-mail (link de assinatura enviado ao email do signatário).
    """
    payload = {
        "signer": {
            "email": email,
            "auths": ["email"],        # campo correto na API v1
            "name": nome,
            "phone_number": None,
            "documentation": None,
            "birthday": None,
            "has_documentation": False,
        }
    }
    resp = httpx.post(_url("/api/v1/signers"), json=payload, headers=_h(), timeout=15)

    if resp.is_success:
        return resp.json().get("signer", {}).get("key")

    raise ValueError(f"ClickSign signer falhou ({resp.status_code}): {resp.text[:300]}")


# ── 3. Vincular signatário ao documento ──────────────────────────────────────

PAPEL_MAP = {
    "contratante": "party",
    "contratado":  "sign",
    "testemunha":  "witness",
    "outro":       "sign",
}

def adicionar_signatario_ao_documento(
    document_key: str,
    signer_key: str,
    papel: str = "sign",
) -> str | None:
    """
    Vincula signer ao document.
    Retorna o request_signature_key.
    ↳ O ClickSign envia o email convite automaticamente neste passo
      (documento deve estar em status 'running').
    """
    payload = {
        "list": {
            "document_key": document_key,
            "signer_key":   signer_key,
            "sign_as":      PAPEL_MAP.get(papel, "sign"),
            "refusable":    True,
            "message":      "Por favor, assine o documento.",
        }
    }
    resp = httpx.post(_url("/api/v1/lists"), json=payload, headers=_h(), timeout=15)

    if resp.is_success:
        return resp.json().get("list", {}).get("request_signature_key")

    raise ValueError(f"ClickSign list falhou ({resp.status_code}): {resp.text[:300]}")


# ── 4. Re-enviar notificação (opcional) ──────────────────────────────────────

def notificar_signatario(request_signature_key: str) -> bool:
    """
    Re-envia o email de convite para assinar.
    Útil para lembrar signatários que ainda não assinaram.
    """
    payload = {"request_signature_key": request_signature_key}
    resp = httpx.post(_url("/api/v1/notifications"), json=payload, headers=_h(), timeout=15)
    return resp.is_success


# ── 5. Cancelar documento ─────────────────────────────────────────────────────

def cancelar_documento(document_key: str) -> bool:
    resp = httpx.patch(_url(f"/api/v1/documents/{document_key}/cancel"), headers=_h(), timeout=15)
    return resp.is_success


# ── 6. Baixar PDF assinado ────────────────────────────────────────────────────

def baixar_documento_assinado(document_key: str) -> bytes | None:
    resp = httpx.get(
        _url(f"/api/v1/documents/{document_key}/download"),
        headers={"Accept": "application/pdf"},
        timeout=30,
        follow_redirects=True,
    )
    if resp.is_success:
        return resp.content
    return None


# ── 7. Status do documento ────────────────────────────────────────────────────

def status_documento(document_key: str) -> dict | None:
    resp = httpx.get(_url(f"/api/v1/documents/{document_key}"), headers=_h(), timeout=15)
    if resp.is_success:
        return resp.json().get("document")
    return None
