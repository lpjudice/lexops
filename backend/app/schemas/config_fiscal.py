from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class TemplateDescricao(BaseModel):
    tipo: str
    label: str
    texto: str


class CodigoFavorito(BaseModel):
    codigo: str
    label: str
    descricao: str = ""


class ConfigFiscalBase(BaseModel):
    # Emitente
    razao_social: str
    cnpj: str
    inscricao_municipal: Optional[str] = None
    cnae: Optional[str] = None
    endereco: Optional[str] = None
    municipio_ibge: str
    municipio_nome: str
    uf: str
    email_fiscal: Optional[str] = None
    telefone_fiscal: Optional[str] = None
    regime_tributario: str

    # Bases
    aliquota_iss: Decimal
    regime_especial: str
    anexo_simples: str
    rbt12: Optional[Decimal] = None
    aliquota_efetiva_simples: Decimal
    ret_ir_pct: Decimal
    ret_inss_pct: Decimal
    ret_csll_pct: Decimal
    ret_pis_pct: Decimal
    ret_cofins_pct: Decimal
    iss_retido_padrao: bool

    # IBS/CBS
    ibs_pct: Decimal
    cbs_pct: Decimal
    piloto_ibscbs: bool

    # Contabilidade
    emails_contador: list[str] = []
    email_master: Optional[str] = None
    dia_envio_relatorio: int
    enviar_relatorio_auto: bool

    # Numeração
    serie_padrao: str

    # Catálogos
    codigos_favoritos: list[CodigoFavorito] = []
    templates_descricao: list[TemplateDescricao] = []

    # DANFSe
    rodape_danfse: Optional[str] = None
    danfse_prefixo_numero: str = ""
    carga_media_pct: Decimal = Decimal("16.33")


class ConfigFiscalOut(ConfigFiscalBase):
    updated_at: Optional[datetime] = None
    # Sugestão calculada (não persiste) — preenchida pelo router
    aliquota_simples_sugerida: Optional[Decimal] = None
    faixa_simples: Optional[str] = None
    rbt12_acumulado_12m: Optional[float] = None
    aliquota_pelo_acumulado: Optional[float] = None
    link_publico_token: Optional[str] = None

    model_config = {"from_attributes": True}


class ConfigFiscalUpdate(ConfigFiscalBase):
    pass
