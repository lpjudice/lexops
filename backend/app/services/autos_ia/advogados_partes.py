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
import uuid
from collections import Counter
from dataclasses import dataclass

TIPOS_PETICAO = ("peticao", "recurso")

_UFS = ("AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO")
_NUM = r"(\d{1,3}(?:\.(?:\d{3}|\d \d{2}|\d{2} \d))+|\d{3,6})"   # "4.939" · "14477" · "43.9 93" (quebrado na extração)
# OAB/ES 4.939 · OAB-ES nº 4.939 · OAB (ES) 1.507 · OAB/ES sob o nº 14.477 · OAB nº 4.939/ES
_OAB_UF_NUM = re.compile(rf"OAB\s*[/\-–.:]?\s*\(?\s*(?-i:({_UFS}))\s*\)?\b[^\d]{{0,16}}?{_NUM}", re.I)
_OAB_NUM_UF = re.compile(rf"OAB\s*(?:n[ºo°.]*\s*)?{_NUM}\s*[/\-–(]\s*(?-i:({_UFS}))\b", re.I)

_ZONA_ASSINATURA = 1400   # últimos N caracteres
_APOS_FECHO = 900         # caracteres, depois de "Pede deferimento"/"Termos em que", que contam como assinatura
_FECHO = re.compile(
    r"(?:pede[m]?\s*(?:e\s+espera[m]?\s*)?(?:o\s+)?deferimento|espera[m]?\s+deferimento|termos\s+em\s+que|"
    r"nestes\s+termos|nesses\s+termos|requer[em]*\s+o\s+deferimento)", re.I)
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


# ── O que é "petição" ────────────────────────────────────────────────────────
# Pelo tipo do documento no PJe (andamento.tipo), que é o que o próprio advogado escolheu ao
# protocolar — o tipo da IA confunde anexos ("Documento de representação") com petição.
_TIPO_PETICAO_PJE = re.compile(
    r"^(?:peti[cç]|pedido|habilita|r[eé]plica|embargos|aditamento|contesta|recurso|apela|agravo|impugna|"
    r"manifesta|parecer|extin[cç][aã]o|memoriais|raz[oõ]es|contrarraz|exce[cç]|reconven|alega[cç])", re.I)
_TIPO_ANEXO_PJE = re.compile(r"^(?:documento|procura|demonstra|certid[aã]o regularidade)", re.I)   # anexos
_CABECALHO_PETICAO = re.compile(r"excelent[ií]ssim|egr[eé]gio|meritíssim|ilustr[ií]ssim|ao\s+ju[ií]zo", re.I)


def eh_peticao(tipo_pje: str | None, tipo_ia: str | None, tem_arquivo: bool, texto: str | None) -> bool:
    """Petição = documento (tem arquivo) cujo tipo no PJe é de petição. Sem tipo PJe utilizável,
    vale o da IA (peticao/recurso) se o texto abre com endereçamento ao juízo."""
    if not tem_arquivo:
        return False  # evento de protocolo sem documento ("Petição — Petição (outras): 57")
    t = (tipo_pje or "").strip()
    if t and _TIPO_PETICAO_PJE.match(t):
        return True
    if tipo_ia in TIPOS_PETICAO and (not t or _TIPO_ANEXO_PJE.match(t)):
        # anexo/sem tipo que a IA leu como petição: só vale se abre dirigido ao juízo. Atos do
        # juiz (decisão, despacho…) e movimentos nunca viram petição por este caminho.
        return bool(_CABECALHO_PETICAO.search((texto or "")[:800]))
    return False


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
    fechos = [(m.end(), m.end() + _APOS_FECHO) for m in _FECHO.finditer(texto)]
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
            "assinatura" if ini >= n - _ZONA_ASSINATURA or any(a <= ini < b for a, b in fechos)
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


