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

PRESTADOR_CNPJ    = "10901611000164"
PRESTADOR_NOME    = "PIMENTA JUDICE SOCIEDADE INDIVIDUAL DE ADVOCACIA"
MUNICIPIO_VITORIA_IBGE = "3205309"
PAIS_BRASIL       = "1058"
VER_APLIC         = "LexOps 1.0"
CTN_ADVOCACIA     = "010900"   # LC 116/2003 item 17.14 — Advocacia
NS                = "http://www.sped.fazenda.gov.br/nfse"
BRT               = timezone(timedelta(hours=-3))

# ─── Opções de Código de Tributação Nacional (LC 116/2003) ───────────────────
# Formato: (código, descrição curta, descrição detalhada)
CODIGOS_TRIBUTACAO = [
    ("010900", "Advocacia",                    "Serviços advocatícios em geral (LC 116/2003, item 17.14)"),
    ("010901", "Consultoria Jurídica",         "Assessoria e consultoria jurídica"),
    ("010902", "Planejamento Jurídico",        "Planejamento jurídico-societário e patrimonial"),
    ("010903", "Honorários de Êxito",          "Honorários advocatícios de êxito"),
    ("010100", "Consultoria em Geral",         "Consultoria em geral, exceto nas alíneas a seguir"),
    ("010200", "Análise e Desenvolvimento",    "Análise e desenvolvimento de sistemas"),
]

# ─── Natureza de Operação ─────────────────────────────────────────────────────
# 1=Tributação no Município, 2=Tributação Fora do Município, 3=Isenção,
# 4=Imune, 5=Exigibilidade Suspensa por Dec. Judicial, 6=Exigibilidade Suspensa por Adm.
NATUREZA_OPERACAO_OPCOES = [
    ("1", "Tributação no Município",               "Padrão — ISS devido em Vitória/ES"),
    ("2", "Tributação Fora do Município",           "Serviço prestado em outro município"),
    ("3", "Isenção",                               "Serviço isento de ISS por lei municipal"),
    ("4", "Imune",                                 "Entidade imune — ex: entidade religiosa, educacional"),
    ("5", "Exigibilidade Suspensa (Judicial)",     "Liminar ou antecipação de tutela judicial"),
    ("6", "Exigibilidade Suspensa (Administrativa)","Impugnação ou recurso administrativo"),
]

# ─── Regime Tributário ───────────────────────────────────────────────────────
REGIME_TRIBUTARIO_OPCOES = [
    ("1", "Simples Nacional",         "Microempresa ou Empresa de Pequeno Porte optante pelo Simples"),
    ("2", "Lucro Presumido",          "Empresa optante pelo Lucro Presumido"),
    ("3", "Lucro Real",               "Empresa tributada pelo Lucro Real"),
]

# Regime de apuração no Simples Nacional
# 1 = Tributação dos serviços no próprio SN (não destaca ISS)
# 3 = Tributação dos serviços fora do SN (destaca ISS na nota)
REG_APURACAO_SN_OPCOES = [
    ("1", "Tributação pelo Simples Nacional",
          "Imposto municipal apurado dentro do Simples Nacional — sem destaque de ISS"),
    ("3", "Tributação Federal e Municipal pelo Simples Nacional",
          "Regime de apuração dos tributos federais e municipais pelo Simples Nacional"),
]


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
    telefone: str = ""
    endereco: Optional[EnderecoTomador] = None
    no_exterior: bool = False   # tomador fora do Brasil


@dataclass
class Intermediario:
    nome: str
    cpf_cnpj: str
    inscricao_municipal: str = ""


@dataclass
class Retencoes:
    """Valores de retenção na fonte."""
    ir: Decimal = Decimal("0")
    inss: Decimal = Decimal("0")
    csll: Decimal = Decimal("0")
    cofins: Decimal = Decimal("0")
    pis: Decimal = Decimal("0")
    iss_retido: bool = False  # ISS retido pelo tomador


