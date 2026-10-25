"""Banco de fatos — DETERMINAÇÕES do Juízo e quadro de cumprimento.

1. Atos do Juízo (decisões, despachos) → a IA lista cada ordem ("DETERMINO às requerentes que, em
   15 dias, …"): destinatário, ação, prazo (dias úteis), sanção e se pesa sobre a mediação. Cópias
   da mesma decisão (juntadas/intimações repetidas) são deduplicadas pelo texto.
2. Vencimento ESTIMADO em dias úteis a partir da data de início da contagem (editável: a data de
   intimação real manda) — ver calendario_forense.py.
3. Cumprimento: a IA confronta cada ordem com as peças posteriores (resumos) e classifica em
   cumprida / parcial / não localizada / em prazo / prejudicada, citando as peças-evidência.
   Decisão humana (status manual + nota) sempre prevalece sobre a da IA.
4. Minuta: quadro de descumprimentos pronto para colar numa petição (ex.: contra o avanço da
   mediação com participantes irregulares).
"""
import hashlib
import logging
import re
import threading
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func

from app.database import SessionLocal
from app.models.andamento import AndamentoProcesso
from app.models.autos_ia import AutosIACaso, AutosIAFato, AutosIAPeca
from app.services.autos_ia.calendario_forense import somar_dias
from app.services.autos_ia.fatos_valores import MODELO, _cliente, _link_md, _tool_input, afirmante_de
from app.services.autos_ia.precos import calcular_custo_usd

logger = logging.getLogger(__name__)

TIPO_FATO = "determinacao"
DEST_TIPOS = ["requerentes", "administradora_judicial", "ministerio_publico", "secretaria", "terceiro_especifico",
              "mediacao_interessados", "todos", "outro"]
DEST_ROTULO = {
    "requerentes": "Requerentes (grupo devedor)", "administradora_judicial": "Administradora Judicial / perita",
    "ministerio_publico": "Ministério Público", "secretaria": "Secretaria", "terceiro_especifico": "Terceiro específico",
    "mediacao_interessados": "Interessados (mediação)", "todos": "Todos", "outro": "Outro",
}
TEMAS_DET = ["representacao_processual", "documental_contabil", "esclarecimento_manifestacao", "mediacao",
             "sigilo_acesso", "protecao_patrimonial", "providencia_secretaria", "honorarios_custas", "outro"]
TEMA_DET_ROTULO = {
    "representacao_processual": "Representação processual", "documental_contabil": "Documentos / contábil",
    "esclarecimento_manifestacao": "Esclarecimento / manifestação", "mediacao": "Mediação",
    "sigilo_acesso": "Sigilo / acesso", "protecao_patrimonial": "Proteção patrimonial",
    "providencia_secretaria": "Providência da Secretaria", "honorarios_custas": "Honorários / custas", "outro": "Outro",
}
STATUS_CUMPRIMENTO = ["cumprida", "parcial", "nao_localizada", "em_prazo", "prejudicada", "nao_aplicavel"]
_TEXTO_MIN = 500
_JANELA_DIAS = 45          # peças posteriores consideradas para avaliar uma ordem
_MAX_CANDIDATAS = 45
_RE_JUIZO_PJE = re.compile(r"^(?:decis|outras decis|despacho|liminar|of[ií]cio \(outros\)|intima[cç][aã]o - di[aá]rio)", re.I)

