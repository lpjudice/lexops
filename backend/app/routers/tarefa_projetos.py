import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_optional_user
from app.models.tarefa_projeto import TarefaProjeto
from app.models.usuario import Usuario
from app.schemas.tarefa_projeto import TarefaProjetoCreate, TarefaProjetoOut, TarefaProjetoUpdate

router = APIRouter(prefix="/tarefa-projetos", tags=["tarefa-projetos"])


@router.get("/", response_model=list[TarefaProjetoOut])
def listar(db: Session = Depends(get_db), _u: Usuario | None = Depends(get_optional_user)):
    return db.query(TarefaProjeto).order_by(TarefaProjeto.nome).all()


@router.post("/", response_model=TarefaProjetoOut, status_code=status.HTTP_201_CREATED)
def criar(data: TarefaProjetoCreate, db: Session = Depends(get_db), _u: Usuario | None = Depends(get_optional_user)):
    p = TarefaProjeto(**data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.patch("/{projeto_id}", response_model=TarefaProjetoOut)
def atualizar(projeto_id: uuid.UUID, data: TarefaProjetoUpdate, db: Session = Depends(get_db), _u: Usuario | None = Depends(get_optional_user)):
    p = db.query(TarefaProjeto).filter(TarefaProjeto.id == projeto_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{projeto_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar(projeto_id: uuid.UUID, db: Session = Depends(get_db), _u: Usuario | None = Depends(get_optional_user)):
    p = db.query(TarefaProjeto).filter(TarefaProjeto.id == projeto_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    db.delete(p)
    db.commit()
