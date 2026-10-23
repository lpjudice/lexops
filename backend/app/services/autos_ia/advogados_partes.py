"""Relação advogados × partes, a partir das PETIÇÕES do caso (nunca dos documentos).

Regra: quem assina/qualifica uma petição (OAB/UF + número) representa a parte que a peticionou
(`autos_ia_pecas.autor`). Então cada petição gera vínculos (advogado ↔ parte) e a tela agrega:
por advogado → todas as partes; por parte → todos os advogados.

Extração determinística (sem IA, sem custo, auditável): o advogado é identificado pela OAB
(UF + número) — o nome é só rótulo (varia: "JOSÉ CARLOS STEIN JR." / "José Carlos Stein Junior").
Só contam menções de OAB na ASSINATURA (fim) ou na QUALIFICAÇÃO (início) da petição; OAB citada no
meio do texto costuma ser de advogado de outra parte e é ignorada.
"""
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

TIPOS_PETICAO = ("peticao", "recurso")

_UFS = ("AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO")
_NUM = r"(\d{1,3}(?:\.\d{3})+|\d{3,6})"
# OAB/ES 4.939 · OAB-ES nº 4.939 · OAB/ES sob o nº 14.477 · OAB nº 4.939/ES
_OAB_UF_NUM = re.compile(rf"OAB\s*[/\-–.]?\s*(?-i:({_UFS}))\b[^\d]{{0,16}}?{_NUM}", re.I)
_OAB_NUM_UF = re.compile(rf"OAB\s*(?:n[ºo°.]*\s*)?{_NUM}\s*[/\-–]\s*(?-i:({_UFS}))\b", re.I)

_ZONA_ASSINATURA = 1400   # últimos N caracteres
_ZONA_QUALIFICACAO = 3000  # primeiros N caracteres

_CONECTORES = {"de", "da", "do", "das", "dos", "e", "von", "van", "di"}
_ABREV = {"jr", "dr", "dra", "sr", "sra", "filho", "neto", "junior", "júnior", "prof", "profa"}
_PARADA = {
    "deferimento", "termos", "pede", "pedem", "requer", "requerem", "nestes", "nesses", "esses", "estes", "que",
    "advogado", "advogada", "advogados", "advogadas", "procurador", "procuradora", "inscrito", "inscrita",
    "oab", "dr", "dra", "assinado", "digitalmente", "email", "e-mail", "emails", "telefone", "sócio", "socio",
    "janeiro", "fevereiro", "março", "marco", "abril", "maio", "junho", "julho", "agosto", "setembro",
    "outubro", "novembro", "dezembro", "vitória", "vitoria", "paulo", "janeiro/es", "es", "sp", "rj",
    "p.", "pp.", "obs", "ciente", "cumpra-se", "atenciosamente", "respeitosamente", "ao", "à", "por",
}
_TITULOS = {"dr", "dra", "sr", "sra", "prof", "profa", "doutor", "doutora"}
_FIM_FRASE = re.compile(r"[.;:,!?)\]]$")
_MAIUSC = "A-ZÁÀÂÃÉÈÊÍÓÔÕÚÇ"


@dataclass(frozen=True)
class AdvogadoEncontrado:
    oab: str            # "OAB/ES 4939" — chave canônica
    nome: str | None
    zona: str           # "assinatura" | "qualificacao" | "corpo"
    pessoa: str | None = None   # OAB "cabeça" quando esta é outra inscrição da MESMA pessoa


def _numero(n: str) -> str:
    return re.sub(r"\D", "", n)


