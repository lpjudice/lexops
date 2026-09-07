"""Brinde (isca) gerado via template do Google Docs — Lucas edita o visual
diretamente no Doc (fontes, cores, logo); o backend só substitui os campos
{{...}} e exporta como PDF. Suporta de 1 a MAX_SECOES seções: as que não
forem usadas são removidas do documento (bloco inteiro, entre marcadores).
"""
from __future__ import annotations

import logging
import uuid as _uuid

from app.services.google_docs import _com_refresh, _docs_request

logger = logging.getLogger(__name__)

TEMPLATE_SUBPATH = ["Instagram", "Templates"]
TEMPLATE_NOME = "Modelo — Brinde Instagram (Pimenta Judice)"

MAX_SECOES = 6
TEAL = {"color": {"rgbColor": {"red": 0.109, "green": 0.353, "blue": 0.306}}}  # #1C5A4E
CINZA = {"color": {"rgbColor": {"red": 0.42, "green": 0.46, "blue": 0.44}}}
TINT = {"red": 0.918, "green": 0.953, "blue": 0.941}  # #EAF3F0


def _marca_inicio(i: int) -> str:
    return f"{{{{SECAO_{i}_INICIO}}}}"


def _marca_fim(i: int) -> str:
    return f"{{{{SECAO_{i}_FIM}}}}"


def _montar_template(max_secoes: int = MAX_SECOES) -> tuple[str, list[dict]]:
    """Monta o texto inicial do template com os placeholders {{...}} e
    devolve também os requests de estilo (índices relativos ao início do
    texto — offset de +1 é aplicado depois, pois o corpo do Doc começa em 1)."""
    linhas: list[str] = []
    estilos: list[dict] = []
    pos = 0

    def add(texto: str, sep: str = "\n") -> tuple[int, int]:
        nonlocal pos
        start = pos
        linhas.append(texto)
        pos += len(texto)
        end = pos
        linhas.append(sep)
        pos += len(sep)
        return start, end

    s, e = add("{{TITULO}}")
    estilos.append({"start": s, "end": e, "bold": True, "size": 22, "color": TEAL})

    s, e = add("{{SUBTITULO}}", sep="\n\n")
    estilos.append({"start": s, "end": e, "italic": True, "size": 11, "color": CINZA})

    for i in range(1, max_secoes + 1):
        if i > 1:
            add(_marca_inicio(i))
        s, e = add(f"{{{{SECAO_{i}_TITULO}}}}")
        estilos.append({"start": s, "end": e, "bold": True, "size": 14, "color": TEAL})
        add(f"{{{{SECAO_{i}_TEXTO}}}}")
        s, e = add(f"{{{{SECAO_{i}_BULLETS}}}}")
        estilos.append({"start": s, "end": e, "callout": True})
        if i > 1:
            add(_marca_fim(i))
        add("")  # linha em branco fixa entre seções — fora do range apagável

    s, e = add("{{CTA}}", sep="\n\n")
    estilos.append({"start": s, "end": e, "bold": True, "size": 13, "color": TEAL, "callout": True, "center": True})

    s, e = add("Pimenta Judice Advogados Associados · pimentajudice.com.br", sep="")
    estilos.append({"start": s, "end": e, "size": 9, "color": CINZA, "center": True})

    return "".join(linhas), estilos


def criar_template_padrao() -> dict | None:
    """Cria o Google Doc modelo (em branco) com os placeholders e uma
    formatação inicial básica. Lucas edita fontes/cores/logo livremente
    depois — só os textos entre {{ }} não podem ser apagados/renomeados."""
    from app.services.google_drive import criar_documento_google_raiz

    doc = criar_documento_google_raiz(TEMPLATE_NOME, TEMPLATE_SUBPATH)
    if not doc:
        return None
    doc_id = doc["id"]

    texto, estilos = _montar_template()

    def _popular(tokens: dict):
        requests = [{"insertText": {"location": {"index": 1}, "text": texto}}]
        for est in estilos:
            start, end = 1 + est["start"], 1 + est["end"]
            if end <= start:
                continue
            text_style: dict = {}
            fields = []
            if est.get("bold"):
                text_style["bold"] = True
                fields.append("bold")
            if est.get("italic"):
                text_style["italic"] = True
                fields.append("italic")
            if est.get("size"):
                text_style["fontSize"] = {"magnitude": est["size"], "unit": "PT"}
                fields.append("fontSize")
            if est.get("color"):
                text_style["foregroundColor"] = est["color"]
                fields.append("foregroundColor")
            if fields:
                requests.append({
                    "updateTextStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "textStyle": text_style,
                        "fields": ",".join(fields),
                    }
                })
            para_style: dict = {}
            pfields = []
            if est.get("callout"):
                para_style["shading"] = {"backgroundColor": {"color": {"rgbColor": TINT}}}
                pfields.append("shading")
            if est.get("center"):
                para_style["alignment"] = "CENTER"
                pfields.append("alignment")
            if pfields:
                requests.append({
                    "updateParagraphStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "paragraphStyle": para_style,
                        "fields": ",".join(pfields),
                    }
                })
        _docs_request("POST", f"/{doc_id}:batchUpdate", tokens, json={"requests": requests})

    _com_refresh(_popular)
    return doc


