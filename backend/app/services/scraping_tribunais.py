"""
Scrapers para consulta de publicações nos diários eletrônicos dos tribunais.

Cada tribunal tem sua própria URL e estrutura de consulta.
Todos retornam lista de dicts compatíveis com o model Publicacao.

TJES  → https://dje.tjes.jus.br
TJSP  → https://dje.tjsp.jus.br/cdje/consultaSimples.do
TJAM  → https://www.tjam.jus.br/index.php/diario-da-justica
TJRJ  → https://www3.tjrj.jus.br/consultadje/
DJEN  → legado/experimental (não usado como fonte nacional principal)
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
    "DJEN": "https://www.cnj.jus.br/programas-e-acoes/processo-judicial-eletronico-pje/comunicacoes-processuais/",
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

STOPWORDS = {
    "da", "das", "de", "do", "dos", "e", "em", "na", "nas", "no", "nos",
    "sa", "s.a", "s/a", "sociedade", "advogados", "advocacia", "ltda", "me", "epp",
}


def _inferir_tipo_ato(texto: str) -> str:
    t = texto.lower()
    for tipo, kws in TIPO_ATO_KEYWORDS.items():
        if any(k in t for k in kws):
            return tipo
    return "outro"


def _normalizar_espacos(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").strip())


def expandir_termos_busca(termos: list[str] | None = None) -> list[str]:
    """
    Gera variações úteis para nomes e razões sociais quando o portal
    indexa apenas parte do termo original.
    """
    if not termos:
        return []

    vistos: set[str] = set()
    resultado: list[str] = []

    def adicionar(valor: str) -> None:
        valor = _normalizar_espacos(valor)
        if len(valor) < 3:
            return
        chave = valor.casefold()
        if chave in vistos:
            return
        vistos.add(chave)
        resultado.append(valor)

    for termo in termos:
        termo_limpo = _normalizar_espacos(termo)
        if not termo_limpo:
            continue

        adicionar(termo_limpo)

        palavras = re.findall(r"[A-Za-zÀ-ÿ0-9]+", termo_limpo)
        relevantes = [
            p for p in palavras
            if len(p) >= 4 and p.casefold() not in STOPWORDS
        ]

        for palavra in relevantes:
            adicionar(palavra)

        if len(relevantes) >= 2:
            adicionar(f"{relevantes[0]} {relevantes[-1]}")
            adicionar(" ".join(relevantes[:2]))
            adicionar(" ".join(relevantes[-2:]))

        if len(relevantes) >= 3:
            adicionar(" ".join(relevantes[:3]))
            adicionar(" ".join(relevantes[-3:]))

    return resultado


def _montar_publicacao(
    texto: str,
    tribunal: str,
    fonte: str,
    data_pub: date,
    numero_cnj: str | None = None,
) -> dict:
    tipo = _inferir_tipo_ato(texto)
    resumo = texto[:500].strip()
    completo = texto[:5000]
    url = TRIBUNAL_URLS.get(tribunal)
    return {
        "fonte": fonte,
        "data_publicacao": data_pub,
        "numero_cnj": numero_cnj,
        "tipo_ato": tipo,
        "tribunal": tribunal,
        "texto_resumo": resumo,
        "texto_completo": completo,
        "email_message_id": None,
        "url_fonte": url,
    }


def _termo_encontrado(texto: str, termos: list[str] | None = None) -> bool:
    if not termos:
        return False
    texto_normalizado = texto.lower()
    return any(termo and termo.lower() in texto_normalizado for termo in termos)


def _extrair_trecho_por_termo(texto: str, termos: list[str] | None = None) -> str | None:
    if not termos:
        return None
    texto_normalizado = texto.lower()
    for termo in termos:
        if not termo:
            continue
        idx = texto_normalizado.find(termo.lower())
        if idx >= 0:
            inicio = max(0, idx - 250)
            fim = min(len(texto), idx + max(len(termo), 1) + 1250)
            return texto[inicio:fim].strip()
    return None


def _texto_para_publicacoes(
    texto: str,
    tribunal: str,
    fonte: str,
    data_pub: date,
    termos: list[str] | None = None,
) -> list[dict]:
    cnjs = list(set(CNJ_RE.findall(texto)))

    if cnjs:
        return [_montar_publicacao(texto, tribunal, fonte, data_pub, numero_cnj=cnj) for cnj in cnjs]
    if _termo_encontrado(texto, termos):
        return [_montar_publicacao(texto, tribunal, fonte, data_pub)]
    return []


def _extrair_por_cnj_global(
    soup: BeautifulSoup,
    tribunal: str,
    fonte: str,
    data_pub: date,
    termos: list[str] | None = None,
) -> list[dict]:
    """
    Fallback: varre o texto completo da página procurando números CNJ.
    Extrai um trecho de contexto em volta de cada CNJ encontrado.
    """
    texto_pagina = soup.get_text(" ", strip=True)
    cnjs = list(set(CNJ_RE.findall(texto_pagina)))
    resultado: list[dict] = []

    for cnj in cnjs:
        idx = texto_pagina.find(cnj)
        inicio = max(0, idx - 200)
        fim = min(len(texto_pagina), idx + 800)
        trecho = texto_pagina[inicio:fim].strip()
        resultado.append(_montar_publicacao(trecho, tribunal, fonte, data_pub, numero_cnj=cnj))
    if not resultado:
        trecho_termo = _extrair_trecho_por_termo(texto_pagina, termos)
        if trecho_termo:
            resultado.append(_montar_publicacao(trecho_termo, tribunal, fonte, data_pub))
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
            publicacoes.extend(_texto_para_publicacoes(texto, "TJES", "scraping_tjes", data, termos=termos))

        # Fallback global: varre a página toda por CNJs
        if not publicacoes:
            publicacoes.extend(_extrair_por_cnj_global(soup, "TJES", "scraping_tjes", data, termos=termos))

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
            publicacoes.extend(_texto_para_publicacoes(texto, "TJSP", "scraping_tjsp", data, termos=termos))

        if not publicacoes:
            publicacoes.extend(_extrair_por_cnj_global(soup, "TJSP", "scraping_tjsp", data, termos=termos))

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
            publicacoes.extend(_texto_para_publicacoes(texto, "TJAM", "scraping_tjam", data, termos=termos))

        if not publicacoes:
            publicacoes.extend(_extrair_por_cnj_global(soup, "TJAM", "scraping_tjam", data, termos=termos))

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
            publicacoes.extend(_texto_para_publicacoes(texto, "TJRJ", "scraping_tjrj", data, termos=termos))

        if not publicacoes:
            publicacoes.extend(_extrair_por_cnj_global(soup, "TJRJ", "scraping_tjrj", data, termos=termos))

    except Exception:
        pass

    return publicacoes


# ── DJEN legado/experimental ──────────────────────────────────────────────────

def scrape_djen(data: date | None = None, termos: list[str] | None = None) -> list[dict]:
    """
    Consulta pública best-effort do DJEN.
    Ainda é menos previsível do que os diários estaduais.
    """
    data = data or date.today() - timedelta(days=1)
    data_str = data.strftime("%d/%m/%Y")
    publicacoes: list[dict] = []
    vistos: set[str] = set()

    for termo in expandir_termos_busca(termos) or [""]:
        try:
            resp = httpx.get(
                "https://scon.stj.jus.br/SCON/pesquisar.jsp",
                params={
                    "b": "ACOR",
                    "livre": termo,
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
            blocos = soup.find_all("div", class_=re.compile(r"documento|decisao|resultado", re.I))
            if not blocos:
                blocos = soup.find_all("table", {"class": re.compile(r"resultado|lista", re.I)})

            candidatos: list[dict] = []
            for bloco in blocos:
                texto = bloco.get_text(" ", strip=True)
                if len(texto) < 50:
                    continue
                candidatos.extend(_texto_para_publicacoes(texto, "DJEN", "scraping_djen", data, termos=[termo]))

            if not candidatos:
                candidatos.extend(_extrair_por_cnj_global(soup, "DJEN", "scraping_djen", data, termos=[termo]))

            for pub in candidatos:
                chave = "|".join(
                    [
                        str(pub.get("data_publicacao", "")),
                        pub.get("numero_cnj", "") or "",
                        (pub.get("texto_resumo", "") or "")[:180],
                    ]
                )
                if chave not in vistos:
                    vistos.add(chave)
                    publicacoes.append(pub)
        except Exception:
            continue

    if not publicacoes:
        try:
            resp = httpx.get(
                "https://dje.stj.jus.br/cgi-bin/dgrecadv.exe",
                params={"DataPublicacao": data_str, "Pesquisa": " ".join(termos or [])},
                headers=HEADERS,
                timeout=20,
                follow_redirects=True,
            )
            if resp.is_success:
                soup = BeautifulSoup(resp.text, "html.parser")
                for pub in _extrair_por_cnj_global(soup, "DJEN", "scraping_djen", data, termos=termos):
                    chave = "|".join(
                        [
                            str(pub.get("data_publicacao", "")),
                            pub.get("numero_cnj", "") or "",
                            (pub.get("texto_resumo", "") or "")[:180],
                        ]
                    )
                    if chave not in vistos:
                        vistos.add(chave)
                        publicacoes.append(pub)
        except Exception:
            pass

    return publicacoes


# ── Dispatcher ────────────────────────────────────────────────────────────────

def scrape_todos(
    tribunais: list[str] | None = None,
    data: date | None = None,
    termos: list[str] | None = None,
    days_back: int = 1,
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
    termos_lista = expandir_termos_busca(termos) if termos else [None]
    datas_busca = [data] if data else [date.today() - timedelta(days=offset) for offset in range(1, max(days_back, 1) + 1)]

    visto: set[str] = set()
    resultado: list[dict] = []

    for tribunal in alvos:
        if tribunal not in mapa:
            continue
        fn = mapa[tribunal]
        for data_busca in datas_busca:
            for termo in termos_lista:
                termos_individual = [termo] if termo else None
                novos = fn(data=data_busca, termos=termos_individual)
                for pub in novos:
                    chave = "|".join(
                        [
                            str(pub.get("data_publicacao", "")),
                            pub.get("fonte", "") or "",
                            pub.get("tribunal", "") or "",
                            pub.get("numero_cnj", "") or "",
                            (pub.get("texto_resumo", "") or "")[:180],
                        ]
                    )
                    if chave not in visto:
                        visto.add(chave)
                        resultado.append(pub)

    return resultado
