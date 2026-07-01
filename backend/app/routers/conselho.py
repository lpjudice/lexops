import uuid
from datetime import date, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.conselho import (
    ConselhoAnexo,
    ConselhoContato,
    ConselhoContatoNota,
    ConselhoDiretriz,
    ConselhoDiretrizSubtask,
    ConselhoEvento,
    ConselhoEventoConvidado,
    ConselhoLog,
    ConselhoParceiro,
    ConselhoPipeline,
)
from app.models.usuario import Usuario
from app.schemas.conselho import (
    AnexoLibOut,
    ContatoCreate,
    ContatoNotaCreate,
    ContatoNotaOut,
    ContatoOut,
    ContatoUpdate,
    ConvidadoAdd,
    ConvidadoOut,
    ConvidadoUpdate,
    DiretrizCreate,
    DiretrizOut,
    DiretrizUpdate,
    DispararEmailRequest,
    DispararEmailResponse,
    DisparoResultadoItem,
    EventoCreate,
    EventoOut,
    EventoUpdate,
    LogCreate,
    LogOut,
    MelhorarIARequest,
    MelhorarIAResponse,
    MetricasOut,
    ParceiroCreate,
    ParceiroOut,
    ParceiroUpdate,
    PipelineCreate,
    PipelineOut,
    PipelineUpdate,
)

router = APIRouter(prefix="/conselho", tags=["conselho"])

UPLOADS_DIR = Path("/app/uploads/conselho/anexos")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


# ── Diretrizes ────────────────────────────────────────────────────────────