def _texto_com_offsets(doc: dict) -> tuple[str, list[int]]:
    """Concatena todo o texto do doc e devolve, pra cada caractere, o índice
    real correspondente no documento — usado pra localizar os marcadores de
    seção depois do replaceAllText (que não devolve posições)."""
    chars: list[str] = []
    offsets: list[int] = []

    def walk(elements):
        for el in elements or []:
            if "paragraph" in el:
                for pe in el["paragraph"].get("elements", []):
                    tr = pe.get("textRun")
                    if not tr:
                        continue
                    content = tr.get("content", "")
                    start = pe.get("startIndex", 0)
                    for i, ch in enumerate(content):
                        chars.append(ch)
                        offsets.append(start + i)
            elif "table" in el:
                for row in el["table"].get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        walk(cell.get("content", []))

    walk(doc.get("body", {}).get("content", []))
    return "".join(chars), offsets


def gerar_pdf_via_template(template_doc_id: str, conteudo: dict) -> bytes | None:
    """Copia o template, substitui os {{...}} pelo conteúdo gerado, remove
    os blocos de seção não usados e exporta como PDF. Apaga a cópia
    temporária ao final (best-effort)."""
    from app.services.google_drive import copiar_arquivo_por_id, deletar_arquivo_por_id, exportar_doc_como_pdf

    copia = copiar_arquivo_por_id(template_doc_id, f"_tmp_brinde_{_uuid.uuid4().hex[:8]}")
    if not copia:
        return None
    doc_id = copia["id"]
    try:
        secoes = conteudo.get("secoes") or []

        substituicoes = {
            "{{TITULO}}": conteudo.get("titulo") or "",
            "{{SUBTITULO}}": conteudo.get("subtitulo") or "",
            "{{CTA}}": conteudo.get("cta") or "",
        }
        for i in range(1, MAX_SECOES + 1):
            s = secoes[i - 1] if i <= len(secoes) else None
            bullets = "\n".join(f"•  {b}" for b in (s.get("bullets") or [])) if s else ""
            substituicoes[f"{{{{SECAO_{i}_TITULO}}}}"] = (s.get("titulo") or "") if s else ""
            substituicoes[f"{{{{SECAO_{i}_TEXTO}}}}"] = "\n".join(s.get("paragrafos") or []) if s else ""
            substituicoes[f"{{{{SECAO_{i}_BULLETS}}}}"] = bullets

        def _substituir(tokens: dict):
            requests = [
                {"replaceAllText": {"containsText": {"text": k, "matchCase": True}, "replaceText": v}}
                for k, v in substituicoes.items()
            ]
            _docs_request("POST", f"/{doc_id}:batchUpdate", tokens, json={"requests": requests})

        _com_refresh(_substituir)

        # Remove o bloco inteiro das seções não usadas (entre INICIO/FIM), e
        # tira os marcadores das seções usadas (viram texto invisível senão).
        def _limpar(tokens: dict):
            doc = _docs_request("GET", f"/{doc_id}", tokens)
            texto, offsets = _texto_com_offsets(doc)
            deletar_ranges: list[tuple[int, int]] = []
            marcadores_usados: list[str] = []
            for i in range(2, MAX_SECOES + 1):
                ini, fim = _marca_inicio(i), _marca_fim(i)
                if i > len(secoes):
                    p_ini = texto.find(ini)
                    p_fim = texto.find(fim)
                    if p_ini != -1 and p_fim != -1:
                        start_real = offsets[p_ini]
                        end_real = offsets[p_fim + len(fim) - 1] + 1
                        deletar_ranges.append((start_real, end_real))
                else:
                    marcadores_usados.extend([ini, fim])

            requests = []
            for start, end in sorted(deletar_ranges, key=lambda t: -t[0]):
                requests.append({"deleteContentRange": {"range": {"startIndex": start, "endIndex": end}}})
            if requests:
                _docs_request("POST", f"/{doc_id}:batchUpdate", tokens, json={"requests": requests})
            if marcadores_usados:
                requests2 = [
                    {"replaceAllText": {"containsText": {"text": m, "matchCase": True}, "replaceText": ""}}
                    for m in marcadores_usados
                ]
                _docs_request("POST", f"/{doc_id}:batchUpdate", tokens, json={"requests": requests2})

        _com_refresh(_limpar)

        pdf = exportar_doc_como_pdf(doc_id)
        return pdf
    except Exception:
        logger.exception("Falha ao gerar brinde via template do Google Docs")
        return None
    finally:
        try:
            deletar_arquivo_por_id(doc_id)
        except Exception:
            pass
