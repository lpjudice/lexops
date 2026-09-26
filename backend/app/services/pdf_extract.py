"""Extração de texto de PDF em cascata: pypdf → pdfminer → Claude OCR.

Compartilhado entre PrecedentCheck e a leitura de documentos do Drive pelo
gestor jurídico (contexto do processo).
"""
import io
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


def remover_nul(texto: str) -> str:
    """Postgres/psycopg2 rejeita string com NUL (0x00) embutido — PDFs
    malformados ou digitalizados às vezes produzem esse byte no texto
    extraído (pypdf/pdfminer/OCR), e sem isso o commit falha com "A string
    literal cannot contain NUL (0x00) characters", derrubando a peça (e a
    sincronização inteira, antes de qualquer rede de segurança) sem aviso."""
    return texto.replace("\x00", "") if texto else texto


def _extrair_com_pypdf(content: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    paginas = [page.extract_text() or "" for page in reader.pages[:50]]
    return "\n\n".join(p.strip() for p in paginas if p.strip())


def _extrair_com_pdfminer(content: bytes) -> str:
    from pdfminer.high_level import extract_text as pdfminer_extract
    return pdfminer_extract(io.BytesIO(content), maxpages=50) or ""


# Cada chamada de OCR isola 1 página — nunca o documento inteiro numa chamada só.
# Isso limita o tempo/tamanho de cada chamada (evita travar a fila inteira de
# importação numa chamada grande e sem limite de tempo) e torna a falha
# granular: uma página que falha (timeout, erro da API) é pulada e as demais
# preservam o texto já extraído, em vez de o documento inteiro virar nada.
_OCR_TIMEOUT_SEGUNDOS = 90.0
_OCR_MAX_PAGINAS = 200


def _ocr_pagina_claude(pagina_bytes: bytes, on_custo: Callable[[float], None] | None) -> str:
    """OCR padrão de 1 página — só Claude. Usado quando `extrair_texto_pdf`
    não recebe um `ocr_pagina` alternativo (PrecedentCheck e demais chamadores
    fora do Autos IA continuam só no Claude, sem mudança de comportamento)."""
    import base64
    import anthropic

    client = anthropic.Anthropic(timeout=_OCR_TIMEOUT_SEGUNDOS, max_retries=1)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(pagina_bytes).decode()},
                },
                {
                    "type": "text",
                    "text": (
                        "Extraia TODO o texto desta página exatamente como está, "
                        "preservando parágrafos, numerações e formatação. "
                        "Retorne APENAS o texto extraído, sem comentários adicionais."
                    ),
                },
            ],
        }],
    )
    if on_custo:
        from app.services.autos_ia.precos import calcular_custo_ocr_usd
        on_custo(calcular_custo_ocr_usd(resp.usage.input_tokens, resp.usage.output_tokens))
    return resp.content[0].text if resp.content else ""


def _extrair_com_claude_ocr(
    content: bytes,
    on_custo: Callable[[float], None] | None = None,
    ocr_pagina: Callable[[bytes, Callable[[float], None] | None], str] | None = None,
) -> str:
    """Último recurso: OCR de cada página do PDF, uma chamada por página — nunca
    o documento inteiro numa chamada só (limita tempo/tamanho por chamada e
    torna a falha granular: uma página que falha é pulada, as demais
    preservam o texto). `on_custo(custo_usd)`, quando informado, recebe o
    custo real de cada chamada — sem isso, o OCR é uma chamada de IA paga que
    nenhum lugar do sistema contabiliza. `ocr_pagina(pagina_bytes, on_custo)`,
    quando informado, substitui o OCR padrão (só Claude) por outra estratégia
    — usado pelo fluxo do jus.br pra diluir custo entre provedores; ver
    services/autos_ia/ocr_providers.py."""
    from pypdf import PdfReader, PdfWriter

    ocr_pagina = ocr_pagina or _ocr_pagina_claude
    paginas = PdfReader(io.BytesIO(content)).pages
    if len(paginas) > _OCR_MAX_PAGINAS:
        logger.warning("PDF com %d páginas — OCR limitado às primeiras %d", len(paginas), _OCR_MAX_PAGINAS)
        paginas = paginas[:_OCR_MAX_PAGINAS]

    textos: list[str] = []
    for indice, pagina in enumerate(paginas):
        writer = PdfWriter()
        writer.add_page(pagina)
        buf = io.BytesIO()
        writer.write(buf)
        pagina_bytes = buf.getvalue()
        if len(pagina_bytes) > 5 * 1024 * 1024:
            logger.warning("Página %d grande demais para OCR (>5MB) — pulada", indice)
            continue

        try:
            texto_pagina = ocr_pagina(pagina_bytes, on_custo)
        except Exception as exc:
            logger.warning("OCR falhou na página %d (%s): %s", indice, exc.__class__.__name__, exc)
            continue
        if texto_pagina:
            textos.append(texto_pagina)

    return "\n\n".join(t.strip() for t in textos if t.strip())


def extrair_texto_pdf(
    content: bytes,
    on_custo: Callable[[float], None] | None = None,
    ocr_pagina: Callable[[bytes, Callable[[float], None] | None], str] | None = None,
) -> str:
    """Extrai texto de um PDF em 3 tentativas. Retorna string vazia se todas falharem.
    `on_custo(custo_usd)`, quando informado, recebe o custo real de uma eventual chamada
    de OCR via IA (a única etapa paga desta cascata — pypdf/pdfminer são locais e grátis).
    `ocr_pagina`: ver _extrair_com_claude_ocr."""
    texto = ""
    try:
        texto = _extrair_com_pypdf(content)
    except Exception as exc:
        logger.warning("pypdf falhou: %s", exc)

    if not texto.strip():
        try:
            texto = _extrair_com_pdfminer(content)
        except Exception as exc:
            logger.warning("pdfminer falhou: %s", exc)

    if not texto.strip():
        try:
            texto = _extrair_com_claude_ocr(content, on_custo=on_custo, ocr_pagina=ocr_pagina)
        except Exception as exc:
            logger.warning("OCR falhou: %s", exc)

    return remover_nul(texto.strip())
