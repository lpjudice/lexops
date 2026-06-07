"""Sincronização DFe — distribuição de documentos do ADN (caminho público do governo).

Varre os documentos do CNPJ (GET /DFe/{NSU}), e para cada NFS-e em que o
emitente é a Pimenta Judice e que ainda não está no sistema, cria o registro
(reconciliação) — inclusive notas emitidas direto no portal nacional.
"""
from __future__ import annotations

import base64
import gzip
import logging
from datetime import date, datetime

from lxml import etree
from sqlalchemy.orm import Session

from .client import get_adn_client
from .documentos import so_digitos

log = logging.getLogger(__name__)
NOSSO_CNPJ = "10901611000164"


def _dec(b64: str) -> bytes:
    raw = base64.b64decode(b64)
    try:
        return gzip.decompress(raw)
    except Exception:
        return raw


def _txt(root, name: str) -> str | None:
    els = root.xpath(f"//*[local-name()='{name}']/text()")
    return els[0] if els else None


def sincronizar_dfe(db: Session, max_paginas: int = 40) -> dict:
    from app.models.nota_fiscal import NotaFiscal
    from app.models.config_fiscal import ConfigFiscal

    cfg = db.query(ConfigFiscal).filter(ConfigFiscal.id == 1).first()
    nsu = (cfg.dfe_ultimo_nsu if cfg and cfg.dfe_ultimo_nsu else 0)
    nosso = so_digitos(cfg.cnpj) if cfg and cfg.cnpj else NOSSO_CNPJ

    novas = 0
    recebidas = 0
    maxnsu = nsu
    try:
        client = get_adn_client()
        with client:
            for _ in range(max_paginas):
                r = client.get(f"DFe/{maxnsu}", headers={"Accept": "application/json"})
                if r.status_code != 200:
                    break
                data = r.json()
                lote = data.get("LoteDFe") or []
                if not lote:
                    break
                for item in lote:
                    maxnsu = max(maxnsu, int(item.get("NSU", maxnsu)))
                    if item.get("TipoDocumento") != "NFSE":
                        continue
                    chave = item.get("ChaveAcesso")
                    if not chave:
                        continue
                    try:
                        root = etree.fromstring(_dec(item["ArquivoXml"]))
                    except Exception:
                        continue
                    emit = _txt(root, "CNPJ")  # primeiro CNPJ = emitente
                    if emit != nosso:
                        recebidas += 1
                        continue
                    # Já existe?
                    if db.query(NotaFiscal).filter(NotaFiscal.chave_acesso == chave).first():
                        continue
                    # Cria registro reconciliado
                    nf = _nota_de_xml(root, chave, item.get("ArquivoXml"))
                    db.add(nf)
                    novas += 1
                db.commit()
    except Exception as exc:
        log.warning("DFe sync erro: %s", exc)

    if cfg:
        cfg.dfe_ultimo_nsu = maxnsu
        db.commit()

    return {"novas": novas, "recebidas_ignoradas": recebidas, "ultimo_nsu": maxnsu}


def _nota_de_xml(root, chave: str, arquivo_b64: str) -> "object":
    from app.models.nota_fiscal import NotaFiscal

    numero = _txt(root, "nNFSe")
    dcompet = _txt(root, "dCompet") or ""
    competencia = dcompet[:7] if dcompet else datetime.now().strftime("%Y-%m")
    dhproc = _txt(root, "dhProc")
    data_em = None
    if dhproc:
        try:
            data_em = datetime.fromisoformat(dhproc.replace("Z", "+00:00")).date()
        except Exception:
            data_em = date.today()
    # Tomador: pega o bloco toma
    toma = root.xpath("//*[local-name()='toma']")
    toma_nome = toma_doc = None
    if toma:
        t = toma[0]
        nome = t.xpath("./*[local-name()='xNome']/text()")
        toma_nome = nome[0] if nome else "—"
        cnpj = t.xpath("./*[local-name()='CNPJ']/text()")
        cpf = t.xpath("./*[local-name()='CPF']/text()")
        toma_doc = (cnpj or cpf or [""])[0]
    vserv = _txt(root, "vServ") or "0"
    xml_full = _dec(arquivo_b64).decode("utf-8", errors="replace")

    return NotaFiscal(
        numero_nfse=numero, chave_acesso=chave, serie="1",
        competencia=competencia, data_emissao=data_em,
        tomador_cpf_cnpj=so_digitos(toma_doc or "") or "00000000000",
        tomador_nome=toma_nome or "—",
        cod_tributacao_nacional="171401",
        descricao_servico="(importada via DFe do governo)",
        valor_servicos=float(vserv), status="emitida", ambiente=1,
        xml_nfse=xml_full, origem="dfe",
    )
