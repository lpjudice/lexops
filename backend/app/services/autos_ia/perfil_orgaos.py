"""D11 — Perfil do Juízo, do Ministério Público e da Administradora Judicial.

Só agrega o que já está no banco (peças, fatos de valores, determinações e posições): quanto cada órgão
atuou, em que tipos de peça, o que determinou/afirmou/defendeu e com que prazos. Nenhuma IA aqui."""
from collections import Counter, defaultdict

from app.models.andamento import AndamentoProcesso
from app.models.autos_ia import AutosIAFato, AutosIAPeca
from app.services.autos_ia import fatos_determinacoes as fdet, fatos_posicoes as fpos, fatos_valores as fv

ORGAOS = [("juizo", "Juízo"), ("mp", "Ministério Público"), ("aj", "Administradora Judicial")]


def _pecas_por_orgao(db, caso_id) -> dict[str, list[dict]]:
    q = (db.query(AutosIAPeca, AndamentoProcesso).outerjoin(AndamentoProcesso, AutosIAPeca.andamento_id == AndamentoProcesso.id)
         .filter(AutosIAPeca.caso_id == caso_id))
    out: dict[str, list[dict]] = defaultdict(list)
    for p, a in q.all():
        tipo_pje = a.tipo if a else None
        if not fv.peca_narrativa(tipo_pje, p.tipo, bool(a and (a.arquivo_nome or a.documento_id or a.arquivo_drive_link)), p.texto_md):
            continue
        chave, _ = fv.afirmante_de(p.autor, p.tipo, tipo_pje)
        if chave in ("juizo", "mp", "aj"):
            d = a.data_andamento if a and a.data_andamento else p.data_peca
            out[chave].append({"peca_id": p.id, "id_processual": p.id_processual, "tipo_pje": tipo_pje or "—", "data": d, "titulo": p.titulo_customizado or p.titulo,
                               "link_pdf": a.arquivo_drive_link if a else None, "link_md": fv._link_md(p.md_drive_file_id)})
    return out


def perfil(db, caso_id) -> dict:
    pecas = _pecas_por_orgao(db, caso_id)
    valores = [fv._fato_dict(*t) for t in fv._linhas_fatos(db, caso_id)]
    posicoes = [fpos._item(*t) for t in fpos._linhas(db, caso_id)]
    ordens = fdet.listar(db, caso_id)["itens"]
    orgaos = []
    for chave, rotulo in ORGAOS:
        ps = sorted(pecas.get(chave, []), key=lambda x: str(x["data"] or ""))
        datas = [p["data"] for p in ps if p["data"]]
        vs = [v for v in valores if v["afirmante_chave"] == chave and v["natureza"] != "irrelevante"]
        top_valores = sorted(vs, key=lambda v: -v["valor_centavos"])[:8]
        pos = [i for i in posicoes if any(h["chave"] == chave for h in i["holders"])]
        por_tema: dict[str, list[dict]] = defaultdict(list)
        for i in sorted(pos, key=lambda i: (i["data"] or "", i["peticao"]["id_processual"] or "")):
            por_tema[i["tema"]].append(i)
        posicoes_tema = [{"tema": t, "tema_rotulo": fpos.TEMA_POS_ROTULO.get(t, t), "atual": its[-1]["posicao"], "atual_rotulo": its[-1]["posicao_rotulo"], "n": len(its),
                          "mudou": len({i["posicao"] for i in its}) > 1, "ultima": its[-1]} for t, its in por_tema.items()]
        bloco = {
            "chave": chave, "rotulo": rotulo, "n_pecas": len(ps), "primeira": str(min(datas)) if datas else None, "ultima": str(max(datas)) if datas else None,
            "tipos": [{"tipo": t, "n": n} for t, n in Counter(p["tipo_pje"] for p in ps).most_common(8)],
            "recentes": list(reversed(ps))[:6],
            "valores": {"n": len(vs), "principais": top_valores},
            "posicoes": posicoes_tema,
        }
        if chave == "juizo":
            prazos = [o["prazo_dias"] for o in ordens if o["prazo_dias"]]
            bloco["ordens"] = {
                "total": len(ordens), "por_destinatario": [{"destinatario": d, "n": n} for d, n in Counter(o["destinatario_rotulo"] for o in ordens).most_common()],
                "prazo_medio_dias": round(sum(prazos) / len(prazos), 1) if prazos else None, "com_prazo": len(prazos),
                "ligadas_a_mediacao": sum(1 for o in ordens if o["ligada_a_mediacao"]), "com_sancao": sum(1 for o in ordens if o["sancao"]),
                "por_status": dict(Counter(o["status"] for o in ordens)),
                "decisoes": len({o["decisao"]["peca_id"] for o in ordens}),
            }
        orgaos.append(bloco)
    return {"orgaos": orgaos}
