"""Banco de fatos — VALORES (R$) das peças narrativas dos autos + reconciliador de números.

Fluxo:
1. Só as peças NARRATIVAS (petições, decisões, pareceres, ofícios — onde alguém AFIRMA um número)
   entram; os anexos (extratos, cronogramas, planilhas: 86% das cifras dos autos) ficam de fora e
   servem como CORROBORAÇÃO ("este mesmo valor aparece no comprovante X").
2. Candidatos por regex, deterministicamente (valor normalizado em centavos, com o contexto).
3. A IA só RÓTULA cada candidato (tema, sujeito, natureza, data de referência) — não inventa números.
4. A IA unifica os nomes dos sujeitos ("Grupo Apex" = "Apex Partners Gestão de Ativos S.A.").
5. Tudo guarda peça + trecho; uma pessoa valida, edita ou rejeita. Edição/validação humana nunca é
   sobrescrita por uma nova extração.
"""
import hashlib
import logging
import re
import threading
import unicodedata
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, or_, text

from app.database import SessionLocal
from app.models.andamento import AndamentoProcesso
from app.models.autos_ia import AutosIACaso, AutosIAFato, AutosIAPeca
from app.services.autos_ia.advogados_partes import _TIPO_ANEXO_PJE, eh_peticao, normalizar_partes
from app.services.autos_ia.precos import calcular_custo_usd

logger = logging.getLogger(__name__)

TIPO_FATO = "valor"
MODELO = "claude-sonnet-5"
VALOR_MINIMO_CENTAVOS = 1_000_000      # R$ 10.000 — abaixo disso é custa/taxa/ruído para a negociação
LOTE_CANDIDATOS = 35                   # candidatos por chamada de IA
PARALELO = 3
_TEXTO_MIN = 200

TEMAS = [
    "ativo_total", "passivo_total", "endividamento_bruto", "divida_liquida", "passivo_debentures",
    "passivo_cashback", "passivo_bancario", "passivo_tributario", "passivo_concursal", "patrimonio_liquido",
    "caixa_ou_saldo", "valor_investido_aporte", "valor_em_risco_prejuizo", "ativos_sob_custodia",
    "credito_ou_divida", "valor_da_causa_ou_pedido", "pagamento_ou_restituicao", "captacao_ou_emissao",
    "honorarios_custas", "receita_ou_faturamento", "outro",
]
TEMA_ROTULO = {
    "ativo_total": "Ativo", "passivo_total": "Passivo total", "endividamento_bruto": "Endividamento bruto",
    "divida_liquida": "Dívida líquida", "passivo_debentures": "Debêntures", "passivo_cashback": "Cashback / recompra",
    "passivo_bancario": "Dívida bancária", "passivo_tributario": "Passivo tributário", "passivo_concursal": "Passivo concursal",
    "patrimonio_liquido": "Patrimônio líquido", "caixa_ou_saldo": "Caixa / saldo",
    "valor_investido_aporte": "Valor investido / aporte", "valor_em_risco_prejuizo": "Valor em risco / prejuízo",
    "ativos_sob_custodia": "Ativos sob custódia", "credito_ou_divida": "Crédito / dívida (outros)",
    "valor_da_causa_ou_pedido": "Valor da causa / pedido", "pagamento_ou_restituicao": "Pagamento / restituição",
    "captacao_ou_emissao": "Captação / emissão", "honorarios_custas": "Honorários / custas",
    "receita_ou_faturamento": "Receita / faturamento", "outro": "Outro",
}
_DEFINICAO_TEMAS = (
    "ativo_total = ativo (total ou consolidado) · passivo_total = passivo total/obrigações totais declaradas · "
    "endividamento_bruto = dívida bruta/endividamento total declarado (antes de abater caixa) · divida_liquida = dívida "
    "menos caixa · passivo_debentures = saldo de debêntures · passivo_cashback = obrigações de cashback/recompra com "
    "clientes · passivo_bancario = empréstimos/dívida bancária · passivo_tributario = tributos e parcelamentos · "
    "passivo_concursal = créditos sujeitos à recuperação judicial · caixa_ou_saldo = caixa, equivalentes ou saldo de "
    "conta · valor_investido_aporte = quanto uma pessoa/grupo aportou ou investiu · valor_em_risco_prejuizo = quanto "
    "está em risco, foi perdido ou desviado · ativos_sob_custodia = ativos geridos/custodiados · credito_ou_divida = "
    "outro crédito/dívida específico que não se encaixa acima · valor_da_causa_ou_pedido = valor da causa ou "
    "quantia postulada · pagamento_ou_restituicao = pagamento, restituição ou repasse efetuado · captacao_ou_emissao = "
    "captação/emissão de valores mobiliários · receita_ou_faturamento · honorarios_custas · outro."
)
NATUREZAS = [
    "afirmacao_propria", "citacao_de_terceiro", "determinacao_ou_decisao", "estimativa_ou_calculo",
    "pedido", "irrelevante",
]
STATUS = ("extraido", "validado", "rejeitado")


