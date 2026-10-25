"""Cruzamentos sobre advogados × partes (A1 valor representado, A2 bancas/sobreposição).

Tudo é derivado do que já existe: a relação advogado × parte (só petições, com os ajustes manuais) e o
banco de fatos de valores (cada valor com a peça e o trecho que o sustentam). Nada aqui chama IA e
nenhum número é inventado: o "valor da parte" é um dos valores citados nas peças sobre ela, e o total do
advogado é INDICATIVO (soma de um valor por parte; partes com valor não localizado ficam de fora e são
contadas à parte)."""
import unicodedata
from collections import defaultdict
from itertools import combinations

from app.services.autos_ia import advogados_partes, fatos_valores

# Valores que descrevem "o que a parte tem em jogo" (o seu crédito, aporte ou perda), não o passivo do grupo.
TEMAS_REPRESENTADOS = {"valor_investido_aporte", "credito_ou_divida", "valor_em_risco_prejuizo"}
_STOP = {"de", "da", "do", "das", "dos", "e", "ltda", "sa", "s", "a", "me", "epp", "eireli", "em", "recuperacao", "judicial"}


def _tokens(nome: str | None) -> frozenset[str]:
    t = "".join(c for c in unicodedata.normalize("NFKD", (nome or "").casefold()) if not unicodedata.combining(c))
    return frozenset(w for w in "".join(c if c.isalnum() else " " for c in t).split() if w not in _STOP and len(w) > 1)


def _mesma_entidade(a: frozenset[str], b: frozenset[str]) -> bool:
    """Mesmo conjunto de palavras, ou o nome mais curto (≥ 2 palavras) contido no mais longo."""
    if not a or not b:
        return False
    menor, maior = (a, b) if len(a) <= len(b) else (b, a)
    return menor == maior or (len(menor) >= 2 and menor <= maior)


def valor_da_parte(parte: dict, fatos: list[dict]) -> dict | None:
    """O valor que as peças atribuem à parte: entre os fatos de temas "representados" cujo sujeito é a parte,
    o número citado em mais peças diferentes (empate → o maior). Devolve também quantos valores havia."""
    alvos = [_tokens(parte["nome"])] + [_tokens(v) for v in parte.get("variantes", [])]
    cand = [f for f in fatos if f["tema"] in TEMAS_REPRESENTADOS and f["natureza"] != "irrelevante" and f["status"] != "rejeitado"
            and any(_mesma_entidade(_tokens(f["sujeito_canonico"]), a) for a in alvos)]
    if not cand:
        return None
    por_valor: dict[int, list[dict]] = defaultdict(list)
    for f in cand:
        por_valor[f["valor_centavos"]].append(f)
    melhor = max(por_valor.items(), key=lambda kv: (len({x["peticao"]["peca_id"] for x in kv[1]}), kv[0]))
    fato = sorted(melhor[1], key=lambda x: (x["peticao"]["data"] is None, x["peticao"]["data"] or 0))[0]
    return {"valor_centavos": melhor[0], "valor": fatos_valores.fmt_brl(melhor[0]), "tema_rotulo": fato["tema_rotulo"],
            "n_valores": len(por_valor), "n_pecas": len({x["peticao"]["peca_id"] for x in melhor[1]}),
            "fato_id": fato["id"], "trecho": fato["trecho"], "peticao": fato["peticao"]}


