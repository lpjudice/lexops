"""Extração de texto de PDF em cascata: pypdf → pdfminer → Claude OCR.

Compartilhado entre PrecedentCheck e a leitura de documentos do Drive pelo
gestor jurídico (contexto do processo).
"""
import io
import logging

logger = logging.getLogger(__name__)


def _extrair_com_pypdf(content: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    paginas = [page.extract_text() or "" for page in reader.pages[:50]]
    return "\n\n".join(p.strip() for p in paginas if p.strip())


def _extrair_com_pdfminer(content: bytes) -> str:
    from pdfminer.high_level import extract_text as pdfminer_extract
    return pdfminer_extract(io.BytesIO(content), maxpages=50) or ""


def _extrair_com_claude_ocr(content: bytes) -> str:
    """Último recurso: envia o PDF para Claude ler via visão nativa (PDFs escaneados sem texto)."""
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
    return resp.content[0].text if resp.content else ""


def extrair_texto_pdf(content: bytes) -> str:
    """Extrai texto de um PDF em 3 tentativas. Retorna string vazia se todas falharem."""
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
            texto = _extrair_com_claude_ocr(content)
        except Exception as exc:
            logger.warning("Claude OCR falhou: %s", exc)

    return texto.strip()
