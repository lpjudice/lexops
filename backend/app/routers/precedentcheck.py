"""
PrecedentCheck — verificação reversa de citações jurisprudenciais em peças e decisões.
"""

import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.precedentcheck import PrecedentCheckAnalise

router = APIRouter(prefix="/precedentcheck", tags=["precedentcheck"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AnalisarRequest(BaseModel):
    texto: str
    titulo: str | None = None
    cliente_id: str | None = None
    processo_id: str | None = None


class AnalisarResponse(BaseModel):
    analise_id: str
    total_citacoes: int
    citacoes: list[dict]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

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
    # Limita a 5MB para evitar timeouts
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
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.b64encode(content).decode(),
                    },
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


@router.post("/extrair-pdf")
async def extrair_pdf(arquivo: UploadFile = File(...)):
    """
    Extrai texto de PDF em 3 tentativas:
      1. pypdf (rápido, funciona em PDFs com texto selecionável)
      2. pdfminer (melhor com codificações exóticas)
      3. Claude vision (PDFs escaneados sem camada de texto)
    """
    if not arquivo.filename or not arquivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Arquivo deve ser PDF")
    content = await arquivo.read()

    import logging
    logger = logging.getLogger(__name__)
    logger.info("extrair-pdf: arquivo=%s tamanho=%d bytes", arquivo.filename, len(content))

    # Tentativa 1: pypdf
    texto = ""
    try:
        texto = _extrair_com_pypdf(content)
        logger.info("pypdf extraiu %d chars", len(texto))
    except Exception as exc:
        logger.warning("pypdf falhou: %s", exc)

    # Tentativa 2: pdfminer
    if not texto.strip():
        try:
            texto = _extrair_com_pdfminer(content)
            logger.info("pdfminer extraiu %d chars", len(texto))
        except Exception as exc:
            logger.warning("pdfminer falhou: %s", exc)

    # Tentativa 3: Claude OCR (PDFs escaneados — imagem sem texto)
    if not texto.strip():
        logger.info("tentando Claude OCR")
        try:
            texto = _extrair_com_claude_ocr(content)
            logger.info("Claude OCR extraiu %d chars", len(texto))
        except Exception as e:
            logger.error("Claude OCR falhou: %s", e)
            raise HTTPException(status_code=500, detail=f"Não foi possível extrair texto do PDF: {e}")

    if not texto.strip():
        raise HTTPException(
            status_code=422,
            detail="Não foi possível extrair texto deste PDF. Tente colar o texto manualmente.",
        )
    return {"texto": texto.strip()}


@router.post("/analisar", response_model=AnalisarResponse)
async def analisar(body: AnalisarRequest, db: Session = Depends(get_db)):
    """
    Etapa 1: extrai citações da peça.
    Retorna imediatamente a lista de citações identificadas (sem verificar ainda).
    A verificação detalhada de cada citação é feita via /verificar/{analise_id}/{idx}.
    """
    if not body.texto.strip():
        raise HTTPException(status_code=400, detail="Texto vazio")

    from app.services.precedentcheck_service import extrair_citacoes

    citacoes_raw = extrair_citacoes(body.texto)

    # Salva a análise no banco com citacoes sem verificação ainda
    citacoes_inicial = [
        {**c, "status_geral": "pendente", "verificado": False}
        for c in citacoes_raw
    ]

    analise = PrecedentCheckAnalise(
        cliente_id=uuid.UUID(body.cliente_id) if body.cliente_id else None,
        processo_id=uuid.UUID(body.processo_id) if body.processo_id else None,
        titulo=body.titulo,
        texto_peca=body.texto,
        citacoes=citacoes_inicial,
        total_citacoes=len(citacoes_inicial),
    )
    db.add(analise)
    db.commit()
    db.refresh(analise)

    return AnalisarResponse(
        analise_id=str(analise.id),
        total_citacoes=len(citacoes_inicial),
        citacoes=citacoes_inicial,
    )


@router.post("/verificar/{analise_id}/{idx}")
async def verificar_citacao(analise_id: str, idx: int, db: Session = Depends(get_db)):
    """
    Verifica uma citação específica (por índice) dentro de uma análise.
    Chamado citação a citação pelo frontend para exibição progressiva.
    """
    analise = db.query(PrecedentCheckAnalise).filter(
        PrecedentCheckAnalise.id == uuid.UUID(analise_id)
    ).first()
    if not analise:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    if idx < 0 or idx >= len(analise.citacoes):
        raise HTTPException(status_code=400, detail="Índice fora do range")

    citacao_raw = analise.citacoes[idx]

    from app.services.precedentcheck_service import verificar_citacao as _verificar

    # Extrai contexto geral da peça (primeiros 3000 chars da peça)
    contexto_peca = analise.texto_peca[:3000] if analise.texto_peca else ""

    resultado = _verificar(citacao_raw, contexto_peca)

    # Atualiza o registro no banco
    citacoes = list(analise.citacoes)
    citacoes[idx] = {**citacao_raw, **resultado, "verificado": True}
    analise.citacoes = citacoes

    # Recalcula contadores
    analise.total_ok = sum(1 for c in citacoes if c.get("status_geral") == "verificado")
    analise.total_divergencia = sum(1 for c in citacoes if c.get("status_geral") == "divergencia")
    analise.total_nao_encontrado = sum(1 for c in citacoes if c.get("status_geral") == "nao_encontrado")

    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(analise, "citacoes")
    db.commit()

    return citacoes[idx]


def _serializar(a: PrecedentCheckAnalise) -> dict:
    return {
        "id": str(a.id),
        "titulo": a.titulo,
        "total_citacoes": a.total_citacoes,
        "total_ok": a.total_ok,
        "total_divergencia": a.total_divergencia,
        "total_nao_encontrado": a.total_nao_encontrado,
        "arquivado": bool(a.arquivado),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("/historico")
def listar_historico(arquivado: bool = False, db: Session = Depends(get_db)):
    """Lista análises salvas. ?arquivado=true para ver as arquivadas."""
    analises = (
        db.query(PrecedentCheckAnalise)
        .filter(PrecedentCheckAnalise.arquivado == arquivado)
        .order_by(PrecedentCheckAnalise.created_at.desc())
        .limit(100)
        .all()
    )
    return [_serializar(a) for a in analises]


class PatchAnaliseRequest(BaseModel):
    titulo: str | None = None
    arquivado: bool | None = None


@router.patch("/historico/{analise_id}")
def patch_analise(analise_id: str, body: PatchAnaliseRequest, db: Session = Depends(get_db)):
    analise = db.query(PrecedentCheckAnalise).filter(
        PrecedentCheckAnalise.id == uuid.UUID(analise_id)
    ).first()
    if not analise:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    if body.titulo is not None:
        analise.titulo = body.titulo
    if body.arquivado is not None:
        analise.arquivado = body.arquivado
    db.commit()
    return _serializar(analise)


@router.get("/historico/{analise_id}")
def obter_analise(analise_id: str, db: Session = Depends(get_db)):
    """Retorna uma análise completa com todas as citações verificadas."""
    analise = db.query(PrecedentCheckAnalise).filter(
        PrecedentCheckAnalise.id == uuid.UUID(analise_id)
    ).first()
    if not analise:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    return {
        **_serializar(analise),
        "texto_peca": analise.texto_peca,
        "citacoes": analise.citacoes,
    }


@router.delete("/historico/{analise_id}")
def deletar_analise(analise_id: str, db: Session = Depends(get_db)):
    analise = db.query(PrecedentCheckAnalise).filter(
        PrecedentCheckAnalise.id == uuid.UUID(analise_id)
    ).first()
    if not analise:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    db.delete(analise)
    db.commit()
    return {"ok": True}