# ── 1. Quais peças e quais candidatos ────────────────────────────────────────

_RE_NAO_NARRATIVA_PJE = re.compile(r"^(?:procura|demonstra|certid[aã]o regularidade)", re.I)
_RE_ATO_JUIZO_PJE = re.compile(r"^(?:decis|outras decis|despacho|parecer|of[ií]cio|senten)", re.I)


def peca_narrativa(tipo_pje: str | None, tipo_ia: str | None, tem_arquivo: bool, texto: str | None) -> bool:
    """Peça em que alguém AFIRMA números (petição, decisão, parecer, ofício) — não anexo."""
    if len((texto or "").strip()) < _TEXTO_MIN:
        return False
    t = (tipo_pje or "").strip()
    if _TIPO_ANEXO_PJE.match(t) or _RE_NAO_NARRATIVA_PJE.match(t):
        return False
    if eh_peticao(tipo_pje, tipo_ia, tem_arquivo, texto):
        return True
    return tipo_ia in ("decisao", "despacho", "oficio", "recurso") or bool(_RE_ATO_JUIZO_PJE.match(t))


_RE_VALOR = re.compile(
    r"R\$\s?(\d[\d.]*(?:,\d{1,2})?)(?:\s?(mil|milh(?:ão|ões)|mi|bilh(?:ão|ões)|bi)\b)?", re.I)
_MULT = {"mil": 10**3, "milhão": 10**6, "milhões": 10**6, "mi": 10**6, "bilhão": 10**9, "bilhões": 10**9, "bi": 10**9}


def parse_valor(numero: str, mult: str | None = None) -> int | None:
    """"1.234,56" → 123456 · "8,1"+"bilhões" → 810000000000 · "66"+"mil" → 6600000 (centavos).
    Ambíguo ("1.5" sem multiplicador) → None."""
    n = numero.strip(".")
    try:
        if "," in n:
            inteiro, dec = n.rsplit(",", 1)
            base = Decimal(inteiro.replace(".", "") + "." + dec)
        elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", n) or n.isdigit():
            base = Decimal(n.replace(".", ""))
        elif mult and re.fullmatch(r"\d+\.\d+", n):
            base = Decimal(n)
        else:
            return None
        if mult:
            base *= _MULT[mult.lower()]
        return int((base * 100).to_integral_value())
    except (InvalidOperation, KeyError, ValueError):
        return None


@dataclass
class Candidato:
    valor_centavos: int
    rotulo: str
    pos: int
    contexto: str
    ocorrencias: int = 1


def candidatos_valores(texto: str | None) -> list[Candidato]:
    """Valores em R$ ≥ mínimo, com o contexto. O mesmo valor repetido na mesma peça vira um só
    candidato (primeira ocorrência), com a contagem."""
    if not texto:
        return []
    tn = re.sub(r"\s+", " ", texto)
    por_valor: dict[int, Candidato] = {}
    for m in _RE_VALOR.finditer(tn):
        v = parse_valor(m.group(1), m.group(2))
        if v is None or v < VALOR_MINIMO_CENTAVOS:
            continue
        if v in por_valor:
            por_valor[v].ocorrencias += 1
            continue
        # o valor exato vai marcado (⟦…⟧): o contexto de valores vizinhos se sobrepõe e a IA precisa
        # saber de QUAL número se trata
        ctx = tn[max(0, m.start() - 240): m.start()] + "⟦" + m.group(0).strip() + "⟧" + tn[m.end(): m.end() + 170]
        por_valor[v] = Candidato(v, m.group(0).strip(), m.start(), ctx)
    return list(por_valor.values())


def fmt_brl(centavos: int | None) -> str:
    if centavos is None:
        return ""
    reais, cent = divmod(abs(centavos), 100)
    s = f"{reais:,}".replace(",", ".")
    return f"{'-' if centavos < 0 else ''}R$ {s},{cent:02d}"


# ── 2. Rotulagem por IA ──────────────────────────────────────────────────────

