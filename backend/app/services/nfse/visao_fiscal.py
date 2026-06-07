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
