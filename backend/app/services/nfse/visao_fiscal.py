"""Cálculo da visão fiscal: DAS estimado, quebra por tributo (Anexo IV), carga, alertas."""
from __future__ import annotations

from decimal import Decimal

# Anexo IV — limites de faixa (RBT12), alíquota nominal, parcela a deduzir
ANEXO_IV_FAIXAS = [
    (Decimal("180000.00"),  Decimal("4.50"),  Decimal("0")),
    (Decimal("360000.00"),  Decimal("9.00"),  Decimal("8100")),
    (Decimal("720000.00"),  Decimal("10.20"), Decimal("12420")),
    (Decimal("1800000.00"), Decimal("14.00"), Decimal("39780")),
    (Decimal("3600000.00"), Decimal("22.00"), Decimal("183780")),
    (Decimal("4800000.00"), Decimal("33.00"), Decimal("828000")),
]

# Anexo IV — repartição dos tributos no DAS por faixa: (IRPJ, CSLL, COFINS, PIS, ISS) %
# (CPP/INSS patronal NÃO está no DAS do Anexo IV — é recolhido à parte sobre a folha)
ANEXO_IV_REPART = [
    {"IRPJ": "18.80", "CSLL": "15.20", "COFINS": "17.67", "PIS": "3.83", "ISS": "44.50"},
    {"IRPJ": "19.80", "CSLL": "15.20", "COFINS": "20.55", "PIS": "4.45", "ISS": "40.00"},
    {"IRPJ": "20.80", "CSLL": "15.20", "COFINS": "19.73", "PIS": "4.27", "ISS": "40.00"},
    {"IRPJ": "17.80", "CSLL": "19.20", "COFINS": "18.90", "PIS": "4.10", "ISS": "40.00"},
    {"IRPJ": "18.80", "CSLL": "19.20", "COFINS": "18.08", "PIS": "3.92", "ISS": "40.00"},
    {"IRPJ": "53.50", "CSLL": "21.50", "COFINS": "20.55", "PIS": "4.45", "ISS": "0.00"},
]

SUBLIMITE_ISS = Decimal("3600000.00")
LIMITE_SIMPLES = Decimal("4800000.00")


def faixa_de(rbt12: Decimal) -> int:
    for i, (lim, _, _) in enumerate(ANEXO_IV_FAIXAS):
        if rbt12 <= lim:
            return i
    return len(ANEXO_IV_FAIXAS) - 1


def aliquota_efetiva(rbt12: Decimal) -> Decimal:
    if not rbt12 or rbt12 <= 0:
        return Decimal("0")
    i = faixa_de(rbt12)
    _, nom, ded = ANEXO_IV_FAIXAS[i]
    return ((rbt12 * nom / 100 - ded) / rbt12 * 100).quantize(Decimal("0.01"))


def quebra_das(das: Decimal, faixa: int) -> dict:
    rep = ANEXO_IV_REPART[faixa]
    out = {}
    for trib, pct in rep.items():
        out[trib] = (das * Decimal(pct) / 100).quantize(Decimal("0.01"))
    return out


def repart_pct(faixa: int) -> dict:
    return {k: float(v) for k, v in ANEXO_IV_REPART[faixa].items()}


# ─── Reforma Tributária — transição ISS → IBS/CBS (EC 132 / LC 214) ───────────
# Fator de ISS vigente por ano (substituição gradual a partir de 2029).
ISS_FATOR_POR_ANO = {
    2026: 1.00, 2027: 1.00, 2028: 1.00,
    2029: 0.90, 2030: 0.80, 2031: 0.70, 2032: 0.60, 2033: 0.00,
}


# Alíquotas-piloto 2026 (LC 214/2025, fase de teste): CBS 0,9% + IBS 0,1%,
# compensáveis com PIS/COFINS. Advocacia tem redução de 30% nas alíquotas de
# IBS/CBS (regime favorecido), mas o DESTAQUE é obrigatório mesmo na fase teste.
CBS_TESTE_2026 = Decimal("0.9")
IBS_TESTE_2026 = Decimal("0.1")
REDUCAO_ADVOCACIA = Decimal("0.30")  # 30% de redução para serviços de advocacia


def _aliqs_do_ano(ano: int, ibs_cfg: Decimal, cbs_cfg: Decimal) -> tuple[Decimal, Decimal]:
    """Alíquotas de IBS/CBS vigentes no ano (usa config se informado, senão o piloto)."""
    if ano <= 2025:
        return Decimal("0"), Decimal("0")
    if ano == 2026:
        # Fase teste: valores fixos de lei (config só sobrepõe se preenchido).
        return (ibs_cfg or IBS_TESTE_2026), (cbs_cfg or CBS_TESTE_2026)
    # 2027+ : usa o que estiver configurado (alíquotas serão definidas por LC/resolução).
    return ibs_cfg, cbs_cfg


