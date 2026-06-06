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


def _build_ssl_context() -> ssl.SSLContext:
    pfx_path = settings.nfse_cert_path
    pfx_password = settings.nfse_cert_password

    if not pfx_path or not os.path.exists(pfx_path):
        raise FileNotFoundError(f"Certificado e-CNPJ não encontrado: {pfx_path!r}. "
                                "Configure NFSE_CERT_PATH no .env")
    if not pfx_password:
        raise ValueError("NFSE_CERT_PASSWORD não configurado no .env")

    with open(pfx_path, "rb") as f:
        pfx_data = f.read()

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
