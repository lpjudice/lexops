"""Banco de fatos — POSIÇÕES de cada parte (e do Juízo, MP e Administrador Judicial) por tema.

Alimenta três cruzamentos:
- C7 matriz de posições: quem é a favor/contra/condiciona cada tema (mediação, consolidação, afastamento…);
- C8 linha do tempo de contradições: a mesma parte, no mesmo tema, mudando de posição entre peças;
- A3 conflitos ocultos: o MESMO advogado representando partes com posições opostas no mesmo tema.

Regras: a IA registra só posições que o AUTOR da peça assume de forma expressa (nada inferido, nada atribuído
a terceiros), cada uma com resumo e trecho literal; a pessoa valida, corrige ou rejeita. Uma peça que não
declara posição vira um marcador "lida, sem posições" para não ser relida (e paga) de novo.
"""
import hashlib
import logging
import re
import threading
import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy import func

from app.database import SessionLocal
from app.models.andamento import AndamentoProcesso
from app.models.autos_ia import AutosIACaso, AutosIAFato, AutosIAPeca
from app.services.autos_ia import advogados_partes
from app.services.autos_ia.advogados_partes import normalizar_partes
from app.services.autos_ia.fatos_valores import MODELO, _cliente, _link_md, _tool_input, afirmante_de, peca_narrativa
from app.services.autos_ia.precos import calcular_custo_usd

logger = logging.getLogger(__name__)

TIPO_FATO = "posicao"
TEMAS_POS = ["mediacao", "consolidacao_processual_substancial", "afastamento_ou_fiscalizacao_gestores", "protecao_patrimonial_stay",
             "valores_e_passivo", "legitimidade_e_representacao", "competencia_do_juizo", "atuacao_da_administradora_judicial",
             "plano_ou_proposta_de_pagamento", "prova_e_pericia", "sigilo", "outro"]
TEMA_POS_ROTULO = {
    "mediacao": "Mediação", "consolidacao_processual_substancial": "Consolidação processual / substancial",
    "afastamento_ou_fiscalizacao_gestores": "Afastamento / fiscalização dos gestores",
    "protecao_patrimonial_stay": "Proteção patrimonial / suspensão de execuções", "valores_e_passivo": "Valores e passivo",
    "legitimidade_e_representacao": "Legitimidade e representação", "competencia_do_juizo": "Competência do Juízo",
    "atuacao_da_administradora_judicial": "Atuação da Administradora Judicial", "plano_ou_proposta_de_pagamento": "Plano / proposta de pagamento",
    "prova_e_pericia": "Prova e perícia", "sigilo": "Sigilo", "outro": "Outro",
}
POSICOES = ["favoravel", "contraria", "condicionada", "neutra"]
POSICAO_ROTULO = {"favoravel": "Favorável", "contraria": "Contrária", "condicionada": "Condicionada", "neutra": "Neutra"}
STATUS = {"extraido", "validado", "rejeitado"}
_TEXTO_MIN = 800
_TEXTO_MAX = 150_000
_PARALELO = 3
_ORDEM_TIPO = {"juizo": 0, "mp": 1, "aj": 2, "parte": 3}

TOOL_POS = {
    "name": "registrar_posicoes",
    "description": "Registra as posições que o AUTOR da peça assume de forma expressa, por tema.",
    "input_schema": {
        "type": "object",
        "properties": {"posicoes": {"type": "array", "maxItems": 10, "items": {"type": "object", "properties": {
            "tema": {"type": "string", "enum": TEMAS_POS},
            "posicao": {"type": "string", "enum": POSICOES,
                        "description": "favoravel = apoia/pede/aceita; contraria = rejeita/impugna/se opõe; condicionada = aceita sob condição "
                                       "expressa; neutra = declara não se opor nem apoiar ou apenas submete ao Juízo."},
            "resumo": {"type": "string", "description": "A posição em uma frase objetiva (máx. 220 caracteres)."},
            "pede": {"type": ["string", "null"], "description": "O que requer em concreto sobre o tema, se requer (máx. 200 caracteres)."},
            "trecho": {"type": "string", "description": "Trecho LITERAL da peça que sustenta (máx. 250 caracteres)."},
            "confianca": {"type": "number"},
        }, "required": ["tema", "posicao", "resumo", "trecho"]}}},
        "required": ["posicoes"],
    },
}
SISTEMA_POS = (
    "Você é um advogado que mapeia, numa recuperação judicial de grupo econômico, a POSIÇÃO que cada participante assume "
    "sobre os temas do processo — para entender quem apoia, quem se opõe e quem condiciona. Registre SOMENTE posições que o "
    "AUTOR da peça (quem a assina/peticiona; numa decisão, o Juízo; num parecer, o MP ou a Administradora Judicial) assume de "
    "forma expressa e que sejam relevantes ao processo. Não registre argumentos de terceiros citados na peça, nem o que você "
    "deduz. Se a peça não toma posição sobre nenhum dos temas, devolva a lista vazia. Seja conciso; copie o trecho literalmente."
)


