"""Extração de texto de PDF em cascata: pypdf → pdfminer → Claude OCR.

Compartilhado entre PrecedentCheck e a leitura de documentos do Drive pelo
gestor jurídico (contexto do processo).
"""
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable

logger = logging.getLogger(__name__)

# pypdf/pdfminer não têm timeout nem limite de memória — são bibliotecas CPU/memória
# que num PDF pesado ou patológico podem ficar minutos (ou pra sempre) e consumir
# GBs. Reproduzido de verdade em produção (15/out): um PDF de 41 páginas
# ("Demonstrações contábeis") fez o servidor inteiro ser morto por falta de memória
# (oom_killed=true) 3x seguidas, sempre no mesmo documento — como ele só vira peça
# depois de lido, TODA sincronização voltava a tropeçar nele, derrubando o app (e o
# bot do Telegram, e as outras telas) a cada tentativa.
#
# Antes cada extração rodava numa THREAD com timeout. Só que uma thread presa não
# pode ser morta: a chamada "continuava rodando no vazio" e, na cascata
# pypdf → pdfminer → OCR, as duas bibliotecas acabavam parseando o mesmo PDF ao
# mesmo tempo no processo do servidor. Agora cada etapa roda num PROCESSO FILHO
# separado, com teto de memória (ulimit -v) e morte garantida (SIGKILL) no
# timeout: um PDF ruim derruba só o filho, e a cascata segue pra próxima etapa ou
# devolve vazio (a peça fica com o link do Drive e a descrição do andamento).
_TIMEOUT_PYPDF_SEGUNDOS = 45.0
_TIMEOUT_PDFMINER_SEGUNDOS = 75.0
_TIMEOUT_DIVIDIR_SEGUNDOS = 90.0
# Teto de memória VIRTUAL do filho. O servidor (2 GB de RAM) usa ~0,5–0,8 GB; o filho
# precisa caber no que sobra com folga. Ajustável sem deploy de código pelo ambiente.
_LIMITE_MEMORIA_FILHO_MB = int(os.environ.get("PDF_FILHO_LIMITE_MB", "800"))

_CODIGO_FILHO = r"""
import io, json, sys
modo = sys.argv[1]
dados = sys.stdin.buffer.read()
if modo == "pypdf":
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(dados))
    n = len(r.pages)
    paginas = [p.extract_text() or "" for p in r.pages[:50]]
    sys.stdout.write(json.dumps({"n": n, "texto": "\n\n".join(p.strip() for p in paginas if p.strip())}))
elif modo == "pdfminer":
    from pdfminer.high_level import extract_text
    sys.stdout.write(json.dumps({"texto": extract_text(io.BytesIO(dados), maxpages=50) or ""}))
elif modo == "dividir":
    from pypdf import PdfReader, PdfWriter
    destino, limite = sys.argv[2], int(sys.argv[3])
    r = PdfReader(io.BytesIO(dados))
    n = len(r.pages)
    arquivos = []
    for i, pagina in enumerate(r.pages[:limite]):
        w = PdfWriter()
        w.add_page(pagina)
        caminho = destino + "/p%04d.pdf" % i
        with open(caminho, "wb") as f:
            w.write(f)
        arquivos.append(caminho)
    sys.stdout.write(json.dumps({"n": n, "arquivos": arquivos}))
else:
    raise SystemExit(2)
"""


class ExtracaoPulada(Exception):
    """O usuário clicou em "Pular este documento" enquanto uma etapa de extração rodava."""


