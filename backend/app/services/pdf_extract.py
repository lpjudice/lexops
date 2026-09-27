"""Extração de texto de PDF em cascata: pypdf → pdfminer → Claude OCR.

Compartilhado entre PrecedentCheck e a leitura de documentos do Drive pelo
gestor jurídico (contexto do processo).
"""
import io
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

logger = logging.getLogger(__name__)

# pypdf/pdfminer não têm timeout nativo — são bibliotecas só-CPU que podem
# ficar minutos (ou pra sempre, na prática) num PDF malformado/patológico.
# Reproduzido de verdade: uma sincronização travou 2x seguidas no MESMO
# documento, sempre no mesmo ponto ("tentando pdfminer..."), sem nunca
# lançar exceção nem voltar — o resto do sistema não tem como saber que
# aquilo não vai terminar. `_com_timeout` roda a chamada numa thread separada
# e desiste de esperar após N segundos (a chamada original pode continuar
# rodando "no vazio" em segundo plano — não dá para matar à força uma thread
# Python travada em CPU puro — mas o restante da sincronização não fica mais
# refém dela; a próxima tentativa da cascata assume a partir daí).
_TIMEOUT_PYPDF_SEGUNDOS = 30.0
_TIMEOUT_PDFMINER_SEGUNDOS = 60.0


def _com_timeout(fn, args: tuple, timeout_segundos: float):
    # NÃO usar `with ThreadPoolExecutor(...)` aqui: o `__exit__` do context
    # manager chama shutdown(wait=True), que bloqueia até a thread terminar —
    # inclusive a que acabou de estourar o timeout. Isso anularia o timeout
    # inteiro (a chamada voltaria a esperar pra sempre na saída do `with`).
    executor = ThreadPoolExecutor(max_workers=1)
    futuro = executor.submit(fn, *args)
    try:
        resultado = futuro.result(timeout=timeout_segundos)
    except FuturesTimeoutError:
        executor.shutdown(wait=False)
        raise TimeoutError(f"{fn.__name__} não retornou em {timeout_segundos:.0f}s") from None
    executor.shutdown(wait=False)
    return resultado


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
# Um documento de centenas de páginas (visto de verdade: 607) fazendo OCR
# completo é caro e demorado sem necessidade — pedido do Lucas pra limitar a
# leitura automática às primeiras páginas, preservando o link pro Drive pra
# quem quiser o documento inteiro depois. Bem menor que o limite técnico
# antigo (200): esse número é uma política de custo, não um limite técnico.
_OCR_MAX_PAGINAS = 40


def _ocr_pagina_claude(
    pagina_bytes: bytes,
    on_custo: Callable[[float], None] | None,
    on_status: Callable[[str], None] | None = None,
) -> str:
    """OCR padrão de 1 página — só Claude. Usado quando `extrair_texto_pdf`
    não recebe um `ocr_pagina` alternativo (PrecedentCheck e demais chamadores
    fora do Autos IA continuam só no Claude, sem mudança de comportamento)."""
    import base64
    import anthropic

    if on_status:
        on_status("OCR via Claude...")
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
    ocr_pagina: Callable[..., str] | None = None,
    on_status: Callable[[str], None] | None = None,
    deve_parar: Callable[[], bool] | None = None,
) -> str:
    """Último recurso: OCR de cada página do PDF, uma chamada por página — nunca
    o documento inteiro numa chamada só (limita tempo/tamanho por chamada e
    torna a falha granular: uma página que falha é pulada, as demais
    preservam o texto). `on_custo(custo_usd)`, quando informado, recebe o
    custo real de cada chamada — sem isso, o OCR é uma chamada de IA paga que
    nenhum lugar do sistema contabiliza. `ocr_pagina(pagina_bytes, on_custo,
    on_status)`, quando informado, substitui o OCR padrão (só Claude) por
    outra estratégia — usado pelo fluxo do jus.br pra diluir custo entre
    provedores; ver services/autos_ia/ocr_providers.py. `on_status(msg)`,
    quando informado, recebe uma frase curta a cada página/tentativa — é o
    que dá visibilidade de "documento sendo dividido em N páginas", "OCR
    página X/N via Y", "Y falhou, tentando Z" em vez de só um contador
    parado sem explicação. `deve_parar()`, quando informado e retornando
    True, interrompe o OCR ANTES da próxima página (pedido de "pular este
    documento" do usuário) — as páginas já OCR'das ficam, o resto não é
    tentado."""
    from pypdf import PdfReader, PdfWriter

    ocr_pagina = ocr_pagina or _ocr_pagina_claude
    paginas = PdfReader(io.BytesIO(content)).pages
    if len(paginas) > _OCR_MAX_PAGINAS:
        logger.warning("PDF com %d páginas — OCR limitado às primeiras %d", len(paginas), _OCR_MAX_PAGINAS)
        if on_status:
            on_status(f"PDF com {len(paginas)} páginas — OCR limitado às primeiras {_OCR_MAX_PAGINAS} (link completo salvo)")
        paginas = paginas[:_OCR_MAX_PAGINAS]

    if on_status:
        on_status(
            f"Sem texto nativo — dividindo em {len(paginas)} página(s) para OCR"
            if len(paginas) != 1 else "Sem texto nativo — OCR de 1 página"
        )

    textos: list[str] = []
    for indice, pagina in enumerate(paginas):
        if deve_parar and deve_parar():
            logger.info("OCR interrompido a pedido do usuário na página %d/%d", indice + 1, len(paginas))
            if on_status:
                on_status(f"Pulado a pedido do usuário na página {indice + 1}/{len(paginas)}")
            break

        writer = PdfWriter()
        writer.add_page(pagina)
        buf = io.BytesIO()
        writer.write(buf)
        pagina_bytes = buf.getvalue()
        if len(pagina_bytes) > 5 * 1024 * 1024:
            logger.warning("Página %d grande demais para OCR (>5MB) — pulada", indice)
            if on_status:
                on_status(f"Página {indice + 1}/{len(paginas)}: grande demais para OCR (>5MB), pulada")
            continue

        def _status_pagina(msg: str, _i: int = indice, _n: int = len(paginas)) -> None:
            if on_status:
                on_status(f"OCR página {_i + 1}/{_n}: {msg}")

        try:
            texto_pagina = ocr_pagina(pagina_bytes, on_custo, _status_pagina)
        except Exception as exc:
            logger.warning("OCR falhou na página %d (%s): %s", indice, exc.__class__.__name__, exc)
            if on_status:
                on_status(f"OCR página {indice + 1}/{len(paginas)}: falhou ({exc.__class__.__name__}), pulada")
            continue
        if texto_pagina:
            textos.append(texto_pagina)

    return "\n\n".join(t.strip() for t in textos if t.strip())