def _nome_antes(texto: str, ini: int) -> str | None:
    """Nome (2+ palavras capitalizadas) imediatamente antes de `ini`, parando em pontuação de
    fim de frase, palavra de rotina ("Pede deferimento"), número ou muito material."""
    janela = texto[max(0, ini - 150): ini]
    # tira, do fim, o que liga o nome à OAB: "(", "- ", "advogado", "inscrito na", "sob o nº"
    ligacao = re.compile(
        r"[\s,;:(\[\-–—/]*(?:advogad[oa]s?|inscrit[oa]s?(?:\s+na)?|regularmente|devidamente|"
        r"portador[a]?|brasileir[oa]|casad[oa]|solteir[oa])?[\s,;:(\[\-–—/]*$", re.I)
    for _ in range(6):  # "…, brasileira, advogada, inscrita na" tem vários qualificativos em fila
        nova = ligacao.sub("", janela)
        if nova == janela:
            break
        janela = nova
    tokens = janela.split()
    nome: list[str] = []
    for tok in reversed(tokens):
        limpo = tok.strip("()[]\"'“”,;:")
        baixo = limpo.lower()
        if not limpo:
            break
        eh_conector = baixo in _CONECTORES
        eh_nome = bool(re.match(rf"^[{_MAIUSC}][\wÀ-ÿ'’.\-]*$", limpo)) and not any(c.isdigit() for c in limpo)
        if baixo in _PARADA or not (eh_nome or eh_conector):
            break
        # fronteira de frase: o token à ESQUERDA termina em pontuação forte (ex.: "Deferimento.")
        inicial = bool(re.match(rf"^[{_MAIUSC}]\.$", limpo))
        if nome and _FIM_FRASE.search(tok) and baixo.rstrip(".") not in _ABREV and not inicial:
            break
        nome.insert(0, limpo)
        if len(nome) >= 7:
            break
    while nome and (nome[0].lower() in _CONECTORES or nome[0].lower().rstrip(".") in _TITULOS):
        nome.pop(0)
    palavras = [p for p in nome if p.lower() not in _CONECTORES]
    return " ".join(nome) if len(palavras) >= 2 else None


def extrair_advogados(texto: str | None) -> list[AdvogadoEncontrado]:
    """Todas as OABs citadas no texto, com o nome que as precede e a zona da petição.

    Assinaturas de bancas grandes listam várias inscrições seguidas por pessoa
    ("NOME OAB/SP 1 OAB/ES 2 OAB/MG 3"): numa sequência de OABs separadas só por espaço, a
    primeira leva o nome; as seguintes são a MESMA pessoa se a UF for nova na sequência, e
    pessoa diferente (nome desconhecido) se a UF se repetir."""
    if not texto:
        return []
    n = len(texto)
    brutos: dict[tuple[int, str], tuple[int, int, str, str | None, bool]] = {}
    for rx, i_uf, i_num in ((_OAB_UF_NUM, 1, 2), (_OAB_NUM_UF, 2, 1)):
        for m in rx.finditer(texto):
            uf, num = m.group(i_uf).upper(), _numero(m.group(i_num))
            brutos.setdefault(
                (m.start(), f"OAB/{uf} {num}"),
                (m.start(), m.end(), uf, _nome_antes(texto, m.start()), rx is _OAB_UF_NUM),
            )
    ordem = sorted(brutos.items(), key=lambda kv: kv[0][0])

    achados: list[AdvogadoEncontrado] = []
    cabeca: str | None = None          # OAB que abriu a sequência atual
    cabeca_nome: str | None = None
    ufs_seq: set[str] = set()
    fim_anterior = -1
    for (pos, chave), (ini, fim, uf, nome, pode_depois) in ordem:
        zona = (
            "assinatura" if ini >= n - _ZONA_ASSINATURA
            else "qualificacao" if ini < _ZONA_QUALIFICACAO
            else "corpo"
        )
        em_sequencia = fim_anterior >= 0 and re.fullmatch(r"[\s/,;|]*", texto[fim_anterior:ini] or "") is not None
        if nome is None and pode_depois and not em_sequencia:  # "OAB/ES 4.939 – NOME"
            depois = re.split(r"OAB", texto[fim: fim + 90], maxsplit=1)[0]
            m2 = re.match(rf"\s*[\-–—:,(]*\s*((?:[{_MAIUSC}][\wÀ-ÿ'’.\-]*\s+(?:(?:d[aeo]s?|e)\s+)?){{1,6}}[{_MAIUSC}][\wÀ-ÿ'’.\-]*)", depois)
            if m2 and m2.group(1).split()[0].lower() not in _PARADA:
                nome = m2.group(1)
        pessoa = None
        if em_sequencia and nome is None and uf not in ufs_seq:
            pessoa, nome = cabeca, cabeca_nome           # outra inscrição da mesma pessoa
            ufs_seq.add(uf)
        else:
            cabeca, cabeca_nome, ufs_seq = chave, nome, {uf}
        achados.append(AdvogadoEncontrado(chave, nome, zona, pessoa))
        fim_anterior = fim
    return sorted(achados, key=lambda a: (a.oab, a.zona))


# ── Nome do advogado e da parte ──────────────────────────────────────────────

