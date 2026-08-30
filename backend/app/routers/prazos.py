import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.prazo import Prazo
from app.models.processo import Processo
from app.models.publicacao import Publicacao
from app.models.tarefa import Tarefa
from app.schemas.prazo import PrazoCreate, PrazoOut, PrazoUpdate
from app.services.google_calendar import criar_evento, deletar_evento
from app.services.nada_a_fazer import aplicar_status_prazo
from app.services.prazo_calc import calcular_prazo

router = APIRouter(prefix="/prazos", tags=["prazos"],
                   dependencies=[Depends(get_current_user)])


def _origem_payload(pub: Publicacao) -> dict:
    return {
        "id": pub.id,
        "fonte": pub.fonte,
        # O Recorte Digital OAB é o que entra por Gmail; o resto é Diário Oficial.
        "origem_menu": "recorte" if pub.fonte == "gmail" else "diario",
        "data_publicacao": pub.data_publicacao,
        "numero_cnj": pub.numero_cnj,
        "tribunal": pub.tribunal,
        "texto_resumo": pub.texto_resumo,
        "url_fonte": pub.url_fonte,
        "disposicao": pub.disposicao,
    }


def _recalcular(prazo: Prazo, processo: Processo, db: Session) -> None:
    data_com, data_sem = calcular_prazo(
        db=db,
        data_publicacao=prazo.data_publicacao,
        dias=prazo.dias_prazo,
        estado=processo.estado,
        tipo_contagem=prazo.tipo_contagem,
    )
    prazo.data_limite = data_com
    prazo.data_limite_sem_feriado = data_sem


@router.get("/", response_model=list[PrazoOut])
def listar_prazos(
    processo_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Prazo)
    if processo_id:
        q = q.filter(Prazo.processo_id == processo_id)
    if status:
        q = q.filter(Prazo.status == status)
    prazos = q.order_by(Prazo.data_limite.asc().nullslast()).all()

    tarefas_por_prazo: dict = {}
    for t in db.query(Tarefa).filter(Tarefa.prazo_id.in_([p.id for p in prazos])).all():
        tarefas_por_prazo.setdefault(t.prazo_id, []).append({"id": t.id, "titulo": t.titulo})

    peca_por_prazo: dict = {}
    origem_por_prazo: dict = {}
    for pub in db.query(Publicacao).filter(Publicacao.prazo_id.in_([p.id for p in prazos])).all():
        if pub.peca_doc_url:
            peca_por_prazo[pub.prazo_id] = pub.peca_doc_url
        origem_por_prazo[pub.prazo_id] = _origem_payload(pub)

    for p in prazos:
        p.tarefas_vinculadas = tarefas_por_prazo.get(p.id, [])
        p.peca_doc_url = peca_por_prazo.get(p.id)
        p.publicacao_origem = origem_por_prazo.get(p.id)

    return prazos


@router.post("/", response_model=PrazoOut, status_code=status.HTTP_201_CREATED)
def criar_prazo(data: PrazoCreate, db: Session = Depends(get_db)):
    processo = db.query(Processo).filter(Processo.id == data.processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    prazo = Prazo(**data.model_dump())
    _recalcular(prazo, processo, db)

    db.add(prazo)
    db.commit()
    db.refresh(prazo)

    # Tenta criar evento no Google Calendar (silencioso se não autenticado)
    if prazo.data_limite:
        titulo = f"[PRAZO] {prazo.tipo.upper()} — {processo.numero_cnj}"
        descricao = prazo.descricao or ""
        event_id = criar_evento(titulo, prazo.data_limite, descricao)
        if event_id:
            prazo.google_event_id = event_id
            db.commit()
            db.refresh(prazo)

    return prazo


@router.get("/{prazo_id}", response_model=PrazoOut)
def obter_prazo(prazo_id: uuid.UUID, db: Session = Depends(get_db)):
    prazo = db.query(Prazo).filter(Prazo.id == prazo_id).first()
    if not prazo:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    return prazo


@router.patch("/{prazo_id}", response_model=PrazoOut)
def atualizar_prazo(
    prazo_id: uuid.UUID, data: PrazoUpdate, db: Session = Depends(get_db)
):
    prazo = db.query(Prazo).filter(Prazo.id == prazo_id).first()
    if not prazo:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")

    alteracoes = data.model_dump(exclude_unset=True)

    novo_processo_id = alteracoes.get("processo_id")
    if novo_processo_id and novo_processo_id != prazo.processo_id:
        if not db.query(Processo).filter(Processo.id == novo_processo_id).first():
            raise HTTPException(status_code=404, detail="Processo não encontrado")

    status_anterior = prazo.status
    limite_anterior = prazo.data_limite

    for field, value in alteracoes.items():
        setattr(prazo, field, value)

    db.flush()
    processo = db.query(Processo).filter(Processo.id == prazo.processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo do prazo não encontrado")

    # dias_prazo == 0 é o marcador de "nada a fazer" sem contagem: recalcular
    # empurraria a data limite pro dia útil seguinte sem motivo nenhum.
    if prazo.dias_prazo and prazo.dias_prazo > 0:
        _recalcular(prazo, processo, db)

    novo_status = alteracoes.get("status")
    if novo_status is not None and novo_status != status_anterior:
        aplicar_status_prazo(db, prazo, novo_status)

    db.commit()
    db.refresh(prazo)

    # A data mudou — o evento no Google Calendar tem que acompanhar, senão a
    # agenda passa a mentir sobre o prazo editado.
    if prazo.data_limite and prazo.data_limite != limite_anterior:
        titulo = f"[PRAZO] {prazo.tipo.upper()} — {processo.numero_cnj}"
        event_id = criar_evento(
            titulo, prazo.data_limite, prazo.descricao or "", event_id=prazo.google_event_id
        )
        if event_id and event_id != prazo.google_event_id:
            prazo.google_event_id = event_id
            db.commit()
            db.refresh(prazo)

    pub = db.query(Publicacao).filter(Publicacao.prazo_id == prazo.id).first()
    prazo.publicacao_origem = _origem_payload(pub) if pub else None
    return prazo


@router.get("/legais")
def catalogo_prazos_legais():
    """Catálogo de prazos do CPC e dos Juizados — legenda + sugestão automática.

    Estático (não toca o banco): é texto de lei. Serve os dois usos pela mesma
    fonte de propósito — legenda e auto-preenchimento divergentes seriam pior
    do que não ter legenda.
    """
    from app.services.prazos_legais import catalogo

    return catalogo()


@router.post("/lembretes/enviar")
def disparar_lembretes(
    forcar: bool = Query(False, description="Reenvia mesmo se já foi enviado hoje"),
    db: Session = Depends(get_db),
):
    """Dispara a rodada de lembretes na hora (o scheduler roda sozinho às 07h30)."""
    from app.services.prazo_lembretes import enviar_lembretes

    return enviar_lembretes(db, forcar=forcar)


@router.delete("/{prazo_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_prazo(prazo_id: uuid.UUID, db: Session = Depends(get_db)):
    prazo = db.query(Prazo).filter(Prazo.id == prazo_id).first()
    if not prazo:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    db.delete(prazo)
    db.commit()


@router.post("/{prazo_id}/recalcular", response_model=PrazoOut)
def recalcular_prazo(prazo_id: uuid.UUID, db: Session = Depends(get_db)):
    """Força o recálculo de datas (útil após atualizar a tabela de feriados)."""
    prazo = db.query(Prazo).filter(Prazo.id == prazo_id).first()
    if not prazo:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")
    _recalcular(prazo, prazo.processo, db)
    db.commit()
    db.refresh(prazo)
    return prazo
