"""
Organizador de arquivos para protocolo.
Fluxo:
  1. POST /organizador/analisar — recebe a peça principal + arquivos anexos
  2. Retorna sugestões de renomeação e documentos faltantes
  3. POST /organizador/aplicar   — aplica as renomeações confirmadas e retorna ZIP
"""

import base64
import io
import json
import re
import unicodedata
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pypdf import PdfReader

from app.config import settings
from app.dependencies import get_current_user

STAGING_DIR = Path("/app/uploads/organizador_staging")
STAGING_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/organizador", tags=["organizador"],
                   dependencies=[Depends(get_current_user)])


def _sanitizar_nome(nome: str) -> str:
    """Remove acentos e caracteres especiais do nome de arquivo, mantendo letras, dígitos, espaços, dash e ponto."""
    # Preserva a extensão
    partes = nome.rsplit(".", 1)
    base = partes[0]
    ext = f".{partes[1]}" if len(partes) == 2 else ""

    # Normaliza para NFD e remove marcas de acento
    base = unicodedata.normalize("NFD", base)
    base = "".join(c for c in base if unicodedata.category(c) != "Mn")

    # Mantém letras, dígitos, espaço, dash e ponto interno
    base = re.sub(r"[^\w\s\-.]", "", base, flags=re.ASCII)

    # Colapsa espaços/underscores múltiplos em espaço único
    base = re.sub(r"[\s_]+", " ", base).strip()

    return base + ext


# ── Modelos ───────────────────────────────────────────────────────────────────

class SugestaoArquivo(BaseModel):
    original: str
    sugerido: str
    motivo: str
    ordem: int
    pagina: int | None = None      # página da peça onde é mencionado pela 1ª vez
    contexto: str | None = None    # ~3 palavras imediatamente antes da menção
    cenario: str | None = None     # "A", "B", "C" ou "D"


class AnaliseResult(BaseModel):
    sessao_id: str
    sugestoes: list[SugestaoArquivo]
    faltando: list[str]
    observacoes: str
    cenario_detectado: str | None = None


# ── Análise ───────────────────────────────────────────────────────────────────

@router.post("/analisar", response_model=AnaliseResult)
async def analisar_arquivos(
    peca: UploadFile = File(..., description="PDF da peça processual principal"),
    anexos: list[UploadFile] = File(default=[], description="Arquivos anexos"),
):
    """Analisa a peça processual e os anexos, retorna sugestões de organização."""
    import uuid as uuid_mod
    sessao_id = str(uuid_mod.uuid4())
    pasta = STAGING_DIR / sessao_id
    pasta.mkdir(parents=True)

    # Salva a peça principal
    peca_bytes = await peca.read()
    peca_path = pasta / f"PECA_{peca.filename}"
    peca_path.write_bytes(peca_bytes)

    # Salva os anexos e coleta bytes
    arquivos_nomes: list[str] = []
    anexos_bytes: dict[str, bytes] = {}
    for a in anexos:
        conteudo = await a.read()
        dest = pasta / a.filename
        dest.write_bytes(conteudo)
        arquivos_nomes.append(a.filename)
        anexos_bytes[a.filename] = conteudo

    sugestoes, faltando, obs, cenario = await _analisar_via_ia(
        peca_bytes=peca_bytes,
        peca_nome=peca.filename,
        arquivos=arquivos_nomes,
        sessao_id=sessao_id,
        anexos_bytes=anexos_bytes,
    )

    # Persiste análise para uso em /aplicar
    (pasta / "_analise.json").write_text(
        json.dumps({"sugestoes": [s.model_dump() for s in sugestoes], "faltando": faltando})
    )

    return AnaliseResult(
        sessao_id=sessao_id,
        sugestoes=sugestoes,
        faltando=faltando,
        observacoes=obs,
        cenario_detectado=cenario,
    )