def _rodar_filho(
    modo: str, content: bytes, timeout_segundos: float, *args: str,
    deve_parar: Callable[[], bool] | None = None,
) -> dict:
    """Roda uma etapa de extração num processo Python separado e devolve o JSON que ele
    imprime. Lança TimeoutError (filho morto à força), ExtracaoPulada (o usuário pediu
    pra pular: filho morto na hora) ou RuntimeError (filho caiu — tipicamente
    MemoryError por estourar o teto de memória, ou PDF inválido)."""
    import time

    kb = max(256, _LIMITE_MEMORIA_FILHO_MB) * 1024
    # `ulimit -v` via sh (e não preexec_fn): preexec_fn não é seguro num servidor com threads.
    cmd = ["sh", "-c", f'ulimit -v {kb} 2>/dev/null; exec "$0" "$@"', sys.executable, "-I", "-c", _CODIGO_FILHO, modo, *args]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    limite = time.monotonic() + timeout_segundos
    entrada: bytes | None = content
    try:
        while True:
            try:
                saida, erro = proc.communicate(input=entrada, timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                entrada = None  # já entregue: nas próximas voltas só espera (comportamento documentado do communicate)
                if deve_parar is not None and deve_parar():
                    proc.kill()
                    proc.communicate()
                    raise ExtracaoPulada(f"{modo}: pulado a pedido do usuário") from None
                if time.monotonic() > limite:
                    proc.kill()
                    proc.communicate()
                    raise TimeoutError(f"{modo} não terminou em {timeout_segundos:.0f}s (processo encerrado)") from None
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise
    if proc.returncode != 0:
        detalhe = erro.decode("utf-8", "replace").strip().splitlines()[-1:] or ["sem detalhe"]
        causa = "memória estourou o teto do processo" if proc.returncode in (-9, 137) or b"MemoryError" in erro else f"código {proc.returncode}"
        raise RuntimeError(f"{modo} falhou ({causa}): {detalhe[0][:200]}")
    return json.loads(saida.decode("utf-8"))


def remover_nul(texto: str) -> str:
    """Postgres/psycopg2 rejeita string com NUL (0x00) embutido — PDFs
    malformados ou digitalizados às vezes produzem esse byte no texto
    extraído (pypdf/pdfminer/OCR), e sem isso o commit falha com "A string
    literal cannot contain NUL (0x00) characters", derrubando a peça (e a
    sincronização inteira, antes de qualquer rede de segurança) sem aviso."""
    return texto.replace("\x00", "") if texto else texto


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
    ocr_pagina = ocr_pagina or _ocr_pagina_claude
    # A divisão em páginas (PdfReader/PdfWriter) é a parte pesada em memória: roda num
    # processo filho, que grava 1 PDF por página numa pasta temporária — o servidor só
    # lê cada página de lá, uma de cada vez, na hora do OCR.
    pasta = tempfile.mkdtemp(prefix="ocr_paginas_")
    try:
        divisao = _rodar_filho("dividir", content, _TIMEOUT_DIVIDIR_SEGUNDOS, pasta, str(_OCR_MAX_PAGINAS), deve_parar=deve_parar)
        total_paginas = int(divisao["n"])
        arquivos_paginas: list[str] = divisao["arquivos"]
        if total_paginas > _OCR_MAX_PAGINAS:
            logger.warning("PDF com %d páginas — OCR limitado às primeiras %d", total_paginas, _OCR_MAX_PAGINAS)
            if on_status:
                on_status(f"PDF com {total_paginas} páginas — OCR limitado às primeiras {_OCR_MAX_PAGINAS} (link completo salvo)")

        if on_status:
            on_status(
                f"Sem texto nativo — dividindo em {len(arquivos_paginas)} página(s) para OCR"
                if len(arquivos_paginas) != 1 else "Sem texto nativo — OCR de 1 página"
            )
        return _ocr_paginas_salvas(arquivos_paginas, on_custo, ocr_pagina, on_status, deve_parar)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def _ocr_paginas_salvas(
    arquivos_paginas: list[str],
    on_custo: Callable[[float], None] | None,
    ocr_pagina: Callable[..., str],
    on_status: Callable[[str], None] | None,
    deve_parar: Callable[[], bool] | None,
) -> str:
    textos: list[str] = []
    paginas = arquivos_paginas
    for indice, caminho in enumerate(paginas):
        if deve_parar and deve_parar():
            logger.info("OCR interrompido a pedido do usuário na página %d/%d", indice + 1, len(paginas))
            if on_status:
                on_status(f"Pulado a pedido do usuário na página {indice + 1}/{len(paginas)}")
            break

        with open(caminho, "rb") as f:
            pagina_bytes = f.read()
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
        on_status("Tentando extração nativa (pypdf)...")

    texto = ""
    try:
        resultado = _rodar_filho("pypdf", content, _TIMEOUT_PYPDF_SEGUNDOS, deve_parar=deve_parar)
        texto = resultado.get("texto", "")
        if on_status and not texto.strip():
            on_status(f"PDF com {resultado.get('n', '?')} página(s) e sem texto nativo (pypdf)...")
    except ExtracaoPulada:
        logger.info("Extração pulada a pedido do usuário (pypdf)")
        return ""
    except Exception as exc:
        logger.warning("pypdf falhou (%s): %s", exc.__class__.__name__, exc)
        if on_status:
            on_status(f"pypdf não conseguiu ler este PDF ({exc.__class__.__name__}) — tentando pdfminer...")

    if not texto.strip():
        if on_status:
            on_status("Sem texto nativo via pypdf — tentando pdfminer...")
        try:
            texto = _rodar_filho("pdfminer", content, _TIMEOUT_PDFMINER_SEGUNDOS, deve_parar=deve_parar).get("texto", "")
        except ExtracaoPulada:
            logger.info("Extração pulada a pedido do usuário (pdfminer)")
            return ""
        except Exception as exc:
            logger.warning("pdfminer falhou (%s): %s", exc.__class__.__name__, exc)
            if on_status:
                on_status(f"pdfminer não conseguiu ler este PDF ({exc.__class__.__name__}) — indo para OCR...")

    if not texto.strip():
        try:
            texto = _extrair_com_claude_ocr(
                content, on_custo=on_custo, ocr_pagina=ocr_pagina, on_status=on_status, deve_parar=deve_parar,
            )
        except ExtracaoPulada:
            logger.info("Extração pulada a pedido do usuário (divisão em páginas)")
            return ""
        except Exception as exc:
            logger.warning("OCR falhou: %s", exc)

    return remover_nul(texto.strip())
