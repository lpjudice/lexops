"""Gestão dos links de autocadastro (autenticado).

Gera/lista/revoga os convites. O preenchimento público e a aprovação vivem em
outros lugares: endpoints públicos em `publico.py` (Fase 2) e a revisão em
staging na Fase 3.
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
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
    # Convite atrelado a cliente: reaproveita um válido ou cria (expira em 5 dias).
    if data.cliente_id:
        cliente = db.query(Cliente).filter(Cliente.id == data.cliente_id).first()
        if not cliente:
            raise HTTPException(404, "Cliente não encontrado")
        return _link_to_dict(_get_or_create_invite(db, cliente, user))

    # Link genérico (reutilizável, sem expiração por padrão).
    expira_em = None
    if data.expira_em_dias:
        expira_em = datetime.now(timezone.utc) + timedelta(days=data.expira_em_dias)
    link = ClienteCadastroLink(
        token=secrets.token_urlsafe(9),
        cliente_id=None,
        rotulo=data.rotulo,
        reutilizavel=True,
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


# ── Envio do link de convite por e-mail / Telegram (Fase 4) ───────────────────

def _base_url(request: Request) -> str:
    """Base pública dos links. Usa CADASTRO_BASE_URL se configurado (domínio
    customizado); senão o host pelo qual o painel foi acessado."""
    if settings.cadastro_base_url.strip():
        return settings.cadastro_base_url.strip().rstrip("/")
    return str(request.base_url).rstrip("/")


INVITE_EXPIRA_DIAS = 5


def _get_or_create_invite(db: Session, cliente: Cliente, user: Usuario) -> ClienteCadastroLink:
    """Reaproveita um convite ainda válido do cliente, ou cria um novo (expira em 5 dias)."""
    agora = datetime.now(timezone.utc)
    link = (
        db.query(ClienteCadastroLink)
        .filter(
            ClienteCadastroLink.cliente_id == cliente.id,
            ClienteCadastroLink.revogado.is_(False),
        )
        .order_by(ClienteCadastroLink.created_at.desc())
        .first()
    )
    if link and link.expira_em is not None and link.expira_em > agora:
        return link
    link = ClienteCadastroLink(
        token=secrets.token_urlsafe(9),
        cliente_id=cliente.id,
        rotulo=cliente.nome,
        reutilizavel=False,
        expira_em=agora + timedelta(days=INVITE_EXPIRA_DIAS),
        created_by_id=user.id,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def _cliente_ou_404(db: Session, cliente_id: uuid.UUID) -> Cliente:
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")
    return cliente


def _url_para(request: Request, db: Session, cliente_id: uuid.UUID | None, user: Usuario):
    """Resolve (url, cliente, is_update). cliente_id nulo => link genérico /cadastro."""
    base = _base_url(request)
    if cliente_id:
        cliente = _cliente_ou_404(db, cliente_id)
        link = _get_or_create_invite(db, cliente, user)
        return f"{base}/cadastro/{link.token}", cliente, True
    return f"{base}/cadastro", None, False


class EnviarEmailPayload(BaseModel):
    cliente_id: uuid.UUID | None = None  # nulo => link genérico
    destinatario: str | None = None      # obrigatório no genérico; sobrescreve o do cliente
    copia_para_mim: bool = True


@router.post("/enviar-email")
def enviar_email(
    payload: EnviarEmailPayload,
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    url, cliente, is_update = _url_para(request, db, payload.cliente_id, user)
    dest = (payload.destinatario or (cliente.email if cliente else "") or "").strip()
    if not dest:
        raise HTTPException(400, "Informe o e-mail do destinatário.")
    cc = None
    if payload.copia_para_mim and user.email and user.email.lower() != dest.lower():
        cc = [user.email]
    from app.services.email_service import send_cadastro_email
    try:
        send_cadastro_email(dest, url, cliente.nome if cliente else None, cc=cc, is_update=is_update)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Não foi possível enviar o e-mail: {exc}")
    return {"ok": True, "destinatario": dest, "url": url}


class EnviarTelegramPayload(BaseModel):
    cliente_id: uuid.UUID | None = None  # nulo => link genérico


@router.post("/enviar-telegram")
def enviar_telegram(
    payload: EnviarTelegramPayload,
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    ids_raw = (settings.telegram_allowed_user_ids or "").split(",")
    chat_ids = [int(x) for x in (i.strip() for i in ids_raw) if x.strip().isdigit()]
    if not chat_ids:
        raise HTTPException(503, "Nenhum Telegram configurado (telegram_allowed_user_ids).")
    url, cliente, _ = _url_para(request, db, payload.cliente_id, user)
    alvo = f"de *{cliente.nome}*" if cliente else "(genérico)"
    from app.services import telegram_api
    texto = f"🔗 Link de cadastro {alvo}:\n{url}"
    # Envia só pro primeiro id (você), pra não vazar pros demais autorizados.
    ok = telegram_api.send_message(chat_ids[0], texto) is not None
    if not ok:
        raise HTTPException(503, "Falha ao enviar pelo Telegram.")
    return {"ok": True, "url": url}
