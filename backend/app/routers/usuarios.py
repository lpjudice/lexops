import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.responsavel import Responsavel
from app.models.usuario import Usuario
from app.schemas.usuario import (
    AcceptInviteRequest,
    LoginRequest,
    TokenResponse,
    UserClienteLink,
    UsuarioCreate,
    UsuarioOut,
    UsuarioUpdate,
)
from app.services.auth_service import criar_token, hash_senha, verificar_senha

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


def _sync_responsavel(db: Session, u: Usuario) -> None:
    """Todo usuário do sistema é também um Responsável (submenu Usuários →
    Responsáveis). Mantém nome/email/ativo em dia com o cadastro."""
    resp = db.query(Responsavel).filter(Responsavel.usuario_id == u.id).first()
    if resp:
        resp.nome = u.nome
        resp.email = u.email
        resp.ativo = u.ativo
    else:
        db.add(Responsavel(nome=u.nome, email=u.email, usuario_id=u.id, categoria="colaborador", ativo=u.ativo))
    db.commit()


def _usuario_to_out(u: Usuario, db: Session) -> UsuarioOut:
    rows = db.execute(
        text("SELECT cliente_id FROM user_clientes WHERE usuario_id = :uid"),
        {"uid": u.id},
    ).fetchall()
    out = UsuarioOut.model_validate(u)
    out.clientes_ids = [r.cliente_id for r in rows]
    if isinstance(u.google_tokens, dict):
        out.google_email = u.google_tokens.get("email")
    if isinstance(u.google_tokens_extra, dict):
        out.google_email_extra = u.google_tokens_extra.get("email")
    return out


# ── Auth ──────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.email == body.email.lower()).first()
    if not usuario or not usuario.senha_hash or not verificar_senha(body.senha, usuario.senha_hash):
        raise HTTPException(status_code=401, detail="Email ou senha incorretos")
    if not usuario.ativo:
        raise HTTPException(status_code=403, detail="Conta ainda não ativada — verifique seu email de convite")
    token = criar_token(usuario.id, usuario.email, usuario.role)
    return TokenResponse(access_token=token, usuario=_usuario_to_out(usuario, db))


@router.get("/me")
def me_via_token(token: str, db: Session = Depends(get_db)):
    from jose import JWTError
    from app.services.auth_service import decodificar_token
    try:
        payload = decodificar_token(token)
        uid = uuid.UUID(payload["sub"])
    except (JWTError, Exception):
        raise HTTPException(status_code=401, detail="Token inválido")
    usuario = db.query(Usuario).filter(Usuario.id == uid).first()
    if not usuario or not usuario.ativo:
        raise HTTPException(status_code=401, detail="Usuário não encontrado ou desativado")
    return _usuario_to_out(usuario, db)


# ── Magic link — accept invite ────────────────────────────────────────────────

@router.get("/aceitar-convite/{token}")
def validar_token_convite(token: str, db: Session = Depends(get_db)):
    """Validate invite token and return user info for the accept-invite page."""
    u = db.query(Usuario).filter(Usuario.invite_token == token).first()
    now = datetime.now(timezone.utc)
    if not u or not u.invite_token_expires or u.invite_token_expires < now:
        raise HTTPException(status_code=404, detail="Link inválido ou expirado")
    return {"nome": u.nome, "email": u.email}


