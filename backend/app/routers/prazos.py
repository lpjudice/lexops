import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.prazo import Prazo
from app.models.processo import Processo
from app.models.publicacao import Publicacao
from app.models.tarefa import Tarefa
from app.schemas.prazo import PrazoCreate, PrazoOut, PrazoUpdate
from app.services.google_calendar import criar_evento, deletar_evento
from app.services.prazo_calc import calcular_prazo

router = APIRouter(prefix="/prazos", tags=["prazos"],
                   dependencies=[Depends(get_current_user)])


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


_TIPO_LABEL = {
    "contestacao": "Contestação",
    "recurso": "Recurso",
    "contrarrazoes": "Contrarrazões",
    "manifestacao": "Manifestação",
    "audiencia": "Audiência",
    "pericia": "Perícia",
    "outro": "Prazo",
}

def _montar_evento(db: Session, prazo: Prazo, processo: Processo) -> tuple[str, str]:
    """Monta (título, descrição) do evento com o que existir no banco.

    Cada linha some quando o dado não existe — nada de "Vara: None".
    """
    cliente_nome = processo.cliente.nome if processo.cliente else None
    parte_contraria = processo.parte_contraria
    tipo_label = _TIPO_LABEL.get(prazo.tipo, prazo.tipo.capitalize())

    # Título curto de propósito: o Google trunca por volta de 30 caracteres
    # na visão de mês, então o CNJ fica no corpo.
    partes_titulo = " x ".join(x for x in (cliente_nome, parte_contraria) if x)
    titulo = f"[PRAZO] {tipo_label}"
    if partes_titulo:
        titulo += f" — {partes_titulo}"

    linhas: list[str] = []
    if cliente_nome:
        papel = f" ({processo.polo})" if processo.polo else ""
        linhas.append(f"Cliente: {cliente_nome}{papel}")
    if parte_contraria:
        linhas.append(f"Parte contrária: {parte_contraria}")
    linhas.append(f"Processo: {processo.numero_cnj}")

    foro = " — ".join(x for x in (processo.vara, processo.comarca) if x)
    if processo.estado and foro:
        foro += f"/{processo.estado}"
    if foro:
        linhas.append(f"Vara: {foro}")
    if processo.materia:
        linhas.append(f"Matéria: {processo.materia}")

    peca_resp = " · ".join(
        x for x in (
            f"Peça: {prazo.peca_necessaria}" if prazo.peca_necessaria else None,
            f"Responsável: {prazo.responsavel}" if prazo.responsavel else None,
        ) if x
    )
    if peca_resp:
        linhas.append(peca_resp)

    contagem = "úteis" if prazo.tipo_contagem == "uteis" else "corridos"
    linhas.append(
        f"Prazo: {prazo.dias_prazo} dias {contagem} a partir de "
        f"{prazo.data_publicacao.strftime('%d/%m/%Y')}"
    )

    if prazo.descricao:
        linhas.append(f"\nNotas: {prazo.descricao}")

    pub = (
        db.query(Publicacao)
        .filter(Publicacao.prazo_id == prazo.id)
        .order_by(Publicacao.data_publicacao.desc())
        .first()
    )
    if pub:
        if pub.texto_resumo:
            resumo = pub.texto_resumo.strip()
            if len(resumo) > 1500:
                resumo = resumo[:1500] + "…"
            linhas.append(f"\nPublicação: {resumo}")
        if pub.peca_doc_url:
            linhas.append(f"Documento: {pub.peca_doc_url}")

    linhas.append(f"\nAbrir no LexOps: {settings.frontend_url}/prazos")
    return titulo, "\n".join(linhas)


def _sincronizar_evento(db: Session, prazo: Prazo, processo: Processo) -> bool:
    """Cria ou atualiza o evento do prazo no Google Calendar.

    Silencioso: qualquer falha (sem autenticação, rede fora, evento apagado
    na mão) é ignorada — o prazo continua salvo no banco.
    Retorna True se o google_event_id mudou (chamador precisa dar commit).
    """
    if not prazo.data_limite:
        return False

    try:
        titulo, descricao = _montar_evento(db, prazo, processo)
        event_id = criar_evento(
            titulo,
            prazo.data_limite,
            descricao,
            prazo.google_event_id,
        )
    except Exception:
        return False

    if event_id and event_id != prazo.google_event_id:
        prazo.google_event_id = event_id
        return True
    return False


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
    for pub in db.query(Publicacao).filter(Publicacao.prazo_id.in_([p.id for p in prazos]), Publicacao.peca_doc_url.isnot(None)).all():
        peca_por_prazo[pub.prazo_id] = pub.peca_doc_url

    for p in prazos:
        p.tarefas_vinculadas = tarefas_por_prazo.get(p.id, [])
        p.peca_doc_url = peca_por_prazo.get(p.id)

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
    if _sincronizar_evento(db, prazo, processo):
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

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(prazo, field, value)

    _recalcular(prazo, prazo.processo, db)
    db.commit()
    db.refresh(prazo)

    # Reflete tipo/descrição/data novos no evento do Google Calendar
    if _sincronizar_evento(db, prazo, prazo.processo):
        db.commit()
        db.refresh(prazo)

    return prazo


@router.delete("/{prazo_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_prazo(prazo_id: uuid.UUID, db: Session = Depends(get_db)):
    prazo = db.query(Prazo).filter(Prazo.id == prazo_id).first()
    if not prazo:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")

    # Remove o evento do Google Calendar (silencioso se não autenticado)
    if prazo.google_event_id:
        try:
            deletar_evento(prazo.google_event_id)
        except Exception:
            pass

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

    # A data mudou — o evento na agenda precisa acompanhar
    if _sincronizar_evento(db, prazo, prazo.processo):
        db.commit()
        db.refresh(prazo)

    return prazo
