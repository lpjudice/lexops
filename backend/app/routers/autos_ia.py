"""Autos IA — leitura incremental de autos processuais volumosos, em paralelo
ao restante do gestor. Cada Caso é um processo independente; os PDFs são
enviados em blocos de páginas, segmentados em peças e resumidos por IA."""
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.dependencies import get_current_user
from app.models.autos_ia import AutosIACaso, AutosIADocumento, AutosIAPeca, AutosIAPerguntaFaq, AutosIAReferencia
from app.schemas.autos_ia import (
    CasoCreate, CasoOut, CasoResumo, CasoUpdate, DocumentoOut, EstimativaImportacaoOut, FaqPerguntaCreate,
    FaqPerguntaOut, GrafoAresta, GrafoNo, GrafoOut, PecaDetalheOut, PecaOut,
)
from app.services.autos_ia import faq as faq_service
from app.services.autos_ia.busca import buscar_pecas
from app.services.autos_ia.estimativa import estimar_importacao_existentes, estimar_reclassificacao
from app.services.autos_ia.ingestao import processar_documento, reclassificar_caso, retomar_documento
from app.services.autos_ia.jusbr_import import (
    importar_apenas_existentes, listar_andamentos_pendentes, sincronizar_caso_jusbr,
)
from app.services.autos_ia.pdf_merge import montar_pdf_pecas

UPLOADS_DIR = Path("/app/uploads/autos_ia")

router = APIRouter(prefix="/autos-ia", tags=["autos-ia"], dependencies=[Depends(get_current_user)])


def _get_caso(db: Session, caso_id: uuid.UUID) -> AutosIACaso:
    caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    return caso


def _validar_sync(processo_id, sync_jusbr_ativo: bool | None) -> None:
    if sync_jusbr_ativo and not processo_id:
        raise HTTPException(
            status_code=422,
            detail="Só é possível ativar a sincronização automática com um processo vinculado.",
        )


# ── Casos ────────────────────────────────────────────────────────────────────

@router.get("/casos", response_model=list[CasoResumo])
def listar_casos(db: Session = Depends(get_db)):
    casos = db.query(AutosIACaso).order_by(AutosIACaso.criado_em.desc()).all()
    out = []
    for c in casos:
        item = CasoResumo.model_validate(c)
        item.total_pecas = db.query(AutosIAPeca).filter(AutosIAPeca.caso_id == c.id).count()
        item.total_documentos = db.query(AutosIADocumento).filter(AutosIADocumento.caso_id == c.id).count()
        item.total_perguntas_faq = db.query(AutosIAPerguntaFaq).filter(AutosIAPerguntaFaq.caso_id == c.id).count()
        out.append(item)
    return out


@router.post("/casos", response_model=CasoOut, status_code=status.HTTP_201_CREATED)
def criar_caso(data: CasoCreate, db: Session = Depends(get_db), usuario=Depends(get_current_user)):
    _validar_sync(data.processo_id, data.sync_jusbr_ativo)
    caso = AutosIACaso(**data.model_dump(), criado_por_id=usuario.id)
    db.add(caso)
    db.commit()
    db.refresh(caso)
    return caso