_RE_MP = re.compile(r"minist[eé]rio p[uú]blico|promotoria|procuradoria", re.I)
_RE_AJ = re.compile(r"administrador[a]?\s+judicial|perit[oa]|laspro", re.I)
_RE_PROMOTOR = re.compile(r"([A-ZÁÀÂÃÉÊÍÓÔÕÚÇ][A-ZÁÀÂÃÉÊÍÓÔÕÚÇ ]{5,60})\s+(?:Promotor|Procurador)[a]?\s+de\s+Justi[cç]a", re.U)


def motivo_sem_advogado(autor: str | None, tipo_pje: str | None, texto: str) -> tuple[str, str | None]:
    """Por que a petição não tem advogado com OAB: não é de advogado (MP, administrador judicial),
    texto cortado (assinatura não chegou) ou simplesmente sem OAB no texto. Devolve (motivo, assinante)."""
    cauda = texto[-500:]
    pm = _RE_PROMOTOR.search(cauda)
    if pm or _RE_MP.search(autor or ""):
        return "ministerio_publico", bonito(pm.group(1).strip()) if pm else None
    if _RE_AJ.search(autor or "") or _RE_AJ.search(tipo_pje or ""):
        return "administrador_judicial", None
    fim = texto.rstrip()[-1:]
    if fim and fim not in ".!?;:)”\"'%" and not fim.isdigit():
        return "texto_incompleto", None      # termina no meio da frase: a assinatura ficou de fora
    return "sem_oab", None


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


class RelacaoErro(ValueError):
    """Pedido de edição inválido (advogado/parte inexistente, nome vazio, OAB ilegível…)."""


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


def normalizar_oab(texto: str | None) -> str | None:
    """"ES 4.939" · "OAB/ES 4939" · "4939/ES" · "OAB (ES) 4.939" → "OAB/ES 4939". None se ilegível."""
    t = (texto or "").strip().upper()
    if not t:
        return None
    t = t if t.startswith("OAB") else f"OAB {t}"
    m = _OAB_UF_NUM.search(t) or _OAB_NUM_UF.search(t)
    if not m:
        return None
    uf, num = (m.group(1), m.group(2)) if m.re is _OAB_UF_NUM else (m.group(2), m.group(1))
    return f"OAB/{uf.upper()} {_numero(num)}"


def _assinatura_dados(db, caso_id):
    from sqlalchemy import func

    from app.models.autos_ia import AutosIAAdvogadoNome as N
    from app.models.autos_ia import AutosIAParteAdvogado as L
    from app.models.autos_ia import AutosIAPeca as P

    a = db.query(func.count(P.id), func.max(P.atualizado_em), func.count(P.md_drive_file_id)).filter(P.caso_id == caso_id).one()
    b = db.query(
        func.count(L.id), func.max(L.atualizado_em),
        func.count(L.id).filter(L.principal), func.count(L.id).filter(L.oculto),
    ).filter(L.caso_id == caso_id).one()
    c = db.query(func.count(N.oab), func.max(N.atualizado_em)).one()
    return tuple(a) + tuple(b) + tuple(c)


