import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.conversa_ia import ConversaIA
from app.models.cliente import Cliente
from app.schemas.conversa_ia import ConversaIACreate, ConversaIAOut, ConversaIAUpdate

router = APIRouter(prefix="/conversas-ia", tags=["conversas_ia"],
                   dependencies=[Depends(get_current_user)])


@router.get("/", response_model=list[ConversaIAOut])
def listar_conversas(
    cliente_id: uuid.UUID | None = Query(None),
    processo_id: uuid.UUID | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(ConversaIA)
    if cliente_id:
        q = q.filter(ConversaIA.cliente_id == cliente_id)
    if processo_id:
        q = q.filter(ConversaIA.processo_id == processo_id)
    return q.order_by(ConversaIA.updated_at.desc()).all()


@router.post("/", response_model=ConversaIAOut, status_code=status.HTTP_201_CREATED)
def criar_conversa(data: ConversaIACreate, db: Session = Depends(get_db)):
    if not db.query(Cliente).filter(Cliente.id == data.cliente_id).first():
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    c = ConversaIA(**data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.patch("/{conversa_id}", response_model=ConversaIAOut)
def atualizar_conversa(conversa_id: uuid.UUID, data: ConversaIAUpdate, db: Session = Depends(get_db)):
    c = db.query(ConversaIA).filter(ConversaIA.id == conversa_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(c, field, value)
    db.commit()
    db.refresh(c)

    # Salva conversa como PDF no Drive do cliente
    _salvar_conversa_pdf(c, db)

    return c


def _salvar_conversa_pdf(c: ConversaIA, db: Session) -> None:
    """Persiste a conversa como PDF na pasta IA do cliente no Drive."""
    try:
        from app.services.gerar_pdf_texto import texto_para_pdf
        from app.models.cliente import Cliente as _Cliente

        cliente = db.query(_Cliente).filter(_Cliente.id == c.cliente_id).first()
        if not cliente or not c.historico:
            return

        titulo = c.titulo or "Conversa IA"
        linhas: list[str] = []
        for msg in c.historico:
            role = "Você" if msg.get("role") == "user" else "IA"
            linhas.append(f"**{role}:** {msg.get('content', '')}\n")
        conteudo = "\n\n".join(linhas)

        from datetime import date
        pdf_bytes = texto_para_pdf(
            conteudo=conteudo,
            titulo=titulo,
            subtitulo=f"Modelo: {c.modelo or 'Gemini'}",
            cliente_nome=cliente.nome,
            data=date.today(),
        )
        id_curto = str(c.id)[:8]
        nome = f"conversa_ia_{id_curto}.pdf"
        from app.services.google_drive import upload_arquivo
        upload_arquivo(pdf_bytes, nome, cliente.nome, "IA")
    except Exception:
        pass


@router.delete("/{conversa_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_conversa(conversa_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.query(ConversaIA).filter(ConversaIA.id == conversa_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    db.delete(c)
    db.commit()


@router.post("/{conversa_id}/compactar", response_model=ConversaIAOut)
def compactar_conversa(conversa_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Pede para a IA resumir o histórico e cria uma NOVA conversa do tipo 'resumo'
    vinculada à original via parent_conversa_id.
    A conversa original não é alterada.
    """
    c = db.query(ConversaIA).filter(ConversaIA.id == conversa_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")

    historico = c.historico or []
    if not historico:
        raise HTTPException(status_code=400, detail="Conversa vazia")

    texto_conv = "\n\n".join(
        f"{'Usuário' if m.get('role') == 'user' else 'IA'}: {m.get('content', '')}"
        for m in historico
    )
    prompt = (
        "Faça um resumo executivo desta conversa, destacando: "
        "os tópicos discutidos, conclusões, decisões tomadas e próximos passos. "
        "Seja conciso mas completo.\n\n" + texto_conv[:6000]
    )

    from app.services.gemini_chat import chat_processo
    resumo_texto = chat_processo(pergunta=prompt, historico=[], pdf_paths=[])

    titulo_original = c.titulo or "Conversa"
    resumo_conversa = ConversaIA(
        cliente_id=c.cliente_id,
        processo_id=c.processo_id,
        titulo=f"[Resumo] {titulo_original}",
        modelo=c.modelo,
        historico=[{"role": "model", "content": resumo_texto}],
        resumo=resumo_texto,
        parent_conversa_id=c.id,
    )
    db.add(resumo_conversa)
    db.commit()
    db.refresh(resumo_conversa)
    return resumo_conversa


@router.get("/{conversa_id}/pdf")
def exportar_pdf(conversa_id: uuid.UUID, db: Session = Depends(get_db)):
    """Gera e retorna o PDF da conversa para download."""
    from datetime import date
    from app.services.gerar_pdf_texto import texto_para_pdf

    c = db.query(ConversaIA).filter(ConversaIA.id == conversa_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")

    cliente = db.query(Cliente).filter(Cliente.id == c.cliente_id).first()

    titulo = c.titulo or "Conversa IA"
    linhas: list[str] = []
    for msg in (c.historico or []):
        role = "Você" if msg.get("role") == "user" else "IA"
        linhas.append(f"**{role}:** {msg.get('content', '')}\n")
    conteudo = "\n\n".join(linhas) if linhas else "Conversa sem mensagens."

    pdf_bytes = texto_para_pdf(
        conteudo=conteudo,
        titulo=titulo,
        subtitulo=f"Modelo: {c.modelo or 'Gemini'}",
        cliente_nome=cliente.nome if cliente else None,
        data=date.today(),
    )

    nome = f"conversa_{str(c.id)[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
