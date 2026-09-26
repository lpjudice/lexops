"""Autos IA — leitura incremental de autos processuais volumosos, em paralelo
ao restante do gestor. Cada Caso é um processo independente; os PDFs são
enviados em blocos de páginas, segmentados em peças e resumidos por IA."""
import logging
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import DateTime, cast, func, or_
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.dependencies import get_current_user
from app.models.andamento import AndamentoProcesso
from app.models.autos_ia import AutosIACaso, AutosIADocumento, AutosIAPeca, AutosIAPerguntaFaq, AutosIAReferencia
from app.schemas.autos_ia import (
    CasoCreate, CasoOut, CasoResumo, CasoUpdate, DocumentoDriveAnexoOut, DocumentoDriveOut, DocumentoOut,
    EstimativaImportacaoOut, FaqPerguntaCreate, FaqPerguntaOut, GrafoAresta, GrafoNo, GrafoOut, PecaAnotacaoUpdate,
    PecaDetalheOut, PecaOut, PecaTipoUpdate,
)
from app.services.autos_ia import faq as faq_service
from app.services.autos_ia.busca import buscar_pecas
from app.services.autos_ia.estimativa import estimar_importacao_existentes, estimar_reclassificacao
from app.services.autos_ia.ingestao import processar_documento, reclassificar_caso, retomar_documento
from app.services.autos_ia.jusbr_import import (
    atualizar_metadados_jusbr, importar_apenas_existentes, listar_andamentos_pendentes,
    reagrupar_pecas_jusbr, sincronizar_caso_jusbr,
)
from app.services.autos_ia.nomes import derivar_nome_indexado
from app.services.autos_ia.pdf_merge import montar_pdf_pecas

logger = logging.getLogger(__name__)

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

def _carregar_sessao_jusbr() -> dict | None:
    """Sessão do próprio lexops (colar token); se caiu, cai pra sessão do bot
    do Telegram (id=2), que fica ativa por muito mais tempo (offline_access +
    refresh proativo) — mesmo fallback que telegram_andamentos.py já usa ao
    contrário."""
    from app.services.consulta_processual.jusbr_session import load_session

    session_data = load_session()
    if session_data:
        return session_data
    from app.services.andamentos_auth import load_session as load_session_bot

    return load_session_bot()


def _forcar_status_erro(caso_id: uuid.UUID, mensagem: str) -> None:
    """Última rede de segurança: se a sincronização travar em algo que nem o
    próprio try/except dela trata (ex.: o pool de conexões do banco esgotado
    no meio do processo), sem isso o caso ficava preso em "processando" pra
    sempre — só um redeploy (que reseta tudo no /health de novo) desemperrava.
    Abre uma sessão NOVA de propósito: a sessão original pode ser a própria
    quebrada."""
    db = SessionLocal()
    try:
        caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
        if caso:
            caso.ultimo_sync_status = "erro"
            caso.ultimo_sync_mensagem = mensagem[:500]
            caso.sync_etapa = None
            caso.sync_total_itens = None
            caso.sync_itens_processados = None
            db.commit()
    except Exception:
        logger.exception("Autos IA: falha ao registrar erro do caso %s (banco indisponível?)", caso_id)
    finally:
        db.close()


