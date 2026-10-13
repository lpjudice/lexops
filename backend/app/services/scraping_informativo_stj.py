"""Scraping do Informativo de Jurisprudência do STJ.

O RSS oficial do STJ (processo.stj.jus.br/.../InformativoFeed) só anuncia a
edição nova (número + data), sem conteúdo. O conteúdo completo só é servido
em scon.stj.jus.br por trás de um desafio Cloudflare que um cliente HTTP
simples não resolve — MAS o link que o STJ manda por e-mail/RSS aponta para
processo.stj.jus.br/jurisprudencia/externo/informativo/?acao=pesquisarumaedicao&livre=NNNN.cod.&from=feed,
que devolve o HTML completo sem desafio nenhum (confirmado via curl simples).
É esse host que este módulo usa.

Parsing é defensivo por design: nunca usa índice fixo de posição, âncora por
classe/rótulo de campo. Um verbete malformado é pulado com log (não aborta a
edição); se a edição inteira não render nenhum verbete, levanta ParsingStjError.
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

from app.models.informativo_stj import (
    InformativoStjConfig,
    InformativoStjEdicao,
    InformativoStjItem,
)

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
TIMEOUT_SECONDS = 30.0
MAX_TENTATIVAS = 3

URL_EDICAO = (
    "https://processo.stj.jus.br/jurisprudencia/externo/informativo/"
    "?acao=pesquisarumaedicao&livre={numero:04d}.cod.&from=feed"
)
URL_FEED = "https://processo.stj.jus.br/jurisprudencia/externo/InformativoFeed"

_MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}


class ParsingStjError(Exception):
    """A edição não casou com nenhum padrão esperado — não é erro de rede."""


def _get(url: str) -> str:
    last_exc: Exception | None = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            with httpx.Client(headers=HEADERS, timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                # O STJ serve ISO-8859-1 mas às vezes sem o header correto.
                resp.encoding = resp.encoding or "ISO-8859-1"
                return resp.text
        except httpx.HTTPError as exc:
            last_exc = exc
            time.sleep(min(0.6 * tentativa, 3.0))
    raise last_exc  # type: ignore[misc]


def _normalizar(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode("ascii")
    return txt.lower().strip()


def _parse_data_extenso(txt: str) -> date | None:
    # Dia 1 vem como "1º" (ordinal) — ex. "1º de setembro de 2026" (edição 899).
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


def _label_text(label_div) -> str:
    # O label pode ter markup aninhado (ícone, checkbox) antes do texto real —
    # pega só o texto "solto" relevante, ignorando spans decorativos conhecidos.
    for lixo in label_div.select(".clsCheckSelecionaNota, .listaODS"):
        lixo.extract()
    return label_div.get_text(" ", strip=True)


def _value_text(value_div) -> str:
    return value_div.get_text(" ", strip=True) if value_div else ""


def scrape_edicao_stj(numero: int) -> dict:
    """Baixa e faz parsing de UMA edição do Informativo STJ pelo número."""
    url = URL_EDICAO.format(numero=numero)
    html = _get(url)
    soup = BeautifulSoup(html, "html.parser")

    titulo_edicao = soup.select_one(".clsInformativoTitulo")
    numero_edicao = numero
    data_publicacao = None
    if titulo_edicao:
        texto_titulo = titulo_edicao.get_text(" ", strip=True)
        m_num = re.search(r"n[ºo°]\s*(\d+)", texto_titulo, re.IGNORECASE)
        if m_num:
            numero_edicao = int(m_num.group(1))
        data_publicacao = _parse_data_extenso(texto_titulo)

    tipo = "extraordinaria" if "extraordin" in _normalizar(html[:2000]) else "ordinaria"

    blocos = soup.select(".clsInformativoOrgaojulgadorBloco, .clsInformativoTextoBloco")
    itens: list[dict] = []
    orgao_atual = ""
    ordem = 0

    for bloco in blocos:
        classes = bloco.get("class") or []
        if "clsInformativoOrgaojulgadorBloco" in classes:
            span = bloco.select_one(".clsInformativoOrgaojulgador")
            if span:
                orgao_atual = span.get_text(strip=True)
            continue

        # clsInformativoTextoBloco — um verbete completo
        try:
            item = _parse_verbete(bloco, orgao_atual, ordem)
        except Exception:
            logger.warning("Informativo STJ: verbete malformado pulado (edição %s)", numero_edicao, exc_info=True)
            continue
        if item:
            itens.append(item)
            ordem += 1

    if not itens:
        raise ParsingStjError(
            f"Nenhum verbete reconhecido na edição {numero_edicao} — estrutura HTML pode ter mudado."
        )

    return {
        "numero": numero_edicao,
        "data_publicacao": data_publicacao,
        "tipo": tipo,
        "url_origem": url,
        "itens": itens,
    }


def _parse_verbete(bloco, orgao_julgador: str, ordem: int) -> dict | None:
    campos: dict[str, str] = {}
    campos_html: dict[str, object] = {}

    # O rótulo e o valor de um campo nem sempre estão na mesma .divLinha (ex:
    # "Destaque" e "Informações do Inteiro Teor" usam duas .divLinha separadas,
    # uma só com o label, outra só com o valor) — por isso processamos em
    # sequência e carregamos o último rótulo visto até achar um valor.
    rotulo_atual: str | None = None
    for linha in bloco.select(".divLinha"):
        label_div = linha.select_one(".clsInformativoLabel")
        value_div = linha.select_one(".clsInformativoTexto, .clsInformativoTextoFormatado")
        if label_div:
            texto_rotulo = _normalizar(_label_text(label_div))
            if texto_rotulo:
                rotulo_atual = texto_rotulo
        if value_div and rotulo_atual:
            campos[rotulo_atual] = _value_text(value_div)
            campos_html[rotulo_atual] = value_div
            if label_div:
                # linha com label E valor juntos (ex: Processo) — não reaproveita rótulo na próxima
                pass

    processo_texto = campos.get("processo", "")
    if not processo_texto:
        return None

    processo_div = campos_html.get("processo")
    processo_numero = None
    processo_url = None
    if processo_div is not None:
        primeiro_link = processo_div.find("a")
        if primeiro_link:
            processo_numero = primeiro_link.get_text(strip=True)
            processo_url = primeiro_link.get("href")
    if not processo_numero:
        m = re.search(r"[A-Z]{2,6}\s*\d[\d.]*-[A-Z]{2}", processo_texto)
        processo_numero = m.group(0) if m else None

    m_relator = re.search(r"Rel\.?\s*Ministr[oa]\s+([^,]+)", processo_texto)
    relator = m_relator.group(1).strip() if m_relator else None

    m_data = re.search(r"julgado em\s+(\d{1,2}/\d{1,2}/\d{4})", processo_texto)
    data_julgamento = None
    if m_data:
        try:
            dia, mes, ano = m_data.group(1).split("/")
            data_julgamento = date(int(ano), int(mes), int(dia))
        except ValueError:
            data_julgamento = None

    titulo = campos.get("tema", "") or processo_texto[:255]
    ramo_direito = campos.get("ramo do direito", "") or "Não classificado"
    destaque_oficial = campos.get("destaque", "")
    texto_explicativo = campos.get("informacoes do inteiro teor", "") or None
    legislacao_citada: list[str] = []
    info_adicionais_div = campos_html.get("informacoes adicionais")
    if info_adicionais_div is not None:
        legislacao_citada = [a.get_text(strip=True) for a in info_adicionais_div.find_all("a") if a.get_text(strip=True)]

    return {
        "orgao_julgador": orgao_julgador,
        "ramo_direito": ramo_direito.strip().title() if ramo_direito else "Não classificado",
        "titulo": titulo.strip(),
        "destaque_oficial": destaque_oficial.strip(),
        "processo_numero": processo_numero,
        "processo_url": processo_url,
        "relator": relator,
        "data_julgamento": data_julgamento,
        "texto_explicativo": texto_explicativo,
        "legislacao_citada": legislacao_citada,
        "ordem": ordem,
    }


def listar_edicoes_recentes_feed() -> list[dict]:
    """Lê o feed Atom do STJ (só título+link+data, sem conteúdo)."""
    xml = _get(URL_FEED)
    soup = BeautifulSoup(xml, "xml")
    edicoes = []
    for entry in soup.find_all("entry"):
        titulo = entry.find("title")
        if not titulo:
            continue
        m = re.search(r"n[ºo°.]*\s*(\d+)", titulo.get_text())
        if not m:
            continue
        edicoes.append({"numero": int(m.group(1)), "titulo": titulo.get_text(strip=True)})
    return edicoes


def _get_config(db: Session) -> InformativoStjConfig:
    config = db.get(InformativoStjConfig, 1)
    if not config:
        config = InformativoStjConfig(id=1, areas_selecionadas=[], keywords_livres=[])
        db.add(config)
        db.flush()
    return config


def calcular_destaque(item: dict, config: InformativoStjConfig) -> tuple[bool, str | None]:
    ramo_norm = _normalizar(item.get("ramo_direito", ""))
    for area in config.areas_selecionadas or []:
        if _normalizar(area) == ramo_norm:
            return True, f"área: {area}"

    texto_busca = _normalizar(f"{item.get('titulo', '')} {item.get('destaque_oficial', '')}")
    for kw in config.keywords_livres or []:
        kw_norm = _normalizar(kw)
        if kw_norm and kw_norm in texto_busca:
            return True, f"keyword: {kw}"

    return False, None


def sincronizar_edicao(numero: int, db: Session) -> dict:
    """Orquestra scrape -> upsert edição -> upsert itens -> calcula destaque."""
    edicao_existente = db.scalar(
        select(InformativoStjEdicao).where(InformativoStjEdicao.numero == numero)
    )
    if edicao_existente and edicao_existente.status_scraping == "ok":
        return {"edicao_id": edicao_existente.id, "inseridos": 0, "duplicatas": 0, "erros": 0, "destacados": 0, "ja_sincronizada": True}

    try:
        dados = scrape_edicao_stj(numero)
    except ParsingStjError as exc:
        if edicao_existente:
            edicao_existente.status_scraping = "erro_parsing"
            edicao_existente.erro_scraping = str(exc)
        else:
            edicao_existente = InformativoStjEdicao(
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
        edicao = InformativoStjEdicao(
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
            select(InformativoStjItem).where(InformativoStjItem.edicao_id == edicao.id)
        )
    }

    inseridos = duplicatas = destacados = 0
    for item_dados in dados["itens"]:
        destacado, motivo = calcular_destaque(item_dados, config)
        if item_dados["ordem"] in existentes:
            duplicatas += 1
            continue
        item = InformativoStjItem(
            edicao_id=edicao.id,
            destacado=destacado,
            motivo_destaque=motivo,
            status_ia="pendente",  # resumo de IA roda em TODOS os itens, não só destacados
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
    """Varre o feed, sincroniza as edições ainda não sincronizadas (mais recentes primeiro)."""
    try:
        edicoes_feed = listar_edicoes_recentes_feed()
    except httpx.HTTPError:
        logger.warning("Informativo STJ: falha ao ler feed de edições", exc_info=True)
        return {"edicoes_processadas": 0, "erro": "feed_indisponivel"}

    numeros_existentes = {
        n for n, in db.execute(select(InformativoStjEdicao.numero)).all()
    }
    novos = [e["numero"] for e in edicoes_feed if e["numero"] not in numeros_existentes]
    novos = sorted(novos, reverse=True)[:max_edicoes]

    resultados = []
    for numero in novos:
        resultados.append(sincronizar_edicao(numero, db))

    return {"edicoes_processadas": len(resultados), "detalhe": resultados}


def sincronizar_processar_e_notificar(db: Session) -> dict:
    """Orquestra sync -> IA -> e-mail de destaques. Usado pelo botão manual e pelo cron."""
    from app.services import ia_informativo_stj, informativo_stj_email

    resultado = sincronizar_novas_edicoes(db)
    ia_informativo_stj.processar_pendentes(db)

    for detalhe in resultado.get("detalhe") or []:
        edicao_id = detalhe.get("edicao_id") if isinstance(detalhe, dict) else None
        if not edicao_id:
            continue
        edicao = db.get(InformativoStjEdicao, edicao_id)
        if not edicao:
            continue
        itens_destacados = list(db.scalars(
            select(InformativoStjItem)
            .where(InformativoStjItem.edicao_id == edicao_id)
            .where(InformativoStjItem.destacado.is_(True))
            .where(InformativoStjItem.status_ia == "ok")
        ).all())
        if itens_destacados:
            try:
                informativo_stj_email.enviar_email_destaques(edicao, itens_destacados)
            except Exception:
                logger.warning("Informativo STJ: falha ao enviar e-mail de destaques (edição %s)", edicao.numero, exc_info=True)

    return resultado


def listar_candidatos(db: Session, apenas_nao_usados: bool = False) -> list[dict]:
    """Itens destacados com resumo de IA pronto — consumidos por PJudice e Instagram."""
    itens = db.scalars(
        select(InformativoStjItem)
        .where(InformativoStjItem.destacado.is_(True))
        .where(InformativoStjItem.status_ia == "ok")
        .order_by(InformativoStjItem.criado_em.desc())
    ).all()
    return [
        {
            "item_id": str(i.id),
            "titulo": i.titulo,
            "tema_central": i.resumo_tema_central,
            "ratio_decidendi": i.resumo_ratio_decidendi,
            "processo_numero": i.processo_numero,
            "ramo_direito": i.ramo_direito,
            "edicao_numero": db.get(InformativoStjEdicao, i.edicao_id).numero if i.edicao_id else None,
            "url_origem": i.processo_url,
        }
        for i in itens
    ]


def buscar_itens(db: Session, q: str, limit: int = 100) -> list[InformativoStjItem]:
    """Busca por texto em TODOS os itens (não só os 20 visíveis na listagem)."""
    termo = f"%{q.strip()}%"
    if not q.strip():
        return []
    return list(db.scalars(
        select(InformativoStjItem)
        .where(
            InformativoStjItem.titulo.ilike(termo)
            | InformativoStjItem.destaque_oficial.ilike(termo)
            | InformativoStjItem.texto_explicativo.ilike(termo)
            | InformativoStjItem.resumo_tema_central.ilike(termo)
            | InformativoStjItem.resumo_ratio_decidendi.ilike(termo)
            | InformativoStjItem.processo_numero.ilike(termo)
            | InformativoStjItem.ramo_direito.ilike(termo)
        )
        .order_by(InformativoStjItem.criado_em.desc())
        .limit(limit)
    ).all())


def toggle_favorito(item_id, db: Session) -> InformativoStjItem:
    item = db.get(InformativoStjItem, item_id)
    if not item:
        raise ValueError(f"Item {item_id} não encontrado")
    item.favorito = not item.favorito
    db.commit()
    return item


def listar_favoritos(db: Session) -> list[InformativoStjItem]:
    return list(db.scalars(
        select(InformativoStjItem)
        .where(InformativoStjItem.favorito.is_(True))
        .order_by(InformativoStjItem.criado_em.desc())
    ).all())
