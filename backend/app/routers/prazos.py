import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.andamento import AndamentoProcesso
from app.models.comentario_prazo import ComentarioPrazo
from app.models.prazo import Prazo
from app.models.processo import Processo
from app.models.publicacao import Publicacao
from app.models.tarefa import Tarefa
from app.models.usuario import Usuario
from app.schemas.prazo import (
    ComentarioPrazoCreate,
    ComentarioPrazoOut,
    ComentarioPrazoProcessoOut,
    PrazoCreate,
    PrazoOut,
    PrazoUpdate,
)
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
        # Mostrada ao lado da publicação no card pra dar conferir a contagem na
        # hora (art. 224, §2º: publicação = 1º dia útil após a disponibilização).
        "data_disponibilizacao": pub.data_disponibilizacao,
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
    origem_por_prazo: dict = {}
    for pub in db.query(Publicacao).filter(Publicacao.prazo_id.in_([p.id for p in prazos])).all():
        if pub.peca_doc_url:
            peca_por_prazo[pub.prazo_id] = pub.peca_doc_url
        origem_por_prazo[pub.prazo_id] = _origem_payload(pub)

    comentarios_por_prazo: dict = {}
    comentarios = (
        db.query(ComentarioPrazo)
        .filter(ComentarioPrazo.prazo_id.in_([p.id for p in prazos]))
        .order_by(ComentarioPrazo.created_at.desc())
        .all()
    )
    for c in comentarios:
        comentarios_por_prazo.setdefault(c.prazo_id, []).append(c)

    for p in prazos:
        p.tarefas_vinculadas = tarefas_por_prazo.get(p.id, [])
        p.peca_doc_url = peca_por_prazo.get(p.id)
        p.publicacao_origem = origem_por_prazo.get(p.id)
        p.comentarios = comentarios_por_prazo.get(p.id, [])

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


# ── ATENÇÃO À ORDEM ──────────────────────────────────────────────────────────
# Rotas de caminho FIXO precisam vir ANTES de "/{prazo_id}". O FastAPI casa as
# rotas na ordem de registro, então "/legais" registrado depois seria capturado
# por "/{prazo_id}" com prazo_id="legais" e devolveria 422 (não é UUID).
# Foi exatamente o bug da legenda em v440. Novas rotas fixas: coloque aqui.
@router.get("/legais")
def catalogo_prazos_legais():
    """Catálogo de prazos do CPC e dos Juizados — legenda + sugestão automática.

    Estático (não toca o banco): é texto de lei. Serve os dois usos pela mesma
    fonte de propósito — legenda e auto-preenchimento divergentes seriam pior
    do que não ter legenda.
    """
    from app.services.prazos_legais import catalogo

    return catalogo()


@router.get("/processo/{processo_id}/comentarios", response_model=list[ComentarioPrazoProcessoOut])
def listar_comentarios_do_processo(processo_id: uuid.UUID, db: Session = Depends(get_db)):
    """Todos os comentários de prazo deste processo, vinculados ou não a um
    andamento — alimenta o painel "Anotações de Prazos" em Processos e, pra
    quem está vinculado, a nota interleaved na linha do tempo de Andamentos.
    Achatado de propósito (ver ComentarioPrazoProcessoOut)."""
    linhas = (
        db.query(
            ComentarioPrazo.id.label("id"),
            ComentarioPrazo.texto.label("texto"),
            ComentarioPrazo.autor_nome.label("autor_nome"),
            ComentarioPrazo.created_at.label("created_at"),
            ComentarioPrazo.andamento_id.label("andamento_id"),
            AndamentoProcesso.tipo.label("andamento_tipo"),
            AndamentoProcesso.data_andamento.label("andamento_data"),
            Prazo.id.label("prazo_id"),
            Prazo.tipo.label("prazo_tipo"),
            Prazo.peca_necessaria.label("prazo_peca"),
            Prazo.status.label("prazo_status"),
            Prazo.data_limite.label("prazo_data_limite"),
        )
        .join(Prazo, ComentarioPrazo.prazo_id == Prazo.id)
        .outerjoin(AndamentoProcesso, ComentarioPrazo.andamento_id == AndamentoProcesso.id)
        .filter(Prazo.processo_id == processo_id)
        .order_by(ComentarioPrazo.created_at.desc())
        .all()
    )
    return linhas


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

    # Motivo só faz sentido quando o novo status é "perdido" — status virando
    # outra coisa sem motivo explícito na mesma chamada limpa o campo.
    if alteracoes.get("status") not in (None, "perdido") and "motivo_perda" not in alteracoes:
        alteracoes["motivo_perda"] = None

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

    # Reflete tipo/descrição/data novos no evento do Google Calendar
    if _sincronizar_evento(db, prazo, prazo.processo):
        db.commit()
        db.refresh(prazo)

    pub = db.query(Publicacao).filter(Publicacao.prazo_id == prazo.id).first()
    prazo.publicacao_origem = _origem_payload(pub) if pub else None

    return prazo


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


# ── Comentários (anotação livre, sem relação com dado de tribunal) ───────────
# Mesmo padrão de /patrimonio/{bem_id}/comentarios. Pensados pra registrar POR
# QUE um ato foi ou não praticado — ainda sem vínculo com Andamentos do
# processo (isso é a próxima etapa, depois de validar o mockup com o Lucas).
@router.post(
    "/{prazo_id}/comentarios",
    response_model=ComentarioPrazoOut,
    status_code=status.HTTP_201_CREATED,
)
def criar_comentario_prazo(
    prazo_id: uuid.UUID,
    data: ComentarioPrazoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    prazo = db.query(Prazo).filter(Prazo.id == prazo_id).first()
    if not prazo:
        raise HTTPException(status_code=404, detail="Prazo não encontrado")

    if data.andamento_id:
        andamento = db.query(AndamentoProcesso).filter(AndamentoProcesso.id == data.andamento_id).first()
        # Precisa pertencer ao MESMO processo do prazo — sem isso dá pra
        # vincular por engano a andamento de outro cliente (o front só lista
        # candidatos do processo certo, mas o backend não confia nisso).
        if not andamento or andamento.processo_id != prazo.processo_id:
            raise HTTPException(
                status_code=400,
                detail="Andamento não encontrado ou não pertence ao processo deste prazo",
            )

    com = ComentarioPrazo(
        prazo_id=prazo.id,
        andamento_id=data.andamento_id,
        texto=data.texto,
        autor_id=usuario.id,
        autor_nome=getattr(usuario, "nome", None) or getattr(usuario, "email", None),
    )
    db.add(com)
    db.commit()
    db.refresh(com)
    return com


@router.delete("/{prazo_id}/comentarios/{comentario_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_comentario_prazo(prazo_id: uuid.UUID, comentario_id: uuid.UUID, db: Session = Depends(get_db)):
    com = (
        db.query(ComentarioPrazo)
        .filter(ComentarioPrazo.id == comentario_id, ComentarioPrazo.prazo_id == prazo_id)
        .first()
    )
    if not com:
        raise HTTPException(status_code=404, detail="Comentário não encontrado")
    db.delete(com)
    db.commit()
