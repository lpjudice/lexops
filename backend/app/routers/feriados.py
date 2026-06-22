from datetime import date

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.feriados_seed import FERIADOS_SEED
from app.models.feriado import Feriado

router = APIRouter(prefix="/feriados", tags=["feriados"],
                   dependencies=[Depends(get_current_user)])


@router.post("/seed", status_code=status.HTTP_200_OK)
def popular_feriados(db: Session = Depends(get_db)):
    """Popula a tabela de feriados com o seed padrão. Idempotente."""
    inseridos = 0
    for f in FERIADOS_SEED:
        d = date.fromisoformat(f["data"])
        existe = (
            db.query(Feriado)
            .filter(Feriado.data == d, Feriado.estado == f["estado"])
            .first()
        )
        if not existe:
            db.add(
                Feriado(
                    data=d,
                    nome=f["nome"],
                    estado=f["estado"],
                    recorrente=f["recorrente"],
                )
            )
            inseridos += 1
    db.commit()
    return {"inseridos": inseridos, "total_seed": len(FERIADOS_SEED)}


@router.get("/")
def listar_feriados(estado: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Feriado)
    if estado:
        q = q.filter(Feriado.estado.in_(["nacional", estado]))
    return q.order_by(Feriado.data).all()