def bonito(nome: str) -> str:
    """Caixa alta → Título (conectores em minúscula); preserva o que já está misto."""
    if not nome.isupper():
        return nome
    palavras = []
    for i, p in enumerate(nome.split()):
        palavras.append(p.lower() if (p.lower() in _CONECTORES and i) else p.capitalize())
    return " ".join(palavras)


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalizar_parte(autor: str | None) -> tuple[str, str] | None:
    """(chave, rótulo) da parte a partir do peticionante. A chave junta variações do mesmo nome
    ("Apex … S.A e Outras (Requerentes)" = "Apex … S.A. e outras"); o rótulo é o texto limpo."""
    if not autor or not autor.strip():
        return None
    s = re.sub(r"\([^)]*\)", " ", autor)                                  # (Requerentes), (perita…)
    s = re.split(r",?\s+representad[oa]s?\s+por\b", s, maxsplit=1, flags=re.I)[0]
    s = re.sub(r"\s+e\s+(?:outr[ao]s?|demais)\b.*$", "", s, flags=re.I)     # "... e outras"
    s = re.sub(r"\s+e\s+outros?\s+\d+\b.*$", "", s, flags=re.I)             # "… e outros 25 …"
    s = re.sub(r"\s+", " ", s).strip(" ,;.-–—")
    if not s:
        return None
    chave = _chave_parte(s)
    return (chave, s) if chave else None


_SUFIXO_EMPRESA = re.compile(r"(?:ltda|s\.?\s?/?\s?a|s/s|me|epp|eireli|holding|spe)\.?$", re.I)
_PALAVRA_EMPRESA = re.compile(
    r"\b(?:participa[cç][oõ]es|investimentos|empreendimentos|assessoria|assessores|gest[aã]o|servi[cç]os|"
    r"com[eé]rcio|engenharia|cooperativa|banco|grupo|consultoria|consultores|imobili[aá]rios|ltda|holding|"
    r"associa[cç][aã]o|fundo|spe|s\.a|s/a|s/s|seguros|corretora)\b", re.I)


def _separar_e(segmento: str) -> list[str]:
    """Divide "A e B" só quando são duas partes distintas — não quebra razão social com "e"
    ("Participações e Investimentos S.A."): divide se o lado esquerdo termina em sufixo de
    empresa (Ltda, S.A., …) ou se os dois lados são pessoas (sem palavra de empresa, 2+ palavras)."""
    partes = re.split(r"\s+e\s+", segmento)
    if len(partes) < 2:
        return [segmento]
    saida = [partes[0]]
    for nxt in partes[1:]:
        ant = saida[-1]
        dois_nomes = len(ant.split()) >= 2 and len(nxt.split()) >= 2
        pessoas = dois_nomes and not _PALAVRA_EMPRESA.search(ant) and not _PALAVRA_EMPRESA.search(nxt)
        if _SUFIXO_EMPRESA.search(ant.strip(" ,;")) or pessoas:
            saida.append(nxt)
        else:
            saida[-1] = f"{ant} e {nxt}"
    return saida


def _chave_parte(s: str) -> str:
    chave = _sem_acento(s.casefold())
    chave = re.sub(r"\bs\s*/\s*a\b|\bs\.\s*a\b\.?", "sa", chave)
    chave = re.sub(r"\bltda\b\.?", "ltda", chave)
    return re.sub(r"[^a-z0-9]+", " ", chave).strip()


def normalizar_partes(autor: str | None) -> list[tuple[str, str]]:
    """Partes individuais (chave, rótulo) do peticionante. Petição conjunta lista várias partes
    ("A Ltda., B, C e D"): todas são representadas por quem assina, então cada uma vira uma parte."""
    unica = normalizar_parte(autor)
    if unica is None:
        return []
    s = re.sub(r"\([^)]*\)", " ", autor or "")
    s = re.split(r",?\s+representad[oa]s?\s+por\b", s, maxsplit=1, flags=re.I)[0]
    s = re.sub(r"\s+e\s+(?:outr[ao]s?|demais)\b.*$", "", s, flags=re.I)
    s = re.sub(r"\s+e\s+outros?\s+\d+\b.*$", "", s, flags=re.I)
    saida: list[tuple[str, str]] = []
    vistos: set[str] = set()
    for pedaco in re.split(r"\s*[;,]\s*", s):
        for parte in _separar_e(pedaco):
            rotulo = re.sub(r"\s+", " ", parte).strip(" ,;.-–—")
            chave = _chave_parte(rotulo)
            # sufixos soltos ("Ltda.", "S.A.") e pedaços minúsculos não são parte
            if len(chave) < 3 or _SUFIXO_EMPRESA.fullmatch(rotulo.strip(" .")) or chave in vistos:
                continue
            vistos.add(chave)
            saida.append((chave, rotulo))
    return saida or [unica]


