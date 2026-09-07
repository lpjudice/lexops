"""Escreve o conteúdo de uma peça (gerada pela IA em ia_despacho.gerar_peca)
num Google Doc real — parte de uma cópia do timbrado do escritório, com
negrito de verdade e os itens faltantes (XXX) em vermelho.
"""
import logging
import re

import httpx

from app.services.google_drive import _auth_headers, _is_unauthorized, _load_tokens, _refresh, copiar_arquivo_por_id

logger = logging.getLogger(__name__)

DOCS_API = "https://docs.googleapis.com/v1/documents"

VERMELHO = {"color": {"rgbColor": {"red": 0.80, "green": 0.10, "blue": 0.10}}}

TIMBRADO_TEMPLATE_ID = "18DTRqtJWXZkr9Jc0EW7LAMb1pL4jBxX1VHmNvsZ_kwM"


def _parse_markup(texto: str, start_offset: int) -> tuple[str, list[dict]]:
    """Remove marcadores **negrito** (mantém o texto) e detecta trechos
    XXX...XXX (mantém literal). Retorna (texto_limpo, estilos) com índices
    relativos a start_offset."""
    partes = re.split(r"(\*\*[^*]+\*\*|XXX[^X]*XXX)", texto)
    limpo: list[str] = []
    estilos: list[dict] = []
    pos = start_offset
    for parte in partes:
        if not parte:
            continue
        if parte.startswith("**") and parte.endswith("**"):
            inner = parte[2:-2]
            estilos.append({"start": pos, "end": pos + len(inner), "bold": True})
            limpo.append(inner)
            pos += len(inner)
        elif parte.startswith("XXX"):
            estilos.append({"start": pos, "end": pos + len(parte), "red": True})
            limpo.append(parte)
            pos += len(parte)
        else:
            limpo.append(parte)
            pos += len(parte)
    return "".join(limpo), estilos


_NUMERACAO_PROPRIA = re.compile(r"^\s*\d+[\.\)]\s*")


def montar_texto_e_estilos(peca: dict) -> tuple[str, list[dict], dict, dict]:
    """Monta o texto final e a lista de estilos (negrito/vermelho) a aplicar
    depois de inserir o texto. A numeração dos parágrafos do corpo usa lista
    numerada NATIVA do Docs (não texto "1. " manual) — se ajusta sozinha e
    não duplica caso a IA já tenha incluído seu próprio número. Retorna
    também os ranges do título (centralizar) e do corpo (aplicar numeração)."""
    blocos: list[str] = []
    estilos: list[dict] = []
    pos = 0
    titulo_range = {"start": 0, "end": 0}
    corpo_range = {"start": 0, "end": 0}

    def add(texto: str, is_titulo: bool = False, separador: str = "\n\n") -> None:
        nonlocal pos
        limpo, est = _parse_markup(texto, pos)
        estilos.extend(est)
        if is_titulo:
            titulo_range["start"] = pos
            titulo_range["end"] = pos + len(limpo)
            estilos.append({"start": pos, "end": pos + len(limpo), "bold": True})
        blocos.append(limpo)
        pos += len(limpo)
        blocos.append(separador)
        pos += len(separador)

    add(peca["titulo_peca"], is_titulo=True)
    add(peca["enderecamento"])
    add(peca["qualificacao"])

    corpo_range["start"] = pos
    paragrafos = peca.get("paragrafos") or []
    for i, paragrafo in enumerate(paragrafos):
        # Remove numeração que a própria IA às vezes inclui — quem numera é o Docs.
        texto_limpo = _NUMERACAO_PROPRIA.sub("", paragrafo)
        # Sem linha em branco entre itens da lista numerada — senão o Docs
        # numera a linha vazia também (item fantasma). A última leva \n\n
        # normal pra separar do fechamento.
        ultimo = i == len(paragrafos) - 1
        add(texto_limpo, separador="\n\n" if ultimo else "\n")
    corpo_range["end"] = pos - 2  # tira o \n\n final do último parágrafo

    add(peca["fechamento"])

    return "".join(blocos), estilos, titulo_range, corpo_range


def _docs_request(method: str, path: str, tokens: dict, **kwargs):
    h = _auth_headers(tokens)
    r = httpx.request(method, f"{DOCS_API}{path}", headers=h, timeout=30, **kwargs)
    r.raise_for_status()
    return r.json()


