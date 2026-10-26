"""Estrutura do grupo: organograma societário (empresas e participações) × relação de créditos (planilha).

- O organograma vem do PDF vetorial do processo (`organograma_pdf`) e os níveis (Holding, Unidade de Negócio,
  Investimentos, Veículo de Investimento, Projeto/SPE, Operacional) vêm do "Doc. 06 — Lista de empresas".
- A relação de créditos vem da planilha de credores (editável): cada importação é um lote — o ativo é o que
  vale, os anteriores ficam para comparação.
- O elo entre as duas é o CNPJ (só dígitos; a filial 0004 conta na matriz 0001). Tudo é cálculo sobre esses
  dados — sem IA, e cada número da tela remonta à linha da planilha.
"""
import io
import re
import uuid
from collections import defaultdict
from datetime import date, datetime

from app.models.autos_ia import AutosIACredito, AutosIACreditoLote, AutosIAEntidade, AutosIAParticipacao
from app.services.autos_ia import organograma_pdf

NIVEIS = ["Holding", "Unidade de Negócio", "Investimentos", "Veículo de Investimento", "Projeto / SPE", "Operacional"]
_RE_CNPJ = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")


class EstruturaErro(ValueError):
    pass


def so_digitos(v) -> str | None:
    d = re.sub(r"\D", "", str(v or ""))
    return d if len(d) in (11, 14) else (d.zfill(14) if 11 < len(d) < 14 else None)


def fmt_cnpj(d: str | None) -> str | None:
    if not d:
        return None
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return d


def raiz_matriz(d: str | None) -> str | None:
    """Filial → matriz (mesma raiz de 8 dígitos): o CNPJ da matriz é raiz + 0001 + DV; sem recalcular o DV,
    a ligação é feita pela raiz."""
    return d[:8] if d and len(d) == 14 else None


def fmt_brl(centavos: int) -> str:
    neg = centavos < 0
    c = abs(int(centavos))
    s = f"{c // 100:,}".replace(",", ".") + f",{c % 100:02d}"
    return f"{'-' if neg else ''}R$ {s}"


# ── Doc. 06: níveis ─────────────────────────────────────────────────────────

def ler_doc06(texto: str) -> dict[str, dict]:
    """{cnpj_digitos: {nivel, descricao}} a partir do texto da "Lista de empresas e atividades"."""
    out: dict[str, dict] = {}
    marcas = list(_RE_CNPJ.finditer(texto or ""))
    padrao = re.compile(r"\s*(" + "|".join(re.escape(n).replace(r"\ ", r"\s*") for n in sorted(NIVEIS, key=len, reverse=True)) + ")", re.I)
    for i, m in enumerate(marcas):
        resto = texto[m.end(): m.end() + 60]
        n = padrao.match(resto)
        if not n:
            continue
        nivel = next((x for x in NIVEIS if re.sub(r"\s+", "", x).lower() == re.sub(r"\s+", "", n.group(1)).lower()), None)
        ini = m.end() + n.end()
        fim = len(texto)
        if i + 1 < len(marcas):
            fim = texto.rfind("\n", ini, marcas[i + 1].start())
            fim = fim if fim > ini else marcas[i + 1].start()
        desc = re.sub(r"\s+", " ", texto[ini:fim]).strip()
        out[so_digitos(m.group(0))] = {"nivel": nivel, "descricao": desc[:600] or None}
    return out


# ── Organograma ─────────────────────────────────────────────────────────────

def _pct(txt: str | None) -> float | None:
    if not txt:
        return None
    try:
        return round(float(txt.replace("%", "").replace(",", ".")), 4)
    except ValueError:
        return None


