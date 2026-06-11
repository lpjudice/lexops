"""Motor de cálculo comparativo de regimes tributários.

Dados de entrada → ResultadoCalculo com breakdown linha a linha por regime.
Fórmulas baseadas na legislação vigente; premissas configuráveis por mês.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# ─── Tabelas legais ───────────────────────────────────────────────────────────

# Simples Nacional Anexo IV (advocacia) — RBT12 acumulado 12 meses
# (limite, alíq_nominal, dedução)
FAIXAS_SN_IV = [
    (180_000.0,   0.045,  0.0),
    (360_000.0,   0.090,  8_100.0),
    (720_000.0,   0.102,  12_420.0),
    (1_800_000.0, 0.140,  39_780.0),
    (3_600_000.0, 0.220,  183_780.0),
    (4_800_000.0, 0.330,  828_000.0),
]

# LP — serviços em geral / advocacia
BASE_PRESUMIDA_LP_IRPJ  = 0.32   # IRPJ: 32% da receita
BASE_PRESUMIDA_LP_CSLL  = 0.32   # CSLL: 32% da receita
IRPJ_ALIQ               = 0.15
IRPJ_ADICIONAL_ALIQ     = 0.10   # sobre base que exceder 20k/mês
IRPJ_ADICIONAL_LIMITE   = 20_000.0
CSLL_ALIQ               = 0.09
PIS_LP                  = 0.0065  # cumulativo
COFINS_LP               = 0.0300  # cumulativo

# LR — serviços
PIS_LR                  = 0.0165  # não-cumulativo
COFINS_LR               = 0.0760  # não-cumulativo


# ─── Tipos ────────────────────────────────────────────────────────────────────

@dataclass
class PremissasMes:
    """Premissas tributárias do mês (derivadas de ConfigFiscal + override FiscalMes)."""
    rbt12: float             # receita bruta acumulada 12 meses (para Simples)
    aliquota_iss: float      # ISS municipal em % (ex: 2.0 = 2%)
    ibs_saida_pct: float     # IBS efetivo na saída (já com redução setorial)
    cbs_saida_pct: float     # CBS efetivo na saída (já com redução setorial)
    ibs_entrada_pct: float   # IBS cobrado nos insumos (alíq. do fornecedor, normalmente sem redução)
    cbs_entrada_pct: float   # CBS cobrado nos insumos
    credito_modo: str = "integral"  # integral | parcial


@dataclass
class EntradaMes:
    """Totais já agregados do mês — calculados pelo router a partir dos modelos."""
    receita_total: float
    receita_pj_regular: float    # para calcular crédito transferível ao cliente
    folha_salarios: float
    folha_prolabore: float
    folha_inss_patronal: float
    folha_fgts: float
    folha_beneficios: float
    folha_outros: float
    despesas_total: float
    despesas_elegiveis: float    # com nota + elegível
    retencoes_sofridas: float

    @property
    def folha_total(self) -> float:
        return (self.folha_salarios + self.folha_prolabore + self.folha_inss_patronal
                + self.folha_fgts + self.folha_beneficios + self.folha_outros)


@dataclass
class LinhaRegime:
    """Breakdown linha a linha de um regime."""
    das: float = 0.0
    pis: float = 0.0
    cofins: float = 0.0
    irpj: float = 0.0
    csll: float = 0.0
    iss: float = 0.0
    ibs_bruto: float = 0.0
    cbs_bruto: float = 0.0
    credito_ibs: float = 0.0
    credito_cbs: float = 0.0
    # Folha de pagamento (idêntica entre regimes, mas incluída para visão total)
    inss_patronal: float = 0.0
    fgts: float = 0.0

    @property
    def ibs_liquido(self) -> float:
        return max(self.ibs_bruto - self.credito_ibs, 0.0)

    @property
    def cbs_liquido(self) -> float:
        return max(self.cbs_bruto - self.credito_cbs, 0.0)

    @property
    def total_tributos(self) -> float:
        """Apenas tributos s/ a operação — exclui folha."""
        return (self.das + self.pis + self.cofins + self.irpj + self.csll
                + self.iss + self.ibs_liquido + self.cbs_liquido)

    @property
    def total_com_folha(self) -> float:
        return self.total_tributos + self.inss_patronal + self.fgts


@dataclass
class ResultadoRegime:
    nome: str
    slug: str
    linha: LinhaRegime
    carga_efetiva_pct: float       # total_com_folha / receita × 100
    credito_cliente: float          # crédito IBS/CBS que o cliente PJ pode aproveitar
    ranking: int = 0
    obs: str = ""


@dataclass
class ResultadoCalculo:
    regimes: list[ResultadoRegime]
    vencedor: ResultadoRegime
    totais: dict = field(default_factory=dict)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _aliquota_simples_iv(rbt12: float) -> tuple[float | None, str]:
    if rbt12 <= 0:
        return None, "RBT12 não informado"
    if rbt12 > 4_800_000:
        return None, "Acima do teto SN (R$ 4,8M)"
    for i, (limite, aliq_nom, deducao) in enumerate(FAIXAS_SN_IV):
        if rbt12 <= limite:
            aliq_ef = (rbt12 * aliq_nom - deducao) / rbt12
            return aliq_ef, f"Faixa {i + 1}"
    return None, "Fora do SN"


def _credito_ibscbs(despesas_elegiveis: float, premissas: PremissasMes) -> tuple[float, float]:
    fator = 0.5 if premissas.credito_modo == "parcial" else 1.0
    ibs = despesas_elegiveis * (premissas.ibs_entrada_pct / 100) * fator
    cbs = despesas_elegiveis * (premissas.cbs_entrada_pct / 100) * fator
    return ibs, cbs


def _irpj_base(base: float) -> float:
    normal = base * IRPJ_ALIQ
    adicional = max(base - IRPJ_ADICIONAL_LIMITE, 0.0) * IRPJ_ADICIONAL_ALIQ
    return normal + adicional


# ─── Cálculo por regime ───────────────────────────────────────────────────────

def _calc_simples(entrada: EntradaMes, premissas: PremissasMes) -> tuple[LinhaRegime, str]:
    aliq_ef, obs = _aliquota_simples_iv(premissas.rbt12)
    linha = LinhaRegime(inss_patronal=entrada.folha_inss_patronal, fgts=entrada.folha_fgts)
    if aliq_ef is None:
        linha.das = 0.0
        return linha, obs

    # DAS Anexo IV inclui IRPJ, CSLL, COFINS, PIS, ISS (CPP excluído)
    linha.das = entrada.receita_total * aliq_ef

    # IBS/CBS (transição 2026+)
    cred_ibs, cred_cbs = _credito_ibscbs(entrada.despesas_elegiveis, premissas)
    linha.ibs_bruto = entrada.receita_total * premissas.ibs_saida_pct / 100
    linha.cbs_bruto = entrada.receita_total * premissas.cbs_saida_pct / 100
    linha.credito_ibs = cred_ibs
    linha.credito_cbs = cred_cbs

    return linha, obs


def _calc_lp(entrada: EntradaMes, premissas: PremissasMes) -> tuple[LinhaRegime, str]:
    linha = LinhaRegime(inss_patronal=entrada.folha_inss_patronal, fgts=entrada.folha_fgts)
    r = entrada.receita_total

    base_irpj = r * BASE_PRESUMIDA_LP_IRPJ
    linha.irpj  = _irpj_base(base_irpj)
    linha.csll  = r * BASE_PRESUMIDA_LP_CSLL * CSLL_ALIQ
    linha.pis   = r * PIS_LP
    linha.cofins = r * COFINS_LP
    linha.iss   = r * premissas.aliquota_iss / 100

    cred_ibs, cred_cbs = _credito_ibscbs(entrada.despesas_elegiveis, premissas)
    linha.ibs_bruto = r * premissas.ibs_saida_pct / 100
    linha.cbs_bruto = r * premissas.cbs_saida_pct / 100
    linha.credito_ibs = cred_ibs
    linha.credito_cbs = cred_cbs

    return linha, ""


def _calc_lr(entrada: EntradaMes, premissas: PremissasMes) -> tuple[LinhaRegime, str]:
    linha = LinhaRegime(inss_patronal=entrada.folha_inss_patronal, fgts=entrada.folha_fgts)
    r = entrada.receita_total

    # Lucro contábil simplificado
    lucro = max(r - entrada.folha_total - entrada.despesas_total, 0.0)
    linha.irpj  = _irpj_base(lucro)
    linha.csll  = lucro * CSLL_ALIQ
    linha.iss   = r * premissas.aliquota_iss / 100

    # PIS/COFINS não-cumulativos — crédito sobre entradas (folha não gera crédito)
    credito_piscofins = entrada.despesas_elegiveis * (PIS_LR + COFINS_LR)
    linha.pis    = max(r * PIS_LR   - credito_piscofins * PIS_LR   / (PIS_LR + COFINS_LR), 0.0)
    linha.cofins = max(r * COFINS_LR - credito_piscofins * COFINS_LR / (PIS_LR + COFINS_LR), 0.0)

    cred_ibs, cred_cbs = _credito_ibscbs(entrada.despesas_elegiveis, premissas)
    linha.ibs_bruto = r * premissas.ibs_saida_pct / 100
    linha.cbs_bruto = r * premissas.cbs_saida_pct / 100
    linha.credito_ibs = cred_ibs
    linha.credito_cbs = cred_cbs

    return linha, "Lucro contábil simplificado — confirme com contador"


# ─── Entry point ─────────────────────────────────────────────────────────────

def calcular(entrada: EntradaMes, premissas: PremissasMes) -> ResultadoCalculo:
    r = entrada.receita_total
    if r <= 0:
        r = 1  # evita divisão por zero

    def _resultado(nome: str, slug: str, linha: LinhaRegime, obs: str) -> ResultadoRegime:
        credito_cliente = (
            entrada.receita_pj_regular * (premissas.ibs_saida_pct + premissas.cbs_saida_pct) / 100
        )
        return ResultadoRegime(
            nome=nome,
            slug=slug,
            linha=linha,
            carga_efetiva_pct=round(linha.total_com_folha / r * 100, 2),
            credito_cliente=credito_cliente,
            obs=obs,
        )

    linha_sn, obs_sn = _calc_simples(entrada, premissas)
    linha_lp, obs_lp = _calc_lp(entrada, premissas)
    linha_lr, obs_lr = _calc_lr(entrada, premissas)

    regimes = [
        _resultado("Simples Nacional", "simples", linha_sn, obs_sn),
        _resultado("Lucro Presumido",  "lp",      linha_lp, obs_lp),
        _resultado("Lucro Real",       "lr",      linha_lr, obs_lr),
    ]

    # Ranking por total_com_folha (menor = melhor para caixa)
    regimes.sort(key=lambda x: x.linha.total_com_folha)
    for i, reg in enumerate(regimes):
        reg.ranking = i + 1

    vencedor = regimes[0]

    cred_ibs_total, cred_cbs_total = _credito_ibscbs(entrada.despesas_elegiveis, premissas)

    totais = {
        "receita_total": entrada.receita_total,
        "folha_total": entrada.folha_total,
        "despesas_total": entrada.despesas_total,
        "despesas_elegiveis": entrada.despesas_elegiveis,
        "credito_ibs": cred_ibs_total,
        "credito_cbs": cred_cbs_total,
        "credito_total": cred_ibs_total + cred_cbs_total,
        "retencoes_sofridas": entrada.retencoes_sofridas,
    }

    return ResultadoCalculo(regimes=regimes, vencedor=vencedor, totais=totais)