def _hash_texto(t: str) -> str:
    return hashlib.sha256((t or "").encode("utf-8")).hexdigest()


def peca_elegivel(tipo_pje, tipo_ia, tem_arquivo, texto) -> bool:
    return len((texto or "").strip()) >= _TEXTO_MIN and peca_narrativa(tipo_pje, tipo_ia, tem_arquivo, texto)


def holders_da_peca(autor: str | None, tipo_ia: str | None, tipo_pje: str | None) -> list[dict]:
    """Quem assume a posição: Juízo/MP/AJ (um só) ou as partes do peticionante (cada uma é um participante)."""
    chave, rotulo = afirmante_de(autor, tipo_ia, tipo_pje)
    if chave in ("juizo", "mp", "aj"):
        return [{"chave": chave, "nome": rotulo, "tipo": chave}]
    partes = normalizar_partes(autor)
    if partes:
        return [{"chave": c, "nome": n, "tipo": "parte"} for c, n in partes]
    return [{"chave": chave, "nome": rotulo, "tipo": "parte"}]


def extrair_posicoes_peca(info: dict, texto: str, cliente=None) -> tuple[list[dict], float]:
    cliente = cliente or _cliente()
    prompt = (f"Peça: ID {info.get('id_processual') or 's/ ID'} · tipo no PJe: {info.get('tipo_pje') or '—'} · "
              f"autor/peticionante: {info.get('autor') or '—'} · data: {info.get('data') or '—'}.\n\nTexto integral:\n\n{texto[:_TEXTO_MAX]}")
    resp = cliente.messages.create(
        model=MODELO, max_tokens=8000, system=SISTEMA_POS, tools=[TOOL_POS],
        tool_choice={"type": "tool", "name": "registrar_posicoes"},
        messages=[{"role": "user", "content": prompt}],
    )
    custo = calcular_custo_usd(resp.usage.input_tokens, resp.usage.output_tokens)
    if getattr(resp, "stop_reason", None) == "max_tokens":
        raise RuntimeError("A resposta da IA foi cortada; peça não lida.")
    itens = _tool_input(resp, "registrar_posicoes").get("posicoes")
    out = []
    for it in itens if isinstance(itens, list) else []:
        if not isinstance(it, dict) or it.get("posicao") not in POSICOES or not str(it.get("resumo") or "").strip():
            continue
        try:
            conf = max(0.0, min(1.0, float(it.get("confianca"))))
        except (TypeError, ValueError):
            conf = None
        out.append({
            "tema": it.get("tema") if it.get("tema") in TEMAS_POS else "outro", "posicao": it["posicao"],
            "resumo": str(it["resumo"]).strip()[:300], "pede": (str(it["pede"]).strip()[:300] if it.get("pede") else None),
            "trecho": str(it.get("trecho") or "").strip()[:500], "confianca": conf,
        })
    return out, custo