def importar_organograma(db, caso_id, pdf_bytes: bytes, doc06_texto: str | None = None) -> dict:
    lido = organograma_pdf.ler(pdf_bytes)
    niveis = ler_doc06(doc06_texto) if doc06_texto else {}
    atuais = {e.cnpj: e for e in db.query(AutosIAEntidade).filter(AutosIAEntidade.caso_id == caso_id)}
    novas = 0
    for n in lido["nos"]:
        c = so_digitos(n["cnpj"])
        info = niveis.get(c, {})
        e = atuais.get(c)
        if e is None:
            e = AutosIAEntidade(caso_id=caso_id, cnpj=c, nome=n["nome"][:255], nivel=info.get("nivel"), descricao=info.get("descricao"), origem="organograma")
            db.add(e)
            atuais[c] = e
            novas += 1
        elif e.origem != "manual":
            e.nome = n["nome"][:255]
            if info:
                e.nivel, e.descricao = info.get("nivel") or e.nivel, info.get("descricao") or e.descricao
    db.flush()
    existentes = {(p.pai_cnpj, p.filho_cnpj): p for p in db.query(AutosIAParticipacao).filter(AutosIAParticipacao.caso_id == caso_id)}
    vistos = set()
    novas_p = 0
    for r in lido["relacoes"]:
        chave = (so_digitos(r["pai"]), so_digitos(r["filho"]))
        vistos.add(chave)
        p = existentes.get(chave)
        if p is None:
            db.add(AutosIAParticipacao(caso_id=caso_id, pai_cnpj=chave[0], filho_cnpj=chave[1], pct=_pct(r["pct"]), tracejado=r["tracejado"], origem="organograma"))
            novas_p += 1
        elif p.status == "extraido" and p.origem == "organograma":
            p.pct, p.tracejado = _pct(r["pct"]), r["tracejado"]
    removidas = 0
    for chave, p in existentes.items():          # sumiu do desenho novo (e ninguém mexeu): sai
        if chave not in vistos and p.origem == "organograma" and p.status == "extraido":
            db.delete(p)
            removidas += 1
    db.commit()
    return {"empresas": len(lido["nos"]), "empresas_novas": novas, "vinculos": len(lido["relacoes"]), "vinculos_novos": novas_p, "vinculos_removidos": removidas,
            "niveis_lidos": len(niveis), "avisos": lido["avisos"]}


# ── Planilha de créditos ────────────────────────────────────────────────────

_COLUNAS = {
    "devedor_cnpj": ["cnpj devedor", "cnpj da devedora", "cnpj do devedor"],
    "devedor_nome": ["razao social devedora", "devedora", "devedor"],
    "credor_nome": ["credor / razao social", "credor", "razao social do credor"],
    "credor_cnpj": ["cpf/cnpj do credor", "cnpj do credor", "cpf/cnpj credor"],
    "credor_endereco": ["endereco completo", "endereco"],
    "credor_email": ["e-mail", "email"],
    "natureza": ["natureza/origem do credito", "natureza", "origem do credito"],
    "classe": ["classe sugerida", "classe"],
    "valor": ["valor na data-base (r$)", "valor na data-base", "valor"],
    "data_base": ["data-base", "data base"],
    "vencimento": ["data de vencimento", "vencimento"],
    "coobrigados": ["coobrigados/fiadores", "coobrigados"],
    "pagina_pdf": ["pagina do pdf", "pagina"],
}


def _norm(s) -> str:
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFKD", str(s or "").casefold()) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip()


def categorizar(natureza: str | None) -> tuple[str, str | None]:
    """(categoria, subcategoria) pela natureza do crédito — regras fixas e conferíveis."""
    n = (natureza or "").strip()
    nl = n.lower()
    par = re.search(r"\(([^)]+)\)\s*$", n)
    sub_par = par.group(1).strip().title() if par else None
    if "intercompany" in nl or "partes relacionadas" in nl:
        return "Intercompany (partes relacionadas)", None
    if "emissão rhino" in nl or "emissao rhino" in nl or "cessão fiduciária" in nl:
        m = re.search(r"(\d+)\s*[ªa]\s*emiss", n)
        return "Emissões Rhino (cessão fiduciária + NP)", (f"{m.group(1)}ª emissão" if m else None)
    if nl.startswith("ccb") or "nota comercial" in nl or "empréstimo bancário" in nl:
        banco = next((b for b in ("Sicoob Sul-Serrano", "Daycoval", "BTG Pactual") if b.lower() in nl), None)
        return "Dívida bancária (CCB / nota comercial)", banco
    if "debênture" in nl or "debenture" in nl:
        return "Debênture Apex conversível", None
    if nl.startswith("m&a") or "earn-out" in nl:
        return "M&A / earn-out", sub_par
    if nl.startswith("fornecedores"):
        return "Fornecedores / custeio", sub_par
    if nl.startswith("pessoal"):
        return "Pessoal (sócio / associado)", sub_par
    if "compromisso de" in nl and ("compra" in nl or "venda" in nl):
        return "Imóveis (compra e venda)", None
    if nl.startswith("ação") or nl.startswith("acao") or "reclamação trabalhista" in nl or "reclamacao trabalhista" in nl:
        return "Ações judiciais", None
    return "Outros", None


