"""
Rota de Análise de Jurisprudência.
Recebe texto de decisão/acórdão e retorna análise estruturada com IA.
"""

import io
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cliente import Cliente

router = APIRouter(prefix="/jurisprudencia", tags=["jurisprudencia"])

PROMPT_ANALISE = """
Você é um jurista experiente especializado em análise de jurisprudência. Analise o julgado/decisão judicial abaixo e produza um relatório estruturado com as seguintes seções:

**IDENTIFICAÇÃO**
- Órgão julgador, número do processo (se disponível), data, relator

**EMENTA / SÍNTESE**
- Resumo do que foi julgado em 2-3 frases

**TESE VENCEDORA**
- Qual o entendimento que prevaleceu e seus fundamentos principais

**TESE CONTRÁRIA / VENCIDA** (se houver votos divergentes)
- Qual foi a posição minoritária e seus argumentos

**RATIO DECIDENDI**
- A razão de decidir, ou seja, o núcleo jurídico da decisão que a torna vinculante/persuasiva

**OBITER DICTA** (se houver)
- Observações relevantes que não compõem a ratio

**IMPACTO PRÁTICO**
- Como essa decisão pode afetar casos semelhantes; se é favorável ou desfavorável a clientes que estejam em posição similar

**TENDÊNCIA JURISPRUDENCIAL**
- Se essa decisão representa consolidação, mudança ou divergência em relação à tendência atual

**APLICABILIDADE**
- Em quais situações práticas esse precedente pode ser invocado como argumento

---

Texto do julgado:

{texto}
"""


class AnalisarRequest(BaseModel):
    texto: str
    modelo: str = "gemini"


@router.post("/analisar")
async def analisar_jurisprudencia(body: AnalisarRequest):
    if not body.texto.strip():
        raise HTTPException(status_code=400, detail="Texto vazio")

    prompt = PROMPT_ANALISE.format(texto=body.texto[:15000])

    try:
        if body.modelo == "gemini":
            from app.services.gemini_chat import chat_processo
            resultado = chat_processo(pergunta=prompt, historico=[], pdf_paths=[])
        elif body.modelo == "claude":
            from app.services.ia_cliente import chat_claude
            resultado = chat_claude(pergunta=prompt, historico=[], cliente_id="", contexto="")
        elif body.modelo == "gpt":
            from app.services.ia_cliente import chat_gpt
            resultado = chat_gpt(pergunta=prompt, historico=[], cliente_id="", contexto="")
        else:
            raise HTTPException(status_code=400, detail="Modelo inválido")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"analise": resultado}


@router.post("/extrair-pdf")
async def extrair_pdf(arquivo: UploadFile = File(...)):
    """Extrai texto de um PDF enviado pelo usuário."""
    if not arquivo.filename or not arquivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Arquivo deve ser PDF")

    content = await arquivo.read()

    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        paginas = [page.extract_text() or "" for page in reader.pages[:30]]
        texto = "\n\n".join(p.strip() for p in paginas if p.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar PDF: {e}")

    if not texto.strip():
        raise HTTPException(status_code=422, detail="Não foi possível extrair texto do PDF")

    return {"texto": texto}


class SalvarRequest(BaseModel):
    cliente_id: uuid.UUID
    processo_id: uuid.UUID | None = None
    titulo: str | None = None
    analise: str
    texto_original: str


@router.post("/salvar")
def salvar_jurisprudencia(body: SalvarRequest, db: Session = Depends(get_db)):
    """Saves analysis + original text to client's Jurisprudência/ folder."""
    cliente = db.query(Cliente).filter(Cliente.id == body.cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    from app.services.pasta_cliente import pasta_tipo, salvar_arquivo, _host_disponivel
    from app.services.gerar_pdf_texto import texto_para_pdf
    if not _host_disponivel():
        raise HTTPException(status_code=503, detail="Pasta do cliente não disponível")

    hoje = date.today()
    import re
    slug_raw = body.titulo.replace(" ", "_")[:40] if body.titulo else "julgado"
    slug = re.sub(r'[^\w\-]', '_', slug_raw)
    hoje_str = hoje.strftime("%Y-%m-%d")

    pasta = pasta_tipo(cliente.nome, "jurisprudencia")

    # PDF da análise
    nome_analise = f"{hoje_str}_{slug}_analise.pdf"
    pdf_analise = texto_para_pdf(
        conteudo=body.analise,
        titulo=f"Análise — {body.titulo or 'Julgado'}",
        subtitulo="Análise de Jurisprudência",
        cliente_nome=cliente.nome,
        data=hoje,
    )
    salvar_arquivo(pasta, nome_analise, pdf_analise)

    # PDF do inteiro teor
    nome_teor = f"{hoje_str}_{slug}_inteiro_teor.pdf"
    pdf_teor = texto_para_pdf(
        conteudo=body.texto_original,
        titulo=f"Inteiro Teor — {body.titulo or 'Julgado'}",
        subtitulo="Texto Original do Julgado",
        cliente_nome=cliente.nome,
        data=hoje,
    )
    salvar_arquivo(pasta, nome_teor, pdf_teor)

    # Upload para Google Drive
    try:
        from app.services.google_drive import upload_arquivo
        upload_arquivo(pdf_analise, nome_analise, cliente.nome, "Jurisprudência")
        upload_arquivo(pdf_teor, nome_teor, cliente.nome, "Jurisprudência")
    except Exception:
        pass

    return {"ok": True, "pasta": str(pasta), "slug": slug}