def rotulo_mais_comum(rotulos: list[str]) -> str:
    return Counter(rotulos).most_common(1)[0][0]


def nome_mais_completo(nomes: list[str]) -> str | None:
    """Entre variações do nome do mesmo advogado, a mais frequente; empate → a mais longa."""
    nomes = [n for n in nomes if n]
    if not nomes:
        return None
    freq = Counter(bonito(n) for n in nomes)
    return sorted(freq.items(), key=lambda kv: (-kv[1], -len(kv[0])))[0][0]


# ── Relação do caso (banco → advogados × partes) ─────────────────────────────

_SEM_PARTE = ("sem-parte", "(parte não identificada)")
_TEXTO_MIN = 200  # abaixo disso a peça é só um stub (arquivo não lido): não dá para extrair nada
_CACHE: dict[str, tuple[tuple, dict]] = {}


def _link_md(file_id: str | None) -> str | None:
    return f"https://drive.google.com/file/d/{file_id}/view" if file_id else None


class _Uniao:
    def __init__(self):
        self.pai: dict[str, str] = {}

    def achar(self, x: str) -> str:
        self.pai.setdefault(x, x)
        while self.pai[x] != x:
            self.pai[x] = self.pai[self.pai[x]]
            x = self.pai[x]
        return x

    def unir(self, a: str, b: str) -> None:
        ra, rb = self.achar(a), self.achar(b)
        if ra != rb:
            self.pai[max(ra, rb)] = min(ra, rb)


def _chave_nome(nome: str | None) -> str | None:
    """Chave para reconhecer a mesma pessoa com OABs diferentes (>= 3 palavras, sem acento)."""
    if not nome:
        return None
    palavras = re.sub(r"[^a-z ]+", " ", _sem_acento(nome.casefold())).split()
    palavras = [p for p in palavras if p not in _CONECTORES and len(p) > 1]
    return " ".join(palavras) if len(palavras) >= 3 else None