@router.get("/diretrizes", response_model=list[DiretrizOut])
def listar_diretrizes(
    categoria: str | None = Query(None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    q = db.query(ConselhoDiretriz).options(
        selectinload(ConselhoDiretriz.subtasks), selectinload(ConselhoDiretriz.anexos)
    )
    if categoria:
        q = q.filter(ConselhoDiretriz.categoria == categoria)
    return q.order_by(ConselhoDiretriz.created_at.desc()).all()


@router.post("/diretrizes", response_model=DiretrizOut, status_code=status.HTTP_201_CREATED)
def criar_diretriz(
    data: DiretrizCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    payload = data.model_dump(exclude={"subtasks"})
    diretriz = ConselhoDiretriz(**payload)
    db.add(diretriz)
    db.flush()
    for i, st in enumerate(data.subtasks):
        db.add(ConselhoDiretrizSubtask(diretriz_id=diretriz.id, texto=st.texto, concluida=st.concluida, ordem=st.ordem or i))
    db.commit()
    db.refresh(diretriz)
    return diretriz


@router.patch("/diretrizes/{diretriz_id}", response_model=DiretrizOut)
def atualizar_diretriz(
    diretriz_id: uuid.UUID,
    data: DiretrizUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    d = db.query(ConselhoDiretriz).filter(ConselhoDiretriz.id == diretriz_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Diretriz não encontrada")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(d, field, value)
    db.commit()
    db.refresh(d)
    return d


@router.delete("/diretrizes/{diretriz_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_diretriz(
    diretriz_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    d = db.query(ConselhoDiretriz).filter(ConselhoDiretriz.id == diretriz_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Diretriz não encontrada")
    db.delete(d)
    db.commit()


@router.post("/diretrizes/{diretriz_id}/subtasks", response_model=DiretrizOut)
def add_subtask(
    diretriz_id: uuid.UUID,
    texto: str = Query(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    d = db.query(ConselhoDiretriz).filter(ConselhoDiretriz.id == diretriz_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Diretriz não encontrada")
    ordem = len(d.subtasks)
    db.add(ConselhoDiretrizSubtask(diretriz_id=d.id, texto=texto, ordem=ordem))
    db.commit()
    db.refresh(d)
    return d


@router.patch("/diretrizes/subtasks/{subtask_id}", response_model=DiretrizOut)
def toggle_subtask(
    subtask_id: uuid.UUID,
    concluida: bool | None = Query(None),
    texto: str | None = Query(None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    st = db.query(ConselhoDiretrizSubtask).filter(ConselhoDiretrizSubtask.id == subtask_id).first()
    if not st:
        raise HTTPException(status_code=404, detail="Subtask não encontrada")
    if concluida is not None:
        st.concluida = concluida
    if texto is not None and texto.strip():
        st.texto = texto.strip()
    db.commit()
    d = db.query(ConselhoDiretriz).filter(ConselhoDiretriz.id == st.diretriz_id).first()
    db.refresh(d)
    return d


@router.delete("/diretrizes/subtasks/{subtask_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_subtask(
    subtask_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    st = db.query(ConselhoDiretrizSubtask).filter(ConselhoDiretrizSubtask.id == subtask_id).first()
    if not st:
        raise HTTPException(status_code=404, detail="Subtask não encontrada")
    db.delete(st)
    db.commit()


# ── Pipeline ──────────────────────────────────────────────────────────────

@router.get("/pipeline", response_model=list[PipelineOut])
def listar_pipeline(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    return db.query(ConselhoPipeline).order_by(ConselhoPipeline.created_at.desc()).all()


@router.post("/pipeline", response_model=PipelineOut, status_code=status.HTTP_201_CREATED)
def criar_pipeline(
    data: PipelineCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    p = ConselhoPipeline(**data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.patch("/pipeline/{pipeline_id}", response_model=PipelineOut)
def atualizar_pipeline(
    pipeline_id: uuid.UUID,
    data: PipelineUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    p = db.query(ConselhoPipeline).filter(ConselhoPipeline.id == pipeline_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/pipeline/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_pipeline(
    pipeline_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    p = db.query(ConselhoPipeline).filter(ConselhoPipeline.id == pipeline_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada")
    db.delete(p)
    db.commit()


# ── Contatos ──────────────────────────────────────────────────────────────

def _contato_out(c: ConselhoContato, db: Session) -> ContatoOut:
    out = ContatoOut.model_validate(c)
    nomes_evento: dict[str, str] = {}
    convidados = db.query(ConselhoEventoConvidado).filter(ConselhoEventoConvidado.contato_id == c.id).all()
    for cv in convidados:
        ev = db.query(ConselhoEvento).filter(ConselhoEvento.id == cv.evento_id).first()
        if ev:
            nomes_evento[str(ev.id)] = ev.nome
    out.eventos = list(nomes_evento.values())
    notas_out = []
    for n in c.notas:
        no = ContatoNotaOut.model_validate(n)
        if n.evento_id:
            ev = db.query(ConselhoEvento).filter(ConselhoEvento.id == n.evento_id).first()
            no.evento_nome = ev.nome if ev else None
        notas_out.append(no)
    out.notas = notas_out
    return out


@router.get("/contatos", response_model=list[ContatoOut])
def listar_contatos(
    evento_id: uuid.UUID | None = Query(None),
    presenca_confirmada: bool | None = Query(None),
    participacao_confirmada: bool | None = Query(None),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    if evento_id or presenca_confirmada is not None or participacao_confirmada is not None:
        q = db.query(ConselhoEventoConvidado).join(ConselhoContato)
        if evento_id:
            q = q.filter(ConselhoEventoConvidado.evento_id == evento_id)
        if presenca_confirmada is not None:
            q = q.filter(ConselhoEventoConvidado.presenca_confirmada == presenca_confirmada)
        if participacao_confirmada is not None:
            q = q.filter(ConselhoEventoConvidado.participacao_confirmada == participacao_confirmada)
        contato_ids = {cv.contato_id for cv in q.all()}
        contatos = db.query(ConselhoContato).filter(ConselhoContato.id.in_(contato_ids)).all() if contato_ids else []
    else:
        contatos = db.query(ConselhoContato).order_by(ConselhoContato.primeiro_nome).all()
    return [_contato_out(c, db) for c in contatos]


@router.get("/contatos/buscar", response_model=list[ContatoOut])
def buscar_contatos(
    q: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    termo = f"%{q}%"
    contatos = (
        db.query(ConselhoContato)
        .filter(
            (ConselhoContato.primeiro_nome.ilike(termo))
            | (ConselhoContato.sobrenome.ilike(termo))
            | (ConselhoContato.email.ilike(termo))
            | (ConselhoContato.whatsapp.ilike(termo))
        )
        .order_by(ConselhoContato.primeiro_nome)
        .limit(20)
        .all()
    )
    return [_contato_out(c, db) for c in contatos]


@router.post("/contatos", response_model=ContatoOut, status_code=status.HTTP_201_CREATED)
def criar_contato(
    data: ContatoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    payload = data.model_dump(exclude={"evento_id"})
    contato = ConselhoContato(**payload)
    db.add(contato)
    db.flush()
    if data.evento_id:
        evento = db.query(ConselhoEvento).filter(ConselhoEvento.id == data.evento_id).first()
        if not evento:
            raise HTTPException(status_code=404, detail="Evento não encontrado")
        db.add(ConselhoEventoConvidado(evento_id=data.evento_id, contato_id=contato.id))
    db.commit()
    db.refresh(contato)
    return _contato_out(contato, db)


@router.patch("/contatos/{contato_id}", response_model=ContatoOut)
def atualizar_contato(
    contato_id: uuid.UUID,
    data: ContatoUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    c = db.query(ConselhoContato).filter(ConselhoContato.id == contato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contato não encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(c, field, value)
    db.commit()
    db.refresh(c)
    return _contato_out(c, db)


@router.delete("/contatos/{contato_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_contato(
    contato_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    c = db.query(ConselhoContato).filter(ConselhoContato.id == contato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contato não encontrado")
    db.delete(c)
    db.commit()


@router.delete("/contatos/notas/{nota_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_nota_contato(
    nota_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Usuario = Depends(get_current_user),
):
    nota = db.query(ConselhoContatoNota).filter(ConselhoContatoNota.id == nota_id).first()
    if not nota:
        raise HTTPException(status_code=404, detail="Nota não encontrada")
    db.delete(nota)
    db.commit()


@router.post("/contatos/{contato_id}/notas", response_model=ContatoOut)
def add_nota_contato(
    contato_id: uuid.UUID,
    data: ContatoNotaCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    c = db.query(ConselhoContato).filter(ConselhoContato.id == contato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contato não encontrado")
    db.add(ConselhoContatoNota(contato_id=contato_id, evento_id=data.evento_id, texto=data.texto, data=data.data or date.today()))
    db.commit()
    db.refresh(c)
    return _contato_out(c, db)


# ── Eventos ───────────────────────────────────────────────────────────────

@router.get("/eventos", response_model=list[EventoOut])
def listar_eventos(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    eventos = (
        db.query(ConselhoEvento)
        .options(selectinload(ConselhoEvento.convidados).selectinload(ConselhoEventoConvidado.contato))
        .order_by(ConselhoEvento.data.desc().nullslast(), ConselhoEvento.created_at.desc())
        .all()
    )
    return eventos


@router.post("/eventos", response_model=EventoOut, status_code=status.HTTP_201_CREATED)
def criar_evento(
    data: EventoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    evento = ConselhoEvento(**data.model_dump())
    db.add(evento)
    db.commit()
    db.refresh(evento)
    return evento


@router.get("/eventos/{evento_id}", response_model=EventoOut)
def obter_evento(
    evento_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    evento = (
        db.query(ConselhoEvento)
        .options(selectinload(ConselhoEvento.convidados).selectinload(ConselhoEventoConvidado.contato))
        .filter(ConselhoEvento.id == evento_id)
        .first()
    )
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return evento


@router.patch("/eventos/{evento_id}", response_model=EventoOut)
def atualizar_evento(
    evento_id: uuid.UUID,
    data: EventoUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    evento = db.query(ConselhoEvento).filter(ConselhoEvento.id == evento_id).first()
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(evento, field, value)
    db.commit()
    db.refresh(evento)
    return evento


@router.delete("/eventos/{evento_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_evento(
    evento_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    evento = db.query(ConselhoEvento).filter(ConselhoEvento.id == evento_id).first()
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    db.delete(evento)
    db.commit()


@router.post("/eventos/{evento_id}/convidados", response_model=EventoOut)
def add_convidado(
    evento_id: uuid.UUID,
    data: ConvidadoAdd,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    evento = db.query(ConselhoEvento).filter(ConselhoEvento.id == evento_id).first()
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    contato = db.query(ConselhoContato).filter(ConselhoContato.id == data.contato_id).first()
    if not contato:
        raise HTTPException(status_code=404, detail="Contato não encontrado")
    existente = (
        db.query(ConselhoEventoConvidado)
        .filter(ConselhoEventoConvidado.evento_id == evento_id, ConselhoEventoConvidado.contato_id == data.contato_id)
        .first()
    )
    if not existente:
        db.add(ConselhoEventoConvidado(evento_id=evento_id, contato_id=data.contato_id))
        db.commit()
    db.refresh(evento)
    return evento


@router.patch("/eventos/convidados/{convidado_id}", response_model=ConvidadoOut)
def atualizar_convidado(
    convidado_id: uuid.UUID,
    data: ConvidadoUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    from app.models.tarefa import Tarefa

    cv = db.query(ConselhoEventoConvidado).filter(ConselhoEventoConvidado.id == convidado_id).first()
    if not cv:
        raise HTTPException(status_code=404, detail="Convidado não encontrado")

    followup_anterior = cv.followup_data
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(cv, field, value)

    # Cria tarefa para Monielly quando followup_data é definida pela primeira vez
    nova_followup = updates.get("followup_data")
    if nova_followup and nova_followup != followup_anterior:
        evento = db.query(ConselhoEvento).filter(ConselhoEvento.id == cv.evento_id).first()
        contato = cv.contato
        nome_contato = f"{contato.primeiro_nome} {contato.sobrenome or ''}".strip()
        nome_evento = evento.nome if evento else "evento"
        obs = cv.pendente_obs or updates.get("pendente_obs") or ""
        tarefa = Tarefa(
            titulo=f"Follow-up: {nome_contato} – {nome_evento}",
            descricao=obs or None,
            responsavel="Monielly",
            data_limite=nova_followup,
            status="pendente",
            criado_por_id=usuario.id,
        )
        db.add(tarefa)

    db.commit()
    db.refresh(cv)
    return cv


@router.delete("/eventos/convidados/{convidado_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_convidado(
    convidado_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    cv = db.query(ConselhoEventoConvidado).filter(ConselhoEventoConvidado.id == convidado_id).first()
    if not cv:
        raise HTTPException(status_code=404, detail="Convidado não encontrado")
    db.delete(cv)
    db.commit()


# ── Parceiros ─────────────────────────────────────────────────────────────

@router.get("/parceiros", response_model=list[ParceiroOut])
def listar_parceiros(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    return db.query(ConselhoParceiro).order_by(ConselhoParceiro.created_at.desc()).all()


@router.post("/parceiros", response_model=ParceiroOut, status_code=status.HTTP_201_CREATED)
def criar_parceiro(
    data: ParceiroCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    p = ConselhoParceiro(**data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.patch("/parceiros/{parceiro_id}", response_model=ParceiroOut)
def atualizar_parceiro(
    parceiro_id: uuid.UUID,
    data: ParceiroUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    p = db.query(ConselhoParceiro).filter(ConselhoParceiro.id == parceiro_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Parceiro não encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/parceiros/{parceiro_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_parceiro(
    parceiro_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    p = db.query(ConselhoParceiro).filter(ConselhoParceiro.id == parceiro_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Parceiro não encontrado")
    db.delete(p)
    db.commit()


# ── Logs / Métricas ───────────────────────────────────────────────────────

@router.get("/logs", response_model=list[LogOut])
def listar_logs(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    return db.query(ConselhoLog).order_by(ConselhoLog.data.desc()).all()


@router.post("/logs", response_model=LogOut, status_code=status.HTTP_201_CREATED)
def criar_log(
    data: LogCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    log = ConselhoLog(**data.model_dump())
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.delete("/logs/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_log(
    log_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    log = db.query(ConselhoLog).filter(ConselhoLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Registro não encontrado")
    db.delete(log)
    db.commit()


@router.get("/metricas", response_model=MetricasOut)
def obter_metricas(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    sete_dias_atras = date.today() - timedelta(days=7)
    logs_7d = db.query(ConselhoLog).filter(ConselhoLog.data >= sete_dias_atras).all()
    media_logs_7d = (sum(float(l.numero) for l in logs_7d) / len(logs_7d)) if logs_7d else 0.0

    total_contatos = db.query(ConselhoContato).count()

    convidados = db.query(ConselhoEventoConvidado).all()
    por_contato: dict[uuid.UUID, list[ConselhoEventoConvidado]] = {}
    for cv in convidados:
        por_contato.setdefault(cv.contato_id, []).append(cv)

    participaram = sum(1 for cvs in por_contato.values() if any(c.participacao_confirmada for c in cvs))
    reconvidados = sum(1 for cvs in por_contato.values() if len(cvs) >= 2)
    reiterados = sum(1 for cvs in por_contato.values() if sum(1 for c in cvs if c.participacao_confirmada) >= 2)

    return MetricasOut(
        media_logs_7d=round(media_logs_7d, 2),
        total_contatos=total_contatos,
        contatos_participaram_ao_menos_uma_vez=participaram,
        contatos_reconvidados=reconvidados,
        contatos_reiterados=reiterados,
    )


# ── IA ────────────────────────────────────────────────────────────────────

@router.post("/ia/melhorar", response_model=MelhorarIAResponse)
def melhorar_ia(
    data: MelhorarIARequest,
    usuario: Usuario = Depends(get_current_user),
):
    from app.services.ia_conselho import melhorar_texto

    return MelhorarIAResponse(texto=melhorar_texto(data.campo, data.texto))


# ── Anexos (biblioteca do módulo) ──────────────────────────────────────────

@router.get("/anexos", response_model=list[AnexoLibOut])
def listar_anexos(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    return db.query(ConselhoAnexo).order_by(ConselhoAnexo.created_at.desc()).all()


@router.post("/anexos", response_model=AnexoLibOut, status_code=status.HTTP_201_CREATED)
async def upload_anexo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    if (file.content_type or "") != "application/pdf" and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Apenas arquivos PDF são suportados")
    conteudo = await file.read()
    nome_arquivo = file.filename or "anexo.pdf"
    destino = UPLOADS_DIR / f"{uuid.uuid4()}_{nome_arquivo}"
    destino.write_bytes(conteudo)
    anexo = ConselhoAnexo(nome_arquivo=nome_arquivo, storage_path=str(destino), content_type=file.content_type)
    db.add(anexo)
    db.commit()
    db.refresh(anexo)
    return anexo


@router.delete("/anexos/{anexo_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_anexo(
    anexo_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    anexo = db.query(ConselhoAnexo).filter(ConselhoAnexo.id == anexo_id).first()
    if not anexo:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    try:
        Path(anexo.storage_path).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(anexo)
    db.commit()


# ── Disparo de e-mail ───────────────────────────────────────────────────────

def _aplicar_placeholders(template: str, primeiro: str, ultimo: str, evento: str) -> str:
    return (
        template.replace("{primeiro}", primeiro)
        .replace("{ultimo}", ultimo or "")
        .replace("{evento}", evento or "")
    )


@router.post("/disparar-email", response_model=DispararEmailResponse)
def disparar_email(
    data: DispararEmailRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    from app.services.gmail_conselho import enviar_email

    pdf_bytes: bytes | None = None
    pdf_filename: str | None = None
    if data.anexo_id:
        anexo = db.query(ConselhoAnexo).filter(ConselhoAnexo.id == data.anexo_id).first()
        if not anexo:
            raise HTTPException(status_code=404, detail="Anexo não encontrado")
        try:
            pdf_bytes = Path(anexo.storage_path).read_bytes()
            pdf_filename = anexo.nome_arquivo
        except Exception:
            raise HTTPException(status_code=500, detail="Não foi possível ler o anexo")

    contatos: dict[uuid.UUID, ConselhoContato] = {}
    for dest in data.destinatarios:
        if dest.contato_id not in contatos:
            c = db.query(ConselhoContato).filter(ConselhoContato.id == dest.contato_id).first()
            if c:
                contatos[dest.contato_id] = c

    resultados: list[DisparoResultadoItem] = []
    enviado_por = ""

    if data.modo == "bcc_unico":
        emails = [contatos[d.contato_id].email for d in data.destinatarios if contatos.get(d.contato_id) and contatos[d.contato_id].email]
        if not emails:
            raise HTTPException(status_code=400, detail="Nenhum destinatário com e-mail")
        corpo_generico = (
            data.corpo_template.replace("{primeiro}", "").replace("{ultimo}", "").replace("{evento}", data.evento_nome or "")
        )
        try:
            enviado_por = enviar_email(
                usuario, db,
                to=emails[0],
                subject=data.assunto,
                html=corpo_generico.replace("\n", "<br>"),
                pdf_bytes=pdf_bytes,
                pdf_filename=pdf_filename,
                bcc=emails[1:] if len(emails) > 1 else None,
            )
            for d in data.destinatarios:
                c = contatos.get(d.contato_id)
                if c:
                    resultados.append(DisparoResultadoItem(contato_id=d.contato_id, nome=c.primeiro_nome, email=c.email, sucesso=True))
        except Exception as exc:
            for d in data.destinatarios:
                c = contatos.get(d.contato_id)
                resultados.append(DisparoResultadoItem(
                    contato_id=d.contato_id, nome=c.primeiro_nome if c else "?", email=c.email if c else None,
                    sucesso=False, erro=str(exc),
                ))
    else:
        for dest in data.destinatarios:
            c = contatos.get(dest.contato_id)
            if not c:
                resultados.append(DisparoResultadoItem(contato_id=dest.contato_id, nome="?", email=None, sucesso=False, erro="Contato não encontrado"))
                continue
            if not c.email:
                resultados.append(DisparoResultadoItem(contato_id=c.id, nome=c.primeiro_nome, email=None, sucesso=False, erro="Contato sem e-mail"))
                continue
            corpo = _aplicar_placeholders(data.corpo_template, c.primeiro_nome, c.sobrenome or "", data.evento_nome or "")
            try:
                enviado_por = enviar_email(
                    usuario, db,
                    to=c.email,
                    subject=data.assunto,
                    html=corpo.replace("\n", "<br>"),
                    pdf_bytes=pdf_bytes,
                    pdf_filename=pdf_filename,
                )
                resultados.append(DisparoResultadoItem(contato_id=c.id, nome=c.primeiro_nome, email=c.email, sucesso=True))
            except Exception as exc:
                resultados.append(DisparoResultadoItem(contato_id=c.id, nome=c.primeiro_nome, email=c.email, sucesso=False, erro=str(exc)))

    return DispararEmailResponse(enviado_por=enviado_por or "—", resultados=resultados)
