"""Emissão, consulta e cancelamento de NFS-e via Sefin Nacional.

Fluxo de emissão (POST /nfse):
  1. Monta XML da DPS
  2. Assina (XMLDSIG) com e-CNPJ A1
  3. GZip + Base64
  4. POST JSON {"dpsXmlGZipB64": "..."}
  5. Resposta 201: {chaveAcesso, nfseXmlGZipB64, ...}
     Resposta 400/403/500: {erros: [{codigo, descricao, ...}]}
"""
from __future__ import annotations

import base64
import gzip
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from .client import get_sefin_client, get_adn_client
from .dps_builder import DadosDPS, montar_dps
from .signer import assinar_dps, assinar_evento

log = logging.getLogger(__name__)


@dataclass
class ResultadoEmissao:
    sucesso: bool
    chave_acesso: Optional[str] = None
    numero_nfse: Optional[str] = None
    xml_nfse: Optional[str] = None
    erro_codigo: Optional[str] = None
    erro_mensagem: Optional[str] = None


@dataclass
class ResultadoCancelamento:
    sucesso: bool
    erro_mensagem: Optional[str] = None


# ─── Helpers de (de)compressão ───────────────────────────────────────────────

def _gzip_b64(xml: bytes) -> str:
    return base64.b64encode(gzip.compress(xml)).decode("ascii")


def _ungzip_b64(b64: str) -> str:
    try:
        return gzip.decompress(base64.b64decode(b64)).decode("utf-8")
    except Exception:
        # alguns retornos podem não estar comprimidos
        try:
            return base64.b64decode(b64).decode("utf-8")
        except Exception:
            return b64


def _fmt_erros(payload: dict) -> tuple[str, str]:
    """Extrai (codigo, mensagem) da resposta de erro do Sefin."""
    erros = payload.get("erros") or payload.get("Erros") or []
    if not erros:
        msg = payload.get("mensagem") or payload.get("message") or str(payload)[:500]
        return "?", msg
    partes = []
    primeiro_codigo = "?"
    for i, e in enumerate(erros):
        cod = e.get("codigo") or e.get("Codigo") or "?"
        desc = e.get("descricao") or e.get("Descricao") or e.get("mensagem") or ""
        compl = e.get("complemento") or e.get("Complemento") or ""
        if i == 0:
            primeiro_codigo = cod
        partes.append(f"[{cod}] {desc}{(' — ' + compl) if compl else ''}")
    return primeiro_codigo, " | ".join(partes)


# ─── Emissão ─────────────────────────────────────────────────────────────────

def emitir_nfse(dados: DadosDPS) -> ResultadoEmissao:
    # 1) Monta o XML
    xml_dps = montar_dps(dados)

    # 2) Assina
    try:
        xml_assinado = assinar_dps(xml_dps)
    except Exception as exc:
        log.exception("Falha ao assinar DPS")
        return ResultadoEmissao(sucesso=False, erro_mensagem=f"Erro ao assinar DPS: {exc}")

    # 3+4) GZip + Base64 + payload JSON
    payload = {"dpsXmlGZipB64": _gzip_b64(xml_assinado)}

    # 5) POST
    try:
        with get_sefin_client() as client:
            resp = client.post("nfse", json=payload)
    except httpx.RequestError as exc:
        log.error("Erro de conexão com Sefin: %s", exc)
        return ResultadoEmissao(sucesso=False, erro_mensagem=f"Erro de conexão: {exc}")

    log.warning("SEFIN POST /nfse status=%s body=%s", resp.status_code, resp.text[:1500])

    # Parse JSON (sucesso ou erro)
    try:
        data = resp.json()
    except Exception:
        return ResultadoEmissao(
            sucesso=False,
            erro_codigo=str(resp.status_code),
            erro_mensagem=f"HTTP {resp.status_code} — resposta não-JSON: {resp.text[:300]}",
        )

    if resp.status_code in (200, 201):
        chave = data.get("chaveAcesso") or data.get("ChaveAcesso")
        nfse_xml = None
        if data.get("nfseXmlGZipB64"):
            nfse_xml = _ungzip_b64(data["nfseXmlGZipB64"])
        # número da NFS-e é parte da chave (posições específicas) — guardamos a chave
        return ResultadoEmissao(
            sucesso=True,
            chave_acesso=chave,
            numero_nfse=_numero_da_chave(chave),
            xml_nfse=nfse_xml,
        )

    codigo, msg = _fmt_erros(data)
    return ResultadoEmissao(sucesso=False, erro_codigo=codigo, erro_mensagem=msg)


def _numero_da_chave(chave: Optional[str]) -> Optional[str]:
    """Extrai o número sequencial da NFS-e da chave de acesso (50 dígitos)."""
    if not chave or len(chave) < 25:
        return None
    # Layout da chave NFS-e nacional: o número da NFSe são 13 dígitos (pos 18-30 aprox)
    # Retorna os dígitos centrais como referência; exibição é só informativa.
    return chave[18:31] if len(chave) >= 31 else chave