@dataclass
class DadosDPS:
    # Identificação da DPS
    serie: str
    numero: int
    competencia: str         # YYYY-MM

    # Tomador
    tomador: Tomador

    # Serviço
    descricao_servico: str
    cod_tributacao_nacional: str = "010900"

    # Tributação
    natureza_operacao: str = "1"   # 1 = Tributado no município
    regime_tributario: str = "1"   # 1 = Simples Nacional
    reg_apuracao_sn: str = "3"     # 3 = Fed+Mun pelo Simples Nacional

    # Valores
    valor_servicos: Decimal = Decimal("0")
    retencoes: Retencoes = field(default_factory=Retencoes)

    # Intermediário (opcional)
    intermediario: Optional[Intermediario] = None

    # IBS/CBS — reforma tributária (agosto 2026)
    ibs_valor: Optional[Decimal] = None
    cbs_valor: Optional[Decimal] = None

    # Controle
    ambiente: int = 1
    data_emissao: Optional[datetime] = None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _apenas_digitos(v: str) -> str:
    return re.sub(r"\D", "", v or "")


def _fmt_valor(v: Decimal) -> str:
    return f"{v:.2f}"


def _id_dps(cnpj: str, serie: str, numero: int, competencia: str) -> str:
    ano_mes = competencia.replace("-", "")
    return f"DPS{cnpj}{serie.zfill(5)}{str(numero).zfill(15)}{ano_mes}"


def _sub(parent: etree._Element, tag: str, text: str | None = None) -> etree._Element:
    el = etree.SubElement(parent, tag)
    if text is not None:
        el.text = text
    return el


# ─── Builder principal ───────────────────────────────────────────────────────