def _persistir_peca(db, peca: AutosIAPeca, info: dict, posicoes: list[dict], tipo_ia, tipo_pje) -> int:
    """Troca as posições 'extraido' da peça pelas novas (validado/rejeitado — decisão humana — ficam)."""
    db.query(AutosIAFato).filter(AutosIAFato.peca_id == peca.id, AutosIAFato.tipo == TIPO_FATO, AutosIAFato.status == "extraido").delete(synchronize_session=False)
    mantidas = {p for (p,) in db.query(AutosIAFato.pos).filter(AutosIAFato.peca_id == peca.id, AutosIAFato.tipo == TIPO_FATO)}
    h = _hash_texto(peca.texto_md)
    holders = holders_da_peca(peca.autor, tipo_ia, tipo_pje)
    n = 0
    if not posicoes and -1 not in mantidas:
        db.add(AutosIAFato(caso_id=peca.caso_id, peca_id=peca.id, tipo=TIPO_FATO, tema="outro", sujeito="—", pos=-1, origem="sistema",
                           status="rejeitado", dados={"texto_hash": h, "marcador": True}))
    for i, p in enumerate(posicoes):
        if i in mantidas:
            continue
        db.add(AutosIAFato(
            caso_id=peca.caso_id, peca_id=peca.id, tipo=TIPO_FATO, tema=p["tema"], sujeito=holders[0]["nome"][:255], natureza=p["posicao"],
            data_ref=info.get("data"), trecho=p["trecho"], pos=i, confianca=p["confianca"], origem="ia", status="extraido",
            dados={"resumo": p["resumo"], "pede": p["pede"], "texto_hash": h, "holders": holders},
        ))
        n += 1
    return n


# ── Execução ─────────────────────────────────────────────────────────────────

_LOCK = threading.Lock()
_PROGRESSO: dict[str, dict] = {}


def _pecas_elegiveis(db, caso_id) -> list[tuple]:
    q = (
        db.query(AutosIAPeca.id, AutosIAPeca.texto_md, AutosIAPeca.tipo, AndamentoProcesso.tipo, AndamentoProcesso.arquivo_nome,
                 AndamentoProcesso.documento_id, AndamentoProcesso.arquivo_drive_link)
        .outerjoin(AndamentoProcesso, AutosIAPeca.andamento_id == AndamentoProcesso.id)
        .filter(AutosIAPeca.caso_id == caso_id)
        .order_by(AndamentoProcesso.data_andamento.asc().nulls_last(), AutosIAPeca.id_processual)
    )
    return [(pid, texto) for pid, texto, tipo_ia, tipo_pje, arq, doc, link in q.all() if peca_elegivel(tipo_pje, tipo_ia, bool(arq or doc or link), texto)]


def pecas_para_extrair(db, caso_id, forcar: bool = False) -> list[uuid.UUID]:
    lidas = {}
    for pid, h in db.query(AutosIAFato.peca_id, AutosIAFato.dados["texto_hash"].astext).filter(AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO):
        lidas.setdefault(pid, set()).add(h)
    return [pid for pid, texto in _pecas_elegiveis(db, caso_id) if forcar or _hash_texto(texto) not in lidas.get(pid, set())]


def status_extracao(db, caso_id) -> dict:
    p = dict(_PROGRESSO.get(str(caso_id)) or {})
    total = db.query(func.count(AutosIAFato.id)).filter(AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO, AutosIAFato.pos >= 0).scalar()
    com = db.query(func.count(func.distinct(AutosIAFato.peca_id))).filter(AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO, AutosIAFato.pos >= 0).scalar()
    validadas = db.query(func.count(AutosIAFato.id)).filter(AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO, AutosIAFato.status == "validado").scalar()
    return {
        "estado": p.get("estado", "ocioso"), "total_posicoes": total, "pecas_com_posicoes": com, "validadas": validadas,
        "pecas_pendentes": len(pecas_para_extrair(db, caso_id)), "total": p.get("total", 0), "feitos": p.get("feitos", 0),
        "novas": p.get("novas", 0), "erros": p.get("erros", 0), "custo_usd": round(p.get("custo_usd", 0.0), 4), "mensagem": p.get("mensagem"),
    }