def extrair_texto_pdf(
    content: bytes,
    on_custo: Callable[[float], None] | None = None,
    ocr_pagina: Callable[..., str] | None = None,
    on_status: Callable[[str], None] | None = None,
    deve_parar: Callable[[], bool] | None = None,
) -> str:
    """Extrai texto de um PDF em 3 tentativas. Retorna string vazia se todas falharem.
    `on_custo(custo_usd)`, quando informado, recebe o custo real de uma eventual chamada
    de OCR via IA (a única etapa paga desta cascata — pypdf/pdfminer são locais e grátis).
    `ocr_pagina`/`on_status`/`deve_parar`: ver _extrair_com_claude_ocr.

    `on_status`, quando informado, também recebe uma mensagem ANTES de cada uma
    das duas primeiras tentativas (nativas, sem IA) — sem isso, um PDF grande
    ou malformado que trava o pypdf/pdfminer (acontece; nenhum dos dois tem
    timeout, e pdfminer em especial pode ser bem lento em certos PDFs) ficava
    sem nenhuma mensagem na tela até (se um dia) chegar no OCR — parecendo
    travado num documento pequeno, sem informar sequer quantas páginas ele
    tem nem em qual das 3 tentativas está."""
    if on_status:
        try:
            from pypdf import PdfReader
            n_paginas = len(PdfReader(io.BytesIO(content)).pages)
            on_status(f"PDF com {n_paginas} página(s) — tentando extração nativa (pypdf)...")
        except Exception:
            on_status("Tentando extração nativa (pypdf)...")

    texto = ""
    try:
        texto = _com_timeout(_extrair_com_pypdf, (content,), _TIMEOUT_PYPDF_SEGUNDOS)
    except Exception as exc:
        logger.warning("pypdf falhou (%s): %s", exc.__class__.__name__, exc)
        if on_status and isinstance(exc, TimeoutError):
            on_status(f"pypdf não respondeu em {_TIMEOUT_PYPDF_SEGUNDOS:.0f}s — pulando para pdfminer...")

    if not texto.strip():
        if on_status:
            on_status("Sem texto nativo via pypdf — tentando pdfminer...")
        try:
            texto = _com_timeout(_extrair_com_pdfminer, (content,), _TIMEOUT_PDFMINER_SEGUNDOS)
        except Exception as exc:
            logger.warning("pdfminer falhou (%s): %s", exc.__class__.__name__, exc)
            if on_status and isinstance(exc, TimeoutError):
                on_status(f"pdfminer não respondeu em {_TIMEOUT_PDFMINER_SEGUNDOS:.0f}s — indo para OCR...")

    if not texto.strip():
        try:
            texto = _extrair_com_claude_ocr(
                content, on_custo=on_custo, ocr_pagina=ocr_pagina, on_status=on_status, deve_parar=deve_parar,
            )
        except Exception as exc:
            logger.warning("OCR falhou: %s", exc)

    return remover_nul(texto.strip())
