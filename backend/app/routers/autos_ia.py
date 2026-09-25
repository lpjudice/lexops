"""Autos IA — leitura incremental de autos processuais volumosos, em paralelo
ao restante do gestor. Cada Caso é um processo independente; os PDFs são
enviados em blocos de páginas, segmentados em peças e resumidos por IA."""
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.dependencies import get_current_user
from app.models.autos_ia import AutosIACaso, AutosIADocumento, AutosIAPeca, AutosIAPerguntaFaq, AutosIAReferencia
from app.schemas.autos_ia import (
    CasoCreate, CasoOut, CasoResumo, CasoUpdate, DocumentoOut, FaqPerguntaCreate, FaqPerguntaOut,
    GrafoAresta, GrafoNo, GrafoOut, PecaDetalheOut, PecaOut,
)
from app.services.autos_ia import faq as faq_service
from app.services.autos_ia.busca import buscar_pecas
from app.services.autos_ia.ingestao import processar_documento

UPLOADS_DIR = Path("/app/uploads/autos_ia")

router = APIRouter(prefix="/autos-ia", tags=["autos-ia"], dependencies=[Depends(get_current_user)])


def _get_caso(db: Session, caso_id: uuid.UUID) -> AutosIACaso:
    caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    return caso


# ── Casos ────────────────────────────────────────────────────────────────────

@router.get("/casos", response_model=list[CasoResumo])
def listar_casos(db: Session = Depends(get_db)):
    casos = db.query(AutosIACaso).order_by(AutosIACaso.criado_em.desc()).all()
    out = []
    for c in casos:
        item = CasoResumo.model_validate(c)
        item.total_pecas = db.query(AutosIAPeca).filter(AutosIAPeca.caso_id == c.id).count()
        item.total_documentos = db.query(AutosIADocumento).filter(AutosIADocumento.caso_id == c.id).count()
        item.total_perguntas_faq = db.query(AutosIAPerguntaFaq).filter(AutosIAPerguntaFaq.caso_id == c.id).count()
        out.append(item)
    return out


@router.post("/casos", response_model=CasoOut, status_code=status.HTTP_201_CREATED)
def criar_caso(data: CasoCreate, db: Session = Depends(get_db), usuario=Depends(get_current_user)):
    caso = AutosIACaso(**data.model_dump(), criado_por_id=usuario.id)
    db.add(caso)
    db.commit()
    db.refresh(caso)
    return caso