def montar_relacao(db, caso_id) -> dict:
    """Advogados × partes do caso, só a partir das petições (documento com tipo de petição no PJe).

    Cada petição liga as OABs que a assinam/qualificam às partes que a peticionaram. Sobre isso
    entram os ajustes manuais: nome do advogado (por OAB), advogado adicionado a uma parte,
    advogado PRINCIPAL da parte e vínculos removidos. Devolve as duas visões (por advogado e por
    parte), as petições sem advogado e a cobertura."""
    from sqlalchemy import func

    from app.models.andamento import AndamentoProcesso
    from app.models.autos_ia import AutosIAAdvogadoNome as N
    from app.models.autos_ia import AutosIAParteAdvogado as L
    from app.models.autos_ia import AutosIAPeca as P

    chave_cache = _assinatura_dados(db, caso_id)
    hit = _CACHE.get(str(caso_id))
    if hit and hit[0] == chave_cache:
        return hit[1]

    todas = (
        db.query(
            P.id, P.id_processual, P.autor, P.titulo, P.titulo_customizado, P.texto_md, P.md_drive_file_id,
            AndamentoProcesso.arquivo_drive_link, AndamentoProcesso.data_andamento, P.data_peca,
            AndamentoProcesso.tipo, P.tipo, AndamentoProcesso.arquivo_nome, AndamentoProcesso.documento_id,
        )
        .outerjoin(AndamentoProcesso, P.andamento_id == AndamentoProcesso.id)
        .filter(P.caso_id == caso_id)
        .order_by(AndamentoProcesso.data_andamento.asc().nulls_last(), P.id_processual)
        .all()
    )
    rows, eventos_sem_arquivo = [], 0
    for r in todas:
        tipo_pje, tipo_ia, arq, doc = r[10], r[11], r[12], r[13]
        tem_arquivo = bool(arq or doc or r[7])
        if (tipo_pje or "").strip().lower().startswith("peti") and not tem_arquivo:
            eventos_sem_arquivo += 1   # protocolo sem documento: não é a petição em si
        if eh_peticao(tipo_pje, tipo_ia, tem_arquivo, r[5]):
            rows.append(r[:10] + (tipo_pje,))

    uniao = _Uniao()
    nomes_por_oab: dict[str, list[str]] = {}
    ligacoes: list[tuple[str, str, dict]] = []          # (oab, chave_parte, ref)
    rotulos_parte: dict[str, list[str]] = {}
    pets_da_parte: dict[str, dict] = {}                 # chave_parte → {peca_id: ref} (TODAS as petições da parte)
    sem_advogado: list[dict] = []
    com_texto = com_adv = 0

    for (pid, id_proc, autor, titulo, titulo_cust, texto, md_id, pdf, data_and, data_peca, tipo_pje) in rows:
        ref = {
            "peca_id": pid, "id_processual": id_proc, "data": data_and or data_peca,
            "titulo": (titulo_cust or titulo or "Petição"), "link_pdf": pdf, "link_md": _link_md(md_id),
        }
        partes_pet = normalizar_partes(autor) or [_SEM_PARTE]
        rotulo_autor = (normalizar_parte(autor) or (None, None))[1]
        for chave_p, rot_p in partes_pet:
            rotulos_parte.setdefault(chave_p, []).append(rot_p)
            pets_da_parte.setdefault(chave_p, {})[pid] = ref
        if len((texto or "").strip()) < _TEXTO_MIN:
            sem_advogado.append({"motivo": "sem_texto", "parte": rotulo_autor, "assinante": None, "peticao": ref})
            continue
        com_texto += 1
        uteis = [a for a in extrair_advogados(texto) if a.zona != "corpo"]
        if not uteis:
            motivo, assinante = motivo_sem_advogado(autor, tipo_pje, texto)
            sem_advogado.append({"motivo": motivo, "parte": rotulo_autor, "assinante": assinante, "peticao": ref})
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

    # ── ajustes manuais ──
    links = db.query(L).filter(L.caso_id == caso_id).all()
    nomes_ov = {n.oab: n.nome for n in db.query(N).all()}
    for l in links:
        if l.adv_ref.startswith("OAB/"):
            uniao.achar(l.adv_ref)
            if l.nome and l.manual:
                nomes_por_oab.setdefault(l.adv_ref, []).append(l.nome)

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

    nomes_pessoa: dict[str, list[str]] = {}
    oabs_pessoa: dict[str, set[str]] = {}
    for oab in list(uniao.pai):
        raiz = uniao.achar(oab)
        oabs_pessoa.setdefault(raiz, set()).add(oab)
        nomes_pessoa.setdefault(raiz, []).extend(nomes_por_oab.get(oab, []))

    def _raiz(adv_ref: str) -> str:
        return uniao.achar(adv_ref) if adv_ref.startswith("OAB/") else adv_ref

    manuais_sem_oab = {l.adv_ref: l.nome for l in links if l.adv_ref.startswith("manual:") and l.nome}

    def _pessoa(raiz: str) -> dict:
        if raiz.startswith("manual:"):
            return {"id": raiz, "nome": manuais_sem_oab.get(raiz), "oabs": []}
        oabs = sorted(oabs_pessoa.get(raiz, {raiz}))
        nome = next((nomes_ov[o] for o in oabs if o in nomes_ov), None) or nome_mais_completo(nomes_pessoa.get(raiz, []))
        return {"id": raiz, "nome": nome, "oabs": oabs}

    rotulo_parte = {k: rotulo_mais_comum(v) for k, v in rotulos_parte.items()}
    variantes_parte = {k: sorted(set(v)) for k, v in rotulos_parte.items()}

    # petições por (parte, pessoa) e flags manuais por (parte, pessoa)
    vinc: dict[tuple[str, str], dict] = {}
    for oab, chave_parte, ref in ligacoes:
        vinc.setdefault((chave_parte, uniao.achar(oab)), {})[ref["peca_id"]] = ref
    flags: dict[tuple[str, str], dict] = {}
    for l in links:
        f = flags.setdefault((l.parte_chave, _raiz(l.adv_ref)), {"principal": False, "oculto": False, "manual": False})
        f["principal"] |= l.principal
        f["oculto"] |= l.oculto
        f["manual"] |= l.manual

    def _ordena(refs: dict) -> list[dict]:
        return sorted(refs.values(), key=lambda r: (r["data"] is None, r["data"] or 0, r["id_processual"] or ""))

    partes: dict[str, dict] = {}
    for chave_parte, refs in pets_da_parte.items():
        partes[chave_parte] = {
            "chave": chave_parte, "nome": rotulo_parte[chave_parte], "variantes": variantes_parte[chave_parte],
            "total_peticoes": len(refs), "peticoes": _ordena(refs), "advogados": [], "removidos": [],
        }
    membros: dict[str, set[str]] = {}   # chave_parte → pessoas (raízes) com algum vínculo
    for (chave_parte, raiz) in vinc:
        membros.setdefault(chave_parte, set()).add(raiz)
    for (chave_parte, raiz), f in flags.items():
        if chave_parte in partes and (f["manual"] or f["principal"] or f["oculto"]):
            membros.setdefault(chave_parte, set()).add(raiz)

    for chave_parte, raizes in membros.items():
        parte = partes.get(chave_parte)
        if parte is None:   # vínculo manual de uma parte que não existe mais nas petições
            continue
        for raiz in raizes:
            f = flags.get((chave_parte, raiz), {"principal": False, "oculto": False, "manual": False})
            pessoa = _pessoa(raiz)
            pets = _ordena(vinc.get((chave_parte, raiz), {}))
            if f["oculto"]:
                parte["removidos"].append({**pessoa})
                continue
            parte["advogados"].append({**pessoa, "peticoes": pets, "principal": f["principal"], "sugerido": False,
                                       "manual": f["manual"] and not pets})
        advs = parte["advogados"]
        if len(advs) >= 2 and not any(a["principal"] for a in advs):
            ordenados = sorted(advs, key=lambda a: -len(a["peticoes"]))
            if len(ordenados[0]["peticoes"]) > len(ordenados[1]["peticoes"]):
                ordenados[0]["sugerido"] = True
        advs.sort(key=lambda a: (not a["principal"], not a["sugerido"], -len(a["peticoes"]), (a["nome"] or a["id"]).casefold()))
        parte["removidos"].sort(key=lambda a: (a["nome"] or a["id"]).casefold())

    # visão por advogado = inversão da visão por parte
    advogados: dict[str, dict] = {}
    for parte in partes.values():
        for a in parte["advogados"]:
            d = advogados.setdefault(a["id"], {"id": a["id"], "nome": a["nome"], "oabs": a["oabs"], "manual": a["manual"],
                                               "total_peticoes": 0, "partes": [], "_pecas": set()})
            d["manual"] = d["manual"] and a["manual"]
            d["partes"].append({"chave": parte["chave"], "nome": parte["nome"], "variantes": parte["variantes"],
                                "principal": a["principal"], "manual": a["manual"], "peticoes": a["peticoes"]})
            d["_pecas"].update(p["peca_id"] for p in a["peticoes"])
    for d in advogados.values():
        d["total_peticoes"] = len(d.pop("_pecas"))
        d["partes"].sort(key=lambda x: (not x["principal"], -len(x["peticoes"]), x["nome"].casefold()))

    resultado = {
        "resumo": {
            "peticoes_total": len(rows), "peticoes_sem_texto": len(rows) - com_texto,
            "eventos_sem_arquivo": eventos_sem_arquivo,
            "peticoes_com_advogado": com_adv, "peticoes_sem_advogado": com_texto - com_adv,
            "advogados": len(advogados), "partes": len(partes),
        },
        "advogados": sorted(advogados.values(), key=lambda x: (-x["total_peticoes"], (x["nome"] or x["id"]).casefold())),
        "partes": sorted(
            (p for p in partes.values() if p["chave"] != _SEM_PARTE[0] or p["advogados"]),
            key=lambda x: (-x["total_peticoes"], x["nome"].casefold()),
        ),
        "sem_advogado": sem_advogado,
    }
    _CACHE[str(caso_id)] = (chave_cache, resultado)
    return resultado