def _data(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()
    for f in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], f).date()
        except ValueError:
            pass
    return None


def _centavos(v) -> int:
    if v is None or v == "":
        return 0
    if isinstance(v, (int, float)):
        return int(round(float(v) * 100))
    s = re.sub(r"[^\d,.-]", "", str(v))
    s = s.replace(".", "").replace(",", ".") if "," in s else s
    try:
        return int(round(float(s) * 100))
    except ValueError:
        return 0


def ler_planilha(xlsx_bytes: bytes) -> list[dict]:
    import warnings

    import openpyxl
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True, read_only=True)
    aba = next((ws for ws in wb.worksheets if _norm(ws.title) in ("credores", "relacao de credores")), None) or wb.worksheets[0]
    linhas = aba.iter_rows(values_only=True)
    cab = next(linhas, None)
    if not cab:
        raise EstruturaErro("A planilha está vazia.")
    idx = {}
    nomes = [_norm(c) for c in cab]
    for campo, alternativas in _COLUNAS.items():
        for a in alternativas:
            if a in nomes:
                idx[campo] = nomes.index(a)
                break
    faltam = [c for c in ("devedor_cnpj", "credor_nome", "valor") if c not in idx]
    if faltam:
        raise EstruturaErro("Colunas não encontradas na primeira linha: " + ", ".join(faltam) + ". Esperado: 'CNPJ devedor', 'Credor / razão social' e 'Valor na data-base (R$)'.")
    out = []
    for n, row in enumerate(linhas, start=2):
        if not any(v is not None and str(v).strip() for v in row):
            continue
        g = lambda k: row[idx[k]] if k in idx and idx[k] < len(row) else None
        valor = _centavos(g("valor"))
        if not g("devedor_cnpj") and not g("credor_nome") and not valor:
            continue
        natureza = (str(g("natureza")).strip() if g("natureza") else None)
        cat, sub = categorizar(natureza)
        try:
            pag = int(g("pagina_pdf")) if g("pagina_pdf") not in (None, "") else None
        except (TypeError, ValueError):
            pag = None
        out.append({
            "linha": n, "devedor_cnpj": so_digitos(g("devedor_cnpj")), "devedor_nome": (str(g("devedor_nome")).strip()[:255] if g("devedor_nome") else None),
            "credor_cnpj": so_digitos(g("credor_cnpj")), "credor_nome": (str(g("credor_nome")).strip()[:255] if g("credor_nome") else None),
            "credor_endereco": (str(g("credor_endereco")).strip() if g("credor_endereco") else None), "credor_email": (str(g("credor_email")).strip()[:255] if g("credor_email") else None),
            "natureza": natureza[:400] if natureza else None, "classe": (str(g("classe")).strip()[:60] if g("classe") else None),
            "valor_centavos": valor, "data_base": _data(g("data_base")), "vencimento": _data(g("vencimento")),
            "coobrigados": (None if not g("coobrigados") or _norm(g("coobrigados")) in ("nao aplicavel", "n/a", "-") else str(g("coobrigados")).strip()),
            "pagina_pdf": pag, "categoria": cat, "subcategoria": sub,
        })
    if not out:
        raise EstruturaErro("Nenhuma linha de crédito encontrada.")
    return out


def importar_creditos(db, caso_id, xlsx_bytes: bytes, nome_arquivo: str | None, notas: str | None = None) -> dict:
    linhas = ler_planilha(xlsx_bytes)
    db.query(AutosIACreditoLote).filter(AutosIACreditoLote.caso_id == caso_id).update({"ativo": False})
    lote = AutosIACreditoLote(caso_id=caso_id, nome_arquivo=(nome_arquivo or "")[:255] or None, total_linhas=len(linhas),
                              total_centavos=sum(l["valor_centavos"] for l in linhas), ativo=True, notas=(notas or "").strip() or None)
    db.add(lote)
    db.flush()
    db.bulk_insert_mappings(AutosIACredito, [{"id": uuid.uuid4(), "lote_id": lote.id, "caso_id": caso_id, **l} for l in linhas])
    db.commit()
    return _lote_out(lote)


