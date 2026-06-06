import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, get_optional_user
from app.models.cliente import Cliente
from app.models.tarefa import Tarefa
from app.models.usuario import Usuario
from app.schemas.tarefa import (
    PedidoAcessoTarefa,
    SolicitarAcessoTarefaResponse,
    TarefaCreate,
    TarefaOut,
    TarefaUpdate,
)

router = APIRouter(prefix="/tarefas", tags=["tarefas"])


# ── Access helpers ─────────────────────────────────────────────────────────────

def _pode_ver_tarefa(t: Tarefa, usuario: Usuario | None) -> bool:
    """Returns True if user can see full task content."""
    if not t.confidencial:
        return True
    if usuario is None:
        return False
    if usuario.role == "super_admin":
        return True
    if t.criado_por_id and str(usuario.id) == str(t.criado_por_id):
        return True
    return str(usuario.id) in (t.usuarios_com_acesso or [])


def _enrich(t: Tarefa, db: Session, usuario: Usuario | None = None) -> TarefaOut:
    pode_ver = _pode_ver_tarefa(t, usuario)
    is_creator = usuario and t.criado_por_id and str(usuario.id) == str(t.criado_por_id)
    can_manage = usuario and (usuario.role == "super_admin" or is_creator)

    out = TarefaOut.model_validate(t)
    out.acesso_restrito = not pode_ver

    if not pode_ver:
        # Mask: keep only titulo placeholder, cliente_nome, data_limite
        out.titulo = "Tarefa confidencial"
        out.descricao = None
        out.responsavel = None
        out.tags = None
        out.resumo_ia = None

    # Enrich cliente name
    if t.cliente_id:
        c = db.query(Cliente).filter(Cliente.id == t.cliente_id).first()
        if c:
            out.cliente_nome = c.nome

    # Enrich creator name
    if t.criado_por_id:
        u = db.query(Usuario).filter(Usuario.id == t.criado_por_id).first()
        if u:
            out.criado_por_nome = u.nome

    # Pending access requests for creator / super_admin
    if can_manage:
        pedidos: list[PedidoAcessoTarefa] = []
        granted: list[dict] = []
        for entry in (t.usuarios_com_acesso or []):
            if entry.startswith("req:"):
                uid_str = entry[4:]
                try:
                    req_user = db.query(Usuario).filter(Usuario.id == uuid.UUID(uid_str)).first()
                    if req_user:
                        pedidos.append(PedidoAcessoTarefa(usuario_id=uid_str, nome=req_user.nome))
                except (ValueError, TypeError):
                    pass
            else:
                try:
                    granted_user = db.query(Usuario).filter(Usuario.id == uuid.UUID(entry)).first()
                    if granted_user:
                        granted.append({"id": entry, "nome": granted_user.nome})
                except (ValueError, TypeError):
                    pass
        out.pedidos_acesso = pedidos
        out.usuarios_com_acesso_nomes = granted

    # Compute ja_solicitou for the current user
    if usuario is not None:
        req_marker = f"req:{str(usuario.id)}"
        out.ja_solicitou = req_marker in (t.usuarios_com_acesso or [])

    return out