def _com_refresh(fn):
    tokens = _load_tokens()
    if not tokens:
        return None
    try:
        return fn(tokens)
    except Exception as exc:
        if not _is_unauthorized(exc):
            logger.warning("Falha na chamada Docs API: %s", exc)
            return None
        tokens2 = _refresh(tokens)
        try:
            return fn(tokens2)
        except Exception as exc2:
            logger.warning("Falha na chamada Docs API apos refresh: %s", exc2)
            return None


# Marcador que separa o cabeçalho estruturado do corpo do informativo no
# Doc — usado pra localizar onde o corpo começa (não é conteúdo real, some
# visualmente por causa da borda inferior aplicada no parágrafo).
SEPARADOR_INFORMATIVO = "•••"


def provisionar_template_informativo(parent_folder_id: str | None = None) -> dict | None:
    """Cria (uma vez só) o modelo-base dos informativos: cópia do timbrado do
    escritório + esqueleto com uma linha pequena de identificação (nº/mês,
    tipo "dateline" à direita, quebrando o visual de doutrina), o tema como
    título grande, o subtema como subtítulo, resumo estruturado, uma linha
    separadora e o corpo. É só um Google Doc — pode ser aberto e ajustado
    livremente (fonte, cores, logo) depois de criado; os próximos
    informativos copiam a versão mais recente dele."""
    copia = copiar_arquivo_por_id(TIMBRADO_TEMPLATE_ID, "Modelo Base — Informativo (não usar diretamente)",
                                   parent_folder_id=parent_folder_id)
    if not copia:
        return None
    doc_id = copia["id"]

    kicker = "INFORMATIVO Nº {{NUMERO}} · {{MES}}"
    esqueleto = (
        f"{kicker}\n\n"
        "{{TEMA}}\n"
        "{{SUBTEMA}}\n\n"
        "RESUMO ESTRUTURADO\n"
        "{{RESUMO}}\n\n"
        f"{SEPARADOR_INFORMATIVO}\n\n"
        "{{CORPO}}"
    )

    def _montar(tokens: dict):
        doc = _docs_request("GET", f"/{doc_id}", tokens)
        end_index = doc["body"]["content"][-1]["endIndex"]

        requests = []
        if end_index > 2:
            requests.append({"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end_index - 1}}})
        requests.append({"insertText": {"location": {"index": 1}, "text": esqueleto}})
        requests.append({"deleteParagraphBullets": {"range": {"startIndex": 1, "endIndex": 1 + len(esqueleto)}}})
        _docs_request("POST", f"/{doc_id}:batchUpdate", tokens, json={"requests": requests})

        def _rng(marcador: str) -> tuple[int, int]:
            i = 1 + esqueleto.index(marcador)
            return i, i + len(marcador)

        kicker_start, kicker_end = 1, 1 + len(kicker)
        tema_start, tema_end = _rng("{{TEMA}}")
        subtema_start, subtema_end = _rng("{{SUBTEMA}}")
        resumo_label_start, resumo_label_end = _rng("RESUMO ESTRUTURADO")
        sep_start, sep_end = _rng(SEPARADOR_INFORMATIVO)

        CINZA = {"color": {"rgbColor": {"red": 0.45, "green": 0.45, "blue": 0.45}}}
        fmt_requests = [
            # Kicker "Informativo nº X · Mês": pequeno, cinza, alinhado à
            # direita — dateline que quebra o visual de texto de doutrina.
            {"updateTextStyle": {
                "range": {"startIndex": kicker_start, "endIndex": kicker_end},
                "textStyle": {"fontSize": {"magnitude": 9, "unit": "PT"}, "foregroundColor": CINZA},
                "fields": "fontSize,foregroundColor",
            }},
            {"updateParagraphStyle": {
                "range": {"startIndex": kicker_start, "endIndex": kicker_end},
                "paragraphStyle": {"alignment": "END"},
                "fields": "alignment",
            }},
            # Tema = título de verdade do informativo: grande e em negrito.
            {"updateTextStyle": {
                "range": {"startIndex": tema_start, "endIndex": tema_end},
                "textStyle": {"bold": True, "fontSize": {"magnitude": 20, "unit": "PT"}},
                "fields": "bold,fontSize",
            }},
            # Subtema: subtítulo médio, itálico, cinza.
            {"updateTextStyle": {
                "range": {"startIndex": subtema_start, "endIndex": subtema_end},
                "textStyle": {"italic": True, "fontSize": {"magnitude": 12, "unit": "PT"}, "foregroundColor": CINZA},
                "fields": "italic,fontSize,foregroundColor",
            }},
            {"updateTextStyle": {
                "range": {"startIndex": resumo_label_start, "endIndex": resumo_label_end},
                "textStyle": {"bold": True},
                "fields": "bold",
            }},
            # Linha separadora: borda inferior no parágrafo do marcador (o
            # texto do marcador em si não deve aparecer — cor branca).
            {"updateTextStyle": {
                "range": {"startIndex": sep_start, "endIndex": sep_end},
                "textStyle": {"foregroundColor": {"color": {"rgbColor": {"red": 1, "green": 1, "blue": 1}}}, "fontSize": {"magnitude": 1, "unit": "PT"}},
                "fields": "foregroundColor,fontSize",
            }},
            {"updateParagraphStyle": {
                "range": {"startIndex": sep_start, "endIndex": sep_end},
                "paragraphStyle": {
                    "borderBottom": {
                        "color": {"color": {"rgbColor": {"red": 0.6, "green": 0.6, "blue": 0.6}}},
                        "width": {"magnitude": 1, "unit": "PT"},
                        "padding": {"magnitude": 4, "unit": "PT"},
                        "dashStyle": "SOLID",
                    },
                },
                "fields": "borderBottom",
            }},
        ]
        _docs_request("POST", f"/{doc_id}:batchUpdate", tokens, json={"requests": fmt_requests})
        return True

    _com_refresh(_montar)
    return {"id": doc_id, "webViewLink": copia.get("webViewLink")}


def preencher_cabecalho_informativo(doc_id: str, numero: int, mes_label: str, tema: str, subtema: str) -> bool:
    """Preenche os marcadores {{NUMERO}}/{{MES}}/{{TEMA}}/{{SUBTEMA}}/{{TITULO}}
    de um Doc recém-copiado do template. Usa replaceAllText — não precisa
    calcular índice nenhum. {{TITULO}} recebe o mesmo texto de {{TEMA}} (pra
    repetir o título grande logo acima do corpo, se o modelo tiver esse
    marcador — é opcional, replaceAllText simplesmente não faz nada se não
    achar o texto). O resumo e as perguntas-teaser são preenchidos depois,
    por `substituir_resumo_informativo`/`substituir_perguntas_informativo`
    (a IA gera junto com o corpo)."""
    valores = {
        "{{NUMERO}}": str(numero),
        "{{MES}}": mes_label,
        "{{TEMA}}": tema or "",
        "{{TITULO}}": tema or "",
        "{{SUBTEMA}}": subtema or "—",
    }
    requests = [
        {"replaceAllText": {"containsText": {"text": token, "matchCase": True}, "replaceText": valor}}
        for token, valor in valores.items()
    ]

    def _fazer(tokens: dict):
        _docs_request("POST", f"/{doc_id}:batchUpdate", tokens, json={"requests": requests})
        return True

    return bool(_com_refresh(_fazer))


# Texto de cabeçalho usado como âncora pra localizar onde entram as 2-3
# perguntas-teaser ("O que você vai encontrar") — precisa bater com o que
# está escrito no modelo (Google Doc). Ajuste aqui se o texto no Doc mudar.
HEADING_PERGUNTAS = "O QUE VOCÊ VAI ENCONTRAR"


def _substituir_paragrafo_apos_heading(doc_id: str, heading_texto: str, novo_texto: str) -> bool:
    """Substitui o parágrafo logo abaixo de um texto de cabeçalho fixo
    (busca case-insensitive) pelo `novo_texto`. Localiza pelo parágrafo
    seguinte ao cabeçalho, então funciona tanto na 1ª vez (ainda com um
    placeholder tipo {{X}}) quanto em regenerações."""
    def _achar(tokens: dict):
        doc = _docs_request("GET", f"/{doc_id}", tokens)
        paras = _paragrafos_do_doc(doc)
        for i, (txt, _s, _e) in enumerate(paras):
            if heading_texto.lower() in txt.lower() and i + 1 < len(paras):
                return paras[i + 1]
        return None

    alvo = _com_refresh(_achar)
    if not alvo:
        return False
    _texto, start, end = alvo

    def _escrever(tokens: dict):
        requests = []
        if end - 1 > start:
            requests.append({"deleteContentRange": {"range": {"startIndex": start, "endIndex": end - 1}}})
        if novo_texto:
            requests.append({"insertText": {"location": {"index": start}, "text": novo_texto}})
        if requests:
            _docs_request("POST", f"/{doc_id}:batchUpdate", tokens, json={"requests": requests})
        return True

    return bool(_com_refresh(_escrever))


def substituir_resumo_informativo(doc_id: str, resumo: str) -> bool:
    """Substitui o parágrafo logo abaixo de "RESUMO ESTRUTURADO" pelo texto
    informado (curto — 1-2 frases ou palavras-chave)."""
    return _substituir_paragrafo_apos_heading(doc_id, "RESUMO ESTRUTURADO", resumo)


def substituir_perguntas_informativo(doc_id: str, perguntas: list[str]) -> bool:
    """Substitui o parágrafo logo abaixo do cabeçalho `HEADING_PERGUNTAS`
    pelas 2-3 perguntas-teaser, juntas num único parágrafo (separadas por
    " · ") — de propósito uma linha só, pra `_substituir_paragrafo_apos_heading`
    continuar funcionando de forma idempotente em regenerações (se virassem
    parágrafos separados, só o primeiro seria limpo numa 2ª geração)."""
    texto = " · ".join(p.strip().rstrip("?") + "?" for p in perguntas if p.strip())
    return _substituir_paragrafo_apos_heading(doc_id, HEADING_PERGUNTAS, texto)


def _paragrafos_do_doc(doc: dict) -> list[tuple[str, int, int]]:
    """[(texto_do_paragrafo, startIndex, endIndex), ...] de um Doc já lido."""
    saida = []
    for elemento in doc.get("body", {}).get("content", []):
        paragrafo = elemento.get("paragraph")
        if not paragrafo:
            continue
        texto = "".join((it.get("textRun") or {}).get("content", "") for it in paragrafo.get("elements", []))
        saida.append((texto, elemento.get("startIndex", 0), elemento["endIndex"]))
    return saida


def ler_corpo_documento(doc_id: str) -> str | None:
    """Lê só o corpo do informativo (texto depois do separador). Docs
    antigos sem separador (ou o template original) devolvem o texto inteiro."""
    def _ler(tokens: dict):
        return _docs_request("GET", f"/{doc_id}", tokens)

    doc = _com_refresh(_ler)
    if not doc:
        return None

    partes: list[str] = []
    achou = False
    for texto, _start, _end in _paragrafos_do_doc(doc):
        if achou:
            partes.append(texto)
        elif SEPARADOR_INFORMATIVO in texto:
            achou = True
    if achou:
        return "".join(partes).strip()

    return "".join(t for t, _s, _e in _paragrafos_do_doc(doc)).strip()


def ler_texto_documento(doc_id: str) -> str | None:
    """Lê o texto puro (todo o Doc, cabeçalho incluso) — usado só por
    `gerar_documento_peca`."""
    def _ler(tokens: dict):
        return _docs_request("GET", f"/{doc_id}", tokens)

    doc = _com_refresh(_ler)
    if not doc:
        return None
    return "".join(t for t, _s, _e in _paragrafos_do_doc(doc))


def _parse_corpo_markup(texto: str, start_offset: int) -> tuple[str, list[tuple[int, int]], list[tuple[int, int, bool]]]:
    """Quebra o corpo em parágrafos (separados por linha em branco), remove
    marcadores **negrito** (guardando os spans pra aplicar estilo real) e
    identifica blocos de destaque/citação — parágrafos que começam com "> ",
    no estilo markdown de blockquote. Retorna (texto_limpo, estilos_bold,
    paragrafos) onde paragrafos é [(start, end, eh_citacao), ...]."""
    blocos_brutos = [b for b in re.split(r"\n{2,}", texto.strip()) if b.strip()]
    partes: list[str] = []
    estilos_bold: list[tuple[int, int]] = []
    paragrafos: list[tuple[int, int, bool]] = []
    pos = start_offset

    for i, bloco in enumerate(blocos_brutos):
        bloco = bloco.strip()
        eh_citacao = bloco.startswith(">")
        if eh_citacao:
            bloco = re.sub(r"^>\s*", "", bloco)

        p_start = pos
        for parte in re.split(r"(\*\*[^*]+\*\*)", bloco):
            if not parte:
                continue
            if parte.startswith("**") and parte.endswith("**"):
                inner = parte[2:-2]
                estilos_bold.append((pos, pos + len(inner)))
                partes.append(inner)
                pos += len(inner)
            else:
                partes.append(parte)
                pos += len(parte)
        paragrafos.append((p_start, pos, eh_citacao))

        if i < len(blocos_brutos) - 1:
            partes.append("\n\n")
            pos += 2

    return "".join(partes), estilos_bold, paragrafos


def substituir_corpo_informativo(doc_id: str, texto: str) -> bool:
    """Substitui só o corpo (tudo depois do separador) pelo texto informado,
    preservando o cabeçalho estruturado acima. Aplica negrito real (marcado
    com **assim** no texto) e destaca blocos de citação/julgado (parágrafos
    iniciados com "> ") com recuo e borda esquerda. Pode ser chamado várias
    vezes (regenerar rascunho) — sempre localiza o separador de novo."""
    def _achar_corte(tokens: dict):
        doc = _docs_request("GET", f"/{doc_id}", tokens)
        content = doc.get("body", {}).get("content", [])
        fim_doc = content[-1]["endIndex"] if content else 2
        corte = None
        for txt, _start, end in _paragrafos_do_doc(doc):
            if SEPARADOR_INFORMATIVO in txt:
                corte = end
                break
        return corte, fim_doc

    resultado = _com_refresh(_achar_corte)
    if not resultado:
        return False
    corte, fim_doc = resultado
    if corte is None:
        corte = 1  # doc legado sem separador — sobrescreve tudo

    # +1 pro "\n" que recria a linha em branco entre o separador e o corpo
    # (o corte apaga tudo até o fim do doc, inclusive essa linha em branco).
    texto_limpo, estilos_bold, paragrafos = _parse_corpo_markup(texto, corte + 1) if texto else ("", [], [])
    texto_inserido = ("\n" + texto_limpo) if texto_limpo else ""

    def _escrever(tokens: dict):
        requests = []
        if fim_doc - 1 > corte:
            requests.append({"deleteContentRange": {"range": {"startIndex": corte, "endIndex": fim_doc - 1}}})
        if texto_inserido:
            requests.append({"insertText": {"location": {"index": corte}, "text": texto_inserido}})
        if requests:
            _docs_request("POST", f"/{doc_id}:batchUpdate", tokens, json={"requests": requests})
        if not texto_limpo:
            return True

        fmt = [{"updateParagraphStyle": {
            "range": {"startIndex": corte + 1, "endIndex": corte + 1 + len(texto_limpo)},
            "paragraphStyle": {"alignment": "JUSTIFIED", "lineSpacing": 150},
            "fields": "alignment,lineSpacing",
        }}]
        for p_start, p_end, eh_citacao in paragrafos:
            if not eh_citacao or p_end <= p_start:
                continue
            fmt.append({"updateParagraphStyle": {
                "range": {"startIndex": p_start, "endIndex": p_end},
                "paragraphStyle": {
                    "alignment": "START",
                    "indentStart": {"magnitude": 28, "unit": "PT"},
                    "borderLeft": {
                        "color": {"color": {"rgbColor": {"red": 0.11, "green": 0.35, "blue": 0.31}}},
                        "width": {"magnitude": 2, "unit": "PT"},
                        "padding": {"magnitude": 8, "unit": "PT"},
                        "dashStyle": "SOLID",
                    },
                },
                "fields": "alignment,indentStart,borderLeft",
            }})
            fmt.append({"updateTextStyle": {
                "range": {"startIndex": p_start, "endIndex": p_end},
                "textStyle": {"italic": True},
                "fields": "italic",
            }})
        for b_start, b_end in estilos_bold:
            if b_end > b_start:
                fmt.append({"updateTextStyle": {
                    "range": {"startIndex": b_start, "endIndex": b_end},
                    "textStyle": {"bold": True},
                    "fields": "bold",
                }})
        _docs_request("POST", f"/{doc_id}:batchUpdate", tokens, json={"requests": fmt})
        return True

    return bool(_com_refresh(_escrever))


def gerar_documento_peca(
    peca: dict, nome_documento: str,
    nome_cliente: str | None = None, numero_cnj: str | None = None,
) -> dict | None:
    """Copia o timbrado pra dentro da pasta do cliente/processo no Drive
    ({Cliente}/{numero_cnj}/Peças), escreve a peça com formatação real, e
    retorna {"id", "webViewLink"}. None se qualquer etapa falhar."""
    pasta_id = None
    if nome_cliente and numero_cnj:
        from app.services.google_drive import resolver_pasta_id
        pasta_id = resolver_pasta_id(nome_cliente, numero_cnj, "Peças")

    copia = copiar_arquivo_por_id(TIMBRADO_TEMPLATE_ID, nome_documento, parent_folder_id=pasta_id)
    if not copia:
        return None
    doc_id = copia["id"]

    texto, estilos, titulo_range, corpo_range = montar_texto_e_estilos(peca)

    def _inserir(tokens: dict):
        doc = _docs_request("GET", f"/{doc_id}", tokens)
        end_index = doc["body"]["content"][-1]["endIndex"]

        requests = []
        # O timbrado (logo/cabeçalho) fica num header próprio do Docs — o
        # corpo é só texto de exemplo, seguro de apagar antes de escrever.
        if end_index > 2:
            requests.append({
                "deleteContentRange": {"range": {"startIndex": 1, "endIndex": end_index - 1}}
            })
        requests.append({"insertText": {"location": {"index": 1}, "text": texto}})
        # Remove qualquer formatação de lista numerada/bullet herdada, senão
        # cada parágrafo (inclusive as linhas em branco) ganha um marcador.
        requests.append({
            "deleteParagraphBullets": {"range": {"startIndex": 1, "endIndex": 1 + len(texto)}}
        })

        _docs_request("POST", f"/{doc_id}:batchUpdate", tokens, json={"requests": requests})
        return 1

    insert_at = _com_refresh(_inserir)
    if insert_at is None:
        return {"id": doc_id, "webViewLink": copia.get("webViewLink")}

    def _formatar(tokens: dict):
        requests = []
        for estilo in estilos:
            start = insert_at + estilo["start"]
            end = insert_at + estilo["end"]
            if end <= start:
                continue
            if estilo.get("bold"):
                requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "textStyle": {"bold": True},
                        "fields": "bold",
                    }
                })
            if estilo.get("red"):
                requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "textStyle": {"bold": True, "foregroundColor": VERMELHO},
                        "fields": "bold,foregroundColor",
                    }
                })
        # Centraliza o título
        t_start = insert_at + titulo_range["start"]
        t_end = insert_at + titulo_range["end"]
        if t_end > t_start:
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": t_start, "endIndex": t_end},
                    "paragraphStyle": {"alignment": "CENTER"},
                    "fields": "alignment",
                }
            })
        # Numeração de verdade (nativa do Docs) só no corpo — depois da
        # qualificação, antes do fechamento. Ajusta sozinha, não duplica.
        c_start = insert_at + corpo_range["start"]
        c_end = insert_at + corpo_range["end"]
        if c_end > c_start:
            requests.append({
                "createParagraphBullets": {
                    "range": {"startIndex": c_start, "endIndex": c_end},
                    "bulletPreset": "NUMBERED_DECIMAL_ALPHA_ROMAN",
                }
            })
            # Mesmo padrão do timbrado: justificado, espaçamento 150%, só a
            # primeira linha de cada parágrafo com recuo (não o parágrafo
            # inteiro encostado na numeração).
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": c_start, "endIndex": c_end},
                    "paragraphStyle": {
                        "alignment": "JUSTIFIED",
                        "lineSpacing": 150,
                        "indentFirstLine": {"magnitude": 31.5, "unit": "PT"},
                        "indentStart": {"magnitude": 0, "unit": "PT"},
                    },
                    "fields": "alignment,lineSpacing,indentFirstLine,indentStart",
                }
            })
        if requests:
            _docs_request("POST", f"/{doc_id}:batchUpdate", tokens, json={"requests": requests})

    _com_refresh(_formatar)

    return {"id": doc_id, "webViewLink": copia.get("webViewLink")}