def extrair_caso(caso_id: uuid.UUID, forcar: bool = False, limite_pecas: int | None = None, cliente=None) -> dict:
    """Lê as peças narrativas ainda não lidas (ou cujo texto mudou). Uma execução por vez. Nunca lança."""
    from concurrent.futures import ThreadPoolExecutor

    if not _LOCK.acquire(blocking=False):
        return {"estado": "rodando", "mensagem": "Já há uma leitura em andamento."}
    db = SessionLocal()
    chave = str(caso_id)
    try:
        prog = _PROGRESSO[chave] = {"estado": "rodando", "total": 0, "feitos": 0, "novas": 0, "erros": 0, "custo_usd": 0.0, "mensagem": "Selecionando peças…"}
        ids = pecas_para_extrair(db, caso_id, forcar)
        if limite_pecas:
            ids = ids[:limite_pecas]
        prog["total"] = len(ids)
        prog["mensagem"] = f"Lendo as posições de {len(ids)} peça(s)…"
        cliente = cliente or _cliente()

        def _um(args):
            pid, info, texto = args
            try:
                pos, custo = extrair_posicoes_peca(info, texto, cliente)
                return pid, info, pos, custo, None
            except Exception as exc:  # noqa: BLE001 — cada peça falha isolada
                return pid, info, [], 0.0, str(exc)[:300]

        with ThreadPoolExecutor(max_workers=_PARALELO) as pool:
            for ini in range(0, len(ids), 6):
                trabalhos = []
                for pid in ids[ini: ini + 6]:
                    peca = db.get(AutosIAPeca, pid)
                    andamento = db.get(AndamentoProcesso, peca.andamento_id) if peca.andamento_id else None
                    info = {"id_processual": peca.id_processual, "tipo_pje": andamento.tipo if andamento else None, "autor": peca.autor,
                            "data": str(andamento.data_andamento) if andamento and andamento.data_andamento else (str(peca.data_peca) if peca.data_peca else None)}
                    trabalhos.append((pid, info, peca.texto_md))
                for pid, info, pos, custo, erro in pool.map(_um, trabalhos):
                    prog["feitos"] += 1
                    prog["custo_usd"] += custo
                    if erro:
                        prog["erros"] += 1
                        prog["mensagem"] = f"Falha: {erro}"
                        logger.warning("Posições: peça %s falhou: %s", pid, erro)
                        continue
                    peca = db.get(AutosIAPeca, pid)
                    andamento = db.get(AndamentoProcesso, peca.andamento_id) if peca.andamento_id else None
                    prog["novas"] += _persistir_peca(db, peca, info, pos, peca.tipo, andamento.tipo if andamento else None)
                db.commit()
        caso = db.get(AutosIACaso, caso_id)
        if caso:
            caso.custo_usd_total = (caso.custo_usd_total or 0) + prog["custo_usd"]
        db.commit()
        prog["estado"] = "concluido"
        if prog["mensagem"].startswith(("Selecionando", "Lendo")):
            prog["mensagem"] = f"Concluído: {prog['novas']} posição(ões) em {prog['feitos']} peça(s) · US$ {prog['custo_usd']:.2f}."
        return prog
    except Exception as exc:  # noqa: BLE001
        logger.exception("Posições do caso %s falhou", caso_id)
        db.rollback()
        _PROGRESSO[chave] = {**_PROGRESSO.get(chave, {}), "estado": "erro", "mensagem": str(exc)[:300]}
        return _PROGRESSO[chave]
    finally:
        db.close()
        _LOCK.release()


# ── Consulta ─────────────────────────────────────────────────────────────────

class PosicaoErro(ValueError):
    pass


def _item(f: AutosIAFato, peca: AutosIAPeca, andamento: AndamentoProcesso | None) -> dict:
    d = f.dados or {}
    return {
        "id": f.id, "tema": f.tema, "tema_rotulo": TEMA_POS_ROTULO.get(f.tema or "outro", "Outro"), "posicao": f.natureza,
        "posicao_rotulo": POSICAO_ROTULO.get(f.natureza or "", f.natureza), "resumo": d.get("resumo"), "pede": d.get("pede"), "trecho": f.trecho,
        "data": (str(andamento.data_andamento) if andamento and andamento.data_andamento else (str(peca.data_peca) if peca.data_peca else None)),
        "confianca": f.confianca, "status": f.status, "nota": f.nota, "validado": f.status == "validado",
        "holders": d.get("holders") or [{"chave": "desconhecido", "nome": f.sujeito or "—", "tipo": "parte"}],
        "peticao": {"peca_id": peca.id, "id_processual": peca.id_processual, "data": (andamento.data_andamento if andamento and andamento.data_andamento else peca.data_peca),
                    "titulo": peca.titulo_customizado or peca.titulo, "link_pdf": andamento.arquivo_drive_link if andamento else None, "link_md": _link_md(peca.md_drive_file_id)},
    }