async def _analisar_via_ia(
    peca_bytes: bytes,
    peca_nome: str,
    arquivos: list[str],
    sessao_id: str,
    anexos_bytes: dict[str, bytes],
) -> tuple[list[SugestaoArquivo], list[str], str, str | None]:
    """Usa Gemini 2.5 Flash para analisar a peça e sugerir organização dos arquivos."""
    import logging
    log = logging.getLogger("organizador")

    # ── 1. Extrai texto da peça com marcadores de página (pypdf) ─────────────
    # Mesmo que o PDF seja escaneado (texto vazio), a peça TAMBÉM é enviada
    # como inline_data para o Gemini ler visualmente.
    try:
        reader = PdfReader(io.BytesIO(peca_bytes))
        paginas_texto = []
        for i, page in enumerate(reader.pages):
            t = (page.extract_text() or "").strip()
            if t:
                paginas_texto.append(f"=== PÁGINA {i+1} ===\n{t}")
        texto_peca = "\n".join(paginas_texto) if paginas_texto else ""
    except Exception:
        texto_peca = ""

    lista_arquivos = "\n".join(f"- {n}" for n in arquivos) or "(nenhum)"

    texto_peca_section = (
        f"\n\n## Texto extraído da peça (use para localizar páginas exatas)\n\n{texto_peca}"
        if texto_peca else
        "\n\n## Texto extraído da peça\n\n(PDF escaneado — use a leitura visual do PDF acima)"
    )

    prompt = f"""Você é um assistente jurídico especializado em organização de documentos para protocolo no Brasil.

Você recebeu:
- A PEÇA PROCESSUAL como PDF (primeiro inline_data acima, identificado como [{peca_nome}])
- Os ARQUIVOS ANEXOS como PDFs/imagens (inline_data seguintes, cada um identificado pelo label)

**Arquivos anexos presentes (exatamente esses nomes):**
{lista_arquivos}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PASSO 1 — DETECTE O CENÁRIO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Leia a peça processual e identifique QUAL cenário se aplica:

**Cenário A — Placeholders sem número** `(doc. XX)`
A peça tem referências como "(doc. XX)", "conforme doc. XX" onde XX é literal/placeholder (não é um número). A IA mapeia qual arquivo físico corresponde a cada menção pelo contexto/nome/conteúdo e define a ordem pela primeira ocorrência na peça.

**Cenário B — Já numerado** `doc. 1`, `doc. 2`...
⚠️ ATENÇÃO: A peça JÁ TEM numeração definida: "conforme doc. 1", "vide doc. 3", "doc. nº 2" etc.
REGRA OBRIGATÓRIA: O campo `sugerido` DEVE preservar o número exato da peça:
- Se a peça diz "doc. 3" → sugerido começa com "03"
- Se a peça diz "doc. 1" → sugerido começa com "01"
- NÃO invente novos números. NÃO renumere. Use os números que a peça já definiu.

**Cenário C — Placeholders + Rol de Documentos**
A peça tem `(doc. XX)` E também tem uma seção "Rol de Documentos" listando "1. X; 2. Y...". O ROL tem precedência absoluta para definir ordem e nomes.

**Cenário D — Sem marcadores explícitos**
Nenhum "(doc. XX)" nem "doc. N". Use menções implícitas ("em anexo", "comprovante juntado") ou conhecimento jurídico geral sobre o tipo de peça.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PASSO 2 — PARA CADA ARQUIVO ANEXO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Preencha os campos abaixo para CADA arquivo da lista:

- `original`: nome exato do arquivo (conforme a lista acima)
- `sugerido`: nome padronizado `"NN - Tipo - Descrição.ext"`
  - NN = número zero-padded (01, 02...) — para Cenário B, usar o número da peça
  - Manter extensão original (.pdf, .jpg, .png, .docx...)
- `motivo`: 1-2 frases explicando a decisão (pode mencionar trecho da peça)
- `ordem`: inteiro (1 = primeiro a ser protocolado)
- `pagina`: número da página da PEÇA onde este documento é PRIMEIRO mencionado; null se não encontrado
- `contexto`: 3-5 palavras do texto da peça imediatamente ANTES da menção ao documento; null se não encontrado
  - Exemplo: trecho "...conforme procuração (doc. 1)..." → contexto = "conforme procuração"
- `cenario`: letra do cenário detectado ("A", "B", "C" ou "D")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORMATO DA RESPOSTA — JSON puro, sem markdown
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{{
  "cenario_detectado": "B",
  "sugestoes": [
    {{
      "original": "procuracao_cliente.pdf",
      "sugerido": "01 - Procuração - Poderes Ad Judicia.pdf",
      "motivo": "Mencionada como doc. 1 na pág. 3 como 'instrumento de mandato'",
      "ordem": 1,
      "pagina": 3,
      "contexto": "instrumento de mandato",
      "cenario": "B"
    }},
    {{
      "original": "comprovante_residencia.jpg",
      "sugerido": "02 - Comprovante de Residência - Cliente.jpg",
      "motivo": "Referenciada como doc. 2 na pág. 5",
      "ordem": 2,
      "pagina": 5,
      "contexto": "residência conforme doc.",
      "cenario": "B"
    }}
  ],
  "faltando": ["Certidão mencionada na pág. 7 como doc. 3 não encontrada nos anexos"],
  "observacoes": "Cenário B detectado. Numeração preservada conforme definida na peça."
}}{texto_peca_section}
"""

    try:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY não configurada")

        import anthropic as _anthropic

        client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)

        # ── Monta content blocks: peça primeiro, depois anexos, depois prompt ─
        content: list[dict] = []

        # 1. Peça como PDF (document block)
        content.append({
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.b64encode(peca_bytes).decode(),
            },
            "title": peca_nome,
        })

        # 2. Cada anexo como document/image
        IMAGE_MIMES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
        for nome, conteudo in anexos_bytes.items():
            ext = f".{nome.lower().rsplit('.', 1)[-1]}"
            if ext == ".pdf":
                content.append({
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.b64encode(conteudo).decode(),
                    },
                    "title": nome,
                })
            elif ext in IMAGE_MIMES:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": IMAGE_MIMES[ext],
                        "data": base64.b64encode(conteudo).decode(),
                    },
                })
                content.append({"type": "text", "text": f"[Imagem acima: {nome}]"})
            else:
                content.append({"type": "text", "text": f"[Arquivo não-suportado (apenas nome): {nome}]"})

        # 3. Prompt com instruções
        content.append({"type": "text", "text": prompt})

        msg = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=4096,
            temperature=1,  # claude-opus-4-5 exige temperature=1 quando usando extended thinking; sem thinking, 1 é ok
            messages=[{"role": "user", "content": content}],
        )

        texto = msg.content[0].text.strip()
        log.info("Anthropic organizador raw (primeiros 1000): %s", texto[:1000])

        # Strip markdown fences
        if texto.startswith("```"):
            linhas = texto.split("\n")
            texto = "\n".join(linhas[1:-1] if linhas[-1].strip() == "```" else linhas[1:])

        # Tentativa 1: parse direto
        try:
            data = json.loads(texto)
        except json.JSONDecodeError:
            import re as _re
            match = _re.search(r'\{[\s\S]*\}', texto)
            if match:
                try:
                    data = json.loads(match.group(0))
                except json.JSONDecodeError:
                    log.error("Anthropic organizador JSON inválido após regex. Full response:\n%s", texto[:3000])
                    raise
            else:
                log.error("Anthropic organizador sem JSON encontrado. Full response:\n%s", texto[:3000])
                raise

        cenario = data.get("cenario_detectado")
        sugestoes = [
            SugestaoArquivo(**{**s, "sugerido": _sanitizar_nome(s["sugerido"])})
            for s in data.get("sugestoes", [])
        ]
        faltando = data.get("faltando", [])
        obs = data.get("observacoes", "")
        return sugestoes, faltando, obs, cenario

    except Exception as e:
        log.exception("Erro no organizador IA")
        # Fallback: numeração sequencial básica
        sugestoes = [
            SugestaoArquivo(
                original=n,
                sugerido=_sanitizar_nome(f"{str(i+1).zfill(2)} - {n}"),
                motivo="Numeração sequencial automática (IA indisponível)",
                ordem=i + 1,
            )
            for i, n in enumerate(sorted(arquivos))
        ]
        return sugestoes, [], f"Análise IA indisponível: {str(e)[:200]}. Sugestões básicas aplicadas.", None