def _lote_out(l: AutosIACreditoLote) -> dict:
    return {"id": l.id, "nome_arquivo": l.nome_arquivo, "total_linhas": l.total_linhas, "total_centavos": l.total_centavos, "total": fmt_brl(l.total_centavos),
            "ativo": l.ativo, "notas": l.notas, "importado_em": l.importado_em}


def listar_lotes(db, caso_id) -> list[dict]:
    return [_lote_out(l) for l in db.query(AutosIACreditoLote).filter(AutosIACreditoLote.caso_id == caso_id).order_by(AutosIACreditoLote.importado_em.desc())]


def ativar_lote(db, caso_id, lote_id) -> dict:
    l = db.get(AutosIACreditoLote, lote_id)
    if l is None or l.caso_id != caso_id:
        raise EstruturaErro("Importação não encontrada.")
    db.query(AutosIACreditoLote).filter(AutosIACreditoLote.caso_id == caso_id).update({"ativo": False})
    l.ativo = True
    db.commit()
    return _lote_out(l)


def excluir_lote(db, caso_id, lote_id) -> None:
    l = db.get(AutosIACreditoLote, lote_id)
    if l is None or l.caso_id != caso_id:
        raise EstruturaErro("Importação não encontrada.")
    era_ativo = l.ativo
    db.delete(l)
    db.flush()
    if era_ativo:
        ultimo = db.query(AutosIACreditoLote).filter(AutosIACreditoLote.caso_id == caso_id).order_by(AutosIACreditoLote.importado_em.desc()).first()
        if ultimo:
            ultimo.ativo = True
    db.commit()


# ── Consulta ────────────────────────────────────────────────────────────────

def _entidades(db, caso_id) -> dict:
    ents = db.query(AutosIAEntidade).filter(AutosIAEntidade.caso_id == caso_id).all()
    por_cnpj = {e.cnpj: e for e in ents}
    por_raiz = {}
    for e in ents:
        por_raiz.setdefault(raiz_matriz(e.cnpj), e)
    return por_cnpj, por_raiz


def _resolve(por_cnpj, por_raiz, cnpj):
    return por_cnpj.get(cnpj) or (por_raiz.get(raiz_matriz(cnpj)) if cnpj else None)


def creditos(db, caso_id, lote_id=None, hoje: date | None = None) -> list[dict]:
    hoje = hoje or date.today()
    if lote_id is None:
        lote = db.query(AutosIACreditoLote).filter(AutosIACreditoLote.caso_id == caso_id, AutosIACreditoLote.ativo.is_(True)).first()
        if lote is None:
            return []
        lote_id = lote.id
    por_cnpj, por_raiz = _entidades(db, caso_id)
    out = []
    for c in db.query(AutosIACredito).filter(AutosIACredito.caso_id == caso_id, AutosIACredito.lote_id == lote_id).order_by(AutosIACredito.linha):
        dev = _resolve(por_cnpj, por_raiz, c.devedor_cnpj)
        cre = _resolve(por_cnpj, por_raiz, c.credor_cnpj)
        out.append({
            "id": c.id, "linha": c.linha, "devedor_cnpj": c.devedor_cnpj, "devedor_cnpj_fmt": fmt_cnpj(c.devedor_cnpj),
            "devedor": ((dev.nome + (f" — filial {c.devedor_cnpj[8:12]}" if c.devedor_cnpj != dev.cnpj else "") if dev else c.devedor_nome) or "(sem devedora)"), "devedor_cnpj_grupo": dev.cnpj if dev else None,
            "devedor_no_organograma": dev is not None, "nivel_devedor": dev.nivel if dev else None,
            "credor_cnpj": c.credor_cnpj, "credor_cnpj_fmt": fmt_cnpj(c.credor_cnpj), "credor": c.credor_nome or "(sem credor)", "credor_email": c.credor_email, "credor_endereco": c.credor_endereco,
            "credor_cnpj_grupo": cre.cnpj if cre else None, "intragrupo": cre is not None, "nivel_credor": cre.nivel if cre else None,
            "natureza": c.natureza, "classe": c.classe, "categoria": c.categoria or "Outros", "subcategoria": c.subcategoria,
            "valor_centavos": c.valor_centavos, "valor": fmt_brl(c.valor_centavos), "data_base": c.data_base, "vencimento": c.vencimento,
            "vencido": bool(c.vencimento and c.vencimento < hoje), "coobrigados": c.coobrigados, "pagina_pdf": c.pagina_pdf,
        })
    return out


