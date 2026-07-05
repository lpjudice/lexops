import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.prazo import Prazo
from app.models.processo import Processo
from app.models.tarefa import Tarefa
from app.schemas.prazo import PrazoCreate, PrazoOut, PrazoUpdate
from app.services.google_calendar import criar_evento, deletar_evento
from app.services.prazo_calc import calcular_prazo

router = APIRouter(prefix="/prazos", tags=["prazos"],
                   dependencies=[Depends(get_current_user)])


def _recalcular(prazo: Prazo, processo: Processo, db: Session) -> None:
    data_com, data_sem = calcular_prazo(
        db=db,
        data_publicacao=prazo.data_publicacao,
        dias=prazo.dias_prazo,
        estado=processo.estado,
        tipo_contagem=prazo.tipo_contagem,
    )
    prazo.data_limite = data_com
    prazo.data_limite_sem_feriado = data_sem


@router.get("/", response_model=list[PrazoOut])
def listar_prazos(
    processo_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Prazo)
    if processo_id:
        q = q.filter(Prazo.processo_id == processo_id)
    if status:
        q = q.filter(Prazo.status == status)
    prazos = q.order_by(Prazo.data_limite.asc().nullslast()).all()

    tarefas_por_prazo: dict = {}
    for t in db.query(Tarefa).filter(Tarefa.prazo_id.in_([p.id for p in prazos])).all():
        tarefas_por_prazo.setdefault(t.prazo_id, []).append({"id": t.id, "titulo": t.titulo})
    for p in prazos:
        p.tarefas_vinculadas = tarefas_por_prazo.get(p.id, [])

    return prazos


@router.post("/", response_model=PrazoOut, status_code=status.HTTP_201_CREATED)
def criar_prazo(data: PrazoCreate, db: Session = Depends(get_db)):
    processo = db.query(Processo).filter(Processo.id == data.processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    prazo = Prazo(**data.model_dump())
    _recalcular(prazo, processo, db)

    db.add(prazo)
    db.commit()
    db.refresh(prazo)

    # Tenta criar evento no Google Calendar (silencioso se não autenticado)
    if prazo.data_limite:
        titulo = f"[PRAZO] {prazo.tipo.upper()} — {processo.numero_cnj}"
        descricao = prazo.descricao or ""
        event_id = criar_evento(titulo, prazo.data_limite, descricao)
        if event_id:
            prazo.google_event_id = event_id
            db.commit()
            db.refresh(prazo)

    return prazo


@router.get("/{prazo_id}", response_model=PrazoOut)
def obter_prazo(prazo_id: uuid.UUID, db: Session = Depends(get_db)):
    prazo = db.query(Prazo).filter(Prazo.id == prazo_id).first()
    if not prazo:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    return prazo


@router.patch("/{prazo_id}", response_model=PrazoOut)
def atualizar_prazo(
    prazo_id: uuid.UUID, data: PrazoUpdate, db: Session = Depends(get_db)
):
    prazo = db.query(Prazo).filter(Prazo.id == prazo_id).first()
    if not prazo:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(prazo, field, value)

    _recalcular(prazo, prazo.processo, db)
    db.commit()
    db.refresh(prazo)
    return prazo


@router.delete("/{prazo_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_prazo(prazo_id: uuid.UUID, db: Session = Depends(get_db)):
    prazo = db.query(Prazo).filter(Prazo.id == prazo_id).first()
    if not prazo:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    db.delete(prazo)
    db.commit()


@router.post("/{prazo_id}/recalcular", response_model=PrazoOut)
def recalcular_prazo(prazo_id: uuid.UUID, db: Session = Depends(get_db)):
    """Força o recálculo de datas (útil após atualizar a tabela de feriados)."""
    prazo = db.query(Prazo).filter(Prazo.id == prazo_id).first()
    if not prazo:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    _recalcular(prazo, prazo.processo, db)
    db.commit()
    db.refresh(prazo)
    return prazo
