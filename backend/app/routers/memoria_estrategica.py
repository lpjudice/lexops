import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.memoria_estrategica import MemoriaEstrategica
from app.models.usuario import Usuario
from app.schemas.memoria_estrategica import MemoriaEstrategicaCreate, MemoriaEstrategicaOut

router = APIRouter(prefix="/memoria-estrategica", tags=["memoria_estrategica"],
                   dependencies=[Depends(get_current_user)])


@router.get("/", response_model=list[MemoriaEstrategicaOut])
def listar_historico(
    cliente_id: uuid.UUID | None = Query(None),
    processo_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(MemoriaEstrategica)
    if cliente_id:
        q = q.filter(MemoriaEstrategica.cliente_id == cliente_id)
    if processo_id:
        q = q.filter(MemoriaEstrategica.processo_id == processo_id)
    return q.order_by(MemoriaEstrategica.created_at.desc()).all()


@router.post("/", response_model=MemoriaEstrategicaOut, status_code=201)
def criar_versao(
    data: MemoriaEstrategicaCreate,
    db: Session = Depends(get_db),
    current: Usuario = Depends(get_current_user),
):
    m = MemoriaEstrategica(
        cliente_id=data.cliente_id,
        processo_id=data.processo_id,
        texto=data.texto,
        autor_id=current.id,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m
