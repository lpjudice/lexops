"""
PrecedentCheck — verificação reversa de citações jurisprudenciais em peças e decisões.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.precedentcheck import PrecedentCheckAnalise

router = APIRouter(prefix="/precedentcheck", tags=["precedentcheck"],
                   dependencies=[Depends(get_current_user)])


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

    from app.services.pdf_extract import extrair_texto_pdf
    texto = extrair_texto_pdf(content)

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

    import asyncio
    from app.services.precedentcheck_service import extrair_citacoes

    # Roda em thread pool para não bloquear o event loop do uvicorn
    citacoes_raw, custo_extracao = await asyncio.to_thread(extrair_citacoes, body.texto)

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
        custo_usd=custo_extracao,
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

    import asyncio
    from app.services.precedentcheck_service import verificar_citacao as _verificar

    contexto_peca = analise.texto_peca[:3000] if analise.texto_peca else ""

    # Roda em thread pool para não bloquear o event loop do uvicorn
    resultado = await asyncio.to_thread(_verificar, citacao_raw, contexto_peca)

    # Atualiza o registro no banco
    citacoes = list(analise.citacoes)
    citacoes[idx] = {**citacao_raw, **resultado, "verificado": True}
    analise.citacoes = citacoes

    # Recalcula contadores e acumula custo
    analise.total_ok = sum(1 for c in citacoes if c.get("status_geral") == "verificado")
    analise.total_divergencia = sum(1 for c in citacoes if c.get("status_geral") == "divergencia")
    analise.total_nao_encontrado = sum(1 for c in citacoes if c.get("status_geral") == "nao_encontrado")
    analise.custo_usd = round((analise.custo_usd or 0.0) + float(resultado.get("custo_usd") or 0.0), 4)

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
        "custo_usd": float(a.custo_usd or 0.0),
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
