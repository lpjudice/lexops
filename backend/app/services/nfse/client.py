"""mTLS clients para a API NFS-e Nacional.

Dois ambientes/hosts distintos:
- SEFIN Nacional  → emissão (POST /nfse), consulta, eventos, dps
- ADN Contribuinte → distribuição (DFe), parâmetros municipais

Carrega o e-CNPJ A1 (.pfx) uma vez. Sem sessão — cada request é autenticado
pelo certificado (mTLS). O certificado também é usado para assinar o XML da DPS.
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


def load_cert_and_key() -> tuple[bytes, bytes]:
    """Retorna (cert_pem, key_pem) do e-CNPJ A1 — usado para assinar o XML."""
    pfx_password = settings.nfse_cert_password
    if not pfx_password:
        raise ValueError("NFSE_CERT_PASSWORD não configurado no .env")
    pfx_data = _load_pfx_data()
    private_key, certificate, _ = pkcs12.load_key_and_certificates(
        pfx_data, pfx_password.encode()
    )
    cert_pem = certificate.public_bytes(Encoding.PEM)
    key_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    return cert_pem, key_pem


def _build_ssl_context() -> ssl.SSLContext:
    cert_pem, key_pem = load_cert_and_key()

    # O servidor usa CA ICP-Brasil (não inclusa no bundle padrão do Linux).
    # Desabilitamos a verificação do servidor mas mantemos o certificado
    # CLIENTE (mTLS) — que é o que o governo usa para autenticar o emitente.
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

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


def _ctx() -> ssl.SSLContext:
    global _ssl_ctx
    if _ssl_ctx is None:
        _ssl_ctx = _build_ssl_context()
    return _ssl_ctx


SEFIN_PROD = "https://sefin.nfse.gov.br/SefinNacional/"
SEFIN_HOMOLOG = "https://sefin.producaorestrita.nfse.gov.br/SefinNacional/"


def sefin_base(ambiente: int) -> str:
    """URL base do SEFIN conforme ambiente (1=Produção, 2=Homologação)."""
    return SEFIN_HOMOLOG if int(ambiente) == 2 else SEFIN_PROD


def get_sefin_client(ambiente: int | None = None) -> httpx.Client:
    """Client para o SEFIN Nacional — emissão, consulta, eventos.

    Se `ambiente` for informado, escolhe prod/homolog; senão usa o secret.
    """
    base = sefin_base(ambiente) if ambiente else settings.nfse_api_url
    return httpx.Client(
        base_url=base,
        verify=_ctx(),
        timeout=60.0,
        http2=False,  # servidor derruba conexão com HTTP/2
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )


def get_adn_client() -> httpx.Client:
    """Client para o ADN Contribuinte — distribuição, parâmetros municipais."""
    return httpx.Client(
        base_url=settings.nfse_adn_url,
        verify=_ctx(),
        timeout=30.0,
        http2=False,
        headers={"Accept": "application/json"},
    )


# Compat: nome antigo
def get_nfse_client() -> httpx.Client:
    return get_sefin_client()


def reset_client() -> None:
    global _ssl_ctx
    _ssl_ctx = None
