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
    escritório + esqueleto com número/mês, tema/subtema, resumo estruturado,
    uma linha separadora e o corpo. É só um Google Doc — pode ser aberto e
    ajustado livremente (fonte, cores, logo) depois de criado; os próximos
    informativos copiam a versão mais recente dele."""
    copia = copiar_arquivo_por_id(TIMBRADO_TEMPLATE_ID, "Modelo Base — Informativo (não usar diretamente)",
                                   parent_folder_id=parent_folder_id)
    if not copia:
        return None
    doc_id = copia["id"]

    cabecalho = "INFORMATIVO Nº {{NUMERO}} — {{MES}}"
    esqueleto = (
        f"{cabecalho}\n\n"
        "TEMA: {{TEMA}}\n"
        "SUBTEMA: {{SUBTEMA}}\n\n"
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

        titulo_end = 1 + len(cabecalho)
        sep_start = 1 + esqueleto.index(SEPARADOR_INFORMATIVO)
        sep_end = sep_start + len(SEPARADOR_INFORMATIVO)
        fmt_requests = [
            {"updateTextStyle": {
                "range": {"startIndex": 1, "endIndex": titulo_end},
                "textStyle": {"bold": True, "fontSize": {"magnitude": 14, "unit": "PT"}},
                "fields": "bold,fontSize",
            }},
            {"updateTextStyle": {
                "range": {"startIndex": 1 + esqueleto.index("RESUMO ESTRUTURADO"),
                          "endIndex": 1 + esqueleto.index("RESUMO ESTRUTURADO") + len("RESUMO ESTRUTURADO")},
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


def preencher_cabecalho_informativo(
    doc_id: str, numero: int, mes_label: str, tema: str, subtema: str, resumo: str | None = None,
) -> bool:
    """Preenche os marcadores {{NUMERO}}/{{MES}}/{{TEMA}}/{{SUBTEMA}}/{{RESUMO}}
    de um Doc recém-copiado do template. Usa replaceAllText — não precisa
    calcular índice nenhum."""
    valores = {
        "{{NUMERO}}": str(numero),
        "{{MES}}": mes_label,
        "{{TEMA}}": tema or "",
        "{{SUBTEMA}}": subtema or "—",
        "{{RESUMO}}": resumo or "(resumo pendente — preencha depois de escrever o corpo)",
    }
    requests = [
        {"replaceAllText": {"containsText": {"text": token, "matchCase": True}, "replaceText": valor}}
        for token, valor in valores.items()
    ]

    def _fazer(tokens: dict):
        _docs_request("POST", f"/{doc_id}:batchUpdate", tokens, json={"requests": requests})
        return True

    return bool(_com_refresh(_fazer))


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


def substituir_corpo_informativo(doc_id: str, texto: str) -> bool:
    """Substitui só o corpo (tudo depois do separador) pelo texto informado,
    preservando o cabeçalho estruturado acima. Pode ser chamado várias vezes
    (regenerar rascunho) — sempre localiza o separador de novo."""
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

    def _escrever(tokens: dict):
        requests = []
        if fim_doc - 1 > corte:
            requests.append({"deleteContentRange": {"range": {"startIndex": corte, "endIndex": fim_doc - 1}}})
        if texto:
            requests.append({"insertText": {"location": {"index": corte}, "text": texto}})
        if requests:
            _docs_request("POST", f"/{doc_id}:batchUpdate", tokens, json={"requests": requests})
        if texto:
            fmt = [{"updateParagraphStyle": {
                "range": {"startIndex": corte, "endIndex": corte + len(texto)},
                "paragraphStyle": {"alignment": "JUSTIFIED", "lineSpacing": 150},
                "fields": "alignment,lineSpacing",
            }}]
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