def filtrar(itens: list[dict], f: dict) -> list[dict]:
    def em(v, lista):
        return not lista or v in lista

    q = _norm(f.get("q")) if f.get("q") else None
    cq = _norm(f.get("credor_q")) if f.get("credor_q") else None
    nq = _norm(f.get("natureza_q")) if f.get("natureza_q") else None
    cdig = re.sub(r"\D", "", f.get("credor_q") or "")
    out = []
    for i in itens:
        if not (em(i["categoria"], f.get("categoria")) and em(i["subcategoria"], f.get("subcategoria")) and em(i["classe"], f.get("classe"))
                and (not f.get("devedor") or i["devedor_cnpj"] in f["devedor"] or i["devedor_cnpj_grupo"] in f["devedor"]) and em(i["nivel_devedor"], f.get("nivel_devedor"))):
            continue
        if f.get("credor") and (i["credor_cnpj"] or i["credor"]) not in f["credor"]:
            continue
        if f.get("intragrupo") is not None and i["intragrupo"] != f["intragrupo"]:
            continue
        if f.get("vencidos") is not None and i["vencido"] != f["vencidos"]:
            continue
        if f.get("com_coobrigado") is not None and bool(i["coobrigados"]) != f["com_coobrigado"]:
            continue
        if f.get("no_organograma") is not None and i["devedor_no_organograma"] != f["no_organograma"]:
            continue
        if f.get("valor_min") is not None and i["valor_centavos"] < f["valor_min"]:
            continue
        if f.get("valor_max") is not None and i["valor_centavos"] > f["valor_max"]:
            continue
        if f.get("venc_de") and (not i["vencimento"] or i["vencimento"] < f["venc_de"]):
            continue
        if f.get("venc_ate") and (not i["vencimento"] or i["vencimento"] > f["venc_ate"]):
            continue
        if cq and cq not in _norm(i["credor"]) and not (cdig and cdig in (i["credor_cnpj"] or "")):
            continue
        if nq and nq not in _norm(i["natureza"]):
            continue
        if q and q not in _norm(" ".join(str(x or "") for x in (i["devedor"], i["credor"], i["natureza"], i["categoria"], i["subcategoria"], i["coobrigados"], i["credor_cnpj"], i["devedor_cnpj"]))):
            continue
        out.append(i)
    return out


def _soma(itens) -> int:
    return sum(i["valor_centavos"] for i in itens)


def _quebra(itens: list[dict], chave, rotulo=None, top: int | None = None) -> list[dict]:
    g: dict = defaultdict(lambda: {"n": 0, "valor_centavos": 0})
    for i in itens:
        k = chave(i)
        g[k]["n"] += 1
        g[k]["valor_centavos"] += i["valor_centavos"]
    tot = _soma(itens) or 1
    lista = [{"chave": k, "rotulo": (rotulo(k) if rotulo else k) or "(vazio)", "n": v["n"], "valor_centavos": v["valor_centavos"], "valor": fmt_brl(v["valor_centavos"]),
              "pct": round(100 * v["valor_centavos"] / tot, 2)} for k, v in g.items()]
    lista.sort(key=lambda x: -x["valor_centavos"])
    return lista[:top] if top else lista


