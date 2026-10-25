"""B6 — Cenários de recuperação: planilha editável de ativos × passivos.

Cada linha tem um valor (em centavos), um percentual (de REALIZAÇÃO, nos ativos — quanto se espera
realizar; de RECONHECIMENTO, nos passivos — quanto do crédito se admite) e, opcionalmente, a ligação com o
fato de origem (para o número ter fonte clicável). O resultado é uma conta simples e transparente:
ativo realizável, passivo reconhecido, cobertura e o que sobra/falta; nenhuma premissa é da IA."""
import re
import uuid

from app.models.autos_ia import AutosIACenario, AutosIAFato
from app.services.autos_ia import fatos_valores as fv

LADOS = ("ativo", "passivo")
MAX_LINHAS = 200


class CenarioErro(ValueError):
    pass


def _centavos(v) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise CenarioErro("Valor inválido.")
    if n < 0 or n > 10**15:
        raise CenarioErro("Valor fora do intervalo.")
    return n


def _pct(v) -> float:
    try:
        p = float(v)
    except (TypeError, ValueError):
        raise CenarioErro("Percentual inválido.")
    if not 0 <= p <= 100:
        raise CenarioErro("O percentual deve ficar entre 0 e 100.")
    return round(p, 2)


def normalizar_linhas(linhas: list[dict]) -> list[dict]:
    if len(linhas) > MAX_LINHAS:
        raise CenarioErro(f"No máximo {MAX_LINHAS} linhas por cenário.")
    out = []
    for l in linhas:
        lado = l.get("lado")
        if lado not in LADOS:
            raise CenarioErro("Cada linha precisa ser 'ativo' ou 'passivo'.")
        rotulo = re.sub(r"\s+", " ", str(l.get("rotulo") or "")).strip()[:200]
        if not rotulo:
            raise CenarioErro("Cada linha precisa de um rótulo.")
        fato = l.get("fato_id")
        try:
            fato = str(uuid.UUID(str(fato))) if fato else None
        except ValueError:
            fato = None
        out.append({"id": str(l.get("id") or uuid.uuid4()), "lado": lado, "rotulo": rotulo, "valor_centavos": _centavos(l.get("valor_centavos")),
                    "percentual": _pct(100 if l.get("percentual") is None else l.get("percentual")), "fato_id": fato,
                    "nota": (str(l["nota"]).strip()[:300] or None) if l.get("nota") else None})
    return out


def calcular(linhas: list[dict]) -> dict:
    ativo = sum(round(l["valor_centavos"] * l["percentual"] / 100) for l in linhas if l["lado"] == "ativo")
    passivo = sum(round(l["valor_centavos"] * l["percentual"] / 100) for l in linhas if l["lado"] == "passivo")
    bruto_a = sum(l["valor_centavos"] for l in linhas if l["lado"] == "ativo")
    bruto_p = sum(l["valor_centavos"] for l in linhas if l["lado"] == "passivo")
    cobertura = round(ativo / passivo, 4) if passivo else None
    return {
        "ativo_bruto_centavos": bruto_a, "passivo_bruto_centavos": bruto_p, "ativo_realizavel_centavos": ativo, "passivo_reconhecido_centavos": passivo,
        "saldo_centavos": ativo - passivo, "cobertura": cobertura,
        # quanto cada R$ 1 de crédito reconhecido receberia se o ativo realizável fosse rateado (teto: 100%)
        "recuperacao_por_real": round(min(1.0, cobertura), 4) if cobertura is not None else None,
    }


def _out(c: AutosIACenario, fatos: dict | None = None) -> dict:
    linhas = list(c.linhas or [])
    if fatos is not None:
        for l in linhas:
            f = fatos.get(l.get("fato_id"))
            l["fonte"] = f
    return {"id": c.id, "nome": c.nome, "notas": c.notas, "linhas": linhas, "resultado": calcular(linhas),
            "criado_em": c.criado_em, "atualizado_em": c.atualizado_em}


