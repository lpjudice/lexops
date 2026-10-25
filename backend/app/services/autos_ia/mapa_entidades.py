"""B4 — Mapa de entidades: ativo × passivo por entidade (e do grupo), a partir do banco de fatos de valores.

Nada é inventado nem recalculado pela IA: cada célula é o valor mais sustentado pelas peças para aquele
sujeito e aquela medida (o citado em mais peças diferentes; empate → o mais recente), com as alternativas
e as peças/trechos que sustentam cada uma. O "saldo" (ativo − passivo) só é calculado quando os dois
números existem e é sinalizado como INDICATIVO — vindos de fontes ou datas diferentes, não são um balanço."""
import re
from collections import defaultdict

from app.services.autos_ia import fatos_valores as fv

MEDIDAS = [
    ("ativo_total", "Ativo", "ativo"), ("caixa_ou_saldo", "Caixa / saldo", "ativo"), ("ativos_sob_custodia", "Sob custódia", "outro"),
    ("passivo_total", "Passivo total", "passivo"), ("endividamento_bruto", "Endividamento bruto", "passivo"),
    ("divida_liquida", "Dívida líquida", "passivo"), ("passivo_bancario", "Dívida bancária", "passivo"),
    ("passivo_debentures", "Debêntures", "passivo"), ("passivo_cashback", "Cashback / recompra", "passivo"),
    ("passivo_tributario", "Tributário", "passivo"), ("passivo_concursal", "Concursal", "passivo"),
    ("patrimonio_liquido", "Patrimônio líquido", "pl"),
]
_RE_GRUPO = re.compile(r"(?i)\b(grupo|consolidad\w*|requerentes?|conglomerado|sociedades do grupo)\b")
_TEMAS = {m[0] for m in MEDIDAS}


def _escolher(fatos: list[dict]) -> tuple[list[dict], dict]:
    """Agrupa valores próximos; devolve (grupos ordenados por sustentação, grupo principal)."""
    clusters = fv._clusters([f["valor_centavos"] for f in fatos])
    grupos = []
    for cl in clusters:
        membros = [f for f in fatos if f["valor_centavos"] in cl]
        pecas = {m["peticao"]["peca_id"] for m in membros}
        datas = [m["peticao"]["data"] for m in membros if m["peticao"]["data"]]
        valor = cl[0] if len(cl) == 1 else int(sum(cl) / len(cl))
        grupos.append({
            "valor_centavos": valor, "valor": fv.fmt_brl(valor), "n_pecas": len(pecas), "n_fatos": len(membros),
            "afirmantes": sorted({m["afirmante"] for m in membros}),
            "data_mais_recente": str(max(datas)) if datas else None,
            "fatos": sorted(membros, key=lambda m: (m["peticao"]["data"] is None, m["peticao"]["data"] or 0)),
        })
    grupos.sort(key=lambda g: (g["n_pecas"], g["data_mais_recente"] or ""), reverse=True)
    return grupos, grupos[0]


def mapa(db, caso_id) -> dict:
    fatos = [fv._fato_dict(*t) for t in fv._linhas_fatos(db, caso_id)]
    por_ent: dict[str, dict] = {}
    for f in fatos:
        if f["tema"] not in _TEMAS or f["natureza"] == "irrelevante":
            continue
        nome = f["sujeito_canonico"] or "(sem sujeito)"
        ck = fv.chave_sujeito(nome) or "sem sujeito"
        e = por_ent.setdefault(ck, {"chave": ck, "nomes": defaultdict(int), "por_medida": defaultdict(list)})
        e["nomes"][nome] += 1
        e["por_medida"][f["tema"]].append(f)
    entidades = []
    for ck, e in por_ent.items():
        nome = max(e["nomes"].items(), key=lambda kv: kv[1])[0]
        celulas = {}
        for tema, lista in e["por_medida"].items():
            grupos, principal = _escolher(lista)
            celulas[tema] = {"principal": principal, "alternativas": grupos[1:], "n_valores": len(grupos)}
        ativo = celulas.get("ativo_total", {}).get("principal")
        passivo = celulas.get("passivo_total", {}).get("principal")
        saldo = None
        if ativo and passivo:
            dif = ativo["valor_centavos"] - passivo["valor_centavos"]
            mesma_fonte = bool(set(ativo["afirmantes"]) & set(passivo["afirmantes"]))
            saldo = {"valor_centavos": dif, "valor": fv.fmt_brl(abs(dif)), "negativo": dif < 0, "cobertura": round(ativo["valor_centavos"] / passivo["valor_centavos"], 2) if passivo["valor_centavos"] else None,
                     "mesma_fonte": mesma_fonte}
        maior = max((c["principal"]["valor_centavos"] for c in celulas.values()), default=0)
        entidades.append({"chave": ck, "nome": nome, "variantes": sorted(set(e["nomes"]) - {nome}), "grupo": bool(_RE_GRUPO.search(nome)),
                          "celulas": celulas, "saldo": saldo, "maior_valor": maior, "n_fatos": sum(len(v) for v in e["por_medida"].values())})
    entidades.sort(key=lambda x: (not x["grupo"], not (x["saldo"] is not None), -x["maior_valor"]))
    return {
        "resumo": {"entidades": len(entidades), "com_ativo_e_passivo": sum(1 for x in entidades if x["saldo"]), "grupos": sum(1 for x in entidades if x["grupo"]),
                   "saldo_negativo": sum(1 for x in entidades if x["saldo"] and x["saldo"]["negativo"])},
        "medidas": [{"chave": k, "rotulo": r, "lado": l} for k, r, l in MEDIDAS], "entidades": entidades,
    }