# ── Edição manual ────────────────────────────────────────────────────────────

def _invalidar(caso_id) -> None:
    _CACHE.pop(str(caso_id), None)


def _bate(a: dict, adv_id: str) -> bool:
    """O id da pessoa é a menor OAB do grupo e pode mudar quando duas inscrições são unificadas;
    por isso qualquer OAB dela também identifica o advogado."""
    return a["id"] == adv_id or adv_id in a["oabs"]


def _achar_pessoa(rel: dict, adv_id: str) -> dict:
    for a in rel["advogados"]:
        if _bate(a, adv_id):
            return a
    for p in rel["partes"]:
        for a in p["advogados"] + p["removidos"]:
            if _bate(a, adv_id):
                return a
    raise RelacaoErro("Advogado não encontrado nesta relação.")


def _achar_parte(rel: dict, chave: str) -> dict:
    for p in rel["partes"]:
        if p["chave"] == chave:
            return p
    raise RelacaoErro("Parte não encontrada nesta relação.")


def _linhas(db, caso_id, parte_chave: str, pessoa: dict) -> list:
    from app.models.autos_ia import AutosIAParteAdvogado as L

    refs = {pessoa["id"], *pessoa["oabs"]}
    return db.query(L).filter(L.caso_id == caso_id, L.parte_chave == parte_chave, L.adv_ref.in_(refs)).all()


