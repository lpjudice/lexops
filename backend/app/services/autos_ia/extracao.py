"""Extração de texto página a página de um bloco de PDF dos autos.

Cascata por página: pypdf → pdfminer → OCR nativo do Claude (visão de PDF),
igual ao padrão já usado em app.services.pdf_extract, mas granular por
página — necessário porque um mesmo bloco de autos costuma misturar páginas
com texto nativo e páginas digitalizadas (certidões, documentos de terceiros
juntados como imagem).
"""
import io
import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.services.pdf_extract import remover_nul

logger = logging.getLogger(__name__)

LIMIAR_CHARS_TEXTO_NATIVO = 40


@dataclass
class PaginaExtraida:
    numero_global: int
    texto: str
    ocr_usado: bool


def _texto_pypdf_por_pagina(content: bytes) -> list[str]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    return [(page.extract_text() or "").strip() for page in reader.pages]


def _texto_pdfminer_pagina(content: bytes, indice: int) -> str:
    from pdfminer.high_level import extract_text as pdfminer_extract
    texto = pdfminer_extract(io.BytesIO(content), page_numbers=[indice]) or ""
    return texto.strip()


def _ocr_claude_pagina(content: bytes, indice: int, on_custo: Callable[[float], None] | None = None) -> str:
    """Isola a página `indice` num PDF de 1 página e manda para o Claude ler via visão nativa.
    `on_custo(custo_usd)`, quando informado, recebe o custo real dessa chamada."""
    import base64
    import anthropic
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(content))
    writer = PdfWriter()
    writer.add_page(reader.pages[indice])
    buf = io.BytesIO()
    writer.write(buf)
    pagina_bytes = buf.getvalue()

    # Timeout curto e sem retries longos: uma página travada não pode prender a
    # fila inteira de páginas do bloco (mesmo problema resolvido em pdf_extract.py).
    client = anthropic.Anthropic(timeout=90.0, max_retries=1)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.b64encode(pagina_bytes).decode(),
                    },
                },
                {
                    "type": "text",
                    "text": (
                        "Esta é uma única página de autos de um processo judicial brasileiro, "
                        "provavelmente digitalizada. Transcreva TODO o texto exatamente como "
                        "está, preservando parágrafos, numerações, carimbos e assinaturas "
                        "identificáveis. Retorne APENAS o texto transcrito, sem comentários."
                    ),
                },
            ],
        }],
    )
    if on_custo:
        from app.services.autos_ia.precos import calcular_custo_ocr_usd
        on_custo(calcular_custo_ocr_usd(resp.usage.input_tokens, resp.usage.output_tokens))
    return (resp.content[0].text if resp.content else "").strip()


def extrair_paginas(
    content: bytes,
    pagina_inicio_global: int,
    on_progresso: Callable[[int, int], None] | None = None,
    on_custo: Callable[[float], None] | None = None,
) -> list[PaginaExtraida]:
    """Extrai o texto de cada página de `content`, numerando a partir de `pagina_inicio_global`.

    `on_progresso(paginas_feitas, total_paginas)`, quando informado, é chamado após cada página —
    usado para atualizar o progresso exibido na tela durante blocos grandes.
    `on_custo(custo_usd)`, quando informado, recebe o custo real de cada página que precisou de
    OCR via IA (a única etapa paga desta cascata — pypdf/pdfminer são locais e grátis)."""
    try:
        textos_pypdf = _texto_pypdf_por_pagina(content)
    except Exception as exc:
        logger.warning("pypdf falhou no bloco: %s", exc)
        textos_pypdf = []

    total_paginas = len(textos_pypdf)
    if total_paginas == 0:
        # pypdf não conseguiu nem abrir o arquivo — ainda tentamos contar páginas via pdfminer indiretamente.
        from pypdf import PdfReader
        total_paginas = len(PdfReader(io.BytesIO(content)).pages)
        textos_pypdf = [""] * total_paginas

    paginas: list[PaginaExtraida] = []
    for indice in range(total_paginas):
        numero_global = pagina_inicio_global + indice
        texto = textos_pypdf[indice]
        ocr_usado = False

        if len(texto) < LIMIAR_CHARS_TEXTO_NATIVO:
            try:
                texto_pdfminer = _texto_pdfminer_pagina(content, indice)
                if len(texto_pdfminer) > len(texto):
                    texto = texto_pdfminer
            except Exception as exc:
                logger.warning("pdfminer falhou na página %d: %s", numero_global, exc)

        if len(texto) < LIMIAR_CHARS_TEXTO_NATIVO:
            try:
                texto_ocr = _ocr_claude_pagina(content, indice, on_custo=on_custo)
                if len(texto_ocr) > len(texto):
                    texto = texto_ocr
                    ocr_usado = True
            except Exception as exc:
                logger.warning("OCR Claude falhou na página %d: %s", numero_global, exc)

        paginas.append(PaginaExtraida(numero_global=numero_global, texto=remover_nul(texto), ocr_usado=ocr_usado))
        if on_progresso:
            on_progresso(indice + 1, total_paginas)

    return paginas


def montar_markdown_com_marcadores(paginas: list[PaginaExtraida]) -> str:
    """Concatena as páginas com marcadores `<!-- pagina N -->` para a segmentação em peças localizar limites."""
    partes = []
    for p in paginas:
        partes.append(f"<!-- pagina {p.numero_global} -->\n{p.texto}".strip())
    return "\n\n".join(partes)