def resumo(itens: list[dict]) -> dict:
    nomes_dev = {i["devedor_cnpj"] or "": i["devedor"] for i in itens}
    nomes_cre = {(i["credor_cnpj"] or i["credor"]): i["credor"] for i in itens}
    total = _soma(itens)
    intra = [i for i in itens if i["intragrupo"]]
    return {
        "total_centavos": total, "total": fmt_brl(total), "n": len(itens), "devedoras": len(nomes_dev), "credores": len(nomes_cre),
        "intragrupo": {"n": len(intra), "valor_centavos": _soma(intra), "valor": fmt_brl(_soma(intra)), "pct": round(100 * _soma(intra) / total, 2) if total else 0},
        "vencidos": {"n": sum(1 for i in itens if i["vencido"]), "valor_centavos": _soma([i for i in itens if i["vencido"]])},
        "com_coobrigado": {"n": sum(1 for i in itens if i["coobrigados"]), "valor_centavos": _soma([i for i in itens if i["coobrigados"]])},
        "fora_do_organograma": {"n": sum(1 for i in itens if not i["devedor_no_organograma"]), "valor_centavos": _soma([i for i in itens if not i["devedor_no_organograma"]])},
        "por_categoria": _quebra(itens, lambda i: i["categoria"]),
        "por_classe": _quebra(itens, lambda i: i["classe"] or "(sem classe)"),
        "por_devedora": _quebra(itens, lambda i: i["devedor_cnpj"] or "", lambda k: nomes_dev.get(k), top=25),
        "por_credor": _quebra(itens, lambda i: i["credor_cnpj"] or i["credor"], lambda k: nomes_cre.get(k), top=25),
        "por_nivel_devedora": _quebra(itens, lambda i: i["nivel_devedor"] or "(fora do organograma)"),
        "por_origem": _quebra(itens, lambda i: "Intragrupo" if i["intragrupo"] else "Externo"),
    }


DIMENSOES = {
    "devedora": (lambda i: i["devedor_cnpj"] or "", lambda i: i["devedor"]),
    "credor": (lambda i: i["credor_cnpj"] or i["credor"], lambda i: i["credor"]),
    "categoria": (lambda i: i["categoria"], lambda i: i["categoria"]),
    "subcategoria": (lambda i: i["subcategoria"] or "—", lambda i: i["subcategoria"] or "—"),
    "classe": (lambda i: i["classe"] or "(sem classe)", lambda i: i["classe"] or "(sem classe)"),
    "origem": (lambda i: "Intragrupo" if i["intragrupo"] else "Externo", lambda i: "Intragrupo" if i["intragrupo"] else "Externo"),
    "nivel_devedora": (lambda i: i["nivel_devedor"] or "(fora do organograma)", lambda i: i["nivel_devedor"] or "(fora do organograma)"),
    "vencimento_mes": (lambda i: i["vencimento"].strftime("%Y-%m") if i["vencimento"] else "sem data", lambda i: i["vencimento"].strftime("%m/%Y") if i["vencimento"] else "sem data"),
}


def agrupar(itens: list[dict], linhas: str, colunas: str | None, top_linhas: int = 60, top_colunas: int = 14) -> dict:
    if linhas not in DIMENSOES or (colunas and colunas not in DIMENSOES):
        raise EstruturaErro("Dimensão inválida.")
    kl, rl = DIMENSOES[linhas]
    kc, rc = DIMENSOES[colunas] if colunas else (None, None)
    cel: dict = defaultdict(lambda: defaultdict(lambda: {"n": 0, "v": 0}))
    rot_l, rot_c, tot_l, tot_c = {}, {}, defaultdict(int), defaultdict(int)
    for i in itens:
        a = kl(i)
        b = kc(i) if kc else "total"
        rot_l[a] = rl(i)
        if kc:
            rot_c[b] = rc(i)
        cel[a][b]["n"] += 1
        cel[a][b]["v"] += i["valor_centavos"]
        tot_l[a] += i["valor_centavos"]
        tot_c[b] += i["valor_centavos"]
    ordem_l = sorted(tot_l, key=lambda k: -tot_l[k])
    ordem_c = sorted(tot_c, key=lambda k: -tot_c[k])[:top_colunas] if kc else []
    return {
        "linhas_dim": linhas, "colunas_dim": colunas, "total_centavos": _soma(itens),
        "colunas": [{"chave": c, "rotulo": rot_c[c], "valor_centavos": tot_c[c], "valor": fmt_brl(tot_c[c])} for c in ordem_c],
        "outras_colunas": max(0, len(tot_c) - len(ordem_c)) if kc else 0,
        "linhas": [{"chave": a, "rotulo": rot_l[a], "valor_centavos": tot_l[a], "valor": fmt_brl(tot_l[a]), "n": sum(x["n"] for x in cel[a].values()),
                    "celulas": {c: {"n": cel[a][c]["n"], "valor_centavos": cel[a][c]["v"], "valor": fmt_brl(cel[a][c]["v"])} for c in ordem_c if c in cel[a]}} for a in ordem_l[:top_linhas]],
        "outras_linhas": max(0, len(ordem_l) - top_linhas),
    }


