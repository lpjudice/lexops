"""Camada de emissão, consulta e cancelamento de NFS-e via API do ADN."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx
from lxml import etree

from .client import get_nfse_client
from .dps_builder import DadosDPS, montar_dps

log = logging.getLogger(__name__)

NS = "http://www.sped.fazenda.gov.br/nfse"


# ─── DTOs de retorno ─────────────────────────────────────────────────────────

@dataclass
class ResultadoEmissao:
    sucesso: bool
    chave_acesso: Optional[str] = None
    numero_nfse: Optional[str] = None
    xml_nfse: Optional[str] = None   # XML completo retornado pela API
    erro_codigo: Optional[str] = None
    erro_mensagem: Optional[str] = None


@dataclass
class ResultadoCancelamento:
    sucesso: bool
    erro_mensagem: Optional[str] = None


# ─── Helpers XML ─────────────────────────────────────────────────────────────

def _texto(root: etree._Element, xpath: str) -> Optional[str]:
    els = root.xpath(xpath, namespaces={"n": NS})
    if els:
        return els[0].text if hasattr(els[0], "text") else str(els[0])
    return None


def _parse_erro(xml_bytes: bytes) -> tuple[str, str]:
    """Extrai código e mensagem de erro do XML de rejeição."""
    try:
        root = etree.fromstring(xml_bytes)
        codigo = _texto(root, "//n:cStat") or _texto(root, "//cStat") or "?"
        msg = _texto(root, "//n:xMotivo") or _texto(root, "//xMotivo") or xml_bytes.decode(errors="replace")[:500]
        return codigo, msg
    except Exception:
        return "?", xml_bytes.decode(errors="replace")[:500]


# ─── Emissão ─────────────────────────────────────────────────────────────────

def emitir_nfse(dados: DadosDPS) -> ResultadoEmissao:
    """Monta a DPS, envia para POST /nfse e retorna o resultado."""
    xml_dps = montar_dps(dados)
    log.debug("DPS gerada:\n%s", xml_dps.decode())

    try:
        with get_nfse_client() as client:
            resp = client.post("/nfse", content=xml_dps)
    except httpx.RequestError as exc:
        log.error("Erro de conexão com ADN: %s", exc)
        return ResultadoEmissao(sucesso=False, erro_mensagem=f"Erro de conexão: {exc}")

    log.warning("ADN status=%s headers=%s body=%s",
                resp.status_code,
                dict(resp.headers),
                resp.text[:1000] or "(vazio)")

    if resp.status_code not in (200, 201):
        codigo, msg = _parse_erro(resp.content)
        # Garante que msg nunca seja vazia para diagnóstico
        if not msg:
            msg = f"HTTP {resp.status_code} — resposta vazia do ADN"
        return ResultadoEmissao(sucesso=False, erro_codigo=codigo, erro_mensagem=msg)

    # Parse da NFS-e retornada
    try:
        root = etree.fromstring(resp.content)
        chave = _texto(root, "//n:chNFSe") or _texto(root, "//chNFSe")
        numero = _texto(root, "//n:nNFSe") or _texto(root, "//nNFSe")
        return ResultadoEmissao(
            sucesso=True,
            chave_acesso=chave,
            numero_nfse=numero,
            xml_nfse=resp.text,
        )
    except etree.XMLSyntaxError as exc:
        log.error("Resposta da API não é XML válido: %s", exc)
        return ResultadoEmissao(
            sucesso=True,         # emitiu, mas não conseguimos parsear
            xml_nfse=resp.text,
            erro_mensagem=f"NFS-e emitida mas resposta inesperada: {exc}",
        )


# ─── Consulta ────────────────────────────────────────────────────────────────

def consultar_nfse(chave_acesso: str) -> Optional[str]:
    """Consulta NFS-e pela chave de acesso. Retorna XML ou None."""
    try:
        with get_nfse_client() as client:
            resp = client.get(f"/nfse/{chave_acesso}")
    except httpx.RequestError as exc:
        log.error("Erro ao consultar NFS-e: %s", exc)
        return None

    if resp.status_code == 200:
        return resp.text
    log.warning("Consulta NFS-e %s: status %s", chave_acesso, resp.status_code)
    return None


# ─── Cancelamento ────────────────────────────────────────────────────────────

def cancelar_nfse(chave_acesso: str, motivo: str) -> ResultadoCancelamento:
    """Registra evento de cancelamento na API de Eventos."""
    # O XML de evento de cancelamento segue leiaute do AnexoII
    # Tipo de evento cancelamento: 110111
    xml_evento = _montar_xml_cancelamento(chave_acesso, motivo)

    try:
        with get_nfse_client() as client:
            resp = client.post(f"/nfse/{chave_acesso}/eventos", content=xml_evento)
    except httpx.RequestError as exc:
        return ResultadoCancelamento(sucesso=False, erro_mensagem=str(exc))

    if resp.status_code in (200, 201):
        return ResultadoCancelamento(sucesso=True)

    _, msg = _parse_erro(resp.content)
    return ResultadoCancelamento(sucesso=False, erro_mensagem=msg)


def _montar_xml_cancelamento(chave_acesso: str, motivo: str) -> bytes:
    """Monta XML mínimo de pedido de cancelamento (tipo 110111)."""
    from datetime import datetime, timezone, timedelta

    BRT = timezone(timedelta(hours=-3))
    dh = datetime.now(tz=BRT).strftime("%Y-%m-%dT%H:%M:%S") + "-03:00"

    root = etree.Element("pedRegEvento", nsmap={None: NS})
    root.set("versao", "1.00")

    inf = etree.SubElement(root, "infPedRegEvento")
    inf.set("Id", f"EVT{chave_acesso[:30]}")

    etree.SubElement(inf, "chNFSe").text = chave_acesso
    etree.SubElement(inf, "tpEvento").text = "110111"    # cancelamento
    etree.SubElement(inf, "nSeqEvento").text = "1"
    etree.SubElement(inf, "dhEvento").text = dh

    det = etree.SubElement(inf, "detEvento")
    etree.SubElement(det, "xMotivo").text = motivo[:255]

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# ─── Parâmetros municipais ───────────────────────────────────────────────────

def consultar_parametros_municipio(cod_municipio: str = "3205309") -> Optional[dict]:
    """Consulta parametrizações do convênio do município (alíquotas, etc.)."""
    try:
        with get_nfse_client() as client:
            resp = client.get(
                f"/parametros_municipais/{cod_municipio}/convenio",
                headers={"Accept": "application/json"},
            )
    except httpx.RequestError as exc:
        log.error("Erro ao consultar parâmetros municipais: %s", exc)
        return None

    if resp.status_code == 200:
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}
    return None