def _linhas(db, caso_id, incluir_rejeitadas: bool = False):
    q = (db.query(AutosIAFato, AutosIAPeca, AndamentoProcesso)
         .join(AutosIAPeca, AutosIAFato.peca_id == AutosIAPeca.id)
         .outerjoin(AndamentoProcesso, AutosIAPeca.andamento_id == AndamentoProcesso.id)
         .filter(AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO, AutosIAFato.pos >= 0))
    if not incluir_rejeitadas:
        q = q.filter(AutosIAFato.status != "rejeitado")
    return q.all()


def _ordena_data(itens: list[dict]) -> list[dict]:
    return sorted(itens, key=lambda i: (i["data"] or "", i["peticao"]["id_processual"] or ""))


def listar(db, caso_id, filtros: dict | None = None, limite: int = 300) -> dict:
    f = filtros or {}
    itens = [_item(*t) for t in _linhas(db, caso_id, incluir_rejeitadas=f.get("status") == "rejeitado")]
    if f.get("status"):
        itens = [i for i in itens if i["status"] == f["status"]]
    if f.get("tema"):
        itens = [i for i in itens if i["tema"] == f["tema"]]
    if f.get("posicao"):
        itens = [i for i in itens if i["posicao"] == f["posicao"]]
    if f.get("participante"):
        itens = [i for i in itens if any(h["chave"] == f["participante"] for h in i["holders"])]
    if f.get("q"):
        q = f["q"].lower()
        itens = [i for i in itens if q in " ".join(filter(None, [i["resumo"], i["pede"], i["trecho"], i["nota"], *[h["nome"] for h in i["holders"]]])).lower()]
    itens = _ordena_data(itens)[::-1]
    return {"total": len(itens), "itens": itens[:limite]}


def _por_participante_tema(itens: list[dict]) -> dict[tuple[str, str], dict]:
    """(participante, tema) → {holder, itens ordenados por data}. Petição conjunta vale para cada parte."""
    grupos: dict[tuple[str, str], dict] = {}
    for i in itens:
        for h in i["holders"]:
            g = grupos.setdefault((h["chave"], i["tema"]), {"holder": h, "itens": []})
            g["itens"].append(i)
    for g in grupos.values():
        g["itens"] = _ordena_data(g["itens"])
    return grupos


def matriz(db, caso_id) -> dict:
    """Participantes × temas. Cada célula traz a posição MAIS RECENTE, quantas peças e se houve mudança."""
    itens = [_item(*t) for t in _linhas(db, caso_id)]
    grupos = _por_participante_tema(itens)
    temas_usados = [t for t in TEMAS_POS if any(k[1] == t for k in grupos)]
    linhas: dict[str, dict] = {}
    for (chave, tema), g in grupos.items():
        h = g["holder"]
        lin = linhas.setdefault(chave, {"chave": chave, "nome": h["nome"], "tipo": h["tipo"], "n_pecas": 0, "celulas": {}, "_pecas": set()})
        pos = [i["posicao"] for i in g["itens"]]
        lin["_pecas"].update(i["peticao"]["peca_id"] for i in g["itens"])
        lin["celulas"][tema] = {"atual": pos[-1], "atual_rotulo": POSICAO_ROTULO[pos[-1]], "n": len(pos), "mudou": len(set(pos)) > 1,
                                "inversao": "favoravel" in pos and "contraria" in pos, "itens": g["itens"]}
    for lin in linhas.values():
        lin["n_pecas"] = len(lin.pop("_pecas"))
    ordem = sorted(linhas.values(), key=lambda l: (_ORDEM_TIPO.get(l["tipo"], 9), -l["n_pecas"], l["nome"].casefold()))
    return {
        "resumo": {"participantes": len(ordem), "posicoes": len(itens), "temas": len(temas_usados),
                   "celulas_com_mudanca": sum(1 for l in ordem for c in l["celulas"].values() if c["mudou"])},
        "temas": [{"chave": t, "rotulo": TEMA_POS_ROTULO[t]} for t in temas_usados], "linhas": ordem,
    }