@router.get("/casos/{caso_id}", response_model=CasoOut)
def obter_caso(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_caso(db, caso_id)


@router.patch("/casos/{caso_id}", response_model=CasoOut)
def atualizar_caso(caso_id: uuid.UUID, data: CasoUpdate, db: Session = Depends(get_db)):
    caso = _get_caso(db, caso_id)
    campos = data.model_dump(exclude_unset=True)
    processo_id = campos.get("processo_id", caso.processo_id)
    sync_jusbr_ativo = campos.get("sync_jusbr_ativo", caso.sync_jusbr_ativo)
    _validar_sync(processo_id, sync_jusbr_ativo)
    for campo, valor in campos.items():
        setattr(caso, campo, valor)
    db.commit()
    db.refresh(caso)
    return caso


@router.delete("/casos/{caso_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_caso(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    caso = _get_caso(db, caso_id)
    if caso.ultimo_sync_status == "processando":
        raise HTTPException(
            status_code=422, detail="Cancele a sincronização em andamento antes de excluir o caso."
        )
    doc_processando = (
        db.query(AutosIADocumento)
        .filter(AutosIADocumento.caso_id == caso_id, AutosIADocumento.status == "processando")
        .first()
    )
    if doc_processando:
        raise HTTPException(
            status_code=422, detail="Cancele o processamento do bloco em andamento antes de excluir o caso."
        )
    db.delete(caso)
    db.commit()


# ── Upload / ingestão ───────────────────────────────────────────────────────

def _executar_ingestao_em_background(documento_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        processar_documento(db, documento_id)
    finally:
        db.close()


@router.post("/casos/{caso_id}/upload", response_model=DocumentoOut, status_code=status.HTTP_202_ACCEPTED)
async def enviar_bloco(
    caso_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    arquivo: UploadFile = File(..., description="Bloco de páginas do PDF dos autos"),
    pagina_inicio: int | None = Form(None, description="Página inicial global; padrão = continuar do último bloco"),
    db: Session = Depends(get_db),
):
    caso = _get_caso(db, caso_id)

    conteudo = await arquivo.read()
    if not conteudo:
        raise HTTPException(status_code=422, detail="Arquivo vazio")

    from pypdf import PdfReader
    import io
    try:
        total_paginas_bloco = len(PdfReader(io.BytesIO(conteudo)).pages)
    except Exception:
        raise HTTPException(status_code=422, detail="Não foi possível ler o PDF enviado")

    inicio = pagina_inicio if pagina_inicio is not None else caso.total_paginas + 1
    fim = inicio + total_paginas_bloco - 1

    pasta_caso = UPLOADS_DIR / str(caso.id)
    pasta_caso.mkdir(parents=True, exist_ok=True)
    nome_arquivo = f"{inicio:06d}-{fim:06d}_{uuid.uuid4().hex[:8]}_{arquivo.filename}"
    caminho = pasta_caso / nome_arquivo
    caminho.write_bytes(conteudo)

    documento = AutosIADocumento(
        caso_id=caso.id,
        nome_arquivo=arquivo.filename or nome_arquivo,
        caminho_arquivo=str(caminho),
        pagina_inicio=inicio,
        pagina_fim=fim,
        status="pendente",
    )
    db.add(documento)
    db.commit()
    db.refresh(documento)

    background_tasks.add_task(_executar_ingestao_em_background, documento.id)
    return documento


@router.get("/casos/{caso_id}/documentos", response_model=list[DocumentoOut])
def listar_documentos(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    return (
        db.query(AutosIADocumento)
        .filter(AutosIADocumento.caso_id == caso_id)
        .order_by(AutosIADocumento.pagina_inicio.asc())
        .all()
    )


def _get_documento(db: Session, documento_id: uuid.UUID) -> AutosIADocumento:
    doc = db.query(AutosIADocumento).filter(AutosIADocumento.id == documento_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return doc


@router.post("/documentos/{documento_id}/cancelar", response_model=DocumentoOut)
def cancelar_documento(documento_id: uuid.UUID, db: Session = Depends(get_db)):
    """Pede o cancelamento gracioso do processamento de um bloco em andamento —
    para assim que checar a flag, preservando as peças já resumidas."""
    doc = _get_documento(db, documento_id)
    if doc.status != "processando":
        raise HTTPException(status_code=422, detail="Este documento não está em processamento.")
    doc.cancelar = True
    db.commit()
    db.refresh(doc)
    return doc


def _executar_retomada_em_background(documento_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        retomar_documento(db, documento_id)
    finally:
        db.close()


@router.post("/documentos/{documento_id}/retomar", response_model=DocumentoOut, status_code=status.HTTP_202_ACCEPTED)
def retomar_documento_agora(documento_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Retoma um documento cancelado (ou que ficou com peças em erro): resume só
    o que ainda falta, sem repetir extração/segmentação já feitas."""
    doc = _get_documento(db, documento_id)
    if doc.status not in ("cancelado", "erro"):
        raise HTTPException(status_code=422, detail="Só é possível retomar um documento cancelado ou com erro.")
    doc.status = "processando"
    db.commit()
    db.refresh(doc)
    background_tasks.add_task(_executar_retomada_em_background, doc.id)
    return doc


# ── Sincronização com o processo vinculado (jus.br) ─────────────────────────

def _executar_sync_em_background(caso_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        from app.services.consulta_processual.jusbr_session import load_session
        caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
        if caso:
            sincronizar_caso_jusbr(db, caso, load_session())
    finally:
        db.close()


@router.post("/casos/{caso_id}/sincronizar", response_model=CasoOut, status_code=status.HTTP_202_ACCEPTED)
def sincronizar_agora(caso_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    caso = _get_caso(db, caso_id)
    if not caso.processo_id:
        raise HTTPException(status_code=422, detail="Este caso não está vinculado a um processo.")
    caso.ultimo_sync_status = "processando"
    caso.ultimo_sync_mensagem = None
    db.commit()
    db.refresh(caso)
    background_tasks.add_task(_executar_sync_em_background, caso.id)
    return caso


def _executar_importacao_existentes_em_background(caso_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
        if caso:
            importar_apenas_existentes(db, caso)
    finally:
        db.close()


@router.post("/casos/{caso_id}/importar-existentes", response_model=CasoOut, status_code=status.HTTP_202_ACCEPTED)
def importar_existentes_agora(caso_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Importa só os documentos que o jus.br já baixou pro processo vinculado —
    sem chamar jus.br/DataJud ao vivo. Ideal pro backfill inicial de um caso
    vinculado a um processo que já tem muitos documentos salvos."""
    caso = _get_caso(db, caso_id)
    if not caso.processo_id:
        raise HTTPException(status_code=422, detail="Este caso não está vinculado a um processo.")
    caso.ultimo_sync_status = "processando"
    caso.ultimo_sync_mensagem = None
    db.commit()
    db.refresh(caso)
    background_tasks.add_task(_executar_importacao_existentes_em_background, caso.id)
    return caso


@router.get("/casos/{caso_id}/estimativa-importacao", response_model=EstimativaImportacaoOut)
def estimar_importacao(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    """Projeção de custo/tempo pra importar os documentos já baixados que ainda
    não viraram peça — pra decidir antes de disparar um backfill grande (ex.:
    um caso com centenas de documentos pendentes)."""
    caso = _get_caso(db, caso_id)
    if not caso.processo_id:
        raise HTTPException(status_code=422, detail="Este caso não está vinculado a um processo.")
    pendentes = listar_andamentos_pendentes(db, caso)
    return estimar_importacao_existentes(len(pendentes))


@router.post("/casos/{caso_id}/cancelar-sync", response_model=CasoOut)
def cancelar_sync(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    """Pede o cancelamento gracioso de uma sincronização/importação em
    andamento — a rotina para assim que checar a flag, preservando as peças
    já lidas/resumidas até aquele ponto."""
    caso = _get_caso(db, caso_id)
    if caso.ultimo_sync_status != "processando":
        raise HTTPException(status_code=422, detail="Não há sincronização em andamento para cancelar.")
    caso.sync_cancelar = True
    db.commit()
    db.refresh(caso)
    return caso


@router.get("/casos/{caso_id}/estimativa-reclassificacao", response_model=EstimativaImportacaoOut)
def estimar_reclassificacao_caso(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    """Projeção de custo/tempo pra reclassificar (tipo/peticionante/ID próprio)
    as peças-mãe já resumidas deste caso — bem mais barato que resumir de novo,
    mas ainda assim uma chamada de IA por peça."""
    caso = _get_caso(db, caso_id)
    total = (
        db.query(AutosIAPeca)
        .filter(AutosIAPeca.caso_id == caso_id, AutosIAPeca.peca_pai_id.is_(None), AutosIAPeca.status == "resumida")
        .count()
    )
    return estimar_reclassificacao(total)


def _executar_reclassificacao_em_background(caso_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
        if caso:
            reclassificar_caso(db, caso)
    finally:
        db.close()


@router.post("/casos/{caso_id}/reclassificar", response_model=CasoOut, status_code=status.HTTP_202_ACCEPTED)
def reclassificar_agora(caso_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Reclassifica tipo/peticionante/ID próprio das peças-mãe já resumidas do
    caso — pra atualizar peças indexadas antes desses campos existirem, sem
    pagar de novo pelo resumo inteiro."""
    caso = _get_caso(db, caso_id)
    if caso.ultimo_sync_status == "processando":
        raise HTTPException(status_code=422, detail="Já há uma sincronização/reclassificação em andamento.")
    caso.ultimo_sync_status = "processando"
    caso.ultimo_sync_mensagem = None
    db.commit()
    db.refresh(caso)
    background_tasks.add_task(_executar_reclassificacao_em_background, caso.id)
    return caso


# ── Peças (busca por tema/data/tipo) ────────────────────────────────────────

def _com_total_anexos(db: Session, caso_id: uuid.UUID, pecas: list[AutosIAPeca]) -> list[PecaOut]:
    from sqlalchemy import func as sa_func
    contagens = dict(
        db.query(AutosIAPeca.peca_pai_id, sa_func.count(AutosIAPeca.id))
        .filter(AutosIAPeca.caso_id == caso_id, AutosIAPeca.peca_pai_id.isnot(None))
        .group_by(AutosIAPeca.peca_pai_id)
        .all()
    )
    saida = []
    for p in pecas:
        item = PecaOut.model_validate(p)
        item.total_anexos = contagens.get(p.id, 0)
        saida.append(item)
    return saida


@router.get("/casos/{caso_id}/pecas", response_model=list[PecaOut])
def listar_pecas(
    caso_id: uuid.UUID,
    q: str | None = None,
    tipo: str | None = None,
    data_inicio: str | None = None,
    data_fim: str | None = None,
    incluir_anexos: bool = False,
    offset: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    from datetime import date as date_cls
    _get_caso(db, caso_id)
    di = date_cls.fromisoformat(data_inicio) if data_inicio else None
    df = date_cls.fromisoformat(data_fim) if data_fim else None
    limit = max(1, min(limit, 300))
    pecas = buscar_pecas(
        db, caso_id, query=q, data_inicio=di, data_fim=df, tipo=tipo, incluir_anexos=incluir_anexos,
        offset=max(0, offset), limite=limit,
    )
    return _com_total_anexos(db, caso_id, pecas)


@router.get("/pecas/{peca_id}", response_model=PecaDetalheOut)
def obter_peca(peca_id: uuid.UUID, db: Session = Depends(get_db)):
    peca = db.query(AutosIAPeca).filter(AutosIAPeca.id == peca_id).first()
    if not peca:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    return peca


@router.get("/pecas/{peca_id}/anexos", response_model=list[PecaOut])
def listar_anexos(peca_id: uuid.UUID, db: Session = Depends(get_db)):
    peca = db.query(AutosIAPeca).filter(AutosIAPeca.id == peca_id).first()
    if not peca:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    anexos = (
        db.query(AutosIAPeca)
        .filter(AutosIAPeca.peca_pai_id == peca_id)
        .order_by(AutosIAPeca.pagina_inicio.asc())
        .all()
    )
    return _com_total_anexos(db, peca.caso_id, anexos)


@router.get("/casos/{caso_id}/pecas/download")
def baixar_pecas_pdf(
    caso_id: uuid.UUID,
    apenas_principais: bool = True,
    tipo: str | None = None,
    ids: str | None = None,
    db: Session = Depends(get_db),
):
    caso = _get_caso(db, caso_id)
    peca_ids = [uuid.UUID(i) for i in ids.split(",") if i.strip()] if ids else None
    conteudo = montar_pdf_pecas(db, caso_id, apenas_principais=apenas_principais, tipo=tipo, peca_ids=peca_ids)
    nome_arquivo = f"{caso.nome.strip().replace(' ', '_')}_pecas.pdf"
    return StreamingResponse(
        iter([conteudo]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )


# ── Grafo de referências ─────────────────────────────────────────────────────

@router.get("/casos/{caso_id}/grafo", response_model=GrafoOut)
def obter_grafo(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    pecas = db.query(AutosIAPeca).filter(AutosIAPeca.caso_id == caso_id).all()
    referencias = db.query(AutosIAReferencia).filter(AutosIAReferencia.caso_id == caso_id).all()
    return GrafoOut(
        nos=[GrafoNo.model_validate(p, from_attributes=True) for p in pecas],
        arestas=[GrafoAresta.model_validate(r, from_attributes=True) for r in referencias],
    )


# ── FAQ ──────────────────────────────────────────────────────────────────────

@router.get("/casos/{caso_id}/faq", response_model=list[FaqPerguntaOut])
def listar_faq(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    return (
        db.query(AutosIAPerguntaFaq)
        .filter(AutosIAPerguntaFaq.caso_id == caso_id)
        .order_by(AutosIAPerguntaFaq.criado_em.desc())
        .all()
    )


@router.post("/casos/{caso_id}/faq", response_model=FaqPerguntaOut, status_code=status.HTTP_201_CREATED)
def perguntar(caso_id: uuid.UUID, data: FaqPerguntaCreate, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    pergunta = AutosIAPerguntaFaq(caso_id=caso_id, pergunta=data.pergunta, status="pendente")
    db.add(pergunta)
    db.commit()
    db.refresh(pergunta)
    faq_service.responder_pergunta(db, pergunta)
    db.refresh(pergunta)
    return pergunta


@router.post("/faq/{pergunta_id}/reprocessar", response_model=FaqPerguntaOut)
def reprocessar_pergunta(pergunta_id: uuid.UUID, db: Session = Depends(get_db)):
    pergunta = db.query(AutosIAPerguntaFaq).filter(AutosIAPerguntaFaq.id == pergunta_id).first()
    if not pergunta:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada")
    faq_service.responder_pergunta(db, pergunta)
    db.refresh(pergunta)
    return pergunta


@router.delete("/faq/{pergunta_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_pergunta(pergunta_id: uuid.UUID, db: Session = Depends(get_db)):
    pergunta = db.query(AutosIAPerguntaFaq).filter(AutosIAPerguntaFaq.id == pergunta_id).first()
    if not pergunta:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada")
    db.delete(pergunta)
    db.commit()
