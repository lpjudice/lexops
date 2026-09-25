"""Extração de texto de PDF em cascata: pypdf → pdfminer → Claude OCR.

Compartilhado entre PrecedentCheck e a leitura de documentos do Drive pelo
gestor jurídico (contexto do processo).
"""
import io
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


def _extrair_com_pypdf(content: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    paginas = [page.extract_text() or "" for page in reader.pages[:50]]
    return "\n\n".join(p.strip() for p in paginas if p.strip())


def _extrair_com_pdfminer(content: bytes) -> str:
    from pdfminer.high_level import extract_text as pdfminer_extract
    return pdfminer_extract(io.BytesIO(content), maxpages=50) or ""


def _extrair_com_claude_ocr(content: bytes, on_custo: Callable[[float], None] | None = None) -> str:
    """Último recurso: envia o PDF para Claude ler via visão nativa (PDFs escaneados sem texto).
    `on_custo(custo_usd)`, quando informado, recebe o custo real dessa chamada — sem isso, o
    fallback de OCR é uma chamada de IA paga que nenhum lugar do sistema contabiliza."""
    import base64
    import anthropic
    client = anthropic.Anthropic()
    if len(content) > 5 * 1024 * 1024:
        content = content[:5 * 1024 * 1024]
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(content).decode()},
                },
                {
                    "type": "text",
                    "text": (
                        "Extraia TODO o texto desta peça ou decisão judicial exatamente como está, "
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


def extrair_texto_pdf(content: bytes, on_custo: Callable[[float], None] | None = None) -> str:
    """Extrai texto de um PDF em 3 tentativas. Retorna string vazia se todas falharem.
    `on_custo(custo_usd)`, quando informado, recebe o custo real de uma eventual chamada
    de OCR via IA (a única etapa paga desta cascata — pypdf/pdfminer são locais e grátis)."""
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
            texto = _extrair_com_claude_ocr(content, on_custo=on_custo)
        except Exception as exc:
            logger.warning("Claude OCR falhou: %s", exc)

    return texto.strip()