def _nome_valido(nome: str | None) -> str:
    n = re.sub(r"\s+", " ", (nome or "")).strip()
    if not n:
        raise RelacaoErro("Informe o nome do advogado.")
    if len(n) > 255:
        raise RelacaoErro("Nome muito longo (máximo 255 caracteres).")
    return n


def renomear_advogado(db, caso_id, adv_id: str, nome: str) -> dict:
    """Muda o nome de exibição do advogado. Com OAB, vale para todas as partes e casos (o nome
    fica ligado à OAB); sem OAB (adicionado à mão), vale neste caso."""
    from app.models.autos_ia import AutosIAAdvogadoNome as N
    from app.models.autos_ia import AutosIAParteAdvogado as L

    nome = _nome_valido(nome)
    pessoa = _achar_pessoa(montar_relacao(db, caso_id), adv_id)
    if pessoa["oabs"]:
        for oab in pessoa["oabs"]:
            linha = db.get(N, oab)
            if linha:
                linha.nome = nome
            else:
                db.add(N(oab=oab, nome=nome))
    else:
        for l in db.query(L).filter(L.caso_id == caso_id, L.adv_ref == adv_id).all():
            l.nome = nome
    db.commit()
    _invalidar(caso_id)
    return montar_relacao(db, caso_id)


