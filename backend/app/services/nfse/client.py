"""mTLS httpx client para a API NFS-e Nacional (ADN).

Carrega o e-CNPJ A1 (.pfx) uma vez e reutiliza o SSLContext em todas as
chamadas. Sem sessão, sem login — cada request é autenticado pelo certificado.
"""
import os
import ssl
import tempfile

import httpx
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

from app.config import settings


def _load_pfx_data() -> bytes:
    """Carrega o .pfx: de base64 (Fly.io) ou de arquivo local (dev)."""
    import base64
    b64 = os.environ.get("NFSE_CERT_B64", "").strip()
    if b64:
        return base64.b64decode(b64)

    pfx_path = settings.nfse_cert_path
    if pfx_path and os.path.exists(pfx_path):
        with open(pfx_path, "rb") as f:
            return f.read()

    raise FileNotFoundError(
        "Certificado e-CNPJ não encontrado. "
        "Configure NFSE_CERT_B64 (Fly.io) ou NFSE_CERT_PATH (local) no .env"
    )


def _build_ssl_context() -> ssl.SSLContext:
    pfx_password = settings.nfse_cert_password

    if not pfx_password:
        raise ValueError("NFSE_CERT_PASSWORD não configurado no .env")

    pfx_data = _load_pfx_data()

    private_key, certificate, _ = pkcs12.load_key_and_certificates(
        pfx_data, pfx_password.encode()
    )

    cert_pem = certificate.public_bytes(Encoding.PEM)
    key_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_default_certs()

    cert_tmp = key_tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as cf:
            cf.write(cert_pem)
            cert_tmp = cf.name
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as kf:
            kf.write(key_pem)
            key_tmp = kf.name
        ctx.load_cert_chain(cert_tmp, key_tmp)
    finally:
        if cert_tmp and os.path.exists(cert_tmp):
            os.unlink(cert_tmp)
        if key_tmp and os.path.exists(key_tmp):
            os.unlink(key_tmp)

    return ctx


_ssl_ctx: ssl.SSLContext | None = None


def get_nfse_client() -> httpx.Client:
    """Retorna um httpx.Client configurado com mTLS do e-CNPJ A1."""
    global _ssl_ctx
    if _ssl_ctx is None:
        _ssl_ctx = _build_ssl_context()

    return httpx.Client(
        base_url=settings.nfse_api_url,
        verify=_ssl_ctx,
        timeout=30.0,
        headers={"Content-Type": "application/xml", "Accept": "application/xml"},
    )


def reset_client() -> None:
    """Força rebuild do SSLContext (útil se o .pfx for trocado)."""
    global _ssl_ctx
    _ssl_ctx = None