@router.post("/aceitar-convite/{token}", response_model=TokenResponse)
def aceitar_convite(token: str, body: AcceptInviteRequest, db: Session = Depends(get_db)):
    """Accept invite: set password, activate account."""
    u = db.query(Usuario).filter(Usuario.invite_token == token).first()
    now = datetime.now(timezone.utc)
    if not u or not u.invite_token_expires or u.invite_token_expires < now:
        raise HTTPException(status_code=404, detail="Link inválido ou expirado")
    if len(body.senha) < 8:
        raise HTTPException(status_code=422, detail="A senha deve ter pelo menos 8 caracteres")
    u.senha_hash = hash_senha(body.senha)
    u.ativo = True
    u.invite_token = None
    u.invite_token_expires = None
    u.primeiro_acesso = True
    db.commit()
    db.refresh(u)
    _sync_responsavel(db, u)
    jwt_token = criar_token(u.id, u.email, u.role)
    return TokenResponse(access_token=jwt_token, usuario=_usuario_to_out(u, db))


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[UsuarioOut])
def listar_usuarios(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return [_usuario_to_out(u, db) for u in db.query(Usuario).order_by(Usuario.nome).all()]


@router.post("/", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def criar_usuario(data: UsuarioCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if db.query(Usuario).filter(Usuario.email == data.email.lower()).first():
        raise HTTPException(status_code=409, detail="Email já cadastrado")

    invite_token = secrets.token_urlsafe(32)
    invite_expires = datetime.now(timezone.utc) + timedelta(hours=48)

    u = Usuario(
        email=data.email.lower(),
        nome=data.nome,
        senha_hash=None,
        role=data.role,
        ativo=False,  # activated on invite acceptance
        pode_ver_financeiro=data.pode_ver_financeiro,
        pode_ver_contratos=data.pode_ver_contratos,
        pode_ver_tarefas_outros=data.pode_ver_tarefas_outros,
        clientes_restritos=data.clientes_restritos,
        invite_token=invite_token,
        invite_token_expires=invite_expires,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    _sync_responsavel(db, u)

    invite_url = f"{settings.frontend_url}/aceitar-convite/{invite_token}"

    # Find who's inviting (super admin name or fallback)
    super_admin = db.query(Usuario).filter(Usuario.role == "super_admin").first()
    inviter_name = super_admin.nome if super_admin else "Pimenta Judice"

    background_tasks.add_task(_send_invite, to_email=u.email, invite_url=invite_url, inviter_name=inviter_name)

    return _usuario_to_out(u, db)


def _send_invite(to_email: str, invite_url: str, inviter_name: str) -> None:
    import asyncio
    from app.services.email_service import send_invite_email
    try:
        asyncio.run(send_invite_email(to_email=to_email, invite_url=invite_url, inviter_name=inviter_name))
    except Exception as exc:
        print(f"[CONVITE] Erro ao enviar email para {to_email}: {exc}", flush=True)


@router.patch("/{usuario_id}", response_model=UsuarioOut)
def atualizar_usuario(usuario_id: uuid.UUID, data: UsuarioUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    u = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "senha" and value:
            u.senha_hash = hash_senha(value)
        elif field != "senha":
            setattr(u, field, value)
    db.commit()
    db.refresh(u)
    _sync_responsavel(db, u)
    return _usuario_to_out(u, db)


@router.post("/{usuario_id}/reenviar-convite", status_code=status.HTTP_204_NO_CONTENT)
def reenviar_convite(usuario_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db), _=Depends(get_current_user)):
    u = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if u.ativo:
        raise HTTPException(status_code=400, detail="Usuário já ativo")

    invite_token = secrets.token_urlsafe(32)
    invite_expires = datetime.now(timezone.utc) + timedelta(hours=48)
    u.invite_token = invite_token
    u.invite_token_expires = invite_expires
    db.commit()

    invite_url = f"{settings.frontend_url}/aceitar-convite/{invite_token}"
    super_admin = db.query(Usuario).filter(Usuario.role == "super_admin").first()
    inviter_name = super_admin.nome if super_admin else "Pimenta Judice"

    background_tasks.add_task(_send_invite, to_email=u.email, invite_url=invite_url, inviter_name=inviter_name)


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_usuario(usuario_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(get_current_user)):
    u = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    if u.role == "super_admin":
        raise HTTPException(status_code=403, detail="Não é possível remover o Super Admin")
    db.delete(u)
    db.commit()


@router.post("/{usuario_id}/clientes", status_code=status.HTTP_204_NO_CONTENT)
def vincular_cliente(usuario_id: uuid.UUID, body: UserClienteLink, db: Session = Depends(get_db), _=Depends(get_current_user)):
    u = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")
    db.execute(
        text("INSERT INTO user_clientes (usuario_id, cliente_id) VALUES (:uid, :cid) ON CONFLICT DO NOTHING"),
        {"uid": usuario_id, "cid": body.cliente_id},
    )
    db.commit()


@router.delete("/{usuario_id}/clientes/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def desvincular_cliente(usuario_id: uuid.UUID, cliente_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(get_current_user)):
    db.execute(
        text("DELETE FROM user_clientes WHERE usuario_id = :uid AND cliente_id = :cid"),
        {"uid": usuario_id, "cid": cliente_id},
    )
    db.commit()
