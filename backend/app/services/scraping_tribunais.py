"""
Scrapers para consulta de publicações nos diários eletrônicos dos tribunais.

Cada tribunal tem sua própria URL e estrutura de consulta.
Todos retornam lista de dicts compatíveis com o model Publicacao.

TJES  → https://dje.tjes.jus.br
TJSP  → https://dje.tjsp.jus.br/cdje/consultaSimples.do
TJAM  → https://www.tjam.jus.br/index.php/diario-da-justica
TJRJ  → https://www3.tjrj.jus.br/consultadje/
DJEN  → https://dje.stj.jus.br (Diário da Justiça Eletrônico Nacional — STJ)
"""

import re
from datetime import date, timedelta

import httpx
from bs4 import BeautifulSoup

CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")

TRIBUNAL_URLS: dict[str, str] = {
    "TJES": "https://dje.tjes.jus.br/dje/consultaSimples.do",
    "TJSP": "https://dje.tjsp.jus.br/cdje/consultaSimples.do",
    "TJAM": "https://www.tjam.jus.br/index.php/diario-da-justica",
    "TJRJ": "https://www3.tjrj.jus.br/consultadje/",
    "DJEN": "https://scon.stj.jus.br/SCON/pesquisar.jsp",
}

TIPO_ATO_KEYWORDS = {
    "sentenca": ["sentença", "sentenca", "procedente", "improcedente"],
    "acordao":  ["acórdão", "acordao", "provimento", "câmara", "turma"],
    "decisao":  ["decisão interlocutória", "decisao", "indefiro", "defiro"],
    "intimacao":["intimado", "intimação", "intime-se"],
    "citacao":  ["citado", "citação", "cite-se"],
    "despacho": ["despacho", "vista", "manifeste-se"],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def _inferir_tipo_ato(texto: str) -> str:
    t = texto.lower()
    for tipo, kws in TIPO_ATO_KEYWORDS.items():
        if any(k in t for k in kws):
            return tipo
    return "outro"


def _texto_para_publicacoes(texto: str, tribunal: str, fonte: str, data_pub: date) -> list[dict]:
    cnjs = list(set(CNJ_RE.findall(texto)))
    tipo = _inferir_tipo_ato(texto)
    resumo = texto[:500].strip()
    completo = texto[:5000]
    url = TRIBUNAL_URLS.get(tribunal)

    if cnjs:
        return [
            {
                "fonte": fonte,
                "data_publicacao": data_pub,
                "numero_cnj": cnj,
                "tipo_ato": tipo,
                "tribunal": tribunal,
                "texto_resumo": resumo,
                "texto_completo": completo,
                "email_message_id": None,
                "url_fonte": url,
            }
            for cnj in cnjs
        ]
    return []


def _extrair_por_cnj_global(
    soup: BeautifulSoup, tribunal: str, fonte: str, data_pub: date
) -> list[dict]:
    """
    Fallback: varre o texto completo da página procurando números CNJ.
    Extrai um trecho de contexto em volta de cada CNJ encontrado.
    """
    texto_pagina = soup.get_text(" ", strip=True)
    cnjs = list(set(CNJ_RE.findall(texto_pagina)))
    resultado: list[dict] = []
    url = TRIBUNAL_URLS.get(tribunal)

    for cnj in cnjs:
        idx = texto_pagina.find(cnj)
        inicio = max(0, idx - 200)
        fim = min(len(texto_pagina), idx + 800)
        trecho = texto_pagina[inicio:fim].strip()
        tipo = _inferir_tipo_ato(trecho)
        resultado.append({
            "fonte": fonte,
            "data_publicacao": data_pub,
            "numero_cnj": cnj,
            "tipo_ato": tipo,
            "tribunal": tribunal,
            "texto_resumo": trecho[:500],
            "texto_completo": trecho,
            "email_message_id": None,
            "url_fonte": url,
        })
    return resultado


# ── TJES ──────────────────────────────────────────────────────────────────────

def scrape_tjes(data: date | None = None, termos: list[str] | None = None) -> list[dict]:
    """
    Consulta o DJe do TJES.
    O portal permite busca por texto livre (nome de parte, número de processo).
    """
    data = data or date.today() - timedelta(days=1)
    data_str = data.strftime("%d/%m/%Y")
    publicacoes: list[dict] = []

    try:
        # Endpoint de busca pública do DJe TJES
        resp = httpx.post(
            "https://dje.tjes.jus.br/dje/consultaSimples.do",
            data={
                "dadosConsulta.dtInicio": data_str,
                "dadosConsulta.dtFim": data_str,
                "dadosConsulta.pesquisaLivre": " ".join(termos or [""]),
                "pagina": "1",
            },
            headers=HEADERS,
            timeout=15,
            follow_redirects=True,
        )
        if not resp.is_success:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        # Extrai blocos de texto das publicações
        blocos = soup.find_all("div", class_=re.compile(r"publicacao|conteudo|texto", re.I))
        if not blocos:
            blocos = soup.find_all("td")

        for bloco in blocos:
            texto = bloco.get_text(" ", strip=True)
            if len(texto) < 50:
                continue
            publicacoes.extend(_texto_para_publicacoes(texto, "TJES", "scraping_tjes", data))

        # Fallback global: varre a página toda por CNJs
        if not publicacoes:
            publicacoes.extend(_extrair_por_cnj_global(soup, "TJES", "scraping_tjes", data))

    except Exception:
        pass

    return publicacoes


# ── TJSP ──────────────────────────────────────────────────────────────────────

def scrape_tjsp(data: date | None = None, termos: list[str] | None = None) -> list[dict]:
    """
    Consulta o DJe do TJSP via busca pública.
    """
    data = data or date.today() - timedelta(days=1)
    data_str = data.strftime("%d/%m/%Y")
    publicacoes: list[dict] = []

    try:
        resp = httpx.post(
            "https://dje.tjsp.jus.br/cdje/consultaSimples.do",
            data={
                "dadosConsulta.dtInicio": data_str,
                "dadosConsulta.dtFim": data_str,
                "dadosConsulta.pesquisaLivre": " ".join(termos or [""]),
                "pagina": "1",
            },
            headers=HEADERS,
            timeout=15,
            follow_redirects=True,
        )
        if not resp.is_success:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        blocos = soup.find_all("div", class_=re.compile(r"publicacao|conteudo", re.I))
        if not blocos:
            blocos = soup.find_all("p")

        for bloco in blocos:
            texto = bloco.get_text(" ", strip=True)
            if len(texto) < 50:
                continue
            publicacoes.extend(_texto_para_publicacoes(texto, "TJSP", "scraping_tjsp", data))

        if not publicacoes:
            publicacoes.extend(_extrair_por_cnj_global(soup, "TJSP", "scraping_tjsp", data))

    except Exception:
        pass

    return publicacoes


# ── TJAM ──────────────────────────────────────────────────────────────────────

def scrape_tjam(data: date | None = None, termos: list[str] | None = None) -> list[dict]:
    """
    Consulta o DJe do TJAM.
    """
    data = data or date.today() - timedelta(days=1)
    data_str = data.strftime("%d/%m/%Y")
    publicacoes: list[dict] = []

    try:
        resp = httpx.get(
            "https://www.tjam.jus.br/index.php/diario-da-justica",
            params={
                "option": "com_diario",
                "task": "pesquisa",
                "data": data_str,
                "texto": " ".join(termos or [""]),
            },
            headers=HEADERS,
            timeout=15,
            follow_redirects=True,
        )
        if not resp.is_success:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        blocos = soup.find_all(["div", "p", "td"], string=CNJ_RE)

        for bloco in blocos:
            texto = bloco.get_text(" ", strip=True)
            if len(texto) < 50:
                continue
            publicacoes.extend(_texto_para_publicacoes(texto, "TJAM", "scraping_tjam", data))

        if not publicacoes:
            publicacoes.extend(_extrair_por_cnj_global(soup, "TJAM", "scraping_tjam", data))

    except Exception:
        pass

    return publicacoes


# ── TJRJ ──────────────────────────────────────────────────────────────────────

def scrape_tjrj(data: date | None = None, termos: list[str] | None = None) -> list[dict]:
    """
    Consulta o DJe do TJRJ.
    """
    data = data or date.today() - timedelta(days=1)
    data_str = data.strftime("%d/%m/%Y")
    publicacoes: list[dict] = []

    try:
        resp = httpx.post(
            "https://www3.tjrj.jus.br/consultadje/consultadje.do",
            data={
                "dtInicio": data_str,
                "dtFim": data_str,
                "txtPesquisa": " ".join(termos or [""]),
                "cmbCaderno": "0",
            },
            headers=HEADERS,
            timeout=15,
            follow_redirects=True,
        )
        if not resp.is_success:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        blocos = soup.find_all("div", class_=re.compile(r"resultado|publicacao|texto", re.I))
        if not blocos:
            blocos = soup.find_all("td")

        for bloco in blocos:
            texto = bloco.get_text(" ", strip=True)
            if len(texto) < 50:
                continue
            publicacoes.extend(_texto_para_publicacoes(texto, "TJRJ", "scraping_tjrj", data))

        if not publicacoes:
            publicacoes.extend(_extrair_por_cnj_global(soup, "TJRJ", "scraping_tjrj", data))

    except Exception:
        pass

    return publicacoes


# ── DJEN (Diário de Justiça Eletrônico Nacional — STJ) ───────────────────────

def scrape_djen(data: date | None = None, termos: list[str] | None = None) -> list[dict]:
    """
    Consulta o DJEN do STJ via pesquisa de jurisprudência.
    O portal permite busca por nome de parte, advogado ou número de processo.
    """
    data = data or date.today() - timedelta(days=1)
    data_str = data.strftime("%d/%m/%Y")
    publicacoes: list[dict] = []

    # Busca por cada termo individualmente para maximizar resultados
    termos_busca = termos or [""]
    visto: set[str] = set()

    for termo in termos_busca:
        try:
            resp = httpx.get(
                "https://scon.stj.jus.br/SCON/pesquisar.jsp",
                params={
                    "b": "ACOR",
                    "livre": termo or "",
                    "data": data_str,
                    "processo": "",
                    "tp": "T",
                },
                headers=HEADERS,
                timeout=20,
                follow_redirects=True,
            )
            if not resp.is_success:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Tenta encontrar resultados de acórdão/decisão
            blocos = soup.find_all("div", class_=re.compile(r"documento|decisao|resultado", re.I))
            if not blocos:
                blocos = soup.find_all("table", {"class": re.compile(r"resultado|lista", re.I)})
            if not blocos:
                # fallback global
                novos = _extrair_por_cnj_global(soup, "DJEN", "scraping_djen", data)
                for p in novos:
                    chave = p.get("numero_cnj", "")
                    if chave and chave not in visto:
                        visto.add(chave)
                        publicacoes.append(p)
                continue

            for bloco in blocos:
                texto = bloco.get_text(" ", strip=True)
                if len(texto) < 50:
                    continue
                for p in _texto_para_publicacoes(texto, "DJEN", "scraping_djen", data):
                    chave = p.get("numero_cnj", "")
                    if chave and chave not in visto:
                        visto.add(chave)
                        publicacoes.append(p)

        except Exception:
            continue

    # Segunda tentativa: DJe do STJ por data
    if not publicacoes:
        try:
            resp2 = httpx.get(
                "https://dje.stj.jus.br/cgi-bin/dgrecadv.exe",
                params={"DataPublicacao": data_str, "Pesquisa": " ".join(termos or [])},
                headers=HEADERS,
                timeout=20,
                follow_redirects=True,
            )
            if resp2.is_success:
                soup2 = BeautifulSoup(resp2.text, "html.parser")
                publicacoes.extend(_extrair_por_cnj_global(soup2, "DJEN", "scraping_djen", data))
        except Exception:
            pass

    return publicacoes


# ── Dispatcher ────────────────────────────────────────────────────────────────

def scrape_todos(
    tribunais: list[str] | None = None,
    data: date | None = None,
    termos: list[str] | None = None,
) -> list[dict]:
    """
    Roda todos os scrapers (ou só os solicitados) e retorna lista unificada.
    Cada termo é buscado INDIVIDUALMENTE para não combinar nomes diferentes.
    """
    mapa = {
        "TJES": scrape_tjes,
        "TJSP": scrape_tjsp,
        "TJAM": scrape_tjam,
        "TJRJ": scrape_tjrj,
        "DJEN": scrape_djen,
    }
    alvos = tribunais or list(mapa.keys())

    # Busca cada termo separado — evita "João Maria Silva" que não acha nada
    termos_lista = termos if termos else [None]

    visto: set[str] = set()
    resultado: list[dict] = []

    for tribunal in alvos:
        if tribunal not in mapa:
            continue
        fn = mapa[tribunal]
        for termo in termos_lista:
            termos_individual = [termo] if termo else None
            novos = fn(data=data, termos=termos_individual)
            for pub in novos:
                chave = (
                    pub.get("numero_cnj", "")
                    + "|" + pub.get("fonte", "")
                    + "|" + str(pub.get("data_publicacao", ""))
                )
                if chave not in visto:
                    visto.add(chave)
                    resultado.append(pub)

    return resultado