TOOL_ROTULOS = {
    "name": "registrar_rotulos",
    "description": "Registra, para cada valor em R$ citado numa peça, o que ele é, a quem se refere e quem o afirma.",
    "input_schema": {
        "type": "object",
        "properties": {
            "rotulos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "i": {"type": "integer", "description": "Índice [i] do valor, como numerado no pedido."},
                        "tema": {"type": "string", "enum": TEMAS,
                                 "description": "O que o valor representa. " + _DEFINICAO_TEMAS},
                        "sujeito": {"type": ["string", "null"],
                                    "description": "Pessoa/empresa/veículo (SPE, SCP, fundo, grupo) a quem o valor se refere, "
                                                   "do jeito que a peça o escreve. Null se não identificável."},
                        "natureza": {"type": "string", "enum": NATUREZAS,
                                     "description": "afirmacao_propria = o autor da peça afirma o número como fato/cálculo seu; "
                                                    "citacao_de_terceiro = a peça reproduz número de outra fonte (parecer do AJ, outra "
                                                    "parte, documento); determinacao_ou_decisao = o Juízo fixa/determina o valor; "
                                                    "estimativa_ou_calculo = projeção/cálculo; pedido = valor que se requer/postula; "
                                                    "irrelevante = não é um valor econômico do caso (número de processo, página, "
                                                    "capital de qualificação, exemplo hipotético, preço trivial)."},
                        "fonte_citada": {"type": ["string", "null"],
                                         "description": "Se natureza=citacao_de_terceiro: quem/qual documento é a fonte. Senão null."},
                        "data_ref": {"type": ["string", "null"],
                                     "description": "Data a que o valor se refere (não a da peça): AAAA, AAAA-MM ou AAAA-MM-DD. "
                                                    "Null se não consta."},
                        "confianca": {"type": "number", "description": "0 a 1."},
                    },
                    "required": ["i", "tema", "sujeito", "natureza", "confianca"],
                },
            }
        },
        "required": ["rotulos"],
    },
}

SISTEMA_ROTULOS = (
    "Você é um analista jurídico-financeiro que mapeia, nos autos de uma recuperação judicial, os números que as "
    "partes, o Ministério Público, o administrador judicial e o Juízo afirmam. Para cada valor em R$ citado, indique "
    "o que é, a quem se refere e a natureza da afirmação. REGRAS: nunca invente nem altere números — você só rotula "
    "os que foram fornecidos; baseie-se apenas no contexto dado; se o sujeito não estiver claro, use null; na dúvida "
    "entre afirmação própria e citação de terceiro, prefira citacao_de_terceiro quando o contexto atribui o número a "
    "outra fonte; valores sem relevância econômica para o caso são 'irrelevante'."
)


def _cliente():
    import anthropic
    return anthropic.Anthropic(timeout=120.0, max_retries=2)


_RE_DATA_REF = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def _tool_input(resp, nome: str) -> dict:
    for bloco in resp.content:
        if bloco.type == "tool_use" and bloco.name == nome:
            return bloco.input
    raise RuntimeError(f"A IA não devolveu {nome} via tool_use")


def rotular(info: dict, cands: list[Candidato], cliente=None) -> tuple[dict[int, dict], float]:
    """Rotula os candidatos de UMA peça (em lotes). Devolve ({índice: rótulo}, custo_usd)."""
    cliente = cliente or _cliente()
    saida: dict[int, dict] = {}
    custo = 0.0
    for ini in range(0, len(cands), LOTE_CANDIDATOS):
        lote = cands[ini: ini + LOTE_CANDIDATOS]
        linhas = [
            f"[{ini + k}] {fmt_brl(c.valor_centavos)} (escrito: “{c.rotulo}”) — contexto: «{c.contexto}»"
            for k, c in enumerate(lote)
        ]
        prompt = (
            f"Peça: ID {info.get('id_processual') or 's/ ID'} · tipo no PJe: {info.get('tipo_pje') or '—'} · "
            f"autor/peticionante: {info.get('autor') or '—'} · data: {info.get('data') or '—'}.\n\n"
            "Valores a rotular:\n" + "\n".join(linhas)
        )
        resp = cliente.messages.create(
            model=MODELO, max_tokens=4096, system=SISTEMA_ROTULOS, tools=[TOOL_ROTULOS],
            tool_choice={"type": "tool", "name": "registrar_rotulos"},
            messages=[{"role": "user", "content": prompt}],
        )
        custo += calcular_custo_usd(resp.usage.input_tokens, resp.usage.output_tokens)
        dados = _tool_input(resp, "registrar_rotulos")
        itens = dados.get("rotulos")
        if not isinstance(itens, list):
            continue
        for it in itens:
            try:
                i = int(it.get("i"))
            except (TypeError, ValueError):
                continue
            if not (ini <= i < ini + len(lote)):
                continue
            tema = it.get("tema") if it.get("tema") in TEMAS else "outro"
            natureza = it.get("natureza") if it.get("natureza") in NATUREZAS else "afirmacao_propria"
            dr = it.get("data_ref")
            try:
                conf = max(0.0, min(1.0, float(it.get("confianca"))))
            except (TypeError, ValueError):
                conf = None
            saida[i] = {
                "tema": tema,
                "sujeito": (str(it["sujeito"]).strip()[:255] or None) if it.get("sujeito") else None,
                "natureza": natureza,
                "fonte_citada": (str(it["fonte_citada"]).strip()[:255] or None) if it.get("fonte_citada") else None,
                "data_ref": dr if isinstance(dr, str) and _RE_DATA_REF.match(dr) else None,
                "confianca": conf,
            }
    return saida, custo