TOOL_DET = {
    "name": "registrar_determinacoes",
    "description": "Lista cada ORDEM (obrigação imposta a alguém) contida no ato do Juízo.",
    "input_schema": {
        "type": "object",
        "properties": {"determinacoes": {"type": "array", "items": {"type": "object", "properties": {
            "ordem": {"type": ["string", "null"], "description": "Número/letra do item na decisão (ex.: '15'), se houver."},
            "capitulo": {"type": ["string", "null"], "description": "Seção/capítulo da decisão em que consta, se houver."},
            "destinatario_tipo": {"type": "string", "enum": DEST_TIPOS,
                                  "description": "requerentes = o grupo devedor/autor do pedido de recuperação; "
                                                 "administradora_judicial = administrador(a) judicial e perito(a); "
                                                 "secretaria = serventia; terceiro_especifico = uma parte/credor/banco nomeado; "
                                                 "mediacao_interessados = os interessados na mediação; todos = todos os envolvidos."},
            "destinatario_nome": {"type": ["string", "null"], "description": "Nome do destinatário quando nomeado (ex.: 'Rhino Securitizadora S.A.')."},
            "acao": {"type": "string", "description": "O que deve ser feito, em uma frase imperativa objetiva (máx. 300 caracteres)."},
            "tema": {"type": "string", "enum": TEMAS_DET},
            "prazo_dias": {"type": ["integer", "null"], "description": "Prazo em dias, se fixado."},
            "prazo_tipo": {"type": ["string", "null"], "enum": ["uteis", "corridos", None],
                           "description": "'corridos' só se o ato disser expressamente; no processo civil o padrão é dias úteis."},
            "prazo_condicao": {"type": ["string", "null"], "description": "Se o prazo depende de outro evento (ex.: 'contado do término do prazo de 30 dias das requerentes')."},
            "prazo_data": {"type": ["string", "null"], "description": "Data-limite explícita AAAA-MM-DD, se o ato a fixar."},
            "sancao": {"type": ["string", "null"], "description": "Consequência de descumprir, se declarada (ex.: 'extinção quanto à sociedade irregularmente representada')."},
            "ligada_a_mediacao": {"type": "boolean", "description": "True se a ordem trata da mediação ou de pressuposto dela (representação com poderes para transigir, legitimidade, relação de credores, composição dos participantes)."},
            "trecho": {"type": "string", "description": "Trecho LITERAL do ato que contém a ordem (máx. 250 caracteres; só o essencial)."},
        }, "required": ["destinatario_tipo", "acao", "tema", "ligada_a_mediacao", "trecho"]}}},
        "required": ["determinacoes"],
    },
}
SISTEMA_DET = (
    "Você é um advogado que mapeia, numa recuperação judicial, as ORDENS dadas pelo Juízo para acompanhar seu "
    "cumprimento. Liste só obrigações impostas a alguém (determino, ordeno, intime-se para manifestar, fixo prazo para "
    "indicar/juntar/esclarecer, advirto sob pena…). NÃO liste fundamentação, relatório, nem deferimentos que não impõem "
    "ato a ninguém. Cada ordem separada (cada alínea com destinatário, ato ou prazo diferente) é um item. Copie o trecho "
    "literalmente; não invente prazos nem destinatários — use null quando o ato não diz. Seja conciso: ação em uma frase curta e trecho de até 250 caracteres."
)

TOOL_CUMPRIMENTO = {
    "name": "registrar_cumprimento",
    "description": "Avalia, para cada ordem, se as peças posteriores a cumprem.",
    "input_schema": {
        "type": "object",
        "properties": {"avaliacoes": {"type": "array", "items": {"type": "object", "properties": {
            "i": {"type": "integer", "description": "Índice [i] da ordem."},
            "status": {"type": "string", "enum": STATUS_CUMPRIMENTO,
                       "description": "cumprida = há peça que atende a ordem; parcial = atende em parte; nao_localizada = nenhuma "
                                      "peça posterior a atende; em_prazo = ainda dentro do prazo e sem cumprimento; prejudicada = "
                                      "perdeu o objeto (ex.: outra decisão a substituiu ou a sociedade desistiu); nao_aplicavel = "
                                      "ordem do Juízo à Secretaria/sem ato da parte a verificar."},
            "evidencias": {"type": "array", "items": {"type": "string"}, "description": "IDs (como numerados nas peças candidatas) que sustentam o status."},
            "justificativa": {"type": "string", "description": "Uma ou duas frases objetivas, citando o que a peça fez ou deixou de fazer."},
            "confianca": {"type": "number"},
        }, "required": ["i", "status", "evidencias", "justificativa", "confianca"]}}},
        "required": ["avaliacoes"],
    },
}
SISTEMA_CUMPRIMENTO = (
    "Você confronta ordens do Juízo com as peças que as partes protocolaram DEPOIS, usando apenas os resumos fornecidos. "
    "Seja conservador: só diga 'cumprida' se o resumo mostra o ato exigido (juntada do documento, informação pedida, "
    "manifestação no prazo). Se nenhuma peça candidata trata da ordem, use 'nao_localizada' (ou 'em_prazo' se o prazo ainda "
    "corre). Os resumos podem omitir detalhes — nesse caso use 'parcial' ou 'nao_localizada' e diga na justificativa que a "
    "conferência no inteiro teor é necessária. Cite como evidência apenas IDs que constem da lista."
)


# ── 1. Atos do Juízo e extração ──────────────────────────────────────────────