# ── Aplicar renomeações ───────────────────────────────────────────────────────

class RenomeItem(BaseModel):
    original: str
    novo: str


class AplicarRequest(BaseModel):
    sessao_id: str
    renomeacoes: list[RenomeItem]


@router.post("/aplicar")
def aplicar_renomeacoes(body: AplicarRequest):
    """Aplica as renomeações confirmadas e retorna ZIP com os arquivos organizados."""
    pasta = STAGING_DIR / body.sessao_id
    if not pasta.exists():
        raise HTTPException(status_code=404, detail="Sessão não encontrada. Reanalise os arquivos.")

    buf = io.BytesIO()

    # Normaliza para NFC para evitar divergências entre o nome em disco e o retornado pela IA
    def _norm(s: str) -> str:
        return unicodedata.normalize("NFC", s).strip()

    mapa = {_norm(r.original): r.novo for r in body.renomeacoes}

    import logging
    _log = logging.getLogger("organizador")
    _log.info("Aplicar — mapa de renomeação: %s", list(mapa.keys()))

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(pasta.iterdir()):
            if f.name.startswith("_") or f.name == "_analise.json":
                continue
            nome_no_zip = mapa.get(_norm(f.name), f.name)
            if nome_no_zip == f.name:
                _log.warning("Sem renomeação para '%s' (norm: '%s') — não encontrado no mapa", f.name, _norm(f.name))
            else:
                _log.info("Renomeando '%s' → '%s'", f.name, nome_no_zip)
            zf.write(f, nome_no_zip)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="protocolo_{body.sessao_id[:8]}.zip"'},
    )