def contradicoes(db, caso_id) -> dict:
    """Linha do tempo das mudanças de posição: mesmo participante, mesmo tema, posições diferentes ao longo do tempo."""
    itens = [_item(*t) for t in _linhas(db, caso_id)]
    saida = []
    for (chave, tema), g in _por_participante_tema(itens).items():
        pos = {i["posicao"] for i in g["itens"]}
        if len(pos) < 2:
            continue
        inversao = "favoravel" in pos and "contraria" in pos
        saida.append({"chave": chave, "nome": g["holder"]["nome"], "tipo": g["holder"]["tipo"], "tema": tema, "tema_rotulo": TEMA_POS_ROTULO[tema],
                      "inversao": inversao, "gravidade": "inversao" if inversao else "mudanca", "itens": g["itens"]})
    saida.sort(key=lambda c: (not c["inversao"], _ORDEM_TIPO.get(c["tipo"], 9), -len(c["itens"])))
    return {"total": len(saida), "inversoes": sum(1 for c in saida if c["inversao"]), "itens": saida}


def conflitos_advogados(db, caso_id) -> dict:
    """Advogados que representam partes com posições OPOSTAS no mesmo tema (usa a posição mais recente de cada parte)."""
    rel = advogados_partes.montar_relacao(db, caso_id)
    itens = [_item(*t) for t in _linhas(db, caso_id)]
    atual = {k: g["itens"][-1] for k, g in _por_participante_tema(itens).items() if g["holder"]["tipo"] == "parte"}
    nomes = {p["chave"]: p["nome"] for p in rel["partes"]}
    saida = []
    for adv in rel["advogados"]:
        por_tema: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
        for p in adv["partes"]:
            for tema in TEMAS_POS:
                i = atual.get((p["chave"], tema))
                if i and i["posicao"] in ("favoravel", "contraria"):
                    por_tema[tema][i["posicao"]].append({"chave": p["chave"], "nome": nomes.get(p["chave"], p["nome"]), "principal": p["principal"], "posicao_item": i})
        for tema, d in por_tema.items():
            if d["favoravel"] and d["contraria"]:
                saida.append({"advogado": {"id": adv["id"], "nome": adv["nome"], "oabs": adv["oabs"]}, "tema": tema, "tema_rotulo": TEMA_POS_ROTULO[tema],
                              "favoraveis": d["favoravel"], "contrarias": d["contraria"], "n_partes": len(d["favoravel"]) + len(d["contraria"])})
    saida.sort(key=lambda c: (-c["n_partes"], c["tema"]))
    return {"total": len(saida), "advogados": len({c["advogado"]["id"] for c in saida}), "itens": saida}


def atualizar(db, caso_id, fato_id, posicao=None, tema=None, nota=None, nota_definida=False, status=None) -> dict:
    f = db.get(AutosIAFato, fato_id)
    if f is None or f.caso_id != caso_id or f.tipo != TIPO_FATO or f.pos < 0:
        raise PosicaoErro("Posição não encontrada.")
    if posicao is not None:
        if posicao not in POSICOES:
            raise PosicaoErro("Posição inválida.")
        f.natureza = posicao
    if tema is not None:
        if tema not in TEMAS_POS:
            raise PosicaoErro("Tema inválido.")
        f.tema = tema
    if status is not None:
        if status not in STATUS:
            raise PosicaoErro("Status inválido.")
        f.status = status
    elif posicao is not None or tema is not None:
        f.status = "validado"
    if nota_definida:
        f.nota = (nota or "").strip() or None
    db.commit()
    row = db.query(AutosIAFato, AutosIAPeca, AndamentoProcesso).join(AutosIAPeca, AutosIAFato.peca_id == AutosIAPeca.id) \
        .outerjoin(AndamentoProcesso, AutosIAPeca.andamento_id == AndamentoProcesso.id).filter(AutosIAFato.id == fato_id).one()
    return _item(*row)