def transicao_reforma(ano: int, receita: Decimal, ibs_pct: Decimal, cbs_pct: Decimal,
                      piloto: bool, mes: int = 1) -> dict:
    """Elementos de IBS/CBS e substituição do ISS no tempo (EC 132 / LC 214/2025)."""
    iss_fator = 1.0
    if ano >= 2033:
        iss_fator = 0.0
    elif ano in ISS_FATOR_POR_ANO:
        iss_fator = ISS_FATOR_POR_ANO[ano]

    ibs_a, cbs_a = _aliqs_do_ano(ano, ibs_pct, cbs_pct)
    # Redução de 30% para advocacia já aplicada no destaque
    ibs_eff = (ibs_a * (1 - REDUCAO_ADVOCACIA)).quantize(Decimal("0.0001"))
    cbs_eff = (cbs_a * (1 - REDUCAO_ADVOCACIA)).quantize(Decimal("0.0001"))
    ibs_val = (receita * ibs_eff / 100).quantize(Decimal("0.01"))
    cbs_val = (receita * cbs_eff / 100).quantize(Decimal("0.01"))

    # Destaque obrigatório da CBS a partir de agosto/2026
    cbs_destaque_obrigatorio = (ano > 2026) or (ano == 2026 and mes >= 8)

    if ano <= 2025:
        fase = "Pré-reforma (sem IBS/CBS)"
    elif ano == 2026:
        fase = "2026 — Fase de teste: CBS 0,9% + IBS 0,1% (compensáveis com PIS/COFINS)"
    elif ano <= 2028:
        fase = f"{ano} — CBS substitui PIS/COFINS; IBS em implantação"
    elif ano <= 2032:
        fase = f"{ano} — ISS reduzido a {int(iss_fator*100)}%; IBS crescente"
    else:
        fase = "2033+ — ISS/ICMS extintos; IBS/CBS pleno"

    ativo = ano >= 2026 or piloto or ibs_pct > 0 or cbs_pct > 0
    return {
        "ano": ano,
        "fase": fase,
        "iss_fator": iss_fator,
        "iss_pct_vigente": round(iss_fator * 100),
        "ibs_aliq": float(ibs_eff),
        "cbs_aliq": float(cbs_eff),
        "ibs_estimado": float(ibs_val) if ativo else 0.0,
        "cbs_estimado": float(cbs_val) if ativo else 0.0,
        "reducao_advocacia_pct": float(REDUCAO_ADVOCACIA * 100),
        "cbs_destaque_obrigatorio": cbs_destaque_obrigatorio,
        "compensavel_2026": ano == 2026,
        "ativo": bool(ativo),
        "nota": (
            "Em 2026 CBS/IBS são compensáveis com PIS/COFINS (efeito de caixa ~zero), "
            "mas o destaque na nota é obrigatório a partir de agosto/2026."
            if ano == 2026 else
            "Alíquotas de 2027+ ainda dependem de regulamentação — validar com o contador."
        ),
    }


def projecao_reforma(receita: Decimal, ibs_pct: Decimal, cbs_pct: Decimal) -> list[dict]:
    """Projeção plurianual (2026→2033) da carga de transição sobre a receita do mês.
    Material para o contador validar a fase de transição."""
    linhas = []
    for ano in range(2026, 2034):
        t = transicao_reforma(ano, receita, ibs_pct, cbs_pct, piloto=False, mes=8)
        linhas.append({
            "ano": ano,
            "fase": t["fase"],
            "iss_pct_vigente": t["iss_pct_vigente"],
            "cbs_aliq": t["cbs_aliq"],
            "ibs_aliq": t["ibs_aliq"],
            "cbs_estimado": t["cbs_estimado"],
            "ibs_estimado": t["ibs_estimado"],
        })
    return linhas


def gerar_alertas(rbt12: Decimal | None) -> list[dict]:
    alertas = []
    if not rbt12 or rbt12 <= 0:
        return alertas
    i = faixa_de(rbt12)
    limite_faixa = ANEXO_IV_FAIXAS[i][0]
    margem = limite_faixa - rbt12
    if margem >= 0 and margem <= limite_faixa * Decimal("0.05"):
        alertas.append({
            "nivel": "atencao",
            "titulo": "Próximo de mudar de faixa do Simples",
            "detalhe": f"RBT12 a R$ {margem:,.2f} do limite da Faixa {i+1} "
                       f"(R$ {limite_faixa:,.2f}). A alíquota pode subir.",
        })
    if rbt12 > SUBLIMITE_ISS:
        alertas.append({
            "nivel": "alerta",
            "titulo": "Acima do sublimite de ISS (R$ 3,6 mi)",
            "detalhe": "O ISS passa a ser recolhido fora do Simples (guia municipal própria).",
        })
    if rbt12 >= LIMITE_SIMPLES * Decimal("0.90"):
        alertas.append({
            "nivel": "alerta",
            "titulo": "Próximo do teto do Simples Nacional (R$ 4,8 mi)",
            "detalhe": "Ao ultrapassar, há exclusão do Simples no ano seguinte.",
        })
    return alertas