# ── CRUD ───────────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[TarefaOut])
def listar_tarefas(
    cliente_id: uuid.UUID | None = Query(None),
    processo_id: uuid.UUID | None = Query(None),
    anotacao_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
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
    tarefas = q.order_by(Tarefa.data_limite.asc().nullslast(), Tarefa.created_at.desc()).all()
    return [_enrich(t, db, usuario) for t in tarefas]


@router.post("/", response_model=TarefaOut, status_code=status.HTTP_201_CREATED)
def criar_tarefa(
    data: TarefaCreate,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    tarefa = Tarefa(**data.model_dump())
    if usuario:
        tarefa.criado_por_id = usuario.id
    db.add(tarefa)
    db.commit()
    db.refresh(tarefa)
    return _enrich(tarefa, db, usuario)


@router.get("/{tarefa_id}", response_model=TarefaOut)
def obter_tarefa(
    tarefa_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    t = db.query(Tarefa).filter(Tarefa.id == tarefa_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return _enrich(t, db, usuario)


@router.patch("/{tarefa_id}", response_model=TarefaOut)
def atualizar_tarefa(
    tarefa_id: uuid.UUID,
    data: TarefaUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    t = db.query(Tarefa).filter(Tarefa.id == tarefa_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    if not _pode_ver_tarefa(t, usuario):
        raise HTTPException(status_code=403, detail="Acesso restrito a esta tarefa")

    # Detecta se o responsável está mudando para notificar por email
    resp_anterior = t.responsavel
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(t, field, value)
    db.commit()
    db.refresh(t)

    # Dispara email se o responsável foi definido ou alterado (em background)
    novo_resp = updates.get("responsavel")
    if novo_resp and novo_resp != resp_anterior and t.responsavel_email:
        import threading
        from app.services.tarefa_email import notificar_responsavel
        from app.database import SessionLocal

        def _enviar():
            _db = SessionLocal()
            try:
                _t = _db.query(Tarefa).filter(Tarefa.id == t.id).first()
                if _t:
                    notificar_responsavel(_db, _t, dry_run=False)
            finally:
                _db.close()

        threading.Thread(target=_enviar, daemon=True).start()

    return _enrich(t, db, usuario)


@router.delete("/{tarefa_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_tarefa(
    tarefa_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    t = db.query(Tarefa).filter(Tarefa.id == tarefa_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    # Only super_admin or creator can delete confidential tasks
    if t.confidencial:
        is_creator = usuario and t.criado_por_id and str(usuario.id) == str(t.criado_por_id)
        if not usuario or (usuario.role != "super_admin" and not is_creator):
            raise HTTPException(status_code=403, detail="Apenas o criador ou super administrador pode excluir esta tarefa")
    db.delete(t)
    db.commit()


@router.post("/{tarefa_id}/agendar-calendario", response_model=TarefaOut)
def agendar_tarefa_no_calendario(
    tarefa_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    """Cria ou atualiza evento no Google Calendar para a tarefa."""
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
    return _enrich(t, db, usuario)


# ── Confidentiality / access control ──────────────────────────────────────────

@router.post("/{tarefa_id}/solicitar-acesso", response_model=SolicitarAcessoTarefaResponse)
def solicitar_acesso(
    tarefa_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    t = db.query(Tarefa).filter(Tarefa.id == tarefa_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    if _pode_ver_tarefa(t, usuario):
        return SolicitarAcessoTarefaResponse(ok=True, mensagem="Você já tem acesso a esta tarefa.")

    acesso = list(t.usuarios_com_acesso or [])
    req_marker = f"req:{str(usuario.id)}"
    if req_marker not in acesso:
        acesso.append(req_marker)
        t.usuarios_com_acesso = acesso
        db.commit()

    return SolicitarAcessoTarefaResponse(
        ok=True,
        mensagem="Solicitação enviada. O criador da tarefa e o administrador serão notificados.",
    )


@router.post("/{tarefa_id}/conceder-acesso/{usuario_id}", response_model=TarefaOut)
def conceder_acesso(
    tarefa_id: uuid.UUID,
    usuario_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    t = db.query(Tarefa).filter(Tarefa.id == tarefa_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    is_creator = t.criado_por_id and str(usuario.id) == str(t.criado_por_id)
    if usuario.role != "super_admin" and not is_creator:
        raise HTTPException(status_code=403, detail="Apenas o criador ou super administrador pode conceder acesso")

    alvo = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not alvo:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    acesso = list(t.usuarios_com_acesso or [])
    req_marker = f"req:{str(usuario_id)}"
    if req_marker in acesso:
        acesso.remove(req_marker)
    uid_str = str(usuario_id)
    if uid_str not in acesso:
        acesso.append(uid_str)
    t.usuarios_com_acesso = acesso
    db.commit()
    db.refresh(t)
    return _enrich(t, db, usuario)


@router.post("/{tarefa_id}/revogar-acesso/{usuario_id}", response_model=TarefaOut)
def revogar_acesso(
    tarefa_id: uuid.UUID,
    usuario_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    t = db.query(Tarefa).filter(Tarefa.id == tarefa_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    is_creator = t.criado_por_id and str(usuario.id) == str(t.criado_por_id)
    if usuario.role != "super_admin" and not is_creator:
        raise HTTPException(status_code=403, detail="Apenas o criador ou super administrador pode revogar acesso")

    uid_str = str(usuario_id)
    req_marker = f"req:{uid_str}"
    t.usuarios_com_acesso = [a for a in (t.usuarios_com_acesso or []) if a not in (uid_str, req_marker)]
    db.commit()
    db.refresh(t)
    return _enrich(t, db, usuario)