def _norm(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


def hash_ato(texto: str) -> str:
    n = _norm(texto)
    return hashlib.sha256(f"{len(n)}|{n[:6000]}|{n[-3000:]}".encode("utf-8")).hexdigest()


_RE_OUTRO_ORGAO = re.compile(r"(?i)\b(turma|c[âa]mara|desembargador|des\.|ministro|relator)\b")


def ato_do_juizo(tipo_pje: str | None, tipo_ia: str | None, autor: str | None, texto: str | None) -> bool:
    if len((texto or "").strip()) < _TEXTO_MIN:
        return False
    if _RE_OUTRO_ORGAO.search(autor or ""):
        return False                                   # acórdão/decisão de turma, câmara, tribunal
    chave, _ = afirmante_de(autor, tipo_ia, tipo_pje)
    if chave != "juizo":
        return False
    if tipo_pje and re.match(r"(?i)^documento", tipo_pje):
        return tipo_ia in ("decisao", "despacho")
    return bool(_RE_JUIZO_PJE.match(tipo_pje or "")) or tipo_ia in ("decisao", "despacho")


def _grupos_de_atos(db, caso_id) -> list[dict]:
    """Atos do Juízo agrupados por texto idêntico; o grupo fica com a peça mais antiga como principal."""
    q = (
        db.query(AutosIAPeca.id, AutosIAPeca.id_processual, AutosIAPeca.texto_md, AutosIAPeca.autor, AutosIAPeca.tipo,
                 AndamentoProcesso.tipo, AndamentoProcesso.data_andamento)
        .outerjoin(AndamentoProcesso, AutosIAPeca.andamento_id == AndamentoProcesso.id)
        .filter(AutosIAPeca.caso_id == caso_id)
        .order_by(AndamentoProcesso.data_andamento.asc().nulls_last(), AutosIAPeca.id_processual)
    )
    grupos: dict[str, dict] = {}
    for pid, idp, texto, autor, tipo_ia, tipo_pje, data in q.all():
        if not ato_do_juizo(tipo_pje, tipo_ia, autor, texto):
            continue
        h = hash_ato(texto)
        g = grupos.setdefault(h, {"hash": h, "peca_id": pid, "id_processual": idp, "data": data, "texto": texto, "copias": []})
        g["copias"].append({"peca_id": str(pid), "id_processual": idp, "data": str(data) if data else None})
    return list(grupos.values())


_CHUNK_CHARS = 40_000      # acima disso o ato é lido em partes (a lista de ordens de uma decisão longa estoura a resposta)
_CHUNK_MIN = 6_000
_SOBREPOSICAO = 1_500


def _montar_prompt_ato(g: dict, texto: str | None = None, parte: tuple[int, int] | None = None) -> str:
    cab = f"Ato do Juízo — ID {g['id_processual'] or 's/ ID'}, de {g['data'] or 'data não informada'}."
    if parte and parte[1] > 1:
        cab += (f"\nVocê recebe a PARTE {parte[0]} de {parte[1]} do texto. Liste as ordens que aparecem nesta parte; "
                "o início pode repetir o fim da parte anterior (contexto) — não liste de novo ordens que só aparecem nessa repetição.")
    return f"{cab}\n\nTexto integral:\n\n{(texto if texto is not None else g['texto'])[:300_000]}"


def _dividir(texto: str, max_chars: int) -> list[str]:
    """Quebra em partes de até `max_chars`, preferindo limites de parágrafo, com um trecho de sobreposição."""
    if len(texto) <= max_chars:
        return [texto]
    partes, ini = [], 0
    while ini < len(texto):
        fim = min(len(texto), ini + max_chars)
        if fim < len(texto):
            corte = texto.rfind("\n\n", ini + max_chars // 2, fim)
            fim = corte if corte > ini else fim
        partes.append(texto[max(0, ini - _SOBREPOSICAO if ini else 0): fim])
        ini = fim
    return partes


def _chamar_det(g: dict, texto: str, parte: tuple[int, int], cliente) -> tuple[list, float, bool]:
    resp = cliente.messages.create(
        model=MODELO, max_tokens=12000, system=SISTEMA_DET, tools=[TOOL_DET],
        tool_choice={"type": "tool", "name": "registrar_determinacoes"},
        messages=[{"role": "user", "content": _montar_prompt_ato(g, texto, parte)}],
    )
    custo = calcular_custo_usd(resp.usage.input_tokens, resp.usage.output_tokens)
    truncado = getattr(resp, "stop_reason", None) == "max_tokens"
    itens = [] if truncado else (_tool_input(resp, "registrar_determinacoes").get("determinacoes") or [])
    return itens, custo, truncado


def _ler_trecho(g: dict, texto: str, parte: tuple[int, int], cliente) -> tuple[list, float]:
    """Lê uma parte; se a resposta estourar o limite (muitas ordens), divide ao meio e junta. Nunca devolve
    resultado truncado como se fosse completo."""
    itens, custo, truncado = _chamar_det(g, texto, parte, cliente)
    if not truncado:
        return itens, custo
    if len(texto) <= _CHUNK_MIN * 2:
        raise RuntimeError("A resposta da IA foi cortada mesmo em trecho curto; ato não lido.")
    meio = len(texto) // 2
    corte = texto.rfind("\n\n", meio - 2_000, meio + 2_000)
    meio = corte if corte > 0 else meio
    a, ca = _ler_trecho(g, texto[:meio], parte, cliente)
    b, cb = _ler_trecho(g, texto[max(0, meio - _SOBREPOSICAO):], parte, cliente)
    return a + b, custo + ca + cb


def extrair_determinacoes_ato(g: dict, cliente=None) -> tuple[list[dict], float]:
    cliente = cliente or _cliente()
    partes = _dividir(g["texto"], _CHUNK_CHARS)
    itens, custo = [], 0.0
    for k, trecho in enumerate(partes, 1):
        it, c = _ler_trecho(g, trecho, (k, len(partes)), cliente)
        itens += it
        custo += c
    out, vistos = [], set()
    for it in itens:
        if not isinstance(it, dict) or not str(it.get("acao") or "").strip():
            continue
        try:
            dias = int(it["prazo_dias"]) if it.get("prazo_dias") is not None else None
        except (TypeError, ValueError):
            dias = None
        pd_ = it.get("prazo_data")
        item = {
            "ordem": (str(it["ordem"]).strip()[:20] if it.get("ordem") else None),
            "capitulo": (str(it["capitulo"]).strip()[:200] if it.get("capitulo") else None),
            "destinatario_tipo": it.get("destinatario_tipo") if it.get("destinatario_tipo") in DEST_TIPOS else "outro",
            "destinatario_nome": (str(it["destinatario_nome"]).strip()[:200] if it.get("destinatario_nome") else None),
            "acao": str(it["acao"]).strip()[:400],
            "tema": it.get("tema") if it.get("tema") in TEMAS_DET else "outro",
            "prazo_dias": dias if dias and 0 < dias < 1000 else None,
            "prazo_tipo": "corridos" if it.get("prazo_tipo") == "corridos" else "uteis",
            "prazo_condicao": (str(it["prazo_condicao"]).strip()[:300] if it.get("prazo_condicao") else None),
            "prazo_data": pd_ if isinstance(pd_, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", pd_) else None,
            "sancao": (str(it["sancao"]).strip()[:300] if it.get("sancao") else None),
            "ligada_a_mediacao": bool(it.get("ligada_a_mediacao")),
            "trecho": str(it.get("trecho") or "").strip()[:600],
        }
        chave = (item["ordem"] or "", item["destinatario_tipo"], (item["destinatario_nome"] or "").casefold(), re.sub(r"\W+", " ", item["acao"].casefold())[:60])
        if chave in vistos:                    # a sobreposição entre partes pode repetir a mesma ordem
            continue
        vistos.add(chave)
        out.append(item)
    return out, custo


def _persistir_ato(db, caso_id, g: dict, dets: list[dict]) -> int:
    """Troca as determinações 'extraido' deste ato pelas novas (ordem humana — validado/rejeitado — fica)."""
    db.query(AutosIAFato).filter(
        AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO, AutosIAFato.peca_id == g["peca_id"],
        AutosIAFato.status == "extraido",
    ).delete(synchronize_session=False)
    mantidas = {p for (p,) in db.query(AutosIAFato.pos).filter(AutosIAFato.peca_id == g["peca_id"], AutosIAFato.tipo == TIPO_FATO)}
    n = 0
    if not dets and -1 not in mantidas:
        # marcador "ato lido, sem ordens": evita reler (e pagar de novo) um despacho sem determinações
        db.add(AutosIAFato(
            caso_id=caso_id, peca_id=g["peca_id"], tipo=TIPO_FATO, tema="outro", sujeito="—", pos=-1, origem="sistema",
            status="rejeitado", dados={"texto_hash": g["hash"], "marcador": True, "acao": "(ato lido sem ordens)"},
        ))
    for i, d in enumerate(dets):
        if i in mantidas:
            continue
        db.add(AutosIAFato(
            caso_id=caso_id, peca_id=g["peca_id"], tipo=TIPO_FATO, tema=d["tema"],
            sujeito=d["destinatario_nome"] or DEST_ROTULO[d["destinatario_tipo"]], natureza=d["destinatario_tipo"],
            data_ref=d["prazo_data"], trecho=d["trecho"], pos=i, origem="ia", status="extraido",
            dados={**{k: d[k] for k in ("ordem", "capitulo", "acao", "prazo_dias", "prazo_tipo", "prazo_condicao", "sancao", "ligada_a_mediacao")},
                   "texto_hash": g["hash"], "decisao_data": str(g["data"]) if g["data"] else None,
                   "decisao_id": g["id_processual"], "copias": g["copias"]},
        ))
        n += 1
    return n


# ── 2. Vencimento ────────────────────────────────────────────────────────────

def _d(v) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def vencimento(dados: dict, data_ref: str | None, hoje: date | None = None) -> dict:
    """{inicio, vencimento, estimado, motivo}. Prazo com data explícita manda; prazo condicionado a outro
    evento não é calculado; senão conta em dias úteis a partir da data de início da contagem."""
    if data_ref:
        return {"inicio": None, "vencimento": data_ref, "estimado": False, "motivo": "data fixada no ato"}
    dias = dados.get("prazo_dias")
    if not dias:
        return {"inicio": None, "vencimento": None, "estimado": True, "motivo": "sem prazo fixado"}
    if dados.get("prazo_condicao"):
        return {"inicio": None, "vencimento": None, "estimado": True, "motivo": f"depende de: {dados['prazo_condicao']}"}
    ini = _d(dados.get("intimacao_data")) or _d(dados.get("decisao_data"))
    if ini is None:
        return {"inicio": None, "vencimento": None, "estimado": True, "motivo": "sem data de início da contagem"}
    venc = somar_dias(ini, int(dias), uteis=dados.get("prazo_tipo") != "corridos")
    origem = "intimação informada" if dados.get("intimacao_data") else "data da decisão (informe a intimação)"
    return {"inicio": str(ini), "vencimento": str(venc), "estimado": True, "motivo": f"{dias} dia(s) {'corridos' if dados.get('prazo_tipo') == 'corridos' else 'úteis'} a partir de {ini.strftime('%d/%m/%Y')} — {origem}"}


# ── 3. Cumprimento ───────────────────────────────────────────────────────────

def _candidatas(db, caso_id, g_data: date | None, id_decisao: str | None, prazo_max: int) -> list[dict]:
    """Peças narrativas posteriores ao ato (janela), priorizando as que citam o ID do ato."""
    q = (
        db.query(AutosIAPeca.id, AutosIAPeca.id_processual, AutosIAPeca.autor, AutosIAPeca.tipo, AutosIAPeca.resumo,
                 AutosIAPeca.ids_mencionados, AndamentoProcesso.tipo, AndamentoProcesso.data_andamento)
        .join(AndamentoProcesso, AutosIAPeca.andamento_id == AndamentoProcesso.id)
        .filter(AutosIAPeca.caso_id == caso_id, AutosIAPeca.resumo.isnot(None))
    )
    if g_data:
        q = q.filter(AndamentoProcesso.data_andamento >= g_data)
    cand = []
    for pid, idp, autor, tipo_ia, resumo, ids, tipo_pje, data in q.order_by(AndamentoProcesso.data_andamento.asc()).all():
        if re.match(r"(?i)^(documento|procura|demonstra|certid[aã]o regularidade)", tipo_pje or "") and not (id_decisao and id_decisao in (ids or [])):
            continue
        if re.match(r"(?i)^(conclus|expedi|publica|disponibiliza|intima|decurso|distribui|juntada|certid)", tipo_pje or ""):
            continue
        chave, rot = afirmante_de(autor, tipo_ia, tipo_pje)
        if chave == "juizo":
            continue
        cita = bool(id_decisao and id_decisao in (ids or []))
        dentro = bool(data and g_data and (data - g_data).days <= max(_JANELA_DIAS, prazo_max * 2))
        if cita or dentro:
            cand.append({"peca_id": pid, "id_processual": idp, "afirmante": rot, "tipo_pje": tipo_pje, "data": data, "resumo": _norm(resumo)[:420], "cita": cita})
    cand.sort(key=lambda c: (not c["cita"], c["data"] or date.max))
    return cand[:_MAX_CANDIDATAS]


_LOTE_ORDENS = 20


def avaliar_cumprimento_ato(ordens: list[AutosIAFato], cand: list[dict], hoje: date, cliente=None) -> tuple[dict[int, dict], float]:
    """Avalia, em lotes de ordens, se as peças candidatas as cumprem. Resposta cortada pela IA → o lote é
    dividido (uma decisão longa tem dezenas de ordens); nunca se aceita avaliação truncada como completa."""
    cliente = cliente or _cliente()
    linhas = []
    for k, f in enumerate(ordens):
        d = f.dados or {}
        v = vencimento(d, f.data_ref, hoje)
        linhas.append(f"[{k}] Destinatário: {f.sujeito} ({f.natureza}) · Ação: {d.get('acao')} · Prazo: {v['motivo']}"
                      f"{' · vence ' + v['vencimento'] if v['vencimento'] else ''}"
                      f"{' · Sanção: ' + d['sancao'] if d.get('sancao') else ''} · Trecho: «{(f.trecho or '')[:350]}»")
    pecas = [f"- ID {c['id_processual']} · {c['data']} · {c['afirmante']} · {c['tipo_pje'] or '—'}: {c['resumo']}" for c in cand]
    bloco_pecas = "\n\nPEÇAS POSTERIORES (candidatas a cumprimento):\n" + ("\n".join(pecas) or "(nenhuma peça posterior com resumo)")
    validos = {c["id_processual"] for c in cand if c["id_processual"]}
    out: dict[int, dict] = {}

    def _lote(ini: int, fim: int) -> float:
        prompt = f"Hoje: {hoje.isoformat()}.\n\nORDENS DO JUÍZO:\n" + "\n".join(linhas[ini:fim]) + bloco_pecas
        resp = cliente.messages.create(
            model=MODELO, max_tokens=8000, system=SISTEMA_CUMPRIMENTO, tools=[TOOL_CUMPRIMENTO],
            tool_choice={"type": "tool", "name": "registrar_cumprimento"},
            messages=[{"role": "user", "content": prompt}],
        )
        custo = calcular_custo_usd(resp.usage.input_tokens, resp.usage.output_tokens)
        if getattr(resp, "stop_reason", None) == "max_tokens":
            if fim - ini <= 1:
                raise RuntimeError("A resposta da IA foi cortada numa única ordem; cumprimento não avaliado.")
            meio = (ini + fim) // 2
            return custo + _lote(ini, meio) + _lote(meio, fim)
        for a in _tool_input(resp, "registrar_cumprimento").get("avaliacoes") or []:
            try:
                i = int(a.get("i"))
            except (TypeError, ValueError):
                continue
            if not (ini <= i < fim):
                continue
            out[i] = {
                "status": a.get("status") if a.get("status") in STATUS_CUMPRIMENTO else "nao_localizada",
                "evidencias": [e for e in (a.get("evidencias") or []) if isinstance(e, str) and e in validos][:8],
                "justificativa": str(a.get("justificativa") or "").strip()[:500],
                "confianca": max(0.0, min(1.0, float(a["confianca"]))) if isinstance(a.get("confianca"), (int, float)) else None,
            }
        return custo

    custo = 0.0
    for ini in range(0, len(ordens), _LOTE_ORDENS):
        custo += _lote(ini, min(len(ordens), ini + _LOTE_ORDENS))
    return out, custo


# ── 4. Execução ──────────────────────────────────────────────────────────────

_LOCK = threading.Lock()
_PROGRESSO: dict[str, dict] = {}


def status_extracao(db, caso_id) -> dict:
    p = dict(_PROGRESSO.get(str(caso_id)) or {})
    total = db.query(func.count(AutosIAFato.id)).filter(AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO, AutosIAFato.pos >= 0).scalar()
    atos = {h for (h,) in db.query(AutosIAFato.dados["texto_hash"].astext).filter(AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO).distinct() if h}
    pend = [g for g in _grupos_de_atos(db, caso_id) if g["hash"] not in atos]
    return {
        "estado": p.get("estado", "ocioso"), "total_determinacoes": total, "atos_pendentes": len(pend),
        "total": p.get("total", 0), "feitos": p.get("feitos", 0), "novas": p.get("novas", 0), "erros": p.get("erros", 0),
        "custo_usd": round(p.get("custo_usd", 0.0), 4), "mensagem": p.get("mensagem"),
    }


def extrair_caso(caso_id: uuid.UUID, forcar: bool = False, avaliar: bool = True, cliente=None) -> dict:
    """Extrai as ordens dos atos do Juízo ainda não lidos e (re)avalia o cumprimento. Nunca lança."""
    if not _LOCK.acquire(blocking=False):
        return {"estado": "rodando", "mensagem": "Já há uma execução em andamento."}
    db = SessionLocal()
    chave = str(caso_id)
    try:
        prog = _PROGRESSO[chave] = {"estado": "rodando", "total": 0, "feitos": 0, "novas": 0, "erros": 0, "custo_usd": 0.0, "mensagem": "Procurando decisões…"}
        cliente = cliente or _cliente()
        lidos = {h for (h,) in db.query(AutosIAFato.dados["texto_hash"].astext).filter(AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO).distinct() if h}
        grupos = [g for g in _grupos_de_atos(db, caso_id) if forcar or g["hash"] not in lidos]
        prog["total"] = len(grupos)
        prog["mensagem"] = f"Lendo {len(grupos)} ato(s) do Juízo…"
        for g in grupos:
            try:
                dets, custo = extrair_determinacoes_ato(g, cliente)
                prog["custo_usd"] += custo
                prog["novas"] += _persistir_ato(db, caso_id, g, dets)
                db.commit()
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                prog["erros"] += 1
                prog["mensagem"] = f"Falha no ato {g['id_processual']}: {str(exc)[:160]}"
                logger.warning("Determinações: ato %s falhou: %s", g["id_processual"], exc)
            prog["feitos"] += 1
        if avaliar:
            prog["mensagem"] = "Avaliando o cumprimento…"
            try:
                prog["custo_usd"] += avaliar_cumprimento_caso(db, caso_id, cliente)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                prog["erros"] += 1
                logger.warning("Determinações: avaliação de cumprimento falhou: %s", exc)
                prog["mensagem"] = f"Ordens extraídas; avaliação de cumprimento falhou ({str(exc)[:120]})."
        caso = db.get(AutosIACaso, caso_id)
        if caso:
            caso.custo_usd_total = (caso.custo_usd_total or 0) + prog["custo_usd"]
        db.commit()
        prog["estado"] = "concluido"
        if prog["mensagem"].startswith(("Procurando", "Lendo", "Avaliando")):
            prog["mensagem"] = f"Concluído: {prog['novas']} ordem(ns) em {prog['feitos']} ato(s) · US$ {prog['custo_usd']:.2f}."
        return prog
    except Exception as exc:  # noqa: BLE001
        logger.exception("Determinações do caso %s falhou", caso_id)
        db.rollback()
        _PROGRESSO[chave] = {**_PROGRESSO.get(chave, {}), "estado": "erro", "mensagem": str(exc)[:300]}
        return _PROGRESSO[chave]
    finally:
        db.close()
        _LOCK.release()


def avaliar_cumprimento_caso(db, caso_id, cliente=None, hoje: date | None = None) -> float:
    """Reavalia o cumprimento de todas as ordens não rejeitadas e sem status manual, ato por ato."""
    hoje = hoje or date.today()
    custo = 0.0
    por_ato: dict[str, list[AutosIAFato]] = defaultdict(list)
    for f in db.query(AutosIAFato).filter(AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO, AutosIAFato.status != "rejeitado").all():
        if (f.dados or {}).get("status_manual"):
            continue
        por_ato[str(f.peca_id)].append(f)
    for _, ordens in por_ato.items():
        ordens.sort(key=lambda f: f.pos)
        d0 = ordens[0].dados or {}
        g_data = _d(d0.get("decisao_data"))
        prazo_max = max([int((f.dados or {}).get("prazo_dias") or 0) for f in ordens] + [0])
        cand = _candidatas(db, caso_id, g_data, d0.get("decisao_id"), prazo_max)
        aval, c = avaliar_cumprimento_ato(ordens, cand, hoje, cliente)
        custo += c
        for k, f in enumerate(ordens):
            a = aval.get(k)
            if a is None:
                continue
            f.dados = {**(f.dados or {}), "status_cumprimento": a["status"], "evidencias": a["evidencias"],
                       "justificativa": a["justificativa"], "avaliado_em": hoje.isoformat()}
            f.confianca = a["confianca"]
        db.commit()
    return custo


# ── 5. Leitura ───────────────────────────────────────────────────────────────

def _evid(db, caso_id, ids: list[str]) -> list[dict]:
    if not ids:
        return []
    rows = (
        db.query(AutosIAPeca.id, AutosIAPeca.id_processual, AutosIAPeca.titulo, AutosIAPeca.md_drive_file_id,
                 AndamentoProcesso.arquivo_drive_link, AndamentoProcesso.data_andamento)
        .outerjoin(AndamentoProcesso, AutosIAPeca.andamento_id == AndamentoProcesso.id)
        .filter(AutosIAPeca.caso_id == caso_id, AutosIAPeca.id_processual.in_(ids)).all()
    )
    return [{"peca_id": r[0], "id_processual": r[1], "titulo": r[2], "data": r[5], "link_pdf": r[4], "link_md": _link_md(r[3])} for r in rows]


def status_efetivo(f: AutosIAFato, venc: dict, hoje: date) -> str:
    d = f.dados or {}
    s = d.get("status_manual") or d.get("status_cumprimento") or "nao_avaliada"
    vd = _d(venc["vencimento"])
    if s in ("nao_localizada", "em_prazo", "nao_avaliada") and vd:
        return "vencida_sem_cumprimento" if vd < hoje else "em_prazo"
    return s


def _item(db, caso_id, f: AutosIAFato, hoje: date) -> dict:
    d = f.dados or {}
    peca = db.get(AutosIAPeca, f.peca_id)
    andamento = db.get(AndamentoProcesso, peca.andamento_id) if peca and peca.andamento_id else None
    venc = vencimento(d, f.data_ref, hoje)
    return {
        "id": f.id, "ordem": d.get("ordem"), "capitulo": d.get("capitulo"), "destinatario": f.sujeito,
        "destinatario_tipo": f.natureza, "destinatario_rotulo": DEST_ROTULO.get(f.natureza or "outro", "Outro"),
        "acao": d.get("acao"), "tema": f.tema, "tema_rotulo": TEMA_DET_ROTULO.get(f.tema or "outro", "Outro"),
        "prazo_dias": d.get("prazo_dias"), "prazo_tipo": d.get("prazo_tipo"), "prazo_condicao": d.get("prazo_condicao"),
        "sancao": d.get("sancao"), "ligada_a_mediacao": bool(d.get("ligada_a_mediacao")), "trecho": f.trecho,
        "decisao_data": d.get("decisao_data"), "intimacao_data": d.get("intimacao_data"),
        "vencimento": venc["vencimento"], "vencimento_estimado": venc["estimado"], "vencimento_motivo": venc["motivo"],
        "dias_para_vencer": (_d(venc["vencimento"]) - hoje).days if _d(venc["vencimento"]) else None,
        "status_ia": d.get("status_cumprimento"), "status_manual": d.get("status_manual"),
        "status": status_efetivo(f, venc, hoje), "justificativa": d.get("justificativa"), "nota": f.nota,
        "confianca": f.confianca, "validado": f.status == "validado",
        "evidencias": _evid(db, caso_id, d.get("evidencias") or []),
        "decisao": {
            "peca_id": peca.id, "id_processual": peca.id_processual, "data": andamento.data_andamento if andamento else None,
            "titulo": peca.titulo, "link_pdf": andamento.arquivo_drive_link if andamento else None, "link_md": _link_md(peca.md_drive_file_id),
        },
    }


def listar(db, caso_id, filtros: dict | None = None, hoje: date | None = None) -> dict:
    f = filtros or {}
    hoje = hoje or date.today()
    fatos = (db.query(AutosIAFato).filter(AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO, AutosIAFato.status != "rejeitado")
             .order_by(AutosIAFato.criado_em).all())
    itens = [_item(db, caso_id, x, hoje) for x in fatos]
    itens.sort(key=lambda i: (i["decisao_data"] or "", int(re.sub(r"\D", "", i["ordem"] or "") or 0)), reverse=False)
    resumo = defaultdict(int)
    for i in itens:
        resumo[i["status"]] += 1
    if f.get("destinatario_tipo"):
        itens = [i for i in itens if i["destinatario_tipo"] == f["destinatario_tipo"]]
    if f.get("status"):
        itens = [i for i in itens if i["status"] == f["status"]]
    if f.get("tema"):
        itens = [i for i in itens if i["tema"] == f["tema"]]
    if f.get("decisao"):
        itens = [i for i in itens if i["decisao"]["id_processual"] == f["decisao"]]
    if f.get("mediacao"):
        itens = [i for i in itens if i["ligada_a_mediacao"]]
    if f.get("q"):
        q = f["q"].lower()
        itens = [i for i in itens if q in ((i["acao"] or "") + " " + (i["destinatario"] or "") + " " + (i["trecho"] or "")).lower()]
    return {"total": len(itens), "resumo": dict(resumo), "itens": itens}


class DeterminacaoErro(ValueError):
    pass


STATUS_MANUAIS = STATUS_CUMPRIMENTO + ["automatico"]


def atualizar(db, caso_id, fato_id, status_manual=None, nota=None, nota_definida=False, rejeitar=False, validar=None, hoje=None) -> dict:
    f = db.get(AutosIAFato, fato_id)
    if f is None or f.caso_id != caso_id or f.tipo != TIPO_FATO:
        raise DeterminacaoErro("Determinação não encontrada.")
    d = dict(f.dados or {})
    if status_manual is not None:
        if status_manual not in STATUS_MANUAIS:
            raise DeterminacaoErro("Status inválido.")
        if status_manual == "automatico":
            d.pop("status_manual", None)
        else:
            d["status_manual"] = status_manual
    if nota_definida:
        f.nota = (nota or "").strip() or None
    if rejeitar:
        f.status = "rejeitado"
    elif validar is not None:
        f.status = "validado" if validar else "extraido"
    f.dados = d
    db.commit()
    db.refresh(f)
    return _item(db, caso_id, f, hoje or date.today())


def definir_intimacao(db, caso_id, peca_id, data: str | None) -> int:
    """Data de início da contagem (intimação/publicação) de TODAS as ordens de uma decisão."""
    if data is not None and _d(data) is None:
        raise DeterminacaoErro("Data inválida (use AAAA-MM-DD).")
    n = 0
    for f in db.query(AutosIAFato).filter(AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO, AutosIAFato.peca_id == peca_id).all():
        d = dict(f.dados or {})
        if data:
            d["intimacao_data"] = data
        else:
            d.pop("intimacao_data", None)
        f.dados = d
        n += 1
    if n == 0:
        raise DeterminacaoErro("Decisão sem ordens extraídas.")
    db.commit()
    return n


def minuta_descumprimento(db, caso_id, destinatario_tipo: str | None = None, hoje: date | None = None) -> str:
    """Quadro de ordens vencidas sem cumprimento (e parciais), em Markdown, para colar numa petição."""
    hoje = hoje or date.today()
    r = listar(db, caso_id, {"destinatario_tipo": destinatario_tipo} if destinatario_tipo else None, hoje)
    alvo = [i for i in r["itens"] if i["status"] in ("vencida_sem_cumprimento", "nao_localizada", "parcial")]
    cab = f"## Quadro de ordens do Juízo sem cumprimento comprovado nos autos (posição em {hoje.strftime('%d/%m/%Y')})\n"
    if not alvo:
        return cab + "\nNenhuma ordem vencida sem cumprimento foi identificada com os dados atuais.\n"
    linhas = [cab, "| Decisão | Item | Destinatário | Ordem | Prazo | Situação | Sanção |", "|---|---|---|---|---|---|---|"]
    rotulo = {"vencida_sem_cumprimento": "vencida, sem cumprimento localizado", "nao_localizada": "cumprimento não localizado", "parcial": "cumprida só em parte"}
    for i in alvo:
        dec = f"ID {i['decisao']['id_processual']} ({(i['decisao_data'] or '')[:10]})"
        prazo = (f"{i['vencimento'][8:10]}/{i['vencimento'][5:7]}/{i['vencimento'][:4]}" + (" (est.)" if i["vencimento_estimado"] else "")) if i["vencimento"] else (i["prazo_condicao"] or "—")
        linhas.append(f"| {dec} | {i['ordem'] or '—'} | {i['destinatario']} | {(i['acao'] or '').replace('|', '/')} | {prazo} | {rotulo[i['status']]} | {(i['sancao'] or '—').replace('|', '/')} |")
    linhas.append("\n_Prazos estimados em dias úteis a partir da data indicada; conferir a contagem pela intimação efetiva. Cumprimento aferido pelo exame das peças posteriores — conferir no inteiro teor antes de afirmar em juízo._")
    return "\n".join(linhas) + "\n"
