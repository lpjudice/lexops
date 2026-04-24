"""
Seed de feriados nacionais e estaduais (ES, SP, AM, RJ).
Feriados recorrentes são armazenados com ano=2000 como referência;
o motor de cálculo usa apenas mês e dia para feriados recorrentes.
"""

FERIADOS_SEED = [
    # ── NACIONAIS ──────────────────────────────────────────────────────────
    {"data": "2000-01-01", "nome": "Confraternização Universal",         "estado": "nacional", "recorrente": True},
    {"data": "2000-04-21", "nome": "Tiradentes",                          "estado": "nacional", "recorrente": True},
    {"data": "2000-05-01", "nome": "Dia do Trabalho",                     "estado": "nacional", "recorrente": True},
    {"data": "2000-09-07", "nome": "Independência do Brasil",             "estado": "nacional", "recorrente": True},
    {"data": "2000-10-12", "nome": "Nossa Senhora Aparecida",             "estado": "nacional", "recorrente": True},
    {"data": "2000-11-02", "nome": "Finados",                             "estado": "nacional", "recorrente": True},
    {"data": "2000-11-15", "nome": "Proclamação da República",            "estado": "nacional", "recorrente": True},
    {"data": "2000-11-20", "nome": "Consciência Negra",                   "estado": "nacional", "recorrente": True},
    {"data": "2000-12-25", "nome": "Natal",                               "estado": "nacional", "recorrente": True},
    # Páscoa e Carnaval são móveis — calculados dinamicamente no motor
    # ── ESPÍRITO SANTO ─────────────────────────────────────────────────────
    {"data": "2000-10-28", "nome": "Dia do Servidor Público (ES)",        "estado": "ES",       "recorrente": True},
    # Vitória
    {"data": "2000-09-08", "nome": "Nossa Senhora da Vitória",            "estado": "ES",       "recorrente": True},
    # ── SÃO PAULO ──────────────────────────────────────────────────────────
    {"data": "2000-01-25", "nome": "Aniversário de São Paulo",            "estado": "SP",       "recorrente": True},
    {"data": "2000-07-09", "nome": "Revolução Constitucionalista",        "estado": "SP",       "recorrente": True},
    {"data": "2000-11-20", "nome": "Consciência Negra (SP)",              "estado": "SP",       "recorrente": True},
    # ── AMAZONAS ───────────────────────────────────────────────────────────
    {"data": "2000-09-05", "nome": "Elevação do AM à categoria de Estado","estado": "AM",       "recorrente": True},
    {"data": "2000-11-20", "nome": "Consciência Negra (AM)",              "estado": "AM",       "recorrente": True},
    # Manaus
    {"data": "2000-10-24", "nome": "Aniversário de Manaus",               "estado": "AM",       "recorrente": True},
    # ── RIO DE JANEIRO ─────────────────────────────────────────────────────
    {"data": "2000-01-20", "nome": "Dia de São Sebastião (RJ)",           "estado": "RJ",       "recorrente": True},
    {"data": "2000-04-23", "nome": "Dia de São Jorge (RJ)",               "estado": "RJ",       "recorrente": True},
    {"data": "2000-11-20", "nome": "Consciência Negra (RJ)",              "estado": "RJ",       "recorrente": True},
    {"data": "2000-10-28", "nome": "Dia do Servidor Público (RJ)",        "estado": "RJ",       "recorrente": True},
    # ── PÁSCOA / CARNAVAL FIXADOS PARA ANOS CORRENTES (não-recorrentes) ───
    # 2024
    {"data": "2024-02-12", "nome": "Carnaval (segunda)",  "estado": "nacional", "recorrente": False},
    {"data": "2024-02-13", "nome": "Carnaval (terça)",    "estado": "nacional", "recorrente": False},
    {"data": "2024-03-29", "nome": "Sexta-Feira Santa",   "estado": "nacional", "recorrente": False},
    {"data": "2024-03-31", "nome": "Páscoa",              "estado": "nacional", "recorrente": False},
    {"data": "2024-05-30", "nome": "Corpus Christi",      "estado": "nacional", "recorrente": False},
    # 2025
    {"data": "2025-03-03", "nome": "Carnaval (segunda)",  "estado": "nacional", "recorrente": False},
    {"data": "2025-03-04", "nome": "Carnaval (terça)",    "estado": "nacional", "recorrente": False},
    {"data": "2025-04-18", "nome": "Sexta-Feira Santa",   "estado": "nacional", "recorrente": False},
    {"data": "2025-04-20", "nome": "Páscoa",              "estado": "nacional", "recorrente": False},
    {"data": "2025-06-19", "nome": "Corpus Christi",      "estado": "nacional", "recorrente": False},
    # 2026
    {"data": "2026-02-16", "nome": "Carnaval (segunda)",  "estado": "nacional", "recorrente": False},
    {"data": "2026-02-17", "nome": "Carnaval (terça)",    "estado": "nacional", "recorrente": False},
    {"data": "2026-04-03", "nome": "Sexta-Feira Santa",   "estado": "nacional", "recorrente": False},
    {"data": "2026-04-05", "nome": "Páscoa",              "estado": "nacional", "recorrente": False},
    {"data": "2026-06-04", "nome": "Corpus Christi",      "estado": "nacional", "recorrente": False},
    # 2027
    {"data": "2027-02-08", "nome": "Carnaval (segunda)",  "estado": "nacional", "recorrente": False},
    {"data": "2027-02-09", "nome": "Carnaval (terça)",    "estado": "nacional", "recorrente": False},
    {"data": "2027-03-26", "nome": "Sexta-Feira Santa",   "estado": "nacional", "recorrente": False},
    {"data": "2027-03-28", "nome": "Páscoa",              "estado": "nacional", "recorrente": False},
    {"data": "2027-05-27", "nome": "Corpus Christi",      "estado": "nacional", "recorrente": False},
]
