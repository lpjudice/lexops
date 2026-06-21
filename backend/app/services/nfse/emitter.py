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

import time

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

def _request_retry(metodo: str, alvo: str, path: str, *, max_tentativas: int = 5,
                   ambiente: int | None = None, **kwargs):
    """Faz request com retry — o servidor do gov derruba as 1ªs conexões (warm-up).

    Seguro para POST /nfse: o disconnect ocorre antes do envio (nada é criado);
    além disso a DPS tem Id único (idempotência por nDPS no servidor).
    """
    ultimo_erro = None
    for tentativa in range(max_tentativas):
        try:
            client = get_sefin_client(ambiente) if alvo == "sefin" else get_adn_client()
            with client:
                return client.request(metodo, path, **kwargs)
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError) as exc:
            ultimo_erro = exc
            log.warning("Conexão %s caiu (tentativa %s/%s): %s",
                        alvo, tentativa + 1, max_tentativas, exc)
            time.sleep(0.6 * (tentativa + 1))
    raise ultimo_erro  # type: ignore[misc]


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

    # 5) POST (com retry — produção derruba as 1ªs conexões)
    try:
        resp = _request_retry("POST", "sefin", "nfse", json=payload, ambiente=dados.ambiente)
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
        # número da NFS-e: extrai do <nNFSe> do XML retornado
        numero = _numero_do_xml(nfse_xml)
        if numero:
            log.info(f"NFS-e emitida com sucesso: número={numero}, chave={chave}")
        else:
            log.warning(f"NFS-e emitida mas número não encontrado no XML. Chave={chave}. XML primeiros 500 chars: {(nfse_xml or '')[:500]}")
        return ResultadoEmissao(
            sucesso=True,
            chave_acesso=chave,
            numero_nfse=numero,
            xml_nfse=nfse_xml,
        )

    codigo, msg = _fmt_erros(data)
    return ResultadoEmissao(sucesso=False, erro_codigo=codigo, erro_mensagem=msg)


def _numero_do_xml(xml_nfse: Optional[str]) -> Optional[str]:
    """Extrai o número da NFS-e (<nNFSe>) do XML retornado pelo Sefin."""
    if not xml_nfse:
        return None
    try:
        from lxml import etree
        root = etree.fromstring(xml_nfse.encode() if isinstance(xml_nfse, str) else xml_nfse)
        els = root.xpath("//*[local-name()='nNFSe']")
        return els[0].text if els else None
    except Exception:
        return None


# ─── Consulta ────────────────────────────────────────────────────────────────

def consultar_nfse(chave_acesso: str) -> Optional[str]:
    try:
        resp = _request_retry("GET", "sefin", f"nfse/{chave_acesso}")
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
    log.info(f"Iniciando cancelamento de NF com chave {chave_acesso}")
    xml_evento = _montar_xml_cancelamento(chave_acesso, motivo)
    log.debug(f"XML evento (primeiros 500 bytes): {xml_evento[:500]}")

    # Assinatura
    try:
        log.info("Assinando evento...")
        xml_assinado = assinar_evento(xml_evento)
        log.info(f"Evento assinado com sucesso ({len(xml_assinado)} bytes)")
    except Exception as exc:
        log.error(f"Erro ao assinar evento: {exc}", exc_info=True)
        return ResultadoCancelamento(sucesso=False, erro_mensagem=f"Erro ao assinar: {str(exc)[:200]}")

    payload = {"pedidoRegistroEventoXmlGZipB64": _gzip_b64(xml_assinado)}

    # Request (timeout padrão: 60s do Client)
    try:
        log.info(f"Enviando cancelamento para Sefin (payload size={len(payload['pedidoRegistroEventoXmlGZipB64'])})")
        resp = _request_retry("POST", "sefin", f"nfse/{chave_acesso}/eventos",
                             json=payload)
    except httpx.RequestError as exc:
        log.error(f"Erro de conexão ao Sefin: {exc}", exc_info=True)
        return ResultadoCancelamento(sucesso=False, erro_mensagem=f"Erro de conexão: {str(exc)[:200]}")

    log.warning("SEFIN POST evento status=%s body=%s", resp.status_code, resp.text[:800])
    if resp.status_code in (200, 201):
        log.info(f"Cancelamento aceito pelo Sefin")
        return ResultadoCancelamento(sucesso=True)

    try:
        _, msg = _fmt_erros(resp.json())
    except Exception:
        msg = f"HTTP {resp.status_code}: {resp.text[:300]}"
    log.error(f"Sefin rejeitou cancelamento: {msg}")
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
            resp = _request_retry("GET", alvo, path, headers={"Accept": "application/pdf"})
            if resp.status_code == 200 and resp.content[:4] == b"%PDF":
                return resp.content
            log.warning("DANFSe %s/%s: status %s ct=%s",
                        alvo, path, resp.status_code, resp.headers.get("content-type"))
        except httpx.RequestError as exc:
            log.warning("DANFSe %s erro: %s", alvo, exc)
    return None


_MESES_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
             "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _nome_arquivo_nf(numero: str, competencia: str, cliente: str) -> str:
    """#nota_Mês_Cliente.pdf — limpo para sistema de arquivos."""
    import re
    ano, mes = competencia[:4], int(competencia[5:7])
    mes_lbl = f"{_MESES_PT[mes-1]}{ano}"
    cli = re.sub(r"[^\w\s-]", "", (cliente or "Cliente")).strip().replace(" ", "_")[:40]
    return f"NFSe-{numero}_{mes_lbl}_{cli}.pdf"


def subir_pdf_drive(pdf: bytes, nome_arquivo: str, nome_cliente: str,
                    competencia: str | None = None) -> Optional[str]:
    """Sobe o PDF ao Drive em DOIS locais:
    1) pasta do cliente / Notas Fiscais
    2) Fiscal/NFe/MêsX_Ano  (visão do setor fiscal)
    Retorna o link da pasta do cliente.
    """
    from app.services.google_drive import upload_arquivo
    link_cliente = None
    try:
        link_cliente = upload_arquivo(
            conteudo=pdf, nome_arquivo=nome_arquivo,
            nome_cliente=nome_cliente or "Notas Fiscais",
            subfolder="Notas Fiscais", mimetype="application/pdf",
        )
    except Exception as exc:
        log.warning("Drive (pasta cliente) falhou: %s", exc)

    # Cópia na pasta central do Fiscal: Fiscal/NFe/MêsX_Ano
    if competencia:
        try:
            ano, mes = competencia[:4], int(competencia[5:7])
            mes_pasta = f"{_MESES_PT[mes-1]}_{ano}"
            upload_arquivo(
                conteudo=pdf, nome_arquivo=nome_arquivo,
                nome_cliente="Fiscal", subfolder="NFe",
                sub_subfolder=mes_pasta, mimetype="application/pdf",
            )
        except Exception as exc:
            log.warning("Drive (Fiscal/NFe) falhou: %s", exc)

    return link_cliente


# ─── Parâmetros municipais (ADN) ─────────────────────────────────────────────

def consultar_parametros_municipio(cod_municipio: str = "3205309") -> Optional[dict]:
    try:
        resp = _request_retry("GET", "adn", f"parametros_municipais/{cod_municipio}/convenio")
    except httpx.RequestError as exc:
        log.error("Erro ao consultar parâmetros municipais: %s", exc)
        return None
    if resp.status_code == 200:
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}
    return None