def opcoes(itens: list[dict]) -> dict:
    def distintos(f):
        return sorted({f(i) for i in itens if f(i)})
    return {
        "categorias": distintos(lambda i: i["categoria"]), "subcategorias": distintos(lambda i: i["subcategoria"]), "classes": distintos(lambda i: i["classe"]),
        "niveis": distintos(lambda i: i["nivel_devedor"]),
        "devedoras": [{"chave": k, "rotulo": v} for k, v in sorted({(i["devedor_cnpj"] or ""): i["devedor"] for i in itens}.items(), key=lambda t: t[1].casefold())],
        "credores": [{"chave": k, "rotulo": v} for k, v in sorted({(i["credor_cnpj"] or i["credor"]): i["credor"] for i in itens}.items(), key=lambda t: t[1].casefold())][:1500],
    }


# ── Organograma + dívidas ───────────────────────────────────────────────────

def organograma(db, caso_id, lote_id=None) -> dict:
    ents = db.query(AutosIAEntidade).filter(AutosIAEntidade.caso_id == caso_id).all()
    parts = db.query(AutosIAParticipacao).filter(AutosIAParticipacao.caso_id == caso_id, AutosIAParticipacao.status != "rejeitado").all()
    cr = creditos(db, caso_id, lote_id)
    deve: dict[str, int] = defaultdict(int)
    n_deve: dict[str, int] = defaultdict(int)
    a_receber: dict[str, int] = defaultdict(int)
    intra_deve: dict[str, int] = defaultdict(int)
    arestas: dict[tuple, dict] = {}
    for c in cr:
        d = c["devedor_cnpj_grupo"]
        if d:
            deve[d] += c["valor_centavos"]
            n_deve[d] += 1
        if c["credor_cnpj_grupo"]:
            a_receber[c["credor_cnpj_grupo"]] += c["valor_centavos"]
        if d and c["credor_cnpj_grupo"]:
            intra_deve[d] += c["valor_centavos"]
            e = arestas.setdefault((d, c["credor_cnpj_grupo"]), {"devedora": d, "credora": c["credor_cnpj_grupo"], "valor_centavos": 0, "n": 0, "categorias": defaultdict(int)})
            e["valor_centavos"] += c["valor_centavos"]
            e["n"] += 1
            e["categorias"][c["categoria"]] += c["valor_centavos"]
    filhos_de = defaultdict(int)
    pais_de = defaultdict(list)
    for p in parts:
        filhos_de[p.pai_cnpj] += 1
        pais_de[p.filho_cnpj].append(p)
    sem_pai = [e.cnpj for e in ents if e.cnpj not in pais_de]
    cnpjs = {e.cnpj for e in ents}
    return {
        "resumo": {"empresas": len(ents), "vinculos": len(parts), "raizes": len(sem_pai), "com_divida": len(deve), "intragrupo_total_centavos": sum(e["valor_centavos"] for e in arestas.values()),
                   "devedoras_fora_do_organograma": len({c["devedor_cnpj"] for c in cr if not c["devedor_no_organograma"] and c["devedor_cnpj"]})},
        "empresas": [{
            "cnpj": e.cnpj, "cnpj_fmt": fmt_cnpj(e.cnpj), "nome": e.nome, "nivel": e.nivel, "descricao": e.descricao, "origem": e.origem, "n_filhos": filhos_de.get(e.cnpj, 0),
            "deve_centavos": deve.get(e.cnpj, 0), "n_creditos": n_deve.get(e.cnpj, 0), "a_receber_centavos": a_receber.get(e.cnpj, 0), "intragrupo_deve_centavos": intra_deve.get(e.cnpj, 0),
        } for e in sorted(ents, key=lambda e: e.nome.casefold())],
        "participacoes": [{"id": p.id, "pai": p.pai_cnpj, "filho": p.filho_cnpj, "pct": float(p.pct) if p.pct is not None else None, "tracejado": p.tracejado, "status": p.status, "nota": p.nota, "origem": p.origem}
                          for p in parts if p.pai_cnpj in cnpjs and p.filho_cnpj in cnpjs],
        "dividas_intragrupo": sorted(({**e, "valor": fmt_brl(e["valor_centavos"]), "categorias": [{"categoria": k, "valor_centavos": v, "valor": fmt_brl(v)} for k, v in sorted(e["categorias"].items(), key=lambda kv: -kv[1])]}
                                      for e in arestas.values()), key=lambda e: -e["valor_centavos"]),
        "niveis": NIVEIS,
    }


