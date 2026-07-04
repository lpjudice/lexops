import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.cliente import Cliente
from app.models.processo import Processo
from app.models.usuario import Usuario

router = APIRouter(prefix="/conselho-juridico", tags=["conselho_juridico"],
                   dependencies=[Depends(get_current_user)])


class ConsultarRequest(BaseModel):
    cliente_id: uuid.UUID | None = None
    processo_id: uuid.UUID | None = None
    pergunta: str


@router.post("/consultar")
async def consultar(
    body: ConsultarRequest,
    db: Session = Depends(get_db),
    current: Usuario = Depends(get_current_user),
):
    if not body.processo_id and not body.cliente_id:
        raise HTTPException(status_code=400, detail="Informe cliente_id ou processo_id")

    from app.services.contexto_service import montar_contexto_cliente, montar_contexto_processo
    from app.services.ia_conselho_juridico import consultar_conselho

    if body.processo_id:
        processo = db.query(Processo).filter(Processo.id == body.processo_id).first()
        if not processo:
            raise HTTPException(status_code=404, detail="Processo não encontrado")
        contexto = montar_contexto_processo(db, processo, current)
    else:
        cliente = db.query(Cliente).filter(Cliente.id == body.cliente_id).first()
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")
        contexto = montar_contexto_cliente(db, cliente, current)

    respostas = await consultar_conselho(contexto, body.pergunta)
    return {"respostas": respostas}
