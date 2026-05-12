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

import math
import re
import time
from datetime import date, timedelta

import httpx
from bs4 import BeautifulSoup

CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")

TRIBUNAL_URLS: dict[str, str] = {
    "TJES": "https://dje.tjes.jus.br/dje/consultaSimples.do",
    "TJSP": "https://dje.tjsp.jus.br/cdje/consultaSimples.do",
    "TJAM": "https://www.tjam.jus.br/index.php/diario-da-justica",
    "TJRJ": "https://www3.tjrj.jus.br/consultadje/",
    "DJEN": "https://comunica.pje.jus.br/",
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

COMUNICA_API_URL = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
COMUNICA_ITENS_POR_PAGINA = 50
COMUNICA_MAX_PAGINAS = 4
COMUNICA_MAX_PAGINAS_NOME = 2
COMUNICA_MAX_TENTATIVAS = 3
COMUNICA_TIMEOUT_SECONDS = 8

FONTE_POR_TRIBUNAL = {
    "TJES": "scraping_tjes",
    "TJSP": "scraping_tjsp",
    "TJAM": "scraping_tjam",
    "TJRJ": "scraping_tjrj",
    "DJEN": "scraping_djen",
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


def _normalizar_texto_busca(texto: str) -> str:
    texto = texto or ""
    texto = texto.casefold()
    substituicoes = str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüç",
        "aaaaaeeeeiiiiooooouuuuc",
    )
    texto = texto.translate(substituicoes)
    return _normalizar_espacos(texto)


def _tokenizar_relevantes(texto: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", _normalizar_texto_busca(texto))
    return [token for token in tokens if len(token) >= 4 and token not in STOPWORDS]


def _termo_parece_cnj(termo: str) -> bool:
    return len(re.sub(r"\D", "", termo or "")) == 20


def _termo_nome_buscavel(termo: str) -> bool:
    if _termo_parece_cnj(termo):
        return True
    tokens = _tokenizar_relevantes(termo)
    if len(tokens) >= 2:
        return True
    return len(tokens) == 1 and len(tokens[0]) >= 8


def _termo_exato_no_texto(texto: str, termo: str) -> bool:
    termo_norm = _normalizar_texto_busca(termo)
    if not termo_norm:
        return False
    padrao = r"(?<![a-z0-9])" + re.escape(termo_norm).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
    return re.search(padrao, _normalizar_texto_busca(texto)) is not None


def _texto_tem_match_monitorado(texto: str, termos: list[str] | None = None) -> bool:
    if not termos:
        return False
    for termo in termos:
        if not (_termo_parece_cnj(termo) or _termo_nome_buscavel(termo)):
            continue
        if _termo_exato_no_texto(texto, termo):
            return True
    return False


def expandir_termos_busca(termos: list[str] | None = None) -> list[str]:
    """
    Retorna apenas os termos originais.

    A importação do Diário precisa ser conservadora: por ora, não buscamos
    variantes/similares, porque isso trouxe publicações que não eram de
    clientes, processos ou nomes acompanhados.
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


def _formatar_numero_cnj(numero: str | None) -> str | None:
    if not numero:
        return None
    apenas_digitos = re.sub(r"\D", "", numero)
    if len(apenas_digitos) != 20:
        return numero
    return (
        f"{apenas_digitos[:7]}-{apenas_digitos[7:9]}."
        f"{apenas_digitos[9:13]}.{apenas_digitos[13]}."
        f"{apenas_digitos[14:16]}.{apenas_digitos[16:]}"
    )


def _termo_encontrado(texto: str, termos: list[str] | None = None) -> bool:
    return _texto_tem_match_monitorado(texto, termos)


def _extrair_trecho_por_termo(texto: str, termos: list[str] | None = None) -> str | None:
    if not termos:
        return None
    texto_normalizado = _normalizar_texto_busca(texto)
    for termo in termos:
        if not termo:
            continue
        termo_normalizado = _normalizar_texto_busca(termo)
        idx = texto_normalizado.find(termo_normalizado)
        if idx >= 0:
            inicio = max(0, idx - 250)
            fim = min(len(texto), idx + max(len(termo_normalizado), 1) + 1250)
            return texto[inicio:fim].strip()
    return None


def _texto_para_publicacoes(
    texto: str,
    tribunal: str,
    fonte: str,
    data_pub: date,
    termos: list[str] | None = None,
) -> list[dict]:
    if termos and not _texto_tem_match_monitorado(texto, termos):
        return []

    cnjs = list(set(CNJ_RE.findall(texto)))

    if cnjs:
        return [_montar_publicacao(texto, tribunal, fonte, data_pub, numero_cnj=cnj) for cnj in cnjs]
    if termos:
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

    if termos and not _texto_tem_match_monitorado(texto_pagina, termos):
        return []

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


def _consultas_comunica(termos: list[str] | None = None) -> list[tuple[str, int, str, str, int]]:
    """
    Gera uma lista enxuta de consultas para a API pública.
    Mantém variações úteis, mas evita dezenas de requests para um único nome.
    """
    consultas: list[tuple[str, int, str, str, int]] = []
    vistos: set[tuple[str, str]] = set()

    def adicionar(origem: str, prioridade: int, campo: str, termo: str, max_paginas: int) -> None:
        termo = _normalizar_espacos(termo)
        if len(termo) < 3:
            return
        chave = (campo, termo.casefold())
        if chave in vistos:
            return
        vistos.add(chave)
        consultas.append((origem, prioridade, campo, termo, max_paginas))

    for termo_original in termos or [""]:
        termo_original = _normalizar_espacos(termo_original)
        if not termo_original:
            continue
        if not _termo_nome_buscavel(termo_original):
            continue

        if _termo_parece_cnj(termo_original):
            adicionar(termo_original, -1, "numeroProcesso", re.sub(r"\D", "", termo_original), COMUNICA_MAX_PAGINAS)
        else:
            adicionar(termo_original, 0, "nomeAdvogado", termo_original, COMUNICA_MAX_PAGINAS_NOME)
            adicionar(termo_original, 1, "nomeParte", termo_original, COMUNICA_MAX_PAGINAS_NOME)
            adicionar(termo_original, 2, "texto", termo_original, 1)

    if termos:
        return consultas
    return [("", 0, "texto", "", 1)]


def _normalizar_data_comunica(valor: str | None) -> date | None:
    if not valor:
        return None
    valor = valor.strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(valor, formato).date()
        except ValueError:
            continue
    return None


def _comunica_para_publicacao(item: dict, tribunal_alvo: str) -> dict | None:
    texto = _normalizar_espacos(item.get("texto") or "")
    if len(texto) < 20:
        return None

    tribunal_item = (item.get("siglaTribunal") or tribunal_alvo or "").upper()
    if tribunal_alvo != "DJEN" and tribunal_item != tribunal_alvo:
        return None

    data_pub = (
        _normalizar_data_comunica(item.get("data_disponibilizacao"))
        or _normalizar_data_comunica(item.get("datadisponibilizacao"))
        or date.today()
    )
    numero_cnj = (
        item.get("numeroprocessocommascara")
        or _formatar_numero_cnj(item.get("numero_processo"))
        or _formatar_numero_cnj(item.get("numeroProcesso"))
    )
    url_fonte = item.get("link") or TRIBUNAL_URLS.get("DJEN")
    fonte = FONTE_POR_TRIBUNAL.get(tribunal_alvo, "scraping_djen")

    pub = _montar_publicacao(
        texto=texto,
        tribunal=tribunal_item,
        fonte=fonte,
        data_pub=data_pub,
        numero_cnj=numero_cnj,
    )
    pub["url_fonte"] = url_fonte
    return pub


def _buscar_comunica_api(
    tribunal: str,
    data_inicio: date,
    data_fim: date,
    termos: list[str] | None = None,
) -> list[dict]:
    """
    Consulta a API pública do DJEN/Comunica.
    Quando `tribunal` é DJEN, faz busca nacional; caso contrário, filtra a sigla.
    """
    if data_fim < data_inicio:
        data_inicio, data_fim = data_fim, data_inicio

    vistos: set[str] = set()
    resultado: list[dict] = []
    consultas = _consultas_comunica(termos)

    sucesso_por_origem: dict[str, int] = {}

    with httpx.Client(headers=HEADERS, timeout=COMUNICA_TIMEOUT_SECONDS, follow_redirects=True) as client:
        for origem, prioridade, campo, termo, max_paginas in consultas:
            if origem and sucesso_por_origem.get(origem, 99) < prioridade:
                continue

            pagina = 1
            paginas_limite = max_paginas
            itens_encontrados_nesta_consulta = 0

            while pagina <= paginas_limite:
                params = {
                    "pagina": pagina,
                    "itensPorPagina": COMUNICA_ITENS_POR_PAGINA,
                    "dataDisponibilizacaoInicio": data_inicio.isoformat(),
                    "dataDisponibilizacaoFim": data_fim.isoformat(),
                }
                if termo:
                    params[campo] = termo
                if tribunal != "DJEN":
                    params["siglaTribunal"] = tribunal

                resp = None
                for tentativa in range(1, COMUNICA_MAX_TENTATIVAS + 1):
                    try:
                        resp = client.get(COMUNICA_API_URL, params=params)
                        if resp.status_code < 500:
                            break
                    except httpx.HTTPError:
                        resp = None
                    time.sleep(min(0.6 * tentativa, 3.0))

                if not resp or not resp.is_success:
                    break

                try:
                    payload = resp.json()
                except ValueError:
                    break

                itens = payload.get("items") or []
                total = int(payload.get("count") or 0)
                paginas_limite = min(
                    max(1, math.ceil(total / COMUNICA_ITENS_POR_PAGINA)),
                    max_paginas,
                )

                for item in itens:
                    pub = _comunica_para_publicacao(item, tribunal)
                    if not pub:
                        continue
                    if termos and not _texto_tem_match_monitorado(pub.get("texto_completo") or pub.get("texto_resumo") or "", termos):
                        continue
                    itens_encontrados_nesta_consulta += 1
                    chave = str(item.get("id") or "") or "|".join(
                        [
                            pub.get("fonte", "") or "",
                            pub.get("tribunal", "") or "",
                            pub.get("numero_cnj", "") or "",
                            str(pub.get("data_publicacao", "") or ""),
                            (pub.get("texto_resumo", "") or "")[:180],
                        ]
                    )
                    if chave in vistos:
                        continue
                    vistos.add(chave)
                    resultado.append(pub)

                if not itens:
                    break
                pagina += 1

            if origem and itens_encontrados_nesta_consulta > 0:
                sucesso_por_origem[origem] = min(sucesso_por_origem.get(origem, 99), prioridade)

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
            "https://dje.tjsp.jus.br/cdje/consultaAvancada.do",
            data={
                "dadosConsulta.dtInicio": data_str,
                "dadosConsulta.dtFim": data_str,
                "dadosConsulta.cdCaderno": "-11",
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
    Consulta pública do DJEN via API nacional do Comunica.
    """
    data = data or date.today() - timedelta(days=1)
    return _buscar_comunica_api("DJEN", data, data, termos=termos)


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

    data_fim = data or date.today()
    data_inicio = data_fim if data else (date.today() - timedelta(days=max(days_back, 1) - 1))
    termos_lista = expandir_termos_busca(termos) if termos else [None]
    datas_busca = [data_fim] if data else [date.today() - timedelta(days=offset) for offset in range(0, max(days_back, 1))]

    visto: set[str] = set()
    resultado: list[dict] = []

    for tribunal in alvos:
        if tribunal not in mapa:
            continue

        # DJEN e os estados mais recentes ficam mais confiáveis via API pública do CNJ.
        if tribunal in {"DJEN", "TJES", "TJSP", "TJAM", "TJRJ"}:
            novos = _buscar_comunica_api(tribunal, data_inicio, data_fim, termos=termos)
            if novos or tribunal == "DJEN":
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
                if novos:
                    continue

        fn = mapa[tribunal]
        for data_busca in datas_busca:
            for termo in termos_lista:
                termos_individual = [termo] if termo else None
                novos = fn(data=data_busca, termos=termos_individual)
                for pub in novos:
                    if termos and not _texto_tem_match_monitorado(
                        pub.get("texto_completo") or pub.get("texto_resumo") or "",
                        termos,
                    ):
                        continue
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
