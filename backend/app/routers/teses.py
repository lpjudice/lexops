import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.tese import Tese
from app.schemas.tese import ModeloIA, TeseCreate, TeseOut, TeseUpdate
from app.services import ia_teses

router = APIRouter(prefix="/teses", tags=["teses"],
                   dependencies=[Depends(get_current_user)])

CAMPO_RESPOSTA: dict[str, str] = {
    "claude": "resposta_claude",
    "gpt": "resposta_gpt",
    "gemini": "resposta_gemini",
}


@router.get("/", response_model=list[TeseOut])
def listar_teses(
    cliente_id: uuid.UUID | None = None,
    processo_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Tese)
    if cliente_id:
        q = q.filter(Tese.cliente_id == cliente_id)
    if processo_id:
        q = q.filter(Tese.processo_id == processo_id)
    return q.order_by(Tese.created_at.desc()).all()


@router.post("/", response_model=TeseOut, status_code=status.HTTP_201_CREATED)
def criar_tese(data: TeseCreate, db: Session = Depends(get_db)):
    tese = Tese(**data.model_dump())
    db.add(tese)
    db.commit()
    db.refresh(tese)
    return tese


@router.get("/{tese_id}", response_model=TeseOut)
def obter_tese(tese_id: uuid.UUID, db: Session = Depends(get_db)):
    t = db.query(Tese).filter(Tese.id == tese_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tese não encontrada")
    return t


@router.patch("/{tese_id}", response_model=TeseOut)
def atualizar_tese(tese_id: uuid.UUID, data: TeseUpdate, db: Session = Depends(get_db)):
    t = db.query(Tese).filter(Tese.id == tese_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tese não encontrada")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(t, field, value)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/{tese_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_tese(tese_id: uuid.UUID, db: Session = Depends(get_db)):
    t = db.query(Tese).filter(Tese.id == tese_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tese não encontrada")
    db.delete(t)
    db.commit()


@router.post("/{tese_id}/gerar/{modelo}", response_model=TeseOut)
def gerar_resposta(
    tese_id: uuid.UUID,
    modelo: ModeloIA,
    db: Session = Depends(get_db),
):
    """Chama a IA escolhida e salva a resposta na tese."""
    t = db.query(Tese).filter(Tese.id == tese_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tese não encontrada")

    resposta = ia_teses.gerar(modelo, t.texto_input)
    campo = CAMPO_RESPOSTA[modelo]
    setattr(t, campo, resposta)
    t.modelo_ativo = modelo
    db.commit()
    db.refresh(t)
    return t