def _fontes(db, caso_id, cenarios) -> dict:
    from app.models.andamento import AndamentoProcesso
    from app.models.autos_ia import AutosIAPeca
    ids = {uuid.UUID(l["fato_id"]) for c in cenarios for l in (c.linhas or []) if l.get("fato_id")}
    if not ids:
        return {}
    rows = (db.query(AutosIAFato, AutosIAPeca, AndamentoProcesso).join(AutosIAPeca, AutosIAFato.peca_id == AutosIAPeca.id)
            .outerjoin(AndamentoProcesso, AutosIAPeca.andamento_id == AndamentoProcesso.id)
            .filter(AutosIAFato.caso_id == caso_id, AutosIAFato.id.in_(ids)).all())
    out = {}
    for t in rows:
        f = fv._fato_dict(*t)
        out[str(f["id"])] = {"id_processual": f["peticao"]["id_processual"], "link_pdf": f["peticao"]["link_pdf"], "link_md": f["peticao"]["link_md"],
                             "peca_id": f["peticao"]["peca_id"], "data": f["peticao"]["data"], "titulo": f["peticao"]["titulo"], "trecho": f["trecho"],
                             "afirmante": f["afirmante"], "valor": f["valor"]}
    return out


def listar(db, caso_id) -> list[dict]:
    cs = db.query(AutosIACenario).filter(AutosIACenario.caso_id == caso_id).order_by(AutosIACenario.criado_em.asc()).all()
    fontes = _fontes(db, caso_id, cs)
    return [_out(c, fontes) for c in cs]


def _get(db, caso_id, cenario_id) -> AutosIACenario:
    c = db.get(AutosIACenario, cenario_id)
    if c is None or c.caso_id != caso_id:
        raise CenarioErro("Cenário não encontrado.")
    return c


def _nome(n: str | None) -> str:
    n = re.sub(r"\s+", " ", n or "").strip()[:160]
    if not n:
        raise CenarioErro("Dê um nome ao cenário.")
    return n


def criar(db, caso_id, nome: str, linhas: list[dict] | None = None, notas: str | None = None) -> dict:
    c = AutosIACenario(caso_id=caso_id, nome=_nome(nome), notas=(notas or "").strip() or None, linhas=normalizar_linhas(linhas or []))
    db.add(c)
    db.commit()
    db.refresh(c)
    return _out(c, _fontes(db, caso_id, [c]))


def atualizar(db, caso_id, cenario_id, nome=None, notas=None, notas_definida=False, linhas=None) -> dict:
    c = _get(db, caso_id, cenario_id)
    if nome is not None:
        c.nome = _nome(nome)
    if notas_definida:
        c.notas = (notas or "").strip() or None
    if linhas is not None:
        c.linhas = normalizar_linhas(linhas)
    db.commit()
    db.refresh(c)
    return _out(c, _fontes(db, caso_id, [c]))


def duplicar(db, caso_id, cenario_id) -> dict:
    c = _get(db, caso_id, cenario_id)
    novas = [{**l, "id": str(uuid.uuid4())} for l in (c.linhas or [])]
    return criar(db, caso_id, f"{c.nome} (cópia)"[:160], novas, c.notas)


def excluir(db, caso_id, cenario_id) -> None:
    db.delete(_get(db, caso_id, cenario_id))
    db.commit()


def sugestoes(db, caso_id, q: str | None = None, limite: int = 60) -> list[dict]:
    """Valores do banco de fatos que podem virar linha de cenário (ativo/caixa/passivo/dívida/PL), do maior para o menor."""
    from app.services.autos_ia.mapa_entidades import MEDIDAS
    lado = {k: l for k, _, l in MEDIDAS}
    rot = {k: r for k, r, _ in MEDIDAS}
    itens = []
    for t in fv._linhas_fatos(db, caso_id):
        f = fv._fato_dict(*t)
        if f["tema"] not in lado or lado[f["tema"]] not in ("ativo", "passivo") or f["natureza"] == "irrelevante":
            continue
        nome = f["sujeito_canonico"] or "(sem sujeito)"
        if q and q.lower() not in f"{nome} {rot[f['tema']]} {f['afirmante']}".lower():
            continue
        itens.append({"fato_id": f["id"], "lado": lado[f["tema"]], "rotulo": f"{nome} — {rot[f['tema']]}", "valor_centavos": f["valor_centavos"], "valor": f["valor"],
                      "afirmante": f["afirmante"], "peticao": f["peticao"]})
    itens.sort(key=lambda i: -i["valor_centavos"])
    return itens[:limite]
