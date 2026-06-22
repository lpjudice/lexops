import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, get_optional_user
from app.models.anotacao import Anotacao
from app.models.cliente import Cliente
from app.models.prazo import Prazo
from app.models.publicacao import Publicacao
from app.models.reuniao import Reuniao
from app.models.usuario import Usuario
from app.schemas.anotacao import AnotacaoCreate, AnotacaoOut, AnotacaoUpdate, TimelineItem
from app.services.gmail_cliente import buscar_emails_cliente

router = APIRouter(prefix="/anotacoes", tags=["anotacoes"],
                   dependencies=[Depends(get_current_user)])


def _pode_ver_anotacao(a: Anotacao, usuario: Usuario | None, db: Session) -> bool:
    """Returns True if user can see this annotation (confidential check via source reuniao)."""
    if not a.confidencial:
        return True
    if usuario is None:
        return False
    if usuario.role == "super_admin":
        return True
    if not a.reuniao_id:
        # Confidential annotation with no meeting link — only super_admin can see (already checked)
        return False
    r = db.query(Reuniao).filter(Reuniao.id == a.reuniao_id).first()
    if not r:
        return False
    if r.criado_por_id and str(usuario.id) == str(r.criado_por_id):
        return True
    return str(usuario.id) in (r.usuarios_com_acesso or [])


# ── CRUD de anotações ─────────────────────────────────────────────────────────