TOOL_CONSOLIDAR = {
    "name": "registrar_grupos",
    "description": "Agrupa variações de nome que se referem à MESMA pessoa/empresa/veículo.",
    "input_schema": {
        "type": "object",
        "properties": {
            "grupos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "canonico": {"type": "string", "description": "O nome mais completo e formal do grupo."},
                        "variantes": {"type": "array", "items": {"type": "string"},
                                      "description": "Os nomes da lista (exatamente como fornecidos) que são a mesma entidade."},
                    },
                    "required": ["canonico", "variantes"],
                },
            }
        },
        "required": ["grupos"],
    },
}
SISTEMA_CONSOLIDAR = (
    "Você unifica nomes de pessoas, empresas e veículos (SPE, SCP, fundos, grupos) citados nos autos de uma "
    "recuperação judicial. Agrupe SÓ variações da mesma entidade (abreviação, caixa, 'S.A.' vs 'SA', razão social vs "
    "nome curto, 'Grupo X' quando claramente se refere à mesma sociedade controladora). NÃO una entidades diferentes "
    "só por terem nome parecido — por exemplo, 'BRM Apex Inv RE Vizzo' e 'BRM Apex Inv RE Pedra Azul' são veículos "
    "distintos; um grupo econômico NÃO é a soma de suas empresas. Na dúvida, não una. Use os nomes exatamente como "
    "foram fornecidos em 'variantes'."
)
MAX_SUJEITOS_CONSOLIDAR = 600


def consolidar_nomes(nomes: list[str], cliente=None) -> tuple[dict[str, str], float]:
    """{variante: canônico} — só para o que a IA agrupou. Devolve também o custo."""
    nomes = list(dict.fromkeys(n for n in nomes if n))
    if len(nomes) < 2:
        return {}, 0.0
    cliente = cliente or _cliente()
    prompt = "Nomes (um por linha):\n" + "\n".join(f"- {n}" for n in nomes[:MAX_SUJEITOS_CONSOLIDAR])
    resp = cliente.messages.create(
        model=MODELO, max_tokens=8000, system=SISTEMA_CONSOLIDAR, tools=[TOOL_CONSOLIDAR],
        tool_choice={"type": "tool", "name": "registrar_grupos"},
        messages=[{"role": "user", "content": prompt}],
    )
    custo = calcular_custo_usd(resp.usage.input_tokens, resp.usage.output_tokens)
    dados = _tool_input(resp, "registrar_grupos")
    validos = set(nomes)
    mapa: dict[str, str] = {}
    for g in dados.get("grupos") or []:
        can = str(g.get("canonico") or "").strip()[:255]
        for v in g.get("variantes") or []:
            if v in validos and can and v not in mapa:
                mapa[v] = can
    return mapa, custo


# ── 3. Persistência e execução ───────────────────────────────────────────────

def _hash_texto(texto: str) -> str:
    return hashlib.sha256((texto or "").encode("utf-8")).hexdigest()


def _persistir_peca(db, peca: AutosIAPeca, cands: list[Candidato], rotulos: dict[int, dict]) -> int:
    """Troca os fatos 'extraido' da peça pelos novos; validados/rejeitados (decisão humana) ficam."""
    db.query(AutosIAFato).filter(
        AutosIAFato.peca_id == peca.id, AutosIAFato.tipo == TIPO_FATO, AutosIAFato.status == "extraido"
    ).delete(synchronize_session=False)
    mantidas = {p for (p,) in db.query(AutosIAFato.pos).filter(AutosIAFato.peca_id == peca.id, AutosIAFato.tipo == TIPO_FATO)}
    n = 0
    for i, c in enumerate(cands):
        r = rotulos.get(i)
        if r is None or r["natureza"] == "irrelevante" or c.pos in mantidas:
            continue
        db.add(AutosIAFato(
            caso_id=peca.caso_id, peca_id=peca.id, tipo=TIPO_FATO, tema=r["tema"], sujeito=r["sujeito"],
            natureza=r["natureza"], fonte_citada=r["fonte_citada"], valor_centavos=c.valor_centavos,
            data_ref=r["data_ref"], rotulo_original=c.rotulo[:120], trecho=c.contexto, pos=c.pos,
            confianca=r["confianca"], origem="ia", status="extraido", dados={"ocorrencias": c.ocorrencias},
        ))
        n += 1
    peca.fatos_valores_hash = _hash_texto(peca.texto_md)
    peca.fatos_valores_em = datetime.now(timezone.utc)
    return n


_LOCK = threading.Lock()
_PROGRESSO: dict[str, dict] = {}


def pecas_para_extrair(db, caso_id, forcar: bool = False) -> list[uuid.UUID]:
    q = (
        db.query(
            AutosIAPeca.id, AutosIAPeca.texto_md, AutosIAPeca.tipo, AutosIAPeca.fatos_valores_hash,
            AndamentoProcesso.tipo, AndamentoProcesso.arquivo_nome, AndamentoProcesso.documento_id,
            AndamentoProcesso.arquivo_drive_link,
        )
        .outerjoin(AndamentoProcesso, AutosIAPeca.andamento_id == AndamentoProcesso.id)
        .filter(AutosIAPeca.caso_id == caso_id)
        .order_by(AndamentoProcesso.data_andamento.asc().nulls_last(), AutosIAPeca.id_processual)
    )
    ids = []
    for pid, texto, tipo_ia, h, tipo_pje, arq, doc, link in q.all():
        if not peca_narrativa(tipo_pje, tipo_ia, bool(arq or doc or link), texto):
            continue
        if not candidatos_valores(texto):
            continue
        if forcar or h != _hash_texto(texto):
            ids.append(pid)
    return ids


