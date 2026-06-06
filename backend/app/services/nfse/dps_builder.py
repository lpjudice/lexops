"""Monta o XML da DPS (Declaração de Prestação de Serviços) para o NFS-e Nacional.

Schema: ABRASF / Sefin Nacional NFS-e v1.00
Namespace: http://www.sped.fazenda.gov.br/nfse

Referências:
- AnexoI-LeiautesRN_DPS_NFSe-SNNFSe (leiaute oficial)
- NFSe-ESQUEMAS_XSD-v1.01-20260209 (XSD)

Campos IBS/CBS incluídos como opcionais — ativar a partir de agosto/2026
quando Vitória/ES aderir ao piloto da reforma tributária.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from lxml import etree

# ─── Constantes do prestador (Pimenta Judice) ────────────────────────────────

PRESTADOR_CNPJ = "10901611000164"
PRESTADOR_NOME = "PIMENTA JUDICE SOCIEDADE INDIVIDUAL DE ADVOCACIA"
MUNICIPIO_VITORIA_IBGE = "3205309"
PAIS_BRASIL = "1058"

# Código de Tributação Nacional padrão para advocacia
# LC 116/2003 item 17.14 — Advocacia
CTN_ADVOCACIA = "010900"  # TODO: confirmar código exato no ANEXO_B / portal

# Versão do aplicativo emitente
VER_APLIC = "LexOps 1.0"

NS = "http://www.sped.fazenda.gov.br/nfse"

BRT = timezone(timedelta(hours=-3))


# ─── Dataclasses de entrada ──────────────────────────────────────────────────

@dataclass
class EnderecoTomador:
    logradouro: str
    numero: str
    bairro: str
    cod_municipio: str       # IBGE 7 dígitos
    cep: str                 # apenas dígitos
    complemento: str = ""
    cod_pais: str = "1058"   # Brasil


@dataclass
class Tomador:
    nome: str
    cpf_cnpj: str            # apenas dígitos
    email: str = ""
    telefone: str = ""       # apenas dígitos, opcional
    endereco: Optional[EnderecoTomador] = None


@dataclass
class Retencoes:
    """Valores de retenção na fonte (todos opcionais / zero = não inclui)."""
    ir: Decimal = Decimal("0")
    inss: Decimal = Decimal("0")
    csll: Decimal = Decimal("0")
    cofins: Decimal = Decimal("0")
    pis: Decimal = Decimal("0")


@dataclass
class DadosDPS:
    # Identificação da DPS
    serie: str
    numero: int              # número sequencial da DPS
    competencia: str         # YYYY-MM

    # Tomador
    tomador: Tomador

    # Serviço
    descricao_servico: str
    cod_tributacao_nacional: str = CTN_ADVOCACIA

    # Valores
    valor_servicos: Decimal = Decimal("0")
    retencoes: Retencoes = field(default_factory=Retencoes)

    # IBS/CBS — reforma tributária (agosto 2026)
    ibs_valor: Optional[Decimal] = None
    cbs_valor: Optional[Decimal] = None

    # Controle
    ambiente: int = 1        # 1=Produção, 2=Homologação
    data_emissao: Optional[datetime] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _apenas_digitos(v: str) -> str:
    return re.sub(r"\D", "", v or "")


def _fmt_valor(v: Decimal) -> str:
    return f"{v:.2f}"


def _id_dps(cnpj: str, serie: str, numero: int, competencia: str) -> str:
    """Gera o atributo Id da infDPS no padrão do sistema nacional."""
    ano_mes = competencia.replace("-", "")
    return f"DPS{cnpj}{serie.zfill(5)}{str(numero).zfill(15)}{ano_mes}"


def _sub(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    el = etree.SubElement(parent, tag)
    if text is not None:
        el.text = text
    return el


# ─── Builder principal ───────────────────────────────────────────────────────

def montar_dps(dados: DadosDPS) -> bytes:
    """Retorna o XML da DPS codificado em UTF-8, pronto para POST /nfse."""
    dt_emissao = dados.data_emissao or datetime.now(tz=BRT)
    dh_emi = dt_emissao.strftime("%Y-%m-%dT%H:%M:%S") + "-03:00"

    cnpj = _apenas_digitos(PRESTADOR_CNPJ)
    id_dps = _id_dps(cnpj, dados.serie, dados.numero, dados.competencia)

    # Raiz
    root = etree.Element("DPS", nsmap={None: NS})
    root.set("versao", "1.00")

    inf = _sub(root, "infDPS")
    inf.set("Id", id_dps)

    _sub(inf, "tpAmb", str(dados.ambiente))
    _sub(inf, "dhEmi", dh_emi)
    _sub(inf, "verAplic", VER_APLIC)
    _sub(inf, "serie", dados.serie)
    _sub(inf, "nDPS", str(dados.numero))
    _sub(inf, "dCompet", dados.competencia)

    # Prestador
    prest = _sub(inf, "prest")
    _sub(prest, "CNPJ", cnpj)

    # Tomador
    toma = _sub(inf, "toma")
    cpf_cnpj = _apenas_digitos(dados.tomador.cpf_cnpj)
    if len(cpf_cnpj) == 14:
        _sub(toma, "CNPJ", cpf_cnpj)
    else:
        _sub(toma, "CPF", cpf_cnpj.zfill(11))
    _sub(toma, "xNome", dados.tomador.nome[:150])

    if dados.tomador.endereco:
        end = dados.tomador.endereco
        e = _sub(toma, "end")
        _sub(e, "xLgr", end.logradouro[:125])
        _sub(e, "nro", end.numero[:10])
        if end.complemento:
            _sub(e, "xCompl", end.complemento[:60])
        _sub(e, "xBairro", end.bairro[:72])
        _sub(e, "cMun", _apenas_digitos(end.cod_municipio)[:7])
        _sub(e, "CEP", _apenas_digitos(end.cep)[:8])

    if dados.tomador.telefone:
        _sub(toma, "fone", _apenas_digitos(dados.tomador.telefone)[:11])
    if dados.tomador.email:
        _sub(toma, "email", dados.tomador.email[:80])

    # Serviço
    serv = _sub(inf, "serv")
    loc = _sub(serv, "locPrest")
    _sub(loc, "cLocPrestacao", MUNICIPIO_VITORIA_IBGE)

    cserv = _sub(serv, "cServ")
    _sub(cserv, "cTribNac", dados.cod_tributacao_nacional)
    _sub(cserv, "xDescServ", dados.descricao_servico[:2000])

    # Valores
    valores = _sub(inf, "valores")
    vserv_prest = _sub(valores, "vServPrest")
    _sub(vserv_prest, "vServ", _fmt_valor(dados.valor_servicos))

    # Retenções (só inclui se > 0)
    ret = dados.retencoes
    if any(v > 0 for v in [ret.ir, ret.inss, ret.csll, ret.cofins, ret.pis]):
        vded = _sub(valores, "vDed")
        if ret.ir > 0:
            _sub(vded, "pIR", _fmt_valor(ret.ir))
        if ret.inss > 0:
            _sub(vded, "pINSS", _fmt_valor(ret.inss))
        if ret.csll > 0:
            _sub(vded, "pCSLL", _fmt_valor(ret.csll))
        if ret.cofins > 0:
            _sub(vded, "pCOFINS", _fmt_valor(ret.cofins))
        if ret.pis > 0:
            _sub(vded, "pPIS", _fmt_valor(ret.pis))

    # Tributação
    trib = _sub(valores, "trib")
    trib_mun = _sub(trib, "tribMun")
    _sub(trib_mun, "tribISSQN", "1")        # 1 = Tributado no município
    _sub(trib_mun, "cPaisResult", PAIS_BRASIL)
    bm = _sub(trib_mun, "BM")
    _sub(bm, "cBM", MUNICIPIO_VITORIA_IBGE)
    _sub(bm, "xBM", "Vitória")

    # IBS/CBS — reforma tributária (opcional, agosto 2026)
    if dados.ibs_valor is not None or dados.cbs_valor is not None:
        trib_fed = _sub(trib, "tribFed")
        if dados.ibs_valor is not None:
            _sub(trib_fed, "vIBS", _fmt_valor(dados.ibs_valor))
        if dados.cbs_valor is not None:
            _sub(trib_fed, "vCBS", _fmt_valor(dados.cbs_valor))

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