@router.delete("/sessao/{sessao_id}", status_code=204)
def limpar_sessao(sessao_id: str):
    """Remove os arquivos da sessão de staging."""
    import shutil
    pasta = STAGING_DIR / sessao_id
    if pasta.exists():
        shutil.rmtree(pasta)


# ── Pastas do cliente ─────────────────────────────────────────────────────────

@router.get("/pastas-cliente/{cliente_id}")
def listar_pastas_cliente(cliente_id: str):
    """Lista as subpastas do cliente no Dropbox (processos + tipos)."""
    from app.database import SessionLocal
    from app.models.cliente import Cliente
    from app.services.pasta_cliente import listar_subpastas, caminho_host, _host_disponivel

    db = SessionLocal()
    try:
        cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        pasta_raiz_host = caminho_host(cliente.nome)
        subpastas = listar_subpastas(cliente.nome) if _host_disponivel() else []
        return {
            "cliente_nome": cliente.nome,
            "pasta_raiz": pasta_raiz_host,
            "disponivel": _host_disponivel(),
            "subpastas": subpastas,
        }
    finally:
        db.close()


class SalvarNaPastaRequest(BaseModel):
    sessao_id: str
    cliente_id: str
    subfolder: str
    renomeacoes: list[RenomeItem]


@router.post("/salvar-na-pasta")
def salvar_na_pasta(body: SalvarNaPastaRequest):
    """Aplica renomeações e copia os arquivos diretamente para a pasta Dropbox."""
    from app.database import SessionLocal
    from app.models.cliente import Cliente
    from app.services.pasta_cliente import pasta_cliente as _pasta_dropbox, _host_disponivel

    pasta_sessao = STAGING_DIR / body.sessao_id
    if not pasta_sessao.exists():
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    if not _host_disponivel():
        raise HTTPException(status_code=503, detail="Pasta Dropbox não disponível (volume não montado)")

    db = SessionLocal()
    try:
        cliente = db.query(Cliente).filter(Cliente.id == body.cliente_id).first()
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        pasta_dest = _pasta_dropbox(cliente.nome) / body.subfolder
        pasta_dest.mkdir(parents=True, exist_ok=True)
    finally:
        db.close()

    mapa = {r.original: r.novo for r in body.renomeacoes}
    salvos = []
    for f in sorted(pasta_sessao.iterdir()):
        if f.name.startswith("_"):
            continue
        nome_dest = mapa.get(f.name, f.name)
        destino = pasta_dest / nome_dest
        destino.write_bytes(f.read_bytes())
        salvos.append(nome_dest)

    return {"salvos": salvos, "pasta": str(pasta_dest)}