def status_extracao(db, caso_id) -> dict:
    p = dict(_PROGRESSO.get(str(caso_id)) or {})
    total_fatos = db.query(func.count(AutosIAFato.id)).filter(AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO).scalar()
    validados = db.query(func.count(AutosIAFato.id)).filter(
        AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO, AutosIAFato.status == "validado").scalar()
    pecas_com_fatos = db.query(func.count(func.distinct(AutosIAFato.peca_id))).filter(
        AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO).scalar()
    pendentes = len(pecas_para_extrair(db, caso_id))
    return {
        "estado": p.get("estado", "ocioso"), "total_fatos": total_fatos, "validados": validados,
        "pecas_com_fatos": pecas_com_fatos, "pecas_pendentes": pendentes,
        "total": p.get("total", 0), "feitos": p.get("feitos", 0), "fatos_novos": p.get("fatos_novos", 0),
        "erros": p.get("erros", 0), "custo_usd": round(p.get("custo_usd", 0.0), 4), "mensagem": p.get("mensagem"),
    }


def extrair_caso(caso_id: uuid.UUID, forcar: bool = False, limite_pecas: int | None = None, cliente=None) -> dict:
    """Extrai e rotula os valores das peças narrativas que ainda não foram (ou cujo texto mudou).
    Uma execução por vez. Nunca lança."""
    if not _LOCK.acquire(blocking=False):
        return {"estado": "rodando", "mensagem": "Já há uma extração em andamento."}
    db = SessionLocal()
    chave = str(caso_id)
    try:
        _PROGRESSO[chave] = {"estado": "rodando", "total": 0, "feitos": 0, "fatos_novos": 0, "erros": 0,
                             "custo_usd": 0.0, "mensagem": "Selecionando peças…"}
        prog = _PROGRESSO[chave]
        ids = pecas_para_extrair(db, caso_id, forcar)
        if limite_pecas:
            ids = ids[:limite_pecas]
        prog["total"] = len(ids)
        prog["mensagem"] = f"Rotulando valores de {len(ids)} peça(s)…"
        cliente = cliente or _cliente()
        custo_total = 0.0

        def _um(args):
            pid, info, cands = args
            try:
                rot, custo = rotular(info, cands, cliente)
                return pid, cands, rot, custo, None
            except Exception as exc:  # noqa: BLE001 — cada peça falha isolada
                return pid, cands, {}, 0.0, str(exc)[:300]

        with ThreadPoolExecutor(max_workers=PARALELO) as pool:
            for ini in range(0, len(ids), 6):
                trabalhos = []
                for pid in ids[ini: ini + 6]:
                    peca = db.get(AutosIAPeca, pid)
                    andamento = db.get(AndamentoProcesso, peca.andamento_id) if peca.andamento_id else None
                    info = {"id_processual": peca.id_processual, "tipo_pje": andamento.tipo if andamento else None,
                            "autor": peca.autor, "data": str(andamento.data_andamento) if andamento and andamento.data_andamento else None}
                    trabalhos.append((pid, info, candidatos_valores(peca.texto_md)))
                for pid, cands, rot, custo, erro in pool.map(_um, trabalhos):
                    prog["feitos"] += 1
                    custo_total += custo
                    prog["custo_usd"] = custo_total
                    if erro:
                        prog["erros"] += 1
                        prog["mensagem"] = f"Falha: {erro}"
                        logger.warning("Fatos/valores: peça %s falhou: %s", pid, erro)
                        continue
                    prog["fatos_novos"] += _persistir_peca(db, db.get(AutosIAPeca, pid), cands, rot)
                db.commit()

        prog["mensagem"] = "Unificando nomes dos sujeitos…"
        try:
            custo_total += consolidar_sujeitos(db, caso_id, cliente)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fatos/valores: consolidação de sujeitos falhou: %s", exc)
            prog["mensagem"] = f"Valores extraídos; unificação de nomes falhou ({str(exc)[:120]})."
        caso = db.get(AutosIACaso, caso_id)
        if caso:
            caso.custo_usd_total = (caso.custo_usd_total or 0) + custo_total
        db.commit()
        prog["custo_usd"] = custo_total
        prog["estado"] = "concluido"
        if prog["mensagem"].startswith(("Unificando", "Rotulando")):
            prog["mensagem"] = (f"Concluído: {prog['fatos_novos']} valor(es) em {prog['feitos']} peça(s)"
                                + (f", {prog['erros']} com erro" if prog["erros"] else "") + f" · US$ {custo_total:.2f}.")
        return prog
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fatos/valores do caso %s falhou", caso_id)
        db.rollback()
        _PROGRESSO[chave] = {**_PROGRESSO.get(chave, {}), "estado": "erro", "mensagem": str(exc)[:300]}
        return _PROGRESSO[chave]
    finally:
        db.close()
        _LOCK.release()