def montar_relacao(db, caso_id) -> dict:
    """Advogados × partes do caso, só a partir das petições (tipos em TIPOS_PETICAO).

    Cada petição liga as OABs que a assinam/qualificam à parte peticionante. Devolve as duas
    visões (por advogado e por parte), as petições sem advogado identificável e a cobertura."""
    from sqlalchemy import func

    from app.models.andamento import AndamentoProcesso
    from app.models.autos_ia import AutosIAPeca as P

    assinatura = db.query(
        func.count(P.id), func.max(P.atualizado_em), func.count(P.md_drive_file_id)
    ).filter(P.caso_id == caso_id, P.tipo.in_(TIPOS_PETICAO)).one()
    chave_cache = tuple(assinatura)
    hit = _CACHE.get(str(caso_id))
    if hit and hit[0] == chave_cache:
        return hit[1]

    rows = (
        db.query(
            P.id, P.id_processual, P.autor, P.titulo, P.titulo_customizado, P.texto_md, P.md_drive_file_id,
            AndamentoProcesso.arquivo_drive_link, AndamentoProcesso.data_andamento, P.data_peca,
        )
        .outerjoin(AndamentoProcesso, P.andamento_id == AndamentoProcesso.id)
        .filter(P.caso_id == caso_id, P.tipo.in_(TIPOS_PETICAO))
        .order_by(AndamentoProcesso.data_andamento.asc().nulls_last(), P.id_processual)
        .all()
    )

    uniao = _Uniao()
    nomes_por_oab: dict[str, list[str]] = {}
    ligacoes: list[tuple[str, str, dict]] = []          # (oab, chave_parte, ref)
    rotulos_parte: dict[str, list[str]] = {}
    sem_advogado: list[dict] = []
    com_texto = com_adv = 0

    for (pid, id_proc, autor, titulo, titulo_cust, texto, md_id, pdf, data_and, data_peca) in rows:
        ref = {
            "peca_id": pid, "id_processual": id_proc, "data": data_and or data_peca,
            "titulo": (titulo_cust or titulo or "Petição"), "link_pdf": pdf, "link_md": _link_md(md_id),
        }
        partes_pet = normalizar_partes(autor) or [_SEM_PARTE]
        rotulo_autor = (normalizar_parte(autor) or (None, None))[1]
        for chave_p, rot_p in partes_pet:
            rotulos_parte.setdefault(chave_p, []).append(rot_p)
        if len((texto or "").strip()) < _TEXTO_MIN:
            sem_advogado.append({"motivo": "sem_texto", "parte": rotulo_autor, "peticao": ref})
            continue
        com_texto += 1
        uteis = [a for a in extrair_advogados(texto) if a.zona != "corpo"]
        if not uteis:
            sem_advogado.append({"motivo": "sem_oab", "parte": rotulo_autor, "peticao": ref})
            continue
        com_adv += 1
        for a in uteis:
            uniao.achar(a.oab)
            if a.pessoa:
                uniao.unir(a.oab, a.pessoa)
            if a.nome:
                nomes_por_oab.setdefault(a.oab, []).append(a.nome)
        for oab in {a.oab for a in uteis}:
            for chave_p, _rot in partes_pet:
                ligacoes.append((oab, chave_p, ref))

    # mesma pessoa com OABs diferentes (ex.: inscrição suplementar): mesmo nome completo
    por_nome: dict[str, str] = {}
    for oab, nomes in nomes_por_oab.items():
        for nome in nomes:
            k = _chave_nome(nome)
            if k:
                if k in por_nome:
                    uniao.unir(oab, por_nome[k])
                else:
                    por_nome[k] = oab

    # pessoa (raiz) → dados
    nomes_pessoa: dict[str, list[str]] = {}
    oabs_pessoa: dict[str, set[str]] = {}
    for oab in list(uniao.pai):
        raiz = uniao.achar(oab)
        oabs_pessoa.setdefault(raiz, set()).add(oab)
        nomes_pessoa.setdefault(raiz, []).extend(nomes_por_oab.get(oab, []))

    vinc: dict[tuple[str, str], dict] = {}
    for oab, chave_parte, ref in ligacoes:
        vinc.setdefault((uniao.achar(oab), chave_parte), {})[ref["peca_id"]] = ref

    def _pessoa(raiz: str) -> dict:
        return {
            "id": raiz,
            "nome": nome_mais_completo(nomes_pessoa.get(raiz, [])),
            "oabs": sorted(oabs_pessoa.get(raiz, {raiz})),
        }

    def _ordena(refs: dict) -> list[dict]:
        return sorted(refs.values(), key=lambda r: (r["data"] is None, r["data"] or 0, r["id_processual"] or ""))

    rotulo_parte = {k: rotulo_mais_comum(v) for k, v in rotulos_parte.items()}
    variantes_parte = {k: sorted(set(v)) for k, v in rotulos_parte.items()}

    advogados: dict[str, dict] = {}
    partes: dict[str, dict] = {}
    for (raiz, chave_parte), refs in vinc.items():
        lista = _ordena(refs)
        a = advogados.setdefault(raiz, {**_pessoa(raiz), "total_peticoes": 0, "partes": [], "_pecas": set()})
        a["partes"].append({"chave": chave_parte, "nome": rotulo_parte[chave_parte], "variantes": variantes_parte[chave_parte], "peticoes": lista})
        a["_pecas"].update(refs)
        p = partes.setdefault(chave_parte, {
            "chave": chave_parte, "nome": rotulo_parte[chave_parte], "variantes": variantes_parte[chave_parte],
            "total_peticoes": 0, "advogados": [], "_pecas": set(),
        })
        p["advogados"].append({**_pessoa(raiz), "peticoes": lista})
        p["_pecas"].update(refs)

    for d in list(advogados.values()) + list(partes.values()):
        d["total_peticoes"] = len(d.pop("_pecas"))
    for a in advogados.values():
        a["partes"].sort(key=lambda x: (-len(x["peticoes"]), x["nome"].casefold()))
    for p in partes.values():
        p["advogados"].sort(key=lambda x: (-len(x["peticoes"]), (x["nome"] or x["id"]).casefold()))

    resultado = {
        "resumo": {
            "peticoes_total": len(rows), "peticoes_sem_texto": len(rows) - com_texto,
            "peticoes_com_advogado": com_adv, "peticoes_sem_advogado": com_texto - com_adv,
            "advogados": len(advogados), "partes": len(partes),
        },
        "advogados": sorted(advogados.values(), key=lambda x: (-x["total_peticoes"], (x["nome"] or x["id"]).casefold())),
        "partes": sorted(partes.values(), key=lambda x: (-x["total_peticoes"], x["nome"].casefold())),
        "sem_advogado": sem_advogado,
    }
    _CACHE[str(caso_id)] = (chave_cache, resultado)
    return resultado