def montar_dps(dados: DadosDPS) -> bytes:
    """Retorna o XML da DPS em UTF-8, pronto para POST /nfse."""
    dt_emissao = dados.data_emissao or datetime.now(tz=BRT)
    dh_emi = dt_emissao.strftime("%Y-%m-%dT%H:%M:%S") + "-03:00"

    cnpj = _apenas_digitos(PRESTADOR_CNPJ)
    id_dps = _id_dps(cnpj, dados.serie, dados.numero, dados.competencia)

    root = etree.Element("DPS", nsmap={None: NS})
    root.set("versao", "1.00")

    inf = _sub(root, "infDPS")
    inf.set("Id", id_dps)

    _sub(inf, "tpAmb",    str(dados.ambiente))
    _sub(inf, "dhEmi",    dh_emi)
    _sub(inf, "verAplic", VER_APLIC)
    _sub(inf, "serie",    dados.serie)
    _sub(inf, "nDPS",     str(dados.numero))
    _sub(inf, "dCompet",  dados.competencia)

    # ── Prestador ──────────────────────────────────────────────────────
    prest = _sub(inf, "prest")
    _sub(prest, "CNPJ", cnpj)

    # Regime tributário do prestador
    trib_prest = _sub(prest, "regTrib")
    _sub(trib_prest, "opSimpNac",    "1")                # 1 = optante Simples
    _sub(trib_prest, "regApTribSN",  dados.reg_apuracao_sn)
    _sub(trib_prest, "regTrib",      dados.regime_tributario)

    # ── Tomador ────────────────────────────────────────────────────────
    toma = _sub(inf, "toma")
    cpf_cnpj = _apenas_digitos(dados.tomador.cpf_cnpj)

    if dados.tomador.no_exterior:
        _sub(toma, "NIF", cpf_cnpj or "NAO_INFORMADO")
        _sub(toma, "cPais", dados.tomador.endereco.cod_pais if dados.tomador.endereco else "9999")
    else:
        if len(cpf_cnpj) == 14:
            _sub(toma, "CNPJ", cpf_cnpj)
        else:
            _sub(toma, "CPF", cpf_cnpj.zfill(11))

    _sub(toma, "xNome", dados.tomador.nome[:150])

    if dados.tomador.endereco and not dados.tomador.no_exterior:
        end = dados.tomador.endereco
        e = _sub(toma, "end")
        _sub(e, "xLgr",    end.logradouro[:125])
        _sub(e, "nro",     end.numero[:10])
        if end.complemento:
            _sub(e, "xCompl", end.complemento[:60])
        _sub(e, "xBairro", end.bairro[:72])
        _sub(e, "cMun",    _apenas_digitos(end.cod_municipio)[:7])
        _sub(e, "CEP",     _apenas_digitos(end.cep)[:8])

    if dados.tomador.telefone:
        _sub(toma, "fone", _apenas_digitos(dados.tomador.telefone)[:11])
    if dados.tomador.email:
        _sub(toma, "email", dados.tomador.email[:80])

    # ── Intermediário (opcional) ───────────────────────────────────────
    if dados.intermediario:
        interm = _sub(inf, "interm")
        cpf_interm = _apenas_digitos(dados.intermediario.cpf_cnpj)
        if len(cpf_interm) == 14:
            _sub(interm, "CNPJ", cpf_interm)
        else:
            _sub(interm, "CPF", cpf_interm.zfill(11))
        _sub(interm, "xNome", dados.intermediario.nome[:150])
        if dados.intermediario.inscricao_municipal:
            _sub(interm, "IM", dados.intermediario.inscricao_municipal[:15])

    # ── Serviço ────────────────────────────────────────────────────────
    serv = _sub(inf, "serv")
    loc = _sub(serv, "locPrest")
    if dados.tomador.no_exterior:
        _sub(loc, "cPaisResult", dados.tomador.endereco.cod_pais if dados.tomador.endereco else "9999")
    else:
        _sub(loc, "cLocPrestacao", MUNICIPIO_VITORIA_IBGE)

    cserv = _sub(serv, "cServ")
    _sub(cserv, "cTribNac",  dados.cod_tributacao_nacional)
    _sub(cserv, "xDescServ", dados.descricao_servico[:2000])

    # ── Valores ────────────────────────────────────────────────────────
    valores = _sub(inf, "valores")
    vserv_prest = _sub(valores, "vServPrest")
    _sub(vserv_prest, "vServ", _fmt_valor(dados.valor_servicos))

    # Deduções/retenções
    ret = dados.retencoes
    retencoes_vals = [ret.ir, ret.inss, ret.csll, ret.cofins, ret.pis]
    if any(v > 0 for v in retencoes_vals):
        vded = _sub(valores, "vDed")
        if ret.ir > 0:
            _sub(vded, "vIR",     _fmt_valor(ret.ir))
        if ret.inss > 0:
            _sub(vded, "vINSS",   _fmt_valor(ret.inss))
        if ret.csll > 0:
            _sub(vded, "vCSLL",   _fmt_valor(ret.csll))
        if ret.cofins > 0:
            _sub(vded, "vCOFINS", _fmt_valor(ret.cofins))
        if ret.pis > 0:
            _sub(vded, "vPIS",    _fmt_valor(ret.pis))

    # Tributação
    trib = _sub(valores, "trib")
    trib_mun = _sub(trib, "tribMun")

    _sub(trib_mun, "tribISSQN", dados.natureza_operacao)
    _sub(trib_mun, "cPaisResult", PAIS_BRASIL)

    if dados.natureza_operacao == "1":  # tributado no município
        bm = _sub(trib_mun, "BM")
        _sub(bm, "cBM", MUNICIPIO_VITORIA_IBGE)
        _sub(bm, "xBM", "Vitória")
        if ret.iss_retido:
            _sub(trib_mun, "issRetido", "1")
    elif dados.natureza_operacao in ("3", "4", "5", "6"):
        # Isenção / imunidade / suspensão — não inclui BM
        pass

    # IBS/CBS — reforma tributária (agosto 2026)
    if dados.ibs_valor is not None or dados.cbs_valor is not None:
        trib_fed = _sub(trib, "tribFed")
        if dados.ibs_valor is not None:
            _sub(trib_fed, "vIBS", _fmt_valor(dados.ibs_valor))
        if dados.cbs_valor is not None:
            _sub(trib_fed, "vCBS", _fmt_valor(dados.cbs_valor))

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
