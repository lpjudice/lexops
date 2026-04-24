import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tarefa import Tarefa
from app.schemas.tarefa import TarefaCreate, TarefaOut, TarefaUpdate

router = APIRouter(prefix="/tarefas", tags=["tarefas"])


@router.get("/", response_model=list[TarefaOut])
def listar_tarefas(
    cliente_id: uuid.UUID | None = Query(None),
    processo_id: uuid.UUID | None = Query(None),
    anotacao_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Tarefa)
    if cliente_id:
        q = q.filter(Tarefa.cliente_id == cliente_id)
    if processo_id:
        q = q.filter(Tarefa.processo_id == processo_id)
    if anotacao_id:
        q = q.filter(Tarefa.anotacao_id == anotacao_id)
    if status:
        q = q.filter(Tarefa.status == status)
    return q.order_by(Tarefa.data_limite.asc().nullslast(), Tarefa.created_at.desc()).all()


@router.post("/", response_model=TarefaOut, status_code=status.HTTP_201_CREATED)
def criar_tarefa(data: TarefaCreate, db: Session = Depends(get_db)):
    tarefa = Tarefa(**data.model_dump())
    db.add(tarefa)
    db.commit()
    db.refresh(tarefa)
    return tarefa


@router.get("/{tarefa_id}", response_model=TarefaOut)
def obter_tarefa(tarefa_id: uuid.UUID, db: Session = Depends(get_db)):
    t = db.query(Tarefa).filter(Tarefa.id == tarefa_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return t


@router.patch("/{tarefa_id}", response_model=TarefaOut)
def atualizar_tarefa(tarefa_id: uuid.UUID, data: TarefaUpdate, db: Session = Depends(get_db)):
    t = db.query(Tarefa).filter(Tarefa.id == tarefa_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(t, field, value)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/{tarefa_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_tarefa(tarefa_id: uuid.UUID, db: Session = Depends(get_db)):
    t = db.query(Tarefa).filter(Tarefa.id == tarefa_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    db.delete(t)
    db.commit()


@router.post("/{tarefa_id}/agendar-calendario", response_model=TarefaOut)
def agendar_tarefa_no_calendario(tarefa_id: uuid.UUID, db: Session = Depends(get_db)):
    """Cria ou atualiza evento no Google Calendar para a tarefa, com horário comercial e sem sobreposição."""
    from app.services.google_calendar import criar_evento_tarefa, google_conectado

    t = db.query(Tarefa).filter(Tarefa.id == tarefa_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    if not t.data_limite:
        raise HTTPException(status_code=400, detail="Tarefa sem data de prazo definida")
    if not google_conectado():
        raise HTTPException(status_code=503, detail="Google Calendar não conectado")

    event_id = criar_evento_tarefa(
        titulo=t.titulo,
        data_limite=t.data_limite,
        descricao=t.descricao or "",
        event_id=t.google_event_id,
    )
    if event_id:
        t.google_event_id = event_id
        db.commit()
        db.refresh(t)
    return t
