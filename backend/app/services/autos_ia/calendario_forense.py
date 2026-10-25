"""Contagem de prazos em dias úteis (CPC, art. 219) — ESTIMATIVA para o quadro de cumprimento.

Não substitui a conferência da contagem pelo advogado: o início depende da data de
intimação/publicação, e o calendário do TJES pode ter suspensões locais que não estão aqui
(ex.: ponto facultativo estadual). Por isso o sistema sempre mostra "estimado" e deixa corrigir a
data de início da contagem.

Regras aplicadas: não conta sábado, domingo, feriado nacional nem o recesso forense
(20/12 a 20/01, CPC art. 220); a contagem exclui o dia do começo e inclui o do vencimento; se o
último dia cair em dia não útil, passa ao primeiro dia útil seguinte.
"""
from datetime import date, timedelta

# Feriados nacionais e dias de suspensão geral do expediente forense (2026–2028)
FERIADOS = {
    # 2026
    date(2026, 1, 1), date(2026, 2, 16), date(2026, 2, 17), date(2026, 4, 3), date(2026, 4, 21), date(2026, 5, 1),
    date(2026, 6, 4), date(2026, 9, 7), date(2026, 10, 12), date(2026, 11, 2), date(2026, 11, 15), date(2026, 11, 20),
    date(2026, 12, 25),
    # 2027
    date(2027, 1, 1), date(2027, 2, 8), date(2027, 2, 9), date(2027, 3, 26), date(2027, 4, 21), date(2027, 5, 1),
    date(2027, 5, 27), date(2027, 9, 7), date(2027, 10, 12), date(2027, 11, 2), date(2027, 11, 15), date(2027, 11, 20),
    date(2027, 12, 25),
    # 2028
    date(2028, 1, 1), date(2028, 2, 28), date(2028, 2, 29), date(2028, 4, 14), date(2028, 4, 21), date(2028, 5, 1),
    date(2028, 6, 15), date(2028, 9, 7), date(2028, 10, 12), date(2028, 11, 2), date(2028, 11, 15), date(2028, 11, 20),
    date(2028, 12, 25),
}


def em_recesso(d: date) -> bool:
    """20/12 a 31/12 e 1/1 a 20/1 (CPC art. 220)."""
    return (d.month == 12 and d.day >= 20) or (d.month == 1 and d.day <= 20)


def eh_dia_util(d: date) -> bool:
    return d.weekday() < 5 and d not in FERIADOS and not em_recesso(d)


def proximo_dia_util(d: date) -> date:
    while not eh_dia_util(d):
        d += timedelta(days=1)
    return d


def somar_dias(inicio: date, n: int, uteis: bool = True) -> date:
    """Vencimento de um prazo de `n` dias que começa a correr a partir de `inicio` (o dia do
    início não conta). Em dias corridos, o recesso também suspende; o vencimento que cair em dia
    não útil passa ao primeiro dia útil seguinte."""
    d = inicio
    restante = n
    while restante > 0:
        d += timedelta(days=1)
        if uteis:
            if eh_dia_util(d):
                restante -= 1
        elif not em_recesso(d):
            restante -= 1
    return proximo_dia_util(d)
