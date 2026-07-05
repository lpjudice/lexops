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


def _montar_contexto(db: Session, current: Usuario, cliente_id, processo_id) -> str:
    from app.services.contexto_service import montar_contexto_cliente, montar_contexto_processo

    if processo_id:
        processo = db.query(Processo).filter(Processo.id == processo_id).first()
        if not processo:
            raise HTTPException(status_code=404, detail="Processo não encontrado")
        return montar_contexto_processo(db, processo, current)

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return montar_contexto_cliente(db, cliente, current)


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

    from app.services.ia_conselho_juridico import consultar_conselho

    contexto = _montar_contexto(db, current, body.cliente_id, body.processo_id)
    respostas = await consultar_conselho(contexto, body.pergunta)
    return {"respostas": respostas}


class PerguntarUmRequest(BaseModel):
    cliente_id: uuid.UUID | None = None
    processo_id: uuid.UUID | None = None
    chave: str
    pergunta: str
    historico: list[dict] = []


@router.post("/perguntar-um")
async def perguntar_um(
    body: PerguntarUmRequest,
    db: Session = Depends(get_db),
    current: Usuario = Depends(get_current_user),
):
    """Pergunta de aprofundamento isolada pra UM especialista — não afeta os
    outros cards nem reinicia a conversa deles."""
    if not body.processo_id and not body.cliente_id:
        raise HTTPException(status_code=400, detail="Informe cliente_id ou processo_id")

    from app.services.ia_conselho_juridico import consultar_um

    contexto = _montar_contexto(db, current, body.cliente_id, body.processo_id)
    resposta = await consultar_um(body.chave, contexto, body.pergunta, body.historico)
    return resposta