@router.get("/casos/{caso_id}", response_model=CasoOut)
def obter_caso(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_caso(db, caso_id)


@router.patch("/casos/{caso_id}", response_model=CasoOut)
def atualizar_caso(caso_id: uuid.UUID, data: CasoUpdate, db: Session = Depends(get_db)):
    caso = _get_caso(db, caso_id)
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(caso, campo, valor)
    db.commit()
    db.refresh(caso)
    return caso


@router.delete("/casos/{caso_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_caso(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    caso = _get_caso(db, caso_id)
    db.delete(caso)
    db.commit()


# ── Upload / ingestão ───────────────────────────────────────────────────────

def _executar_ingestao_em_background(documento_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        processar_documento(db, documento_id)
    finally:
        db.close()


@router.post("/casos/{caso_id}/upload", response_model=DocumentoOut, status_code=status.HTTP_202_ACCEPTED)
async def enviar_bloco(
    caso_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    arquivo: UploadFile = File(..., description="Bloco de páginas do PDF dos autos"),
    pagina_inicio: int | None = Form(None, description="Página inicial global; padrão = continuar do último bloco"),
    db: Session = Depends(get_db),
):
    caso = _get_caso(db, caso_id)

    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(status_code=422, detail="Arquivo vazio")

    from pypdf import PdfReader
    import io
    try:
        total_paginas_bloco = len(PdfReader(io.BytesIO(conteudo)).pages)
    except Exception:
        raise HTTPException(status_code=422, detail="Não foi possível ler o PDF enviado")

    inicio = pagina_inicio if pagina_inicio is not None else caso.total_paginas + 1
    fim = inicio + total_paginas_bloco - 1

    pasta_caso = UPLOADS_DIR / str(caso.id)
    pasta_caso.mkdir(parents=True, exist_ok=True)
    nome_arquivo = f"{inicio:06d}-{fim:06d}_{uuid.uuid4().hex[:8]}_{arquivo.filename}"
    caminho = pasta_caso / nome_arquivo
    caminho.write_bytes(conteudo)

    documento = AutosIADocumento(
        caso_id=caso.id,
        nome_arquivo=arquivo.filename or nome_arquivo,
        caminho_arquivo=str(caminho),
        pagina_inicio=inicio,
        pagina_fim=fim,
        status="pendente",
    )
    db.add(documento)
    db.commit()
    db.refresh(documento)

    background_tasks.add_task(_executar_ingestao_em_background, documento.id)
    return documento


@router.get("/casos/{caso_id}/documentos", response_model=list[DocumentoOut])
def listar_documentos(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    return (
        db.query(AutosIADocumento)
        .filter(AutosIADocumento.caso_id == caso_id)
        .order_by(AutosIADocumento.pagina_inicio.asc())
        .all()
    )


# ── Peças (busca por tema/data/tipo) ────────────────────────────────────────

@router.get("/casos/{caso_id}/pecas", response_model=list[PecaOut])
def listar_pecas(
    caso_id: uuid.UUID,
    q: str | None = None,
    tipo: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    db: Session = Depends(get_db),
):
    from datetime import date as date_cls
    _get_caso(db, caso_id)
    di = date_cls.fromisoformat(data_inicio) if data_inicio else None
    df = date_cls.fromisoformat(data_fim) if data_fim else None
    return buscar_pecas(db, caso_id, query=q, data_inicio=di, data_fim=df, tipo=tipo)


@router.get("/pecas/{peca_id}", response_model=PecaDetalheOut)
def obter_peca(peca_id: uuid.UUID, db: Session = Depends(get_db)):
    peca = db.query(AutosIAPeca).filter(AutosIAPeca.id == peca_id).first()
    if not peca:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    return peca


# ── Grafo de referências ─────────────────────────────────────────────────────

@router.get("/casos/{caso_id}/grafo", response_model=GrafoOut)
def obter_grafo(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    pecas = db.query(AutosIAPeca).filter(AutosIAPeca.caso_id == caso_id).all()
    referencias = db.query(AutosIAReferencia).filter(AutosIAReferencia.caso_id == caso_id).all()
    return GrafoOut(
        nos=[GrafoNo.model_validate(p, from_attributes=True) for p in pecas],
        arestas=[GrafoAresta.model_validate(r, from_attributes=True) for r in referencias],
    )


# ── FAQ ──────────────────────────────────────────────────────────────────────

@router.get("/casos/{caso_id}/faq", response_model=list[FaqPerguntaOut])
def listar_faq(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    return (
        db.query(AutosIAPerguntaFaq)
        .filter(AutosIAPerguntaFaq.caso_id == caso_id)
        .order_by(AutosIAPerguntaFaq.criado_em.desc())
        .all()
    )


@router.post("/casos/{caso_id}/faq", response_model=FaqPerguntaOut, status_code=status.HTTP_201_CREATED)
def perguntar(caso_id: uuid.UUID, data: FaqPerguntaCreate, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    pergunta = AutosIAPerguntaFaq(caso_id=caso_id, pergunta=data.pergunta, status="pendente")
    db.add(pergunta)
    db.commit()
    db.refresh(pergunta)
    faq_service.responder_pergunta(db, pergunta)
    db.refresh(pergunta)
    return pergunta


@router.post("/faq/{pergunta_id}/reprocessar", response_model=FaqPerguntaOut)
def reprocessar_pergunta(pergunta_id: uuid.UUID, db: Session = Depends(get_db)):
    pergunta = db.query(AutosIAPerguntaFaq).filter(AutosIAPerguntaFaq.id == pergunta_id).first()
    if not pergunta:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada")
    faq_service.responder_pergunta(db, pergunta)
    db.refresh(pergunta)
    return pergunta


@router.delete("/faq/{pergunta_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_pergunta(pergunta_id: uuid.UUID, db: Session = Depends(get_db)):
    pergunta = db.query(AutosIAPerguntaFaq).filter(AutosIAPerguntaFaq.id == pergunta_id).first()
    if not pergunta:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada")
    db.delete(pergunta)
    db.commit()
