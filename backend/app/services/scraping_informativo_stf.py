"""Scraping do Informativo do STF.

Fonte: https://portal.stf.jus.br/textos/verTexto.asp?servico=informativoSTF
(listagem, dá o número da edição mais recente via link "informativoNNNN.htm")
e https://www.stf.jus.br/arquivo/informativo/documento/informativo{numero}.htm
(HTML de uma edição — exportado do Word pelo STF, cp1252, SEM classes CSS
como no STJ; exige header Referer apontando pro portal ou dá 403).

Estrutura por edição: seções "N Plenário" / "N Turmas" / "N Inovações
Normativas do STF"; dentro de cada, verbetes delimitados pela palavra solta
"Sumário" (artefato do Word/TOC) que aparece entre um verbete e o próximo.
Cada verbete: 1+ linhas "DIREITO X – ..." (ramo), título+processo, "ODS:...",
"Tese fixada:"/"Resumo:" + corpo, notas de rodapé "(n) ...", e por fim uma
linha com processo+relator+data de julgamento.

Parsing é defensivo: nunca por índice fixo, ancorado em marcadores de texto.
Verbete malformado é pulado; só levanta ParsingStfError se a edição inteira
não render nenhum item.
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from datetime import date

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.informativo_stf import (
    InformativoStfConfig,
    InformativoStfEdicao,
    InformativoStfItem,
)

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://portal.stf.jus.br/textos/verTexto.asp?servico=informativoSTF",
}
TIMEOUT_SECONDS = 30.0
MAX_TENTATIVAS = 3

URL_LISTAGEM = "https://portal.stf.jus.br/textos/verTexto.asp?servico=informativoSTF"
URL_EDICAO = "https://www.stf.jus.br/arquivo/informativo/documento/informativo{numero}.htm"

_MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}

SECAO_RE = re.compile(r"^\d+\s+(PLEN[ÁA]RIO|TURMAS|INOVA[ÇC][ÕO]ES NORMATIVAS DO STF)$")
PROC_RE = re.compile(r"(ADI|ADC|ADPF|AO|ARE|HC|INQ|MS|PET|RCL|RE|SL|SS|ACO)\s*\d[\d.]*\s*/\s*[A-Z]{2}", re.IGNORECASE)
FOOTNOTE_RE = re.compile(r"^\(\d+\)\s")
DATA_JULG_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
RELATOR_RE = re.compile(r"relator[a]?\s+Ministr[oa]\s+([^,]+)", re.IGNORECASE)


class ParsingStfError(Exception):
    """A edição não casou com nenhum padrão esperado — não é erro de rede."""


def _get(url: str, encoding: str = "cp1252") -> str:
    last_exc: Exception | None = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            with httpx.Client(headers=HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                resp.encoding = encoding
                return resp.text
        except httpx.HTTPError as exc:
            last_exc = exc
            time.sleep(min(0.6 * tentativa, 3.0))
    raise last_exc  # type: ignore[misc]


def _normalizar(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode("ascii")
    return txt.lower().strip()


def _parse_data_extenso(txt: str) -> date | None:
    m = re.search(r"(\d{1,2})[ºo°]?\s+de\s+(\w+)\s+de\s+(\d{4})", txt, re.IGNORECASE)
    if not m:
        return None
    dia, mes_nome, ano = m.groups()
    mes = _MESES.get(_normalizar(mes_nome))
    if not mes:
        return None
    try:
        return date(int(ano), mes, int(dia))
    except ValueError:
        return None


def listar_numero_mais_recente() -> int:
    """Lê a página de listagem e acha o maior número de edição linkado."""
    html = _get(URL_LISTAGEM, encoding="utf-8")
    numeros = [int(n) for n in re.findall(r"informativo(\d+)\.htm", html, re.IGNORECASE)]
    if not numeros:
        raise ParsingStfError("Não encontrei nenhuma edição linkada na página de listagem do STF.")
    return max(numeros)


def scrape_edicao_stf(numero: int) -> dict:
    """Baixa e faz parsing de UMA edição do Informativo STF pelo número."""
    url = URL_EDICAO.format(numero=numero)
    html = _get(url)
    soup = BeautifulSoup(html, "html.parser")
    paragrafos = [re.sub(r"\s+", " ", p.get_text(" ", strip=True)) for p in soup.find_all("p")]

    texto_cabecalho = " ".join(paragrafos[:12])
    m_num = re.search(r"N[ºo°]\s*(\d+)", texto_cabecalho, re.IGNORECASE)
    numero_edicao = int(m_num.group(1)) if m_num else numero
    data_publicacao = _parse_data_extenso(texto_cabecalho)

    start = None
    for i, p in enumerate(paragrafos):
        if SECAO_RE.match(p):
            start = i
            break
    if start is None:
        raise ParsingStfError(
            f"Não encontrei o início do corpo (seção Plenário/Turmas) na edição {numero_edicao}."
        )

    itens: list[dict] = []
    orgao_atual = ""
    ramos_buffer: list[str] = []
    titulo: str | None = None
    destaque: str | None = None
    tese: str | None = None
    corpo_paras: list[str] = []
    footnotes: list[str] = []
    modo: str | None = None
    ordem = 0
    processo_linha_pendente: str | None = None

    def fechar(processo_linha: str | None):
        nonlocal titulo, destaque, tese, corpo_paras, footnotes, ramos_buffer, ordem
        if not titulo or not (destaque or tese):
            titulo = destaque = tese = None
            corpo_paras, footnotes, ramos_buffer = [], [], []
            return
        texto_explicativo = " ".join(corpo_paras).strip() or None
        destaque_oficial = " ".join(x for x in [tese, destaque] if x).strip()
        processo_numero = relator = None
        data_julg = None
        if processo_linha:
            processo_numero = re.split(r",\s*relator", processo_linha, flags=re.IGNORECASE)[0].strip() or None
            m_rel = RELATOR_RE.search(processo_linha)
            relator = m_rel.group(1).strip() if m_rel else None
            m_data = DATA_JULG_RE.search(processo_linha)
            if m_data:
                try:
                    data_julg = date(int(m_data.group(3)), int(m_data.group(2)), int(m_data.group(1)))
                except ValueError:
                    data_julg = None
        itens.append({
            "orgao_julgador": orgao_atual,
            "ramo_direito": ", ".join(ramos_buffer) or "Não classificado",
            "titulo": titulo.strip(),
            "destaque_oficial": destaque_oficial,
            "processo_numero": processo_numero,
            "processo_url": None,
            "relator": relator,
            "data_julgamento": data_julg,
            "texto_explicativo": texto_explicativo,
            "legislacao_citada": footnotes[:],
            "ordem": ordem,
        })
        ordem += 1
        titulo = destaque = tese = None
        corpo_paras, footnotes, ramos_buffer = [], [], []

    i = start
    while i < len(paragrafos):
        p = paragrafos[i]
        if not p:
            i += 1
            continue

        try:
            if SECAO_RE.match(p):
                orgao_atual = p.split(" ", 1)[1].strip().title()
                i += 1
                continue

            if p == "Sumário":
                fechar(processo_linha_pendente)
                processo_linha_pendente = None
                modo = None
                i += 1
                continue

            if p.upper().startswith("DIREITO") and p == p.upper():
                ramos_buffer.append(p.split(" – ")[0].strip().title())
                i += 1
                continue

            if p.upper().startswith("ODS:"):
                i += 1
                continue

            low = p.rstrip(":").strip().lower()
            if low == "resumo":
                modo = "resumo"
                i += 1
                continue
            if low == "tese fixada":
                modo = "tese"
                i += 1
                continue

            if FOOTNOTE_RE.match(p):
                footnotes.append(p)
                i += 1
                continue

            if RELATOR_RE.search(p) and DATA_JULG_RE.search(p):
                processo_linha_pendente = p
                i += 1
                continue

            if modo is None and titulo is None and PROC_RE.search(p):
                titulo = p
                i += 1
                continue

            if modo == "resumo":
                if destaque is None:
                    destaque = p
                else:
                    corpo_paras.append(p)
            elif modo == "tese":
                tese = p
                modo = "resumo"
            else:
                if titulo:
                    corpo_paras.append(p)
        except Exception:
            logger.warning("Informativo STF: parágrafo malformado pulado (edição %s)", numero_edicao, exc_info=True)
        i += 1

    fechar(processo_linha_pendente)

    if not itens:
        raise ParsingStfError(
            f"Nenhum verbete reconhecido na edição {numero_edicao} — estrutura HTML pode ter mudado."
        )

    return {
        "numero": numero_edicao,
        "data_publicacao": data_publicacao,
        "tipo": "ordinaria",
        "url_origem": url,
        "itens": itens,
    }


def _get_config(db: Session) -> InformativoStfConfig:
    config = db.get(InformativoStfConfig, 1)
    if not config:
        config = InformativoStfConfig(id=1, areas_selecionadas=[], keywords_livres=[])
        db.add(config)
        db.flush()
    return config


def calcular_destaque(item: dict, config: InformativoStfConfig) -> tuple[bool, str | None]:
    ramo_norm = _normalizar(item.get("ramo_direito", ""))
    for area in config.areas_selecionadas or []:
        if _normalizar(area) in ramo_norm or ramo_norm in _normalizar(area):
            return True, f"área: {area}"

    texto_busca = _normalizar(f"{item.get('titulo', '')} {item.get('destaque_oficial', '')}")
    for kw in config.keywords_livres or []:
        kw_norm = _normalizar(kw)
        if kw_norm and kw_norm in texto_busca:
            return True, f"keyword: {kw}"

    return False, None


def sincronizar_edicao(numero: int, db: Session) -> dict:
    edicao_existente = db.scalar(
        select(InformativoStfEdicao).where(InformativoStfEdicao.numero == numero)
    )
    if edicao_existente and edicao_existente.status_scraping == "ok":
        return {"edicao_id": edicao_existente.id, "inseridos": 0, "duplicatas": 0, "erros": 0, "destacados": 0, "ja_sincronizada": True}

    try:
        dados = scrape_edicao_stf(numero)
    except ParsingStfError as exc:
        if edicao_existente:
            edicao_existente.status_scraping = "erro_parsing"
            edicao_existente.erro_scraping = str(exc)
        else:
            edicao_existente = InformativoStfEdicao(
                numero=numero,
                url_origem=URL_EDICAO.format(numero=numero),
                status_scraping="erro_parsing",
                erro_scraping=str(exc),
            )
            db.add(edicao_existente)
        db.flush()
        return {"edicao_id": edicao_existente.id, "inseridos": 0, "duplicatas": 0, "erros": 1, "destacados": 0, "ja_sincronizada": False}

    if edicao_existente:
        edicao = edicao_existente
        edicao.data_publicacao = dados["data_publicacao"]
        edicao.tipo = dados["tipo"]
        edicao.url_origem = dados["url_origem"]
    else:
        edicao = InformativoStfEdicao(
            numero=dados["numero"],
            data_publicacao=dados["data_publicacao"],
            tipo=dados["tipo"],
            url_origem=dados["url_origem"],
        )
        db.add(edicao)
    edicao.status_scraping = "ok"
    edicao.erro_scraping = None
    db.flush()

    config = _get_config(db)

    existentes = {
        i.ordem: i
        for i in db.scalars(
            select(InformativoStfItem).where(InformativoStfItem.edicao_id == edicao.id)
        )
    }

    inseridos = duplicatas = destacados = 0
    for item_dados in dados["itens"]:
        destacado, motivo = calcular_destaque(item_dados, config)
        if item_dados["ordem"] in existentes:
            duplicatas += 1
            continue
        item = InformativoStfItem(
            edicao_id=edicao.id,
            destacado=destacado,
            motivo_destaque=motivo,
            status_ia="pendente",
            **item_dados,
        )
        db.add(item)
        inseridos += 1
        if destacado:
            destacados += 1

    db.commit()

    return {
        "edicao_id": edicao.id,
        "inseridos": inseridos,
        "duplicatas": duplicatas,
        "erros": 0,
        "destacados": destacados,
        "ja_sincronizada": False,
    }


def sincronizar_novas_edicoes(db: Session, max_edicoes: int = 5) -> dict:
    """Acha o número mais recente na listagem e sincroniza os que faltam (mais recentes primeiro)."""
    try:
        numero_recente = listar_numero_mais_recente()
    except (httpx.HTTPError, ParsingStfError):
        logger.warning("Informativo STF: falha ao ler listagem de edições", exc_info=True)
        return {"edicoes_processadas": 0, "erro": "listagem_indisponivel"}

    numeros_existentes = {
        n for n, in db.execute(select(InformativoStfEdicao.numero)).all()
    }
    candidatos = [n for n in range(max(1, numero_recente - max_edicoes + 1), numero_recente + 1) if n not in numeros_existentes]
    candidatos = sorted(candidatos, reverse=True)[:max_edicoes]

    resultados = []
    for numero in candidatos:
        resultados.append(sincronizar_edicao(numero, db))

    return {"edicoes_processadas": len(resultados), "detalhe": resultados}


def sincronizar_processar_e_notificar(db: Session) -> dict:
    from app.services import ia_informativo_stf, informativo_stf_email

    resultado = sincronizar_novas_edicoes(db)
    ia_informativo_stf.processar_pendentes(db)

    for detalhe in resultado.get("detalhe") or []:
        edicao_id = detalhe.get("edicao_id") if isinstance(detalhe, dict) else None
        if not edicao_id:
            continue
        edicao = db.get(InformativoStfEdicao, edicao_id)
        if not edicao:
            continue
        itens_destacados = list(db.scalars(
            select(InformativoStfItem)
            .where(InformativoStfItem.edicao_id == edicao_id)
            .where(InformativoStfItem.destacado.is_(True))
            .where(InformativoStfItem.status_ia == "ok")
        ).all())
        if itens_destacados:
            try:
                informativo_stf_email.enviar_email_destaques(edicao, itens_destacados)
            except Exception:
                logger.warning("Informativo STF: falha ao enviar e-mail de destaques (edição %s)", edicao.numero, exc_info=True)

    return resultado


def listar_candidatos(db: Session, apenas_nao_usados: bool = False) -> list[dict]:
    itens = db.scalars(
        select(InformativoStfItem)
        .where(InformativoStfItem.destacado.is_(True))
        .where(InformativoStfItem.status_ia == "ok")
        .order_by(InformativoStfItem.criado_em.desc())
    ).all()
    return [
        {
            "item_id": str(i.id),
            "titulo": i.titulo,
            "tema_central": i.resumo_tema_central,
            "ratio_decidendi": i.resumo_ratio_decidendi,
            "processo_numero": i.processo_numero,
            "ramo_direito": i.ramo_direito,
            "edicao_numero": db.get(InformativoStfEdicao, i.edicao_id).numero if i.edicao_id else None,
            "url_origem": i.processo_url,
        }
        for i in itens
    ]


def buscar_itens(db: Session, q: str, limit: int = 100) -> list[InformativoStfItem]:
    termo = f"%{q.strip()}%"
    if not q.strip():
        return []
    return list(db.scalars(
        select(InformativoStfItem)
        .where(
            InformativoStfItem.titulo.ilike(termo)
            | InformativoStfItem.destaque_oficial.ilike(termo)
            | InformativoStfItem.texto_explicativo.ilike(termo)
            | InformativoStfItem.resumo_tema_central.ilike(termo)
            | InformativoStfItem.resumo_ratio_decidendi.ilike(termo)
            | InformativoStfItem.processo_numero.ilike(termo)
            | InformativoStfItem.ramo_direito.ilike(termo)
        )
        .order_by(InformativoStfItem.criado_em.desc())
        .limit(limit)
    ).all())


def toggle_favorito(item_id, db: Session) -> InformativoStfItem:
    item = db.get(InformativoStfItem, item_id)
    if not item:
        raise ValueError(f"Item {item_id} não encontrado")
    item.favorito = not item.favorito
    db.commit()
    return item


def listar_favoritos(db: Session) -> list[InformativoStfItem]:
    return list(db.scalars(
        select(InformativoStfItem)
        .where(InformativoStfItem.favorito.is_(True))
        .order_by(InformativoStfItem.criado_em.desc())
    ).all())
