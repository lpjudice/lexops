"""Router do módulo "Tarefas Cards" (teste).

Card macro (estilo Diretriz) + subtarefas + funções da Tarefa. Tabelas próprias,
não compartilha registros com o módulo Tarefas atual.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, get_optional_user
from app.models.cliente import Cliente
from app.models.processo import Processo
from app.models.tarefa_card import TarefaCard, TarefaCardAnexo, TarefaCardSubtask
from app.services import tarefa_drive
from app.models.tarefa_projeto import TarefaProjeto
from app.models.usuario import Usuario
from app.schemas.tarefa_card import (
    PedidoAcessoCard,
    SolicitarAcessoCardResponse,
    SubtaskCardCreate,
    TarefaCardCreate,
    TarefaCardOut,
    TarefaCardUpdate,
)

router = APIRouter(prefix="/tarefa-cards", tags=["tarefa-cards"])


# ── Access helpers ─────────────────────────────────────────────────────────────

def _pode_ver(card: TarefaCard, usuario: Usuario | None) -> bool:
    if not card.confidencial:
        return True
    if usuario is None:
        return False
    if usuario.role == "super_admin":
        return True
    if card.criado_por_id and str(usuario.id) == str(card.criado_por_id):
        return True
    return str(usuario.id) in (card.usuarios_com_acesso or [])


def _enrich(card: TarefaCard, db: Session, usuario: Usuario | None = None) -> TarefaCardOut:
    pode_ver = _pode_ver(card, usuario)
    is_creator = usuario and card.criado_por_id and str(usuario.id) == str(card.criado_por_id)
    can_manage = usuario and (usuario.role == "super_admin" or is_creator)

    out = TarefaCardOut.model_validate(card)
    out.acesso_restrito = not pode_ver

    if not pode_ver:
        out.titulo = "Card confidencial"
        out.descricao = None
        out.notas = None
        out.responsavel = None
        out.subtasks = []
        out.anexos = []

    if card.cliente_id:
        c = db.query(Cliente).filter(Cliente.id == card.cliente_id).first()
        if c:
            out.cliente_nome = c.nome

    if card.processo_id:
        p = db.query(Processo).filter(Processo.id == card.processo_id).first()
        if p:
            out.processo_numero = p.numero_cnj

    if card.criado_por_id:
        u = db.query(Usuario).filter(Usuario.id == card.criado_por_id).first()
        if u:
            out.criado_por_nome = u.nome

    if card.projeto_id:
        pr = db.query(TarefaProjeto).filter(TarefaProjeto.id == card.projeto_id).first()
        if pr and not pr.oculto:
            out.projeto_nome = pr.nome
            out.projeto_cor = pr.cor

    if can_manage:
        pedidos: list[PedidoAcessoCard] = []
        granted: list[dict] = []
        for entry in (card.usuarios_com_acesso or []):
            if entry.startswith("req:"):
                uid_str = entry[4:]
                try:
                    req_user = db.query(Usuario).filter(Usuario.id == uuid.UUID(uid_str)).first()
                    if req_user:
                        pedidos.append(PedidoAcessoCard(usuario_id=uid_str, nome=req_user.nome))
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

    if usuario is not None:
        req_marker = f"req:{str(usuario.id)}"
        out.ja_solicitou = req_marker in (card.usuarios_com_acesso or [])

    return out


# ── CRUD ───────────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[TarefaCardOut])
def listar_cards(
    projeto_id: uuid.UUID | None = Query(None),
    cliente_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    arquivada: bool = Query(False),
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    q = db.query(TarefaCard)
    if projeto_id:
        q = q.filter(TarefaCard.projeto_id == projeto_id)
    if cliente_id:
        q = q.filter(TarefaCard.cliente_id == cliente_id)
    if status:
        q = q.filter(TarefaCard.status == status)
    q = q.filter(TarefaCard.arquivada.is_(True) if arquivada else TarefaCard.arquivada.is_(False))
    if arquivada:
        cards = q.order_by(TarefaCard.arquivada_em.desc().nullslast(), TarefaCard.updated_at.desc()).all()
    else:
        cards = q.order_by(TarefaCard.ordem.asc().nullslast(), TarefaCard.created_at.desc()).all()
    return [_enrich(c, db, usuario) for c in cards]


@router.post("/{card_id}/arquivar", response_model=TarefaCardOut)
def arquivar_card(
    card_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    from datetime import datetime, timezone
    card = db.query(TarefaCard).filter(TarefaCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado")
    if not _pode_ver(card, usuario):
        raise HTTPException(status_code=403, detail="Acesso restrito a este card")
    card.arquivada = True
    card.arquivada_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(card)
    return _enrich(card, db, usuario)


@router.post("/{card_id}/desarquivar", response_model=TarefaCardOut)
def desarquivar_card(
    card_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    card = db.query(TarefaCard).filter(TarefaCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado")
    if not _pode_ver(card, usuario):
        raise HTTPException(status_code=403, detail="Acesso restrito a este card")
    card.arquivada = False
    card.arquivada_em = None
    db.commit()
    db.refresh(card)
    return _enrich(card, db, usuario)


def _notificar_responsavel_card_async(card_id: uuid.UUID) -> None:
    """Envia o email de tarefa atribuída ao responsável, em background (mesma
    lógica do menu Tarefas), com link para /tarefas-cards."""
    import threading

    from app.database import SessionLocal
    from app.services.tarefa_email import notificar_responsavel

    def _enviar() -> None:
        _db = SessionLocal()
        try:
            _c = _db.query(TarefaCard).filter(TarefaCard.id == card_id).first()
            if _c:
                notificar_responsavel(_db, _c, dry_run=False, frontend_path="/tarefas-cards")
        finally:
            _db.close()

    threading.Thread(target=_enviar, daemon=True).start()


@router.post("/", response_model=TarefaCardOut, status_code=status.HTTP_201_CREATED)
def criar_card(
    data: TarefaCardCreate,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    payload = data.model_dump(exclude={"subtasks"})
    card = TarefaCard(**payload)
    card.codigo = tarefa_drive.gerar_codigo()
    if usuario:
        card.criado_por_id = usuario.id
    for idx, st in enumerate(data.subtasks):
        card.subtasks.append(
            TarefaCardSubtask(
                texto=st.texto, concluida=st.concluida, ordem=st.ordem or idx,
                responsavel=st.responsavel, responsavel_email=st.responsavel_email,
                data_limite=st.data_limite,
            )
        )
    db.add(card)
    db.commit()
    db.refresh(card)
    # Notifica o responsável por email se já veio definido na criação
    if card.responsavel:
        _notificar_responsavel_card_async(card.id)
    return _enrich(card, db, usuario)


@router.get("/{card_id}", response_model=TarefaCardOut)
def obter_card(
    card_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    card = db.query(TarefaCard).filter(TarefaCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado")
    return _enrich(card, db, usuario)


@router.patch("/{card_id}", response_model=TarefaCardOut)
def atualizar_card(
    card_id: uuid.UUID,
    data: TarefaCardUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    card = db.query(TarefaCard).filter(TarefaCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado")
    if not _pode_ver(card, usuario):
        raise HTTPException(status_code=403, detail="Acesso restrito a este card")

    resp_anterior = card.responsavel
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(card, field, value)
    # Se o prazo do card mudou, nenhuma subtarefa pode ter prazo maior que ele
    if "data_limite" in updates and card.data_limite:
        for st in card.subtasks:
            if st.data_limite and st.data_limite > card.data_limite:
                st.data_limite = card.data_limite
    db.commit()
    db.refresh(card)
    # Notifica se o responsável foi definido/alterado
    novo_resp = updates.get("responsavel")
    if novo_resp and novo_resp != resp_anterior:
        _notificar_responsavel_card_async(card.id)
    return _enrich(card, db, usuario)


@router.post("/reordenar", status_code=status.HTTP_204_NO_CONTENT)
def reordenar_cards(
    ids: list[str],
    db: Session = Depends(get_db),
    _usuario: Usuario | None = Depends(get_optional_user),
):
    for idx, id_str in enumerate(ids):
        try:
            cid = uuid.UUID(id_str)
        except ValueError:
            continue
        db.query(TarefaCard).filter(TarefaCard.id == cid).update({"ordem": idx})
    db.commit()


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_card(
    card_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    card = db.query(TarefaCard).filter(TarefaCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado")
    if card.confidencial:
        is_creator = usuario and card.criado_por_id and str(usuario.id) == str(card.criado_por_id)
        if not usuario or (usuario.role != "super_admin" and not is_creator):
            raise HTTPException(status_code=403, detail="Apenas o criador ou super administrador pode excluir este card")
    db.delete(card)
    db.commit()


# ── Subtasks ────────────────────────────────────────────────────────────────

@router.post("/{card_id}/subtasks", response_model=TarefaCardOut)
def add_subtask(
    card_id: uuid.UUID,
    data: SubtaskCardCreate | None = None,
    texto: str | None = Query(None),
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    card = db.query(TarefaCard).filter(TarefaCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado")
    if not _pode_ver(card, usuario):
        raise HTTPException(status_code=403, detail="Acesso restrito a este card")
    ordem = max((st.ordem for st in card.subtasks), default=-1) + 1
    if data:
        card.subtasks.append(TarefaCardSubtask(
            texto=data.texto, concluida=data.concluida, ordem=data.ordem or ordem,
            responsavel=data.responsavel, responsavel_email=data.responsavel_email,
            data_limite=data.data_limite,
        ))
    elif texto:
        card.subtasks.append(TarefaCardSubtask(texto=texto, ordem=ordem))
    else:
        raise HTTPException(status_code=422, detail="Forneça 'data' (body) ou 'texto' (query)")
    db.commit()
    db.refresh(card)
    return _enrich(card, db, usuario)


@router.patch("/subtasks/{subtask_id}", response_model=TarefaCardOut)
def toggle_subtask(
    subtask_id: uuid.UUID,
    concluida: bool | None = Query(None),
    texto: str | None = Query(None),
    data_limite: date | None = Query(None),
    limpar_data: bool = Query(False),
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    st = db.query(TarefaCardSubtask).filter(TarefaCardSubtask.id == subtask_id).first()
    if not st:
        raise HTTPException(status_code=404, detail="Subtarefa não encontrada")
    card = db.query(TarefaCard).filter(TarefaCard.id == st.card_id).first()
    if not _pode_ver(card, usuario):
        raise HTTPException(status_code=403, detail="Acesso restrito a este card")
    if concluida is not None:
        st.concluida = concluida
    if texto is not None and texto.strip():
        st.texto = texto.strip()
    if limpar_data:
        st.data_limite = None
    elif data_limite is not None:
        # Prazo interno da subtarefa nunca pode passar do prazo da tarefa macro
        if card.data_limite and data_limite > card.data_limite:
            data_limite = card.data_limite
        st.data_limite = data_limite
    db.commit()
    db.refresh(card)
    return _enrich(card, db, usuario)


@router.delete("/subtasks/{subtask_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_subtask(
    subtask_id: uuid.UUID,
    db: Session = Depends(get_db),
    _usuario: Usuario | None = Depends(get_optional_user),
):
    st = db.query(TarefaCardSubtask).filter(TarefaCardSubtask.id == subtask_id).first()
    if not st:
        raise HTTPException(status_code=404, detail="Subtarefa não encontrada")
    db.delete(st)
    db.commit()


# ── Anexos (Google Drive) ─────────────────────────────────────────────────────

def _ensure_codigo(card: TarefaCard, db: Session) -> str:
    if not card.codigo:
        card.codigo = tarefa_drive.gerar_codigo()
        db.commit()
    return card.codigo


@router.post("/{card_id}/anexos", response_model=TarefaCardOut)
async def upload_anexo_card(
    card_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    from app.services.google_drive import extrair_file_id, upload_arquivo_raiz

    card = db.query(TarefaCard).filter(TarefaCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado")
    if not _pode_ver(card, usuario):
        raise HTTPException(status_code=403, detail="Acesso restrito a este card")

    codigo = _ensure_codigo(card, db)
    conteudo = await file.read()
    nome = file.filename or "anexo"
    nome_drive = tarefa_drive.nome_arquivo_com_codigo(nome, codigo)
    subpath = tarefa_drive.pasta_card(tarefa_drive.abreviar(card.titulo), codigo)
    link = upload_arquivo_raiz(conteudo, nome_drive, subpath, mimetype=file.content_type or "application/octet-stream")
    if not link:
        raise HTTPException(status_code=503, detail="Falha ao enviar para o Google Drive (verifique a conexão)")

    anexo = TarefaCardAnexo(
        card_id=card.id, subtask_id=None, nome_arquivo=nome,
        drive_link=link, drive_file_id=extrair_file_id(link), content_type=file.content_type,
    )
    db.add(anexo)
    db.commit()
    db.refresh(card)
    return _enrich(card, db, usuario)


@router.post("/subtasks/{subtask_id}/anexos", response_model=TarefaCardOut)
async def upload_anexo_subtask(
    subtask_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    from app.services.google_drive import extrair_file_id, upload_arquivo_raiz

    st = db.query(TarefaCardSubtask).filter(TarefaCardSubtask.id == subtask_id).first()
    if not st:
        raise HTTPException(status_code=404, detail="Subtarefa não encontrada")
    card = db.query(TarefaCard).filter(TarefaCard.id == st.card_id).first()
    if not _pode_ver(card, usuario):
        raise HTTPException(status_code=403, detail="Acesso restrito a este card")

    codigo = _ensure_codigo(card, db)
    conteudo = await file.read()
    nome = file.filename or "anexo"
    nome_drive = tarefa_drive.nome_arquivo_com_codigo(nome, codigo)
    subpath = tarefa_drive.pasta_card_subtask(
        tarefa_drive.abreviar(card.titulo), codigo, tarefa_drive.abreviar(st.texto),
    )
    link = upload_arquivo_raiz(conteudo, nome_drive, subpath, mimetype=file.content_type or "application/octet-stream")
    if not link:
        raise HTTPException(status_code=503, detail="Falha ao enviar para o Google Drive (verifique a conexão)")

    anexo = TarefaCardAnexo(
        card_id=card.id, subtask_id=st.id, nome_arquivo=nome,
        drive_link=link, drive_file_id=extrair_file_id(link), content_type=file.content_type,
    )
    db.add(anexo)
    db.commit()
    db.refresh(card)
    return _enrich(card, db, usuario)


@router.delete("/anexos/{anexo_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_anexo_card(
    anexo_id: uuid.UUID,
    db: Session = Depends(get_db),
    _usuario: Usuario | None = Depends(get_optional_user),
):
    from app.services.google_drive import deletar_arquivo_por_id

    anexo = db.query(TarefaCardAnexo).filter(TarefaCardAnexo.id == anexo_id).first()
    if not anexo:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    if anexo.drive_file_id:
        deletar_arquivo_por_id(anexo.drive_file_id)  # best-effort
    db.delete(anexo)
    db.commit()


# ── Google Calendar ───────────────────────────────────────────────────────────

@router.post("/{card_id}/agendar-calendario", response_model=TarefaCardOut)
def agendar_no_calendario(
    card_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    from app.services.google_calendar import criar_evento_tarefa, google_conectado

    card = db.query(TarefaCard).filter(TarefaCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado")
    if not card.data_limite:
        raise HTTPException(status_code=400, detail="Card sem data de prazo definida")
    if not google_conectado():
        raise HTTPException(status_code=503, detail="Google Calendar não conectado")

    event_id = criar_evento_tarefa(
        titulo=card.titulo,
        data_limite=card.data_limite,
        descricao=card.descricao or "",
        event_id=card.google_event_id,
    )
    if event_id:
        card.google_event_id = event_id
        db.commit()
        db.refresh(card)
    return _enrich(card, db, usuario)


# ── Confidencialidade / controle de acesso ─────────────────────────────────────

@router.post("/{card_id}/solicitar-acesso", response_model=SolicitarAcessoCardResponse)
def solicitar_acesso(
    card_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    card = db.query(TarefaCard).filter(TarefaCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado")
    if _pode_ver(card, usuario):
        return SolicitarAcessoCardResponse(ok=True, mensagem="Você já tem acesso a este card.")

    acesso = list(card.usuarios_com_acesso or [])
    req_marker = f"req:{str(usuario.id)}"
    if req_marker not in acesso:
        acesso.append(req_marker)
        card.usuarios_com_acesso = acesso
        db.commit()

    return SolicitarAcessoCardResponse(
        ok=True,
        mensagem="Solicitação enviada. O criador do card e o administrador poderão conceder acesso.",
    )


@router.post("/{card_id}/conceder-acesso/{usuario_id}", response_model=TarefaCardOut)
def conceder_acesso(
    card_id: uuid.UUID,
    usuario_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    card = db.query(TarefaCard).filter(TarefaCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado")

    is_creator = card.criado_por_id and str(usuario.id) == str(card.criado_por_id)
    if usuario.role != "super_admin" and not is_creator:
        raise HTTPException(status_code=403, detail="Apenas o criador ou super administrador pode conceder acesso")

    alvo = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not alvo:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    acesso = list(card.usuarios_com_acesso or [])
    req_marker = f"req:{str(usuario_id)}"
    if req_marker in acesso:
        acesso.remove(req_marker)
    uid_str = str(usuario_id)
    if uid_str not in acesso:
        acesso.append(uid_str)
    card.usuarios_com_acesso = acesso
    db.commit()
    db.refresh(card)
    return _enrich(card, db, usuario)


@router.post("/{card_id}/revogar-acesso/{usuario_id}", response_model=TarefaCardOut)
def revogar_acesso(
    card_id: uuid.UUID,
    usuario_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    card = db.query(TarefaCard).filter(TarefaCard.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card não encontrado")

    is_creator = card.criado_por_id and str(usuario.id) == str(card.criado_por_id)
    if usuario.role != "super_admin" and not is_creator:
        raise HTTPException(status_code=403, detail="Apenas o criador ou super administrador pode revogar acesso")

    uid_str = str(usuario_id)
    req_marker = f"req:{uid_str}"
    card.usuarios_com_acesso = [a for a in (card.usuarios_com_acesso or []) if a not in (uid_str, req_marker)]
    db.commit()
    db.refresh(card)
    return _enrich(card, db, usuario)