def montar(db, caso_id, min_partes: int = 2, cobertura: float = 0.5) -> dict:
    rel = advogados_partes.montar_relacao(db, caso_id)
    fatos = [fatos_valores._fato_dict(*t) for t in fatos_valores._linhas_fatos(db, caso_id)]
    partes = {p["chave"]: p for p in rel["partes"]}
    valores = {k: valor_da_parte(p, fatos) for k, p in partes.items()}

    advs = []
    por_adv: dict[str, set[str]] = {}
    for a in rel["advogados"]:
        chaves = [p["chave"] for p in a["partes"]]
        por_adv[a["id"]] = set(chaves)
        itens = []
        for p in a["partes"]:
            v = valores.get(p["chave"])
            itens.append({"chave": p["chave"], "nome": p["nome"], "principal": p["principal"],
                          "valor_centavos": v["valor_centavos"] if v else None, "valor": v["valor"] if v else None,
                          "valor_info": v})
        itens.sort(key=lambda x: (x["valor_centavos"] is None, -(x["valor_centavos"] or 0), x["nome"].casefold()))
        total = sum(x["valor_centavos"] or 0 for x in itens)
        advs.append({"id": a["id"], "nome": a["nome"], "oabs": a["oabs"], "n_partes": len(itens),
                     "n_partes_com_valor": sum(1 for x in itens if x["valor_centavos"] is not None),
                     "valor_indicativo_centavos": total, "valor_indicativo": fatos_valores.fmt_brl(total) if total else None,
                     "n_partes_principal": sum(1 for x in itens if x["principal"]), "partes": itens})
    advs.sort(key=lambda a: (-a["valor_indicativo_centavos"], -a["n_partes"], (a["nome"] or a["id"]).casefold()))
    nomes = {a["id"]: a["nome"] for a in rel["advogados"]}

    # A2 — pares que dividem clientes e bancas (componentes ligados por sobreposição relevante)
    pares = []
    for x, y in combinations(sorted(por_adv), 2):
        comum = por_adv[x] & por_adv[y]
        if len(comum) < min_partes:
            continue
        menor = min(len(por_adv[x]), len(por_adv[y]))
        cob = len(comum) / menor
        pares.append({"a": {"id": x, "nome": nomes[x]}, "b": {"id": y, "nome": nomes[y]}, "n_comuns": len(comum),
                      "cobertura": round(cob, 2), "partes": sorted(partes[k]["nome"] for k in comum)})
    pares.sort(key=lambda p: (-p["n_comuns"], -p["cobertura"]))
    pai = {a: a for a in por_adv}

    def raiz(z):
        while pai[z] != z:
            pai[z] = pai[pai[z]]
            z = pai[z]
        return z

    for p in pares:
        if p["cobertura"] >= cobertura:
            pai[raiz(p["a"]["id"])] = raiz(p["b"]["id"])
    grupos: dict[str, list[str]] = defaultdict(list)
    for a in por_adv:
        grupos[raiz(a)].append(a)
    bancas = []
    for membros in grupos.values():
        if len(membros) < 2:
            continue
        ps = set().union(*(por_adv[m] for m in membros))
        v = sum((valores[k] or {}).get("valor_centavos", 0) for k in ps)
        bancas.append({"advogados": [{"id": m, "nome": nomes[m], "n_partes": len(por_adv[m])} for m in sorted(membros, key=lambda m: -len(por_adv[m]))],
                       "partes": sorted(partes[k]["nome"] for k in ps), "n_partes": len(ps), "valor_indicativo_centavos": v,
                       "valor_indicativo": fatos_valores.fmt_brl(v) if v else None})
    bancas.sort(key=lambda b: (-b["n_partes"], -len(b["advogados"])))

    # partes com o mesmo conjunto de advogados (blocos representados em conjunto)
    por_conjunto: dict[frozenset, list[str]] = defaultdict(list)
    for k, p in partes.items():
        ids = frozenset(a["id"] for a in p["advogados"])
        if ids:
            por_conjunto[ids].append(k)
    blocos = [{"advogados": [{"id": i, "nome": nomes.get(i)} for i in sorted(ids)], "partes": sorted(partes[k]["nome"] for k in ks), "n_partes": len(ks)}
              for ids, ks in por_conjunto.items() if len(ks) >= 2]
    blocos.sort(key=lambda b: -b["n_partes"])

    return {
        "resumo": {"advogados": len(advs), "partes": len(partes), "partes_com_valor": sum(1 for v in valores.values() if v),
                   "bancas": len(bancas), "pares": len(pares), "blocos": len(blocos)},
        "advogados": advs, "bancas": bancas, "pares": pares[:200], "blocos": blocos[:100],
    }