def consolidar_sujeitos(db, caso_id, cliente=None) -> float:
    """Preenche `sujeito_canonico` (só onde ainda está vazio — edição humana não é sobrescrita)."""
    linhas = db.query(AutosIAFato.sujeito, func.count(AutosIAFato.id)).filter(
        AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO, AutosIAFato.sujeito.isnot(None),
        AutosIAFato.sujeito_canonico.is_(None), AutosIAFato.status != "rejeitado",
    ).group_by(AutosIAFato.sujeito).order_by(func.count(AutosIAFato.id).desc()).all()
    nomes = [s for s, _ in linhas]
    if not nomes:
        return 0.0
    mapa, custo = consolidar_nomes(nomes, cliente)
    for s in nomes:
        db.query(AutosIAFato).filter(
            AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO, AutosIAFato.sujeito == s,
            AutosIAFato.sujeito_canonico.is_(None),
        ).update({"sujeito_canonico": mapa.get(s, s)}, synchronize_session=False)
    db.commit()
    return custo


# ── 4. Leitura: afirmante, listagem, reconciliação, corroboração ─────────────

_RE_JUIZO = re.compile(r"ju[ií]zo|juiz|magistrad|vara\b", re.I)
_RE_MP = re.compile(r"minist[eé]rio p[uú]blico|promotor", re.I)
_RE_AJ = re.compile(r"administrador[a]?\s+judicial|laspro", re.I)


def afirmante_de(autor: str | None, tipo_ia: str | None, tipo_pje: str | None) -> tuple[str, str]:
    """(chave, rótulo) de quem afirma: Juízo, Ministério Público, Administrador Judicial ou a parte."""
    a = autor or ""
    if tipo_ia in ("decisao", "despacho") or _RE_JUIZO.search(a) or re.match(r"(?i)(decis|despacho|outras decis)", tipo_pje or ""):
        return "juizo", "Juízo"
    if _RE_MP.search(a):
        return "mp", "Ministério Público"
    if _RE_AJ.search(a) or re.search(r"(?i)administrador judicial", tipo_pje or ""):
        return "aj", "Administrador Judicial"
    partes = normalizar_partes(a)
    return (partes[0][0], partes[0][1]) if partes else ("desconhecido", "(não identificado)")