@router.get("/", response_model=list[AnotacaoOut])
def listar_anotacoes(
    cliente_id: uuid.UUID | None = Query(None),
    processo_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    q = db.query(Anotacao)
    if cliente_id:
        q = q.filter(Anotacao.cliente_id == cliente_id)
    if processo_id:
        q = q.filter(Anotacao.processo_id == processo_id)
    anotacoes = q.order_by(Anotacao.data_evento.desc()).all()
    # Filter out confidential annotations the user can't see
    return [a for a in anotacoes if _pode_ver_anotacao(a, usuario, db)]


@router.post("/", response_model=AnotacaoOut, status_code=status.HTTP_201_CREATED)
def criar_anotacao(data: AnotacaoCreate, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.id == data.cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    anotacao = Anotacao(**data.model_dump())
    db.add(anotacao)
    db.commit()
    db.refresh(anotacao)
    # Salva PDF na pasta do cliente no Google Drive.
    try:
        from app.services.gerar_pdf_texto import texto_para_pdf
        data_evento_str = anotacao.data_evento.isoformat() if hasattr(anotacao.data_evento, 'isoformat') else str(anotacao.data_evento)
        nome_arquivo = f"{anotacao.tipo}_{data_evento_str}_{str(anotacao.id)[:8]}.pdf"
        titulo_pdf = anotacao.titulo or anotacao.tipo.capitalize()
        conteudo_md = (
            f"**Tipo:** {anotacao.tipo}  \n"
            f"**Data:** {data_evento_str}\n\n"
            f"---\n\n"
            f"{anotacao.texto or ''}"
        )
        pdf_bytes = texto_para_pdf(
            conteudo=conteudo_md,
            titulo=titulo_pdf,
            cliente_nome=cliente.nome,
            data=anotacao.data_evento if hasattr(anotacao.data_evento, 'strftime') else None,
        )
        from app.services.google_drive import upload_arquivo
        upload_arquivo(pdf_bytes, nome_arquivo, cliente.nome, "Anotações")
    except Exception:
        pass
    return anotacao


@router.patch("/{anotacao_id}", response_model=AnotacaoOut)
def atualizar_anotacao(
    anotacao_id: uuid.UUID, data: AnotacaoUpdate, db: Session = Depends(get_db)
):
    anotacao = db.query(Anotacao).filter(Anotacao.id == anotacao_id).first()
    if not anotacao:
        raise HTTPException(status_code=404, detail="Anotação não encontrada")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(anotacao, field, value)
    db.commit()
    db.refresh(anotacao)
    return anotacao


@router.delete("/{anotacao_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_anotacao(anotacao_id: uuid.UUID, db: Session = Depends(get_db)):
    anotacao = db.query(Anotacao).filter(Anotacao.id == anotacao_id).first()
    if not anotacao:
        raise HTTPException(status_code=404, detail="Anotação não encontrada")
    db.delete(anotacao)
    db.commit()


# ── Timeline do cliente ───────────────────────────────────────────────────────

@router.get("/cliente/{cliente_id}/timeline", response_model=list[TimelineItem])
def timeline_cliente(
    cliente_id: uuid.UUID,
    incluir_emails: bool = Query(True),
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    items: list[TimelineItem] = []
    processo_ids = [p.id for p in cliente.processos]

    # ── Anotações ─────────────────────────────────────────────────────────
    for a in db.query(Anotacao).filter(Anotacao.cliente_id == cliente_id).all():
        if not _pode_ver_anotacao(a, usuario, db):
            # Show as confidential placeholder in timeline
            items.append(TimelineItem(
                tipo="anotacao",
                data=datetime.combine(a.data_evento, datetime.min.time()).isoformat(),
                titulo="Anotação confidencial",
                subtitulo=a.tipo,
                texto=None,
                referencia_id=str(a.id),
                meta={"tipo": a.tipo, "confidencial": True, "processo_id": str(a.processo_id) if a.processo_id else None},
            ))
        else:
            items.append(TimelineItem(
                tipo="anotacao",
                data=datetime.combine(a.data_evento, datetime.min.time()).isoformat(),
                titulo=a.titulo or a.tipo.capitalize(),
                subtitulo=a.tipo,
                texto=a.texto,
                referencia_id=str(a.id),
                meta={"tipo": a.tipo, "confidencial": False, "processo_id": str(a.processo_id) if a.processo_id else None},
            ))

    # ── Prazos ────────────────────────────────────────────────────────────
    if processo_ids:
        prazos = db.query(Prazo).filter(Prazo.processo_id.in_(processo_ids)).all()
        for p in prazos:
            data_ref = p.data_limite or p.data_publicacao
            items.append(TimelineItem(
                tipo="prazo",
                data=datetime.combine(data_ref, datetime.min.time()).isoformat(),
                titulo=f"Prazo: {p.tipo}",
                subtitulo=f"{p.dias_prazo} dias {p.tipo_contagem}",
                texto=p.descricao,
                referencia_id=str(p.id),
                meta={
                    "status": p.status,
                    "data_limite": p.data_limite.isoformat() if p.data_limite else None,
                    "data_limite_sem_feriado": p.data_limite_sem_feriado.isoformat() if p.data_limite_sem_feriado else None,
                },
            ))

    # ── Publicações vinculadas ────────────────────────────────────────────
    if processo_ids:
        pubs = db.query(Publicacao).filter(Publicacao.processo_id.in_(processo_ids)).all()
        for pub in pubs:
            items.append(TimelineItem(
                tipo="publicacao",
                data=datetime.combine(pub.data_publicacao, datetime.min.time()).isoformat(),
                titulo=f"Publicação: {pub.tipo_ato or 'diário'}",
                subtitulo=pub.tribunal,
                texto=pub.texto_resumo,
                referencia_id=str(pub.id),
                meta={"fonte": pub.fonte, "numero_cnj": pub.numero_cnj, "lida": pub.lida},
            ))

    # ── Emails do cliente ─────────────────────────────────────────────────
    if incluir_emails and cliente.email:
        emails = buscar_emails_cliente(cliente.email, max_results=30)
        for e in emails:
            items.append(TimelineItem(
                tipo="email",
                data=e.get("data") or "",
                titulo=e.get("assunto") or "(sem assunto)",
                subtitulo=f"De: {e.get('de', '')}",
                texto=e.get("snippet"),
                referencia_id=e.get("id"),
                meta={"de": e.get("de"), "para": e.get("para"), "corpo": e.get("corpo")},
            ))

    # ── Reuniões vinculadas ao cliente ───────────────────────────────────
    reunioes = db.query(Reuniao).filter(Reuniao.cliente_id == cliente_id).all()
    for r in reunioes:
        data_ref = r.data_reuniao or r.created_at
        acoes_count = len([a for a in (r.acoes_sugeridas or []) if a.get("aprovada")])
        items.append(TimelineItem(
            tipo="reuniao",
            data=data_ref.isoformat(),
            titulo=r.titulo if not r.confidencial else "Reunião confidencial",
            subtitulo=r.status,
            texto=r.resumo_ia if not r.confidencial else None,
            referencia_id=str(r.id),
            meta={
                "status": r.status,
                "fonte": r.fonte,
                "acoes_aprovadas": acoes_count,
                "duracao_minutos": r.duracao_minutos,
                "confidencial": r.confidencial,
            },
        ))

    # Ordena por data decrescente
    items.sort(key=lambda x: x.data, reverse=True)
    return items