def _executar_sync_em_background(caso_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
        if caso:
            sincronizar_caso_jusbr(db, caso, _carregar_sessao_jusbr())
    except Exception as exc:
        logger.exception("Autos IA: sincronização do caso %s travou de forma inesperada", caso_id)
        _forcar_status_erro(caso_id, f"Interrompida por um erro inesperado: {exc}")
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


def _executar_atualizar_metadados_em_background(caso_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
        if caso:
            atualizar_metadados_jusbr(db, caso, _carregar_sessao_jusbr())
    except Exception as exc:
        logger.exception("Autos IA: atualizar-metadados do caso %s travou de forma inesperada", caso_id)
        _forcar_status_erro(caso_id, f"Interrompida por um erro inesperado: {exc}")
    finally:
        db.close()


@router.post("/casos/{caso_id}/atualizar-metadados", response_model=CasoOut, status_code=status.HTTP_202_ACCEPTED)
def atualizar_metadados_agora(caso_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Só consulta o jus.br pra atualizar metadados dos andamentos já conhecidos
    (hora de protocolo etc.) — sem processar nenhuma peça nova. Zero custo de
    IA. Use antes de "Reagrupar peças" pra dar a ela dado novo pra trabalhar."""
    caso = _get_caso(db, caso_id)
    if not caso.processo_id:
        raise HTTPException(status_code=422, detail="Este caso não está vinculado a um processo.")
    if caso.ultimo_sync_status == "processando":
        raise HTTPException(status_code=422, detail="Já há uma sincronização em andamento.")
    caso.ultimo_sync_status = "processando"
    caso.ultimo_sync_mensagem = None
    db.commit()
    db.refresh(caso)
    background_tasks.add_task(_executar_atualizar_metadados_em_background, caso.id)
    return caso


def _executar_reagrupar_em_background(caso_id: uuid.UUID) -> None:
    from datetime import datetime, timezone
    db = SessionLocal()
    try:
        caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
        if caso:
            try:
                total = reagrupar_pecas_jusbr(db, caso)
                caso.ultimo_sync_status = "ok"
                caso.ultimo_sync_mensagem = f"{total} peça(s) reagrupada(s) (petição/anexo)."
            except Exception as exc:
                caso.ultimo_sync_status = "erro"
                caso.ultimo_sync_mensagem = str(exc)
            finally:
                caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
                db.commit()
    finally:
        db.close()


@router.post("/casos/{caso_id}/reagrupar", response_model=CasoOut, status_code=status.HTTP_202_ACCEPTED)
def reagrupar_agora(caso_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Reaplica o agrupamento petição/anexo nas peças já importadas, usando a
    hora de protocolo quando disponível — 100% local, sem IA nem rede."""
    caso = _get_caso(db, caso_id)
    if caso.ultimo_sync_status == "processando":
        raise HTTPException(status_code=422, detail="Já há uma sincronização/reagrupamento em andamento.")
    caso.ultimo_sync_status = "processando"
    caso.ultimo_sync_mensagem = None
    db.commit()
    db.refresh(caso)
    background_tasks.add_task(_executar_reagrupar_em_background, caso.id)
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
    """Cancela a sincronização/importação em andamento. Libera a tela na hora
    (muda o status já nesta própria requisição) em vez de só pedir e esperar
    a rotina de fundo perceber — se ela estiver presa numa chamada de IA ou
    numa conexão de banco lenta, podia nunca chegar a checar a flag, e a tela
    ficava travada no botão de cancelar até um redeploy. As peças já lidas/
    resumidas até agora continuam salvas; se a rotina de fundo ainda estiver
    viva e reagir depois, ela só confirma o mesmo status, sem conflito."""
    caso = _get_caso(db, caso_id)
    if caso.ultimo_sync_status != "processando":
        raise HTTPException(status_code=422, detail="Não há sincronização em andamento para cancelar.")
    caso.sync_cancelar = True
    caso.ultimo_sync_status = "cancelado"
    caso.ultimo_sync_mensagem = "Cancelado pelo usuário."
    caso.sync_etapa = None
    caso.sync_total_itens = None
    caso.sync_itens_processados = None
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


# ── Documentos (listagem compacta com link pro Drive) ───────────────────────

def _montar_documento_drive(peca: AutosIAPeca, andamento: AndamentoProcesso | None) -> DocumentoDriveAnexoOut:
    arquivo_nome = andamento.arquivo_nome if andamento else None
    return DocumentoDriveAnexoOut(
        id=peca.id,
        tipo=peca.tipo,
        titulo=peca.titulo,
        resumo=peca.resumo,
        autor=peca.autor,
        data_peca=peca.data_peca,
        protocolado_em=andamento.protocolado_em if andamento else None,
        id_processual=peca.id_processual,
        status=peca.status,
        erro_mensagem=peca.erro_mensagem,
        arquivo_nome=arquivo_nome,
        arquivo_drive_link=andamento.arquivo_drive_link if andamento else None,
        nome_indexado=derivar_nome_indexado(arquivo_nome),
        nota_usuario=peca.nota_usuario,
        keywords_usuario=peca.keywords_usuario,
        titulo_customizado=peca.titulo_customizado,
    )


@router.get("/casos/{caso_id}/documentos-drive", response_model=list[DocumentoDriveOut])
def listar_documentos_drive(
    caso_id: uuid.UUID,
    q: str | None = None,
    ordem: Literal["asc", "desc"] = "asc",
    offset: int = 0,
    limit: int = 60,
    db: Session = Depends(get_db),
):
    """Listagem compacta das peças/documentos vindos do jus.br/Drive, uma linha
    por peça-mãe com seus anexos aninhados — pra identificar cada arquivo pelo
    nome (derivado do próprio nome do arquivo, sem IA) e abrir direto no Drive,
    sem precisar ler o resumo de cada um. Ordena por uma chave única de data/
    hora (protocolado_em quando existe, senão meia-noite de data_andamento) —
    ordenar por data_andamento e protocolado_em como colunas SEPARADAS (cada
    uma com seu próprio nulls_last) fazia andamentos sem hora de protocolo
    "pular" pro fim do dia mesmo quando vieram antes na realidade, o que
    intercalava documento(s) e a petição deles fora de ordem."""
    _get_caso(db, caso_id)
    limit = max(1, min(limit, 200))

    chave_ordem = func.coalesce(
        AndamentoProcesso.protocolado_em,
        cast(AndamentoProcesso.data_andamento, DateTime(timezone=True)),
    )

    base = (
        db.query(AutosIAPeca)
        .join(AndamentoProcesso, AutosIAPeca.andamento_id == AndamentoProcesso.id)
        .filter(
            AutosIAPeca.caso_id == caso_id,
            AutosIAPeca.peca_pai_id.is_(None),
            AutosIAPeca.andamento_id.isnot(None),
        )
    )
    if q and q.strip():
        termo = f"%{q.strip()}%"
        base = base.filter(or_(
            AutosIAPeca.titulo.ilike(termo),
            AutosIAPeca.titulo_customizado.ilike(termo),
            AutosIAPeca.nota_usuario.ilike(termo),
            AutosIAPeca.id_processual.ilike(termo),
            func.array_to_string(AutosIAPeca.keywords_usuario, " ").ilike(termo),
            AndamentoProcesso.arquivo_nome.ilike(termo),
        ))
    if ordem == "asc":
        base = base.order_by(chave_ordem.asc().nulls_last(), AutosIAPeca.pagina_inicio.asc())
    else:
        base = base.order_by(chave_ordem.desc().nulls_last(), AutosIAPeca.pagina_inicio.desc())
    principais = base.offset(max(0, offset)).limit(limit).all()

    anexos: list[AutosIAPeca] = []
    if principais:
        anexos = (
            db.query(AutosIAPeca)
            .filter(AutosIAPeca.peca_pai_id.in_([p.id for p in principais]))
            .order_by(AutosIAPeca.pagina_inicio.asc())
            .all()
        )

    andamento_ids = {p.andamento_id for p in [*principais, *anexos] if p.andamento_id}
    andamentos_por_id: dict[uuid.UUID, AndamentoProcesso] = {}
    if andamento_ids:
        for a in db.query(AndamentoProcesso).filter(AndamentoProcesso.id.in_(andamento_ids)).all():
            andamentos_por_id[a.id] = a

    anexos_por_pai: dict[uuid.UUID, list[DocumentoDriveAnexoOut]] = {}
    for a in anexos:
        anexos_por_pai.setdefault(a.peca_pai_id, []).append(
            _montar_documento_drive(a, andamentos_por_id.get(a.andamento_id))
        )

    resultado = []
    for p in principais:
        item = DocumentoDriveOut(
            **_montar_documento_drive(p, andamentos_por_id.get(p.andamento_id)).model_dump(),
            anexos=anexos_por_pai.get(p.id, []),
        )
        resultado.append(item)
    return resultado


@router.get("/pecas/{peca_id}", response_model=PecaDetalheOut)
def obter_peca(peca_id: uuid.UUID, db: Session = Depends(get_db)):
    peca = db.query(AutosIAPeca).filter(AutosIAPeca.id == peca_id).first()
    if not peca:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    return peca


@router.patch("/pecas/{peca_id}/tipo", response_model=PecaOut)
def atualizar_tipo_peca(peca_id: uuid.UUID, data: PecaTipoUpdate, db: Session = Depends(get_db)):
    """Override manual do tipo de uma peça — usado na aba Documentos pra marcar/
    desmarcar uma linha como petição quando a classificação automática (IA ou
    agrupamento por hora de protocolo) erra."""
    peca = db.query(AutosIAPeca).filter(AutosIAPeca.id == peca_id).first()
    if not peca:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    peca.tipo = data.tipo
    db.commit()
    db.refresh(peca)
    return peca


@router.patch("/pecas/{peca_id}/anotacao", response_model=PecaOut)
def atualizar_anotacao_peca(peca_id: uuid.UUID, data: PecaAnotacaoUpdate, db: Session = Depends(get_db)):
    """Anotação própria do Lucas numa peça — nota livre, palavras-chave e um
    título customizado (o nome original nunca é sobrescrito, só deixa de ser
    o texto principal exibido). Só altera os campos enviados; mandar um campo
    como null o limpa de propósito."""
    peca = db.query(AutosIAPeca).filter(AutosIAPeca.id == peca_id).first()
    if not peca:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(peca, campo, valor)
    db.commit()
    db.refresh(peca)
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