# ─── Consulta ────────────────────────────────────────────────────────────────

def consultar_nfse(chave_acesso: str) -> Optional[str]:
    try:
        with get_sefin_client() as client:
            resp = client.get(f"nfse/{chave_acesso}")
    except httpx.RequestError as exc:
        log.error("Erro ao consultar NFS-e: %s", exc)
        return None
    if resp.status_code == 200:
        try:
            data = resp.json()
            if data.get("nfseXmlGZipB64"):
                return _ungzip_b64(data["nfseXmlGZipB64"])
            return resp.text
        except Exception:
            return resp.text
    log.warning("Consulta NFS-e %s: status %s", chave_acesso, resp.status_code)
    return None


# ─── Cancelamento ────────────────────────────────────────────────────────────

def cancelar_nfse(chave_acesso: str, motivo: str) -> ResultadoCancelamento:
    xml_evento = _montar_xml_cancelamento(chave_acesso, motivo)
    try:
        xml_assinado = assinar_evento(xml_evento)
    except Exception as exc:
        return ResultadoCancelamento(sucesso=False, erro_mensagem=f"Erro ao assinar evento: {exc}")

    payload = {"pedidoRegistroEventoXmlGZipB64": _gzip_b64(xml_assinado)}
    try:
        with get_sefin_client() as client:
            resp = client.post(f"nfse/{chave_acesso}/eventos", json=payload)
    except httpx.RequestError as exc:
        return ResultadoCancelamento(sucesso=False, erro_mensagem=str(exc))

    log.warning("SEFIN POST evento status=%s body=%s", resp.status_code, resp.text[:800])
    if resp.status_code in (200, 201):
        return ResultadoCancelamento(sucesso=True)
    try:
        _, msg = _fmt_erros(resp.json())
    except Exception:
        msg = f"HTTP {resp.status_code}: {resp.text[:300]}"
    return ResultadoCancelamento(sucesso=False, erro_mensagem=msg)


def _montar_xml_cancelamento(chave_acesso: str, motivo: str) -> bytes:
    from datetime import datetime, timezone, timedelta
    from lxml import etree

    NS = "http://www.sped.fazenda.gov.br/nfse"
    BRT = timezone(timedelta(hours=-3))
    dh = datetime.now(tz=BRT).strftime("%Y-%m-%dT%H:%M:%S") + "-03:00"

    root = etree.Element("pedRegEvento", nsmap={None: NS})
    root.set("versao", "1.00")
    inf = etree.SubElement(root, "infPedReg")
    inf.set("Id", f"PRE{chave_acesso}")
    etree.SubElement(inf, "tpAmb").text = "1"
    etree.SubElement(inf, "dhEvento").text = dh
    etree.SubElement(inf, "CNPJAutor").text = "10901611000164"
    etree.SubElement(inf, "chNFSe").text = chave_acesso
    etree.SubElement(inf, "nPedRegEvento").text = "1"
    e101101 = etree.SubElement(inf, "e101101")
    etree.SubElement(e101101, "xDesc").text = "Cancelamento de NFS-e"
    etree.SubElement(e101101, "cMotivo").text = "1"
    etree.SubElement(e101101, "xMotivo").text = motivo[:255]
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


# ─── DANFSe (PDF) ────────────────────────────────────────────────────────────

def baixar_danfse(chave_acesso: str) -> Optional[bytes]:
    """Baixa o PDF da DANFSe pela chave de acesso. Tenta Sefin e ADN."""
    paths = [
        ("sefin", f"danfse/{chave_acesso}"),
        ("adn",   f"danfse/{chave_acesso}"),
        ("adn",   f"DANFSE/{chave_acesso}"),
    ]
    for alvo, path in paths:
        try:
            client = get_sefin_client() if alvo == "sefin" else get_adn_client()
            with client:
                resp = client.get(path, headers={"Accept": "application/pdf"})
            if resp.status_code == 200 and resp.content[:4] == b"%PDF":
                return resp.content
            log.warning("DANFSe %s/%s: status %s ct=%s",
                        alvo, path, resp.status_code, resp.headers.get("content-type"))
        except httpx.RequestError as exc:
            log.warning("DANFSe %s erro: %s", alvo, exc)
    return None


# ─── Parâmetros municipais (ADN) ─────────────────────────────────────────────

def consultar_parametros_municipio(cod_municipio: str = "3205309") -> Optional[dict]:
    try:
        with get_adn_client() as client:
            resp = client.get(f"parametros_municipais/{cod_municipio}/convenio")
    except httpx.RequestError as exc:
        log.error("Erro ao consultar parâmetros municipais: %s", exc)
        return None
    if resp.status_code == 200:
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}
    return None
