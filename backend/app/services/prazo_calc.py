"""
Motor de cálculo de prazos processuais.

Regras:
- Dias úteis: pula sábados, domingos e feriados do estado + nacionais.
- Dias corridos: pula apenas sábados e domingos (feriados não suspendem).
- Retorna duas datas:
    data_com_feriado    → data real considerando feriados
    data_sem_feriado    → data hipotética sem considerar feriados
      (útil para comunicar ao cliente o que seria sem os feriados)
"""

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.feriado import Feriado


def _carregar_feriados(db: Session, estado: str, ano: int) -> set[date]:
    """
    Retorna conjunto de datas de feriados válidos para o estado + nacionais
    no ano informado. Feriados recorrentes são projetados para o ano atual.
    """
    registros = (
        db.query(Feriado)
        .filter(Feriado.estado.in_(["nacional", estado]))
        .all()
    )
    datas: set[date] = set()
    for f in registros:
        if f.recorrente:
            # projeta para o ano calculado (ignora o ano do seed)
            try:
                datas.add(f.data.replace(year=ano))
            except ValueError:
                # 29-fev em ano não bissexto
                pass
        else:
            if f.data.year == ano:
                datas.add(f.data)
    return datas


def _proximo_dia_util(d: date, feriados: set[date]) -> date:
    while d.weekday() >= 5 or d in feriados:
        d += timedelta(days=1)
    return d


def calcular_prazo(
    db: Session,
    data_publicacao: date,
    dias: int,
    estado: str,
    tipo_contagem: str = "uteis",
) -> tuple[date, date]:
    """
    Retorna (data_com_feriado, data_sem_feriado).

    Para prazos processuais, a contagem começa no 1º dia útil APÓS a publicação.
    """
    # ── COM feriados ──────────────────────────────────────────────────────
    feriados = _carregar_feriados(db, estado, data_publicacao.year)
    # garante feriados do ano seguinte se o prazo ultrapassar virada de ano
    feriados |= _carregar_feriados(db, estado, data_publicacao.year + 1)

    data_inicio = data_publicacao + timedelta(days=1)

    if tipo_contagem == "uteis":
        # início da contagem: próximo dia útil
        data_inicio = _proximo_dia_util(data_inicio, feriados)
        atual = data_inicio
        contados = 0
        while contados < dias:
            if atual.weekday() < 5 and atual not in feriados:
                contados += 1
            if contados < dias:
                atual += timedelta(days=1)
        # se o último dia cair em não-útil, avança
        data_com_feriado = _proximo_dia_util(atual, feriados)
    else:
        # corridos: conta todos os dias, pula fim de semana no encerramento
        data_com_feriado_raw = data_inicio + timedelta(days=dias - 1)
        # se cair em fim de semana, avança para segunda
        while data_com_feriado_raw.weekday() >= 5:
            data_com_feriado_raw += timedelta(days=1)
        data_com_feriado = data_com_feriado_raw

    # ── SEM feriados (hipotético) ─────────────────────────────────────────
    if tipo_contagem == "uteis":
        data_inicio_sem = data_publicacao + timedelta(days=1)
        # próximo dia útil desconsiderando feriados (apenas fins de semana)
        while data_inicio_sem.weekday() >= 5:
            data_inicio_sem += timedelta(days=1)
        atual_sem = data_inicio_sem
        contados_sem = 0
        while contados_sem < dias:
            if atual_sem.weekday() < 5:
                contados_sem += 1
            if contados_sem < dias:
                atual_sem += timedelta(days=1)
        while atual_sem.weekday() >= 5:
            atual_sem += timedelta(days=1)
        data_sem_feriado = atual_sem
    else:
        data_sem_feriado_raw = data_publicacao + timedelta(days=dias)
        while data_sem_feriado_raw.weekday() >= 5:
            data_sem_feriado_raw += timedelta(days=1)
        data_sem_feriado = data_sem_feriado_raw

    return data_com_feriado, data_sem_feriado
