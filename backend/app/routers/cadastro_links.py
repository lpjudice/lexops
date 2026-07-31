"""Gestão dos links de autocadastro (autenticado).

Gera/lista/revoga os convites. O preenchimento público e a aprovação vivem em
outros lugares: endpoints públicos em `publico.py` (Fase 2) e a revisão em
staging na Fase 3.
"""
import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.cadastro_link import ClienteCadastroLink, ClienteCadastroSubmissao
from app.models.cliente import Cliente
from app.models.usuario import Usuario

router = APIRouter(
    prefix="/cadastro-links", tags=["cadastro-links"],
    dependencies=[Depends(get_current_user)],
)


class LinkCreate(BaseModel):
    # Nulo => link genérico (reutilizável, captação de cliente novo).
    cliente_id: uuid.UUID | None = None
    rotulo: str | None = None
    # Dias até expirar (None = não expira). Genérico normalmente não expira.
    expira_em_dias: int | None = None


def _link_to_dict(link: ClienteCadastroLink) -> dict:
    return {
        "id": str(link.id),
        "token": link.token,
        "cliente_id": str(link.cliente_id) if link.cliente_id else None,
        "rotulo": link.rotulo,
        "reutilizavel": link.reutilizavel,
        "expira_em": link.expira_em.isoformat() if link.expira_em else None,
        "revogado": link.revogado,
        "usos": link.usos,
        "caminho": f"/cadastro/{link.token}",
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


@router.get("")
def listar_links(db: Session = Depends(get_db)):
    links = (
        db.query(ClienteCadastroLink)
        .order_by(ClienteCadastroLink.created_at.desc())
        .all()
    )
    # Contagem de submissões pendentes por link (para a UI).
    return [_link_to_dict(l) for l in links]


@router.post("", status_code=201)
def criar_link(
    data: LinkCreate,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    cliente_id = None
    reutilizavel = True  # genérico por padrão
    if data.cliente_id:
        cliente = db.query(Cliente).filter(Cliente.id == data.cliente_id).first()
        if not cliente:
            raise HTTPException(404, "Cliente não encontrado")
        cliente_id = cliente.id
        reutilizavel = False  # convite de atualização = uso único

    from datetime import timedelta, timezone
    expira_em = None
    if data.expira_em_dias:
        expira_em = datetime.now(timezone.utc) + timedelta(days=data.expira_em_dias)

    link = ClienteCadastroLink(
        token=secrets.token_urlsafe(32),
        cliente_id=cliente_id,
        rotulo=data.rotulo,
        reutilizavel=reutilizavel,
        expira_em=expira_em,
        created_by_id=user.id,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return _link_to_dict(link)


@router.post("/{link_id}/revogar")
def revogar_link(link_id: uuid.UUID, db: Session = Depends(get_db)):
    link = db.query(ClienteCadastroLink).filter(ClienteCadastroLink.id == link_id).first()
    if not link:
        raise HTTPException(404, "Link não encontrado")
    link.revogado = True
    db.commit()
    return {"ok": True}