def chave_sujeito(s: str | None) -> str | None:
    if not s:
        return None
    t = "".join(c for c in unicodedata.normalize("NFKD", s.casefold()) if not unicodedata.combining(c))
    t = re.sub(r"\bs\s*/\s*a\b|\bs\.\s*a\b\.?", "sa", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip() or None


def _link_md(file_id):
    return f"https://drive.google.com/file/d/{file_id}/view" if file_id else None


def _linhas_fatos(db, caso_id, filtros: dict | None = None):
    f = filtros or {}
    q = (
        db.query(AutosIAFato, AutosIAPeca, AndamentoProcesso)
        .join(AutosIAPeca, AutosIAFato.peca_id == AutosIAPeca.id)
        .outerjoin(AndamentoProcesso, AutosIAPeca.andamento_id == AndamentoProcesso.id)
        .filter(AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO)
    )
    if f.get("status"):
        q = q.filter(AutosIAFato.status == f["status"])
    else:
        q = q.filter(AutosIAFato.status != "rejeitado")
    if f.get("tema"):
        q = q.filter(AutosIAFato.tema == f["tema"])
    if f.get("natureza"):
        q = q.filter(AutosIAFato.natureza == f["natureza"])
    if f.get("minimo") is not None:
        q = q.filter(AutosIAFato.valor_centavos >= f["minimo"])
    if f.get("maximo") is not None:
        q = q.filter(AutosIAFato.valor_centavos <= f["maximo"])
    if f.get("q"):
        like = f"%{f['q']}%"
        q = q.filter(or_(AutosIAFato.sujeito.ilike(like), AutosIAFato.sujeito_canonico.ilike(like),
                         AutosIAFato.trecho.ilike(like), AutosIAFato.nota.ilike(like)))
    return q.order_by(AutosIAFato.valor_centavos.desc()).all()


def _fato_dict(fato: AutosIAFato, peca: AutosIAPeca, andamento: AndamentoProcesso | None) -> dict:
    chave_af, rot_af = afirmante_de(peca.autor, peca.tipo, andamento.tipo if andamento else None)
    return {
        "id": fato.id, "valor_centavos": fato.valor_centavos, "valor": fmt_brl(fato.valor_centavos),
        "rotulo_original": fato.rotulo_original, "tema": fato.tema, "tema_rotulo": TEMA_ROTULO.get(fato.tema or "outro", "Outro"),
        "sujeito": fato.sujeito, "sujeito_canonico": fato.sujeito_canonico or fato.sujeito,
        "natureza": fato.natureza, "fonte_citada": fato.fonte_citada, "data_ref": fato.data_ref,
        "trecho": fato.trecho, "confianca": fato.confianca, "status": fato.status, "nota": fato.nota,
        "ocorrencias": (fato.dados or {}).get("ocorrencias", 1),
        "afirmante": rot_af, "afirmante_chave": chave_af,
        "peticao": {
            "peca_id": peca.id, "id_processual": peca.id_processual,
            "data": (andamento.data_andamento if andamento and andamento.data_andamento else peca.data_peca),
            "titulo": peca.titulo_customizado or peca.titulo,
            "link_pdf": andamento.arquivo_drive_link if andamento else None, "link_md": _link_md(peca.md_drive_file_id),
        },
    }


def listar_fatos(db, caso_id, filtros: dict | None = None, limite: int = 200, offset: int = 0) -> dict:
    f = filtros or {}
    todas = [_fato_dict(*t) for t in _linhas_fatos(db, caso_id, f)]
    if f.get("afirmante"):
        todas = [x for x in todas if x["afirmante_chave"] == f["afirmante"]]
    return {"total": len(todas), "itens": todas[offset: offset + limite]}


def _clusters(valores: list[int], tolerancia: float = 0.01) -> list[list[int]]:
    """Agrupa valores próximos (≤1% de diferença) — 'R$ 8,1 bi' e 'R$ 8.098.000.000' são o mesmo número."""
    out: list[list[int]] = []
    for v in sorted(set(valores)):
        if out and out[-1][-1] > 0 and (v - out[-1][-1]) / out[-1][-1] <= tolerancia:
            out[-1].append(v)
        else:
            out.append([v])
    return out


_TEMAS_COMPARAVEIS = set(TEMAS) - {"outro", "honorarios_custas"}
# Temas que costumam reunir itens DIFERENTES sob o mesmo sujeito (cada crédito, pagamento ou aporte é um
# número próprio): a diferença entre eles raramente é divergência — vão para o fim da fila e ficam sinalizados.
_TEMAS_RUIDOSOS = {"credito_ou_divida", "pagamento_ou_restituicao", "captacao_ou_emissao", "valor_investido_aporte", "valor_da_causa_ou_pedido"}


def reconciliar(db, caso_id) -> dict:
    """Divergências (mesmo tema+sujeito, números diferentes) e corroborações (mesmo número em várias peças)."""
    fatos = [_fato_dict(*t) for t in _linhas_fatos(db, caso_id)]
    por_grupo: dict[tuple, list[dict]] = defaultdict(list)
    for x in fatos:
        ck = chave_sujeito(x["sujeito_canonico"])
        if ck and x["tema"] in _TEMAS_COMPARAVEIS and x["natureza"] != "irrelevante":
            por_grupo[(x["tema"], ck)].append(x)
    divergencias = []
    for (tema, ck), itens in por_grupo.items():
        cl = _clusters([i["valor_centavos"] for i in itens])
        pecas = {i["peticao"]["peca_id"] for i in itens}
        if len(cl) < 2 or len(pecas) < 2:
            continue
        valores = []
        for grupo in cl:
            membros = [i for i in itens if i["valor_centavos"] in grupo]
            valores.append({
                "valor_centavos": grupo[0] if len(grupo) == 1 else int(sum(grupo) / len(grupo)),
                "valor": fmt_brl(grupo[0]) if len(grupo) == 1 else f"≈ {fmt_brl(int(sum(grupo) / len(grupo)))}",
                "afirmantes": sorted({m["afirmante"] for m in membros}),
                "fatos": sorted(membros, key=lambda m: (m["peticao"]["data"] is None, m["peticao"]["data"] or 0)),
            })
        valores.sort(key=lambda v: v["valor_centavos"])
        menor, maior = valores[0]["valor_centavos"], valores[-1]["valor_centavos"]
        divergencias.append({
            "tema": tema, "tema_rotulo": TEMA_ROTULO[tema], "sujeito": itens[0]["sujeito_canonico"],
            "valores": valores, "afirmantes": sorted({a for v in valores for a in v["afirmantes"]}),
            "razao": round(maior / menor, 2) if menor > 0 else None, "n_fatos": len(itens),
            "ruidosa": tema in _TEMAS_RUIDOSOS,
        })
    divergencias.sort(key=lambda d: (d["ruidosa"], -len(d["afirmantes"]), -(d["razao"] or 0), -d["n_fatos"]))

    por_valor: dict[int, list[dict]] = defaultdict(list)
    for x in fatos:
        if x["natureza"] != "irrelevante":
            por_valor[x["valor_centavos"]].append(x)
    corroboracoes = []
    for v, itens in por_valor.items():
        pecas = {i["peticao"]["peca_id"] for i in itens}
        if len(pecas) < 2:
            continue
        corroboracoes.append({
            "valor_centavos": v, "valor": fmt_brl(v), "n_pecas": len(pecas),
            "afirmantes": sorted({i["afirmante"] for i in itens}),
            "temas": sorted({i["tema_rotulo"] for i in itens}),
            "sujeitos": sorted({i["sujeito_canonico"] for i in itens if i["sujeito_canonico"]})[:6],
            "fatos": sorted(itens, key=lambda m: (m["peticao"]["data"] is None, m["peticao"]["data"] or 0)),
        })
    corroboracoes.sort(key=lambda c: (-len(c["afirmantes"]), -c["n_pecas"], -c["valor_centavos"]))
    return {
        "resumo": {"fatos": len(fatos), "divergencias": len(divergencias), "corroboracoes": len(corroboracoes),
                   "validados": sum(1 for x in fatos if x["status"] == "validado")},
        "divergencias": divergencias, "corroboracoes": corroboracoes,
    }


def anexos_com_valor(db, caso_id, fato_id, limite: int = 25) -> list[dict]:
    """Outras peças do caso (sobretudo anexos) em que o mesmo valor aparece escrito igual ("913.271,38") — corroboração/origem."""
    fato = db.get(AutosIAFato, fato_id)
    if fato is None or fato.caso_id != caso_id or not fato.valor_centavos:
        return []
    reais, cent = divmod(fato.valor_centavos, 100)
    padrao = f"{reais:,}".replace(",", ".") + f",{cent:02d}"
    linhas = db.execute(text(
        "SELECT p.id, p.id_processual, p.titulo, a.tipo, a.data_andamento, a.arquivo_drive_link, p.md_drive_file_id, "
        "(length(p.texto_md) - length(replace(p.texto_md, :pad, ''))) / length(:pad) AS n, "
        "substr(p.texto_md, greatest(strpos(p.texto_md, :pad) - 160, 1), 340) AS trecho "
        "FROM autos_ia_pecas p LEFT JOIN andamentos_processo a ON a.id = p.andamento_id "
        "WHERE p.caso_id = :c AND p.id <> :origem AND strpos(p.texto_md, :pad) > 0 "
        "ORDER BY n DESC LIMIT :lim"
    ), {"pad": padrao, "c": caso_id, "origem": fato.peca_id, "lim": limite}).fetchall()
    return [{
        "peca_id": r[0], "id_processual": r[1], "titulo": r[2], "tipo_pje": r[3], "data": r[4],
        "link_pdf": r[5], "link_md": _link_md(r[6]), "ocorrencias": int(r[7] or 0),
        "trecho": re.sub(r"\s+", " ", r[8] or ""),
    } for r in linhas]


class FatoErro(ValueError):
    pass


def atualizar_fato(db, caso_id, fato_id, tema=None, sujeito_canonico=None, status=None, nota=None, nota_definida=False) -> dict:
    """Valida, rejeita ou edita um fato. Editar tema/sujeito conta como validação humana."""
    fato = db.get(AutosIAFato, fato_id)
    if fato is None or fato.caso_id != caso_id:
        raise FatoErro("Fato não encontrado.")
    if status is not None and status not in STATUS:
        raise FatoErro("Status inválido.")
    if tema is not None:
        if tema not in TEMAS:
            raise FatoErro("Tema inválido.")
        fato.tema = tema
    if sujeito_canonico is not None:
        s = re.sub(r"\s+", " ", sujeito_canonico).strip()
        fato.sujeito_canonico = s[:255] or None
    if nota_definida:
        fato.nota = (nota or "").strip() or None
    if status is not None:
        fato.status = status
    elif tema is not None or sujeito_canonico is not None:
        fato.status = "validado"
    fato.origem = "ia" if fato.origem == "ia" and fato.status == "extraido" else fato.origem
    db.commit()
    db.refresh(fato)
    row = db.query(AutosIAFato, AutosIAPeca, AndamentoProcesso).join(AutosIAPeca, AutosIAFato.peca_id == AutosIAPeca.id) \
        .outerjoin(AndamentoProcesso, AutosIAPeca.andamento_id == AndamentoProcesso.id).filter(AutosIAFato.id == fato_id).one()
    return _fato_dict(*row)


def renomear_sujeito(db, caso_id, de: str, para: str) -> int:
    """Unifica à mão: todos os fatos (não rejeitados) cujo sujeito atual é `de` passam a `para`."""
    para = re.sub(r"\s+", " ", para or "").strip()[:255]
    de = (de or "").strip()
    if not para or not de:
        raise FatoErro("Informe o nome atual e o novo.")
    n = db.query(AutosIAFato).filter(
        AutosIAFato.caso_id == caso_id, AutosIAFato.tipo == TIPO_FATO, AutosIAFato.status != "rejeitado",
        func.coalesce(AutosIAFato.sujeito_canonico, AutosIAFato.sujeito) == de,
    ).update({"sujeito_canonico": para}, synchronize_session=False)
    db.commit()
    return n