def atualizar_participacao(db, caso_id, part_id, pct=None, pct_definido=False, status=None, nota=None, nota_definida=False) -> dict:
    p = db.get(AutosIAParticipacao, part_id)
    if p is None or p.caso_id != caso_id:
        raise EstruturaErro("Vínculo não encontrado.")
    if pct_definido:
        if pct is not None and not 0 <= pct <= 100:
            raise EstruturaErro("O percentual deve ficar entre 0 e 100.")
        p.pct = pct
        p.status = "validado"
    if status is not None:
        if status not in ("extraido", "validado", "rejeitado"):
            raise EstruturaErro("Status inválido.")
        p.status = status
    if nota_definida:
        p.nota = (nota or "").strip() or None
    db.commit()
    return {"id": p.id, "pai": p.pai_cnpj, "filho": p.filho_cnpj, "pct": float(p.pct) if p.pct is not None else None, "tracejado": p.tracejado, "status": p.status, "nota": p.nota, "origem": p.origem}


def criar_participacao(db, caso_id, pai: str, filho: str, pct: float | None, tracejado: bool = False) -> dict:
    pai, filho = so_digitos(pai), so_digitos(filho)
    ents = {e.cnpj for e in db.query(AutosIAEntidade).filter(AutosIAEntidade.caso_id == caso_id)}
    if pai not in ents or filho not in ents:
        raise EstruturaErro("As duas empresas precisam estar no organograma.")
    if pai == filho:
        raise EstruturaErro("Uma empresa não pode deter a si mesma.")
    if pct is not None and not 0 <= pct <= 100:
        raise EstruturaErro("O percentual deve ficar entre 0 e 100.")
    ja = db.query(AutosIAParticipacao).filter(AutosIAParticipacao.caso_id == caso_id, AutosIAParticipacao.pai_cnpj == pai, AutosIAParticipacao.filho_cnpj == filho).first()
    if ja:
        raise EstruturaErro("Esse vínculo já existe.")
    p = AutosIAParticipacao(caso_id=caso_id, pai_cnpj=pai, filho_cnpj=filho, pct=pct, tracejado=tracejado, origem="manual", status="validado")
    db.add(p)
    db.commit()
    return {"id": p.id, "pai": pai, "filho": filho, "pct": pct, "tracejado": tracejado, "status": p.status, "nota": None, "origem": "manual"}


def atualizar_entidade(db, caso_id, cnpj: str, nome=None, nivel=None, nivel_definido=False) -> dict:
    e = db.query(AutosIAEntidade).filter(AutosIAEntidade.caso_id == caso_id, AutosIAEntidade.cnpj == so_digitos(cnpj)).first()
    if e is None:
        raise EstruturaErro("Empresa não encontrada.")
    if nome is not None:
        n = re.sub(r"\s+", " ", nome).strip()
        if not n:
            raise EstruturaErro("Informe o nome.")
        e.nome = n[:255]
        e.origem = "manual"
    if nivel_definido:
        if nivel is not None and nivel not in NIVEIS:
            raise EstruturaErro("Nível inválido.")
        e.nivel = nivel
        e.origem = "manual"
    db.commit()
    return {"cnpj": e.cnpj, "nome": e.nome, "nivel": e.nivel}