def adicionar_advogado(db, caso_id, parte_chave: str, nome: str, oab: str | None = None) -> dict:
    """Adiciona um advogado a uma parte. Com OAB, se ela já aparece em outro lugar vira a mesma
    pessoa; sem OAB, fica como advogado só deste caso."""
    from app.models.autos_ia import AutosIAAdvogadoNome as N
    from app.models.autos_ia import AutosIAParteAdvogado as L

    nome = _nome_valido(nome)
    rel = montar_relacao(db, caso_id)
    _achar_parte(rel, parte_chave)
    oab_key = None
    if oab and oab.strip():
        oab_key = normalizar_oab(oab)
        if not oab_key:
            raise RelacaoErro("OAB inválida. Use o formato OAB/UF número (ex.: OAB/ES 4939).")
    ref = oab_key or f"manual:{uuid.uuid4()}"
    linha = db.query(L).filter(L.caso_id == caso_id, L.parte_chave == parte_chave, L.adv_ref == ref).first()
    if linha:
        linha.oculto = False
    else:
        db.add(L(caso_id=caso_id, parte_chave=parte_chave, adv_ref=ref, nome=nome, oab=oab_key, manual=True))
    if oab_key:
        existente = db.get(N, oab_key)
        if existente:
            existente.nome = nome
        else:
            db.add(N(oab=oab_key, nome=nome))
    db.commit()
    _invalidar(caso_id)
    return montar_relacao(db, caso_id)


def definir_principal(db, caso_id, parte_chave: str, adv_id: str | None) -> dict:
    """Marca o advogado principal da parte (um só por parte); adv_id=None desmarca."""
    from app.models.autos_ia import AutosIAParteAdvogado as L

    rel = montar_relacao(db, caso_id)
    parte = _achar_parte(rel, parte_chave)
    pessoa = None
    if adv_id:
        pessoa = next((a for a in parte["advogados"] if _bate(a, adv_id)), None)
        if pessoa is None:
            raise RelacaoErro("Esse advogado não está (ou foi removido) nesta parte.")
    db.query(L).filter(L.caso_id == caso_id, L.parte_chave == parte_chave, L.principal.is_(True)).update({"principal": False})
    if pessoa:
        linhas = _linhas(db, caso_id, parte_chave, pessoa)
        if linhas:
            linhas[0].principal = True
        else:
            db.add(L(caso_id=caso_id, parte_chave=parte_chave, adv_ref=pessoa["id"], principal=True))
    db.commit()
    _invalidar(caso_id)
    return montar_relacao(db, caso_id)


def remover_advogado(db, caso_id, parte_chave: str, adv_id: str) -> dict:
    """Tira o advogado da parte (some da lista; dá para restaurar). Adicionado à mão e sem
    petição nesta parte é apagado de vez."""
    from app.models.autos_ia import AutosIAParteAdvogado as L

    rel = montar_relacao(db, caso_id)
    parte = _achar_parte(rel, parte_chave)
    pessoa = next((a for a in parte["advogados"] if _bate(a, adv_id)), None)
    if pessoa is None:
        raise RelacaoErro("Esse advogado não está nesta parte.")
    linhas = _linhas(db, caso_id, parte_chave, pessoa)
    if pessoa["manual"] and not pessoa["peticoes"]:
        for l in linhas:
            db.delete(l)
    elif linhas:
        for l in linhas:
            l.oculto = True
            l.principal = False
    else:
        db.add(L(caso_id=caso_id, parte_chave=parte_chave, adv_ref=pessoa["id"], oculto=True))
    db.commit()
    _invalidar(caso_id)
    return montar_relacao(db, caso_id)


def restaurar_advogado(db, caso_id, parte_chave: str, adv_id: str) -> dict:
    rel = montar_relacao(db, caso_id)
    parte = _achar_parte(rel, parte_chave)
    pessoa = next((a for a in parte["removidos"] if _bate(a, adv_id)), None)
    if pessoa is None:
        raise RelacaoErro("Esse advogado não está entre os removidos desta parte.")
    for l in _linhas(db, caso_id, parte_chave, pessoa):
        l.oculto = False
    db.commit()
    _invalidar(caso_id)
    return montar_relacao(db, caso_id)
