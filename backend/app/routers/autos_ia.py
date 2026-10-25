"""Autos IA — leitura incremental de autos processuais volumosos, em paralelo
ao restante do gestor. Cada Caso é um processo independente; os PDFs são
enviados em blocos de páginas, segmentados em peças e resumidos por IA."""
import logging
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, defer

from app.database import SessionLocal, get_db
from app.dependencies import get_current_user
from app.models.andamento import AndamentoProcesso
from app.models.autos_ia import AutosIACaso, AutosIADocumento, AutosIAPeca, AutosIAPerguntaFaq, AutosIAReferencia
from app.schemas.autos_ia import (
    AdicionarAdvogadoIn, AdvogadosPartesOut, CenarioCreateIn, CenarioOut, CenarioUpdateIn, MapaEntidadesOut, SugestaoLinhaOut, ConflitosAdvogadosOut, ContradicoesOut, CruzamentosAdvogadosOut, MatrizPosicoesOut, OpcoesPosicoesOut, PosicaoOut, PosicaoUpdateIn, PosicoesListaOut, PosicoesStatusOut, DeterminacaoOut, DeterminacaoUpdateIn, DeterminacoesListaOut, DeterminacoesStatusOut, IntimacaoIn, MinutaOut, OpcoesDeterminacoesOut, AnexoCorroboracaoOut, FatoValorOut, FatoValorUpdateIn, FatosValoresListaOut, FatosValoresStatusOut, ReconciliacaoOut, RenomearSujeitoIn, TemaOut, AlertaConfigOut, AlertaConfigUpdate, CasoCreate, CasoOut, CasoResumo, CasoUpdate, DocumentoDriveAnexoOut, DocumentoDriveOut, DocumentoOut,
    EstimativaImportacaoOut, ExportMdStatusOut, FaqPerguntaCreate, PastasDriveOut, FaqPerguntaOut, GrafoAresta, GrafoNo, GrafoOut, PecaAnotacaoUpdate,
    PecaDetalheOut, PecaOut, PecaTipoUpdate, PrincipalIn, RenomearAdvogadoIn, VinculoIn,
)
from app.services.autos_ia import faq as faq_service
from app.services.autos_ia.busca import buscar_pecas
from app.services.autos_ia import advogados_partes, cenarios, cruzamentos_advogados, mapa_entidades, export_md_drive, fatos_determinacoes, fatos_posicoes, fatos_valores
from app.services.autos_ia.estimativa import estimar_importacao_existentes, estimar_reclassificacao
from app.services.autos_ia.ingestao import processar_documento, reclassificar_caso, retomar_documento
from app.services.autos_ia.jusbr_import import (
    atualizar_metadados_jusbr, contar_pecas_pendentes_resumo, importar_apenas_existentes,
    listar_andamentos_pendentes, reagrupar_pecas_jusbr, recalcular_ids_processuais, reler_peca,
    reler_pecas_pendentes, resumir_pendentes_agora, sincronizar_caso_jusbr,
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
    quebrada. Tenta até 3x com espera curta: reproduzido ao vivo um caso em
    que até essa sessão nova falhou de cara (Postgres recusando conexão
    nova, não só uma conexão velha morta) — mas essas janelas de
    indisponibilidade total observadas até agora duraram só alguns
    segundos, então uma segunda/terceira tentativa tem boa chance de
    conseguir gravar o status em vez de deixar o caso preso."""
    for tentativa in range(3):
        if tentativa:
            time.sleep(1.5 * tentativa)
        db = SessionLocal()
        try:
            caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
            if caso:
                caso.ultimo_sync_status = "erro"
                caso.ultimo_sync_mensagem = mensagem[:500]
                caso.sync_etapa = None
                caso.sync_total_itens = None
                caso.sync_itens_processados = None
                caso.sync_detalhe = None
                db.commit()
            return
        except Exception:
            logger.warning(
                "Autos IA: falha ao registrar erro do caso %s na tentativa %d/3 (banco indisponível?)",
                caso_id, tentativa + 1,
            )
        finally:
            db.close()
    logger.error("Autos IA: não foi possível registrar erro do caso %s em 3 tentativas — banco indisponível", caso_id)


def _executar_sync_em_background(caso_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
        if caso:
            sincronizar_caso_jusbr(db, caso, _carregar_sessao_jusbr())
            # Mesmo alerta (Telegram + e-mail) das sincronizações automáticas. Nunca lança.
            from app.services.autos_ia.alertas import enviar_alertas_pos_sync
            enviar_alertas_pos_sync(caso_id)
            # Atualiza a pasta "Andamentos (MD)" do Drive (só em casos já exportados). Nunca lança.
            export_md_drive.exportar_pos_sync(caso_id)
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


# ── Exportação .md (resumo + inteiro teor) para o Drive ──────────────────────

@router.get("/casos/{caso_id}/advogados-partes", response_model=AdvogadosPartesOut)
def advogados_e_partes(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    """Relação advogados × partes (só petições): por advogado → partes e por parte → advogados."""
    _get_caso(db, caso_id)
    return advogados_partes.montar_relacao(db, caso_id)


def _editar_relacao(db: Session, caso_id: uuid.UUID, fn, *args):
    _get_caso(db, caso_id)
    try:
        return fn(db, caso_id, *args)
    except advogados_partes.RelacaoErro as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/casos/{caso_id}/advogados-partes/renomear", response_model=AdvogadosPartesOut)
def renomear_advogado(caso_id: uuid.UUID, data: RenomearAdvogadoIn, db: Session = Depends(get_db)):
    """Muda o nome de exibição do advogado (com OAB, vale para todas as partes e casos)."""
    return _editar_relacao(db, caso_id, advogados_partes.renomear_advogado, data.adv_id, data.nome)


@router.post("/casos/{caso_id}/advogados-partes/adicionar", response_model=AdvogadosPartesOut)
def adicionar_advogado(caso_id: uuid.UUID, data: AdicionarAdvogadoIn, db: Session = Depends(get_db)):
    """Adiciona um advogado (com ou sem OAB) a uma parte já mapeada."""
    return _editar_relacao(db, caso_id, advogados_partes.adicionar_advogado, data.parte_chave, data.nome, data.oab)


@router.post("/casos/{caso_id}/advogados-partes/principal", response_model=AdvogadosPartesOut)
def definir_advogado_principal(caso_id: uuid.UUID, data: PrincipalIn, db: Session = Depends(get_db)):
    """Marca qual advogado é o principal da parte (um por parte); adv_id nulo desmarca."""
    return _editar_relacao(db, caso_id, advogados_partes.definir_principal, data.parte_chave, data.adv_id)


@router.post("/casos/{caso_id}/advogados-partes/remover", response_model=AdvogadosPartesOut)
def remover_advogado(caso_id: uuid.UUID, data: VinculoIn, db: Session = Depends(get_db)):
    """Tira o advogado da parte (dá para restaurar)."""
    return _editar_relacao(db, caso_id, advogados_partes.remover_advogado, data.parte_chave, data.adv_id)


@router.post("/casos/{caso_id}/advogados-partes/restaurar", response_model=AdvogadosPartesOut)
def restaurar_advogado(caso_id: uuid.UUID, data: VinculoIn, db: Session = Depends(get_db)):
    return _editar_relacao(db, caso_id, advogados_partes.restaurar_advogado, data.parte_chave, data.adv_id)


# ── Banco de fatos: valores (R$) e reconciliador de números ──────────────────

@router.get("/fatos/temas", response_model=list[TemaOut])
def temas_fatos():
    return [{"chave": k, "rotulo": fatos_valores.TEMA_ROTULO[k]} for k in fatos_valores.TEMAS]


@router.get("/casos/{caso_id}/fatos/valores/status", response_model=FatosValoresStatusOut)
def status_fatos_valores(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    return fatos_valores.status_extracao(db, caso_id)


@router.post("/casos/{caso_id}/fatos/valores/extrair", response_model=FatosValoresStatusOut, status_code=status.HTTP_202_ACCEPTED)
def extrair_fatos_valores(
    caso_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    forcar: bool = Query(False, description="Reextrai mesmo as peças já processadas"),
    limite_pecas: int | None = Query(None, ge=1, le=2000, description="Máximo de peças (amostra)"),
    db: Session = Depends(get_db),
):
    """Extrai e rotula os valores em R$ das peças narrativas (usa IA; custo aparece no status)."""
    _get_caso(db, caso_id)
    atual = fatos_valores.status_extracao(db, caso_id)
    if atual["estado"] == "rodando":
        return atual
    background_tasks.add_task(fatos_valores.extrair_caso, caso_id, forcar, limite_pecas)
    atual["estado"] = "rodando"
    atual["mensagem"] = "Iniciando…"
    return atual


@router.get("/casos/{caso_id}/fatos/valores/reconciliacao", response_model=ReconciliacaoOut)
def reconciliacao_valores(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    """Divergências (mesmo tema e sujeito, números diferentes) e corroborações (mesmo número em várias peças)."""
    _get_caso(db, caso_id)
    return fatos_valores.reconciliar(db, caso_id)


@router.post("/casos/{caso_id}/fatos/valores/renomear-sujeito")
def renomear_sujeito_valores(caso_id: uuid.UUID, data: RenomearSujeitoIn, db: Session = Depends(get_db)):
    """Unifica à mão um nome de sujeito em todos os valores do caso."""
    _get_caso(db, caso_id)
    try:
        return {"atualizados": fatos_valores.renomear_sujeito(db, caso_id, data.de, data.para)}
    except fatos_valores.FatoErro as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/casos/{caso_id}/fatos/valores", response_model=FatosValoresListaOut)
def listar_valores(
    caso_id: uuid.UUID,
    tema: str | None = None, afirmante: str | None = None, natureza: str | None = None,
    q: str | None = None, status_fato: str | None = Query(None, alias="status"),
    minimo_reais: float | None = Query(None, ge=0), maximo_reais: float | None = Query(None, ge=0),
    limite: int = Query(200, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    _get_caso(db, caso_id)
    filtros = {
        "tema": tema, "afirmante": afirmante, "natureza": natureza, "q": q, "status": status_fato,
        "minimo": int(minimo_reais * 100) if minimo_reais is not None else None,
        "maximo": int(maximo_reais * 100) if maximo_reais is not None else None,
    }
    return fatos_valores.listar_fatos(db, caso_id, filtros, limite, offset)


@router.get("/casos/{caso_id}/fatos/valores/{fato_id}/anexos", response_model=list[AnexoCorroboracaoOut])
def anexos_do_valor(caso_id: uuid.UUID, fato_id: uuid.UUID, db: Session = Depends(get_db)):
    """Outras peças — sobretudo anexos (extratos, contratos, planilhas) — em que o mesmo valor aparece escrito igual."""
    _get_caso(db, caso_id)
    return fatos_valores.anexos_com_valor(db, caso_id, fato_id)


@router.patch("/casos/{caso_id}/fatos/valores/{fato_id}", response_model=FatoValorOut)
def atualizar_valor(caso_id: uuid.UUID, fato_id: uuid.UUID, data: FatoValorUpdateIn, db: Session = Depends(get_db)):
    """Valida, rejeita ou edita (tema, sujeito, nota) um valor — decisão humana nunca é sobrescrita."""
    _get_caso(db, caso_id)
    try:
        return fatos_valores.atualizar_fato(
            db, caso_id, fato_id, tema=data.tema, sujeito_canonico=data.sujeito_canonico, status=data.status,
            nota=data.nota, nota_definida="nota" in data.model_fields_set,
        )
    except fatos_valores.FatoErro as exc:
        db.rollback()
        raise HTTPException(status_code=422 if "não encontrado" not in str(exc) else 404, detail=str(exc))


# ── Banco de fatos: determinações do Juízo e quadro de cumprimento ───────────

STATUS_ROTULO = {
    "cumprida": "Cumprida", "parcial": "Cumprida em parte", "nao_localizada": "Cumprimento não localizado",
    "em_prazo": "Em prazo", "prejudicada": "Prejudicada", "nao_aplicavel": "Sem ato a verificar",
    "vencida_sem_cumprimento": "Vencida sem cumprimento", "nao_avaliada": "Ainda não avaliada",
}


@router.get("/fatos/determinacoes/opcoes", response_model=OpcoesDeterminacoesOut)
def opcoes_determinacoes():
    return {
        "destinatarios": [{"chave": k, "rotulo": v} for k, v in fatos_determinacoes.DEST_ROTULO.items()],
        "temas": [{"chave": k, "rotulo": v} for k, v in fatos_determinacoes.TEMA_DET_ROTULO.items()],
        "status": [{"chave": k, "rotulo": v} for k, v in STATUS_ROTULO.items()],
    }


@router.get("/casos/{caso_id}/fatos/determinacoes/status", response_model=DeterminacoesStatusOut)
def status_determinacoes(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    return fatos_determinacoes.status_extracao(db, caso_id)


@router.post("/casos/{caso_id}/fatos/determinacoes/extrair", response_model=DeterminacoesStatusOut, status_code=status.HTTP_202_ACCEPTED)
def extrair_determinacoes(
    caso_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    forcar: bool = Query(False, description="Relê também os atos já lidos"),
    db: Session = Depends(get_db),
):
    """Lê as ordens dos atos do Juízo ainda não lidos e reavalia o cumprimento contra as peças posteriores (usa IA)."""
    _get_caso(db, caso_id)
    atual = fatos_determinacoes.status_extracao(db, caso_id)
    if atual["estado"] == "rodando":
        return atual
    background_tasks.add_task(fatos_determinacoes.extrair_caso, caso_id, forcar, True)
    atual["estado"] = "rodando"
    atual["mensagem"] = "Iniciando…"
    return atual


@router.get("/casos/{caso_id}/fatos/determinacoes/minuta", response_model=MinutaOut)
def minuta_determinacoes(caso_id: uuid.UUID, destinatario_tipo: str | None = None, db: Session = Depends(get_db)):
    """Quadro de ordens vencidas/sem cumprimento comprovado, em Markdown, para colar numa petição."""
    _get_caso(db, caso_id)
    return {"markdown": fatos_determinacoes.minuta_descumprimento(db, caso_id, destinatario_tipo)}


@router.post("/casos/{caso_id}/fatos/determinacoes/decisao/{peca_id}/intimacao")
def intimacao_da_decisao(caso_id: uuid.UUID, peca_id: uuid.UUID, data: IntimacaoIn, db: Session = Depends(get_db)):
    """Informa a data de intimação (início da contagem) das ordens de uma decisão."""
    _get_caso(db, caso_id)
    try:
        return {"atualizadas": fatos_determinacoes.definir_intimacao(db, caso_id, peca_id, data.data)}
    except fatos_determinacoes.DeterminacaoErro as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/casos/{caso_id}/fatos/determinacoes", response_model=DeterminacoesListaOut)
def listar_determinacoes(
    caso_id: uuid.UUID,
    destinatario_tipo: str | None = None, status_cumprimento: str | None = Query(None, alias="status"),
    tema: str | None = None, decisao: str | None = None, mediacao: bool = False, q: str | None = None,
    db: Session = Depends(get_db),
):
    _get_caso(db, caso_id)
    return fatos_determinacoes.listar(db, caso_id, {
        "destinatario_tipo": destinatario_tipo, "status": status_cumprimento, "tema": tema,
        "decisao": decisao, "mediacao": mediacao, "q": q,
    })


@router.patch("/casos/{caso_id}/fatos/determinacoes/{fato_id}", response_model=DeterminacaoOut)
def atualizar_determinacao(caso_id: uuid.UUID, fato_id: uuid.UUID, data: DeterminacaoUpdateIn, db: Session = Depends(get_db)):
    """Decisão humana sobre uma ordem: status manual (prevalece sobre a IA), nota, validar ou rejeitar."""
    _get_caso(db, caso_id)
    try:
        return fatos_determinacoes.atualizar(
            db, caso_id, fato_id, status_manual=data.status_manual, nota=data.nota,
            nota_definida="nota" in data.model_fields_set, rejeitar=data.rejeitar, validar=data.validar,
        )
    except fatos_determinacoes.DeterminacaoErro as exc:
        db.rollback()
        raise HTTPException(status_code=404 if "não encontrada" in str(exc) else 422, detail=str(exc))


@router.get("/casos/{caso_id}/advogados-cruzamentos", response_model=CruzamentosAdvogadosOut)
def cruzamentos_dos_advogados(
    caso_id: uuid.UUID,
    min_partes: int = Query(2, ge=1, le=50, description="Partes em comum para dois advogados contarem como parceiros"),
    db: Session = Depends(get_db),
):
    """Valor indicativo representado por advogado, bancas (advogados que dividem clientes) e blocos de partes."""
    _get_caso(db, caso_id)
    return cruzamentos_advogados.montar(db, caso_id, min_partes=min_partes)


# ── Posições (matriz, contradições, conflitos de advogados) ──────────────────

@router.get("/fatos/posicoes/opcoes", response_model=OpcoesPosicoesOut)
def opcoes_posicoes():
    return {
        "temas": [{"chave": k, "rotulo": v} for k, v in fatos_posicoes.TEMA_POS_ROTULO.items()],
        "posicoes": [{"chave": k, "rotulo": v} for k, v in fatos_posicoes.POSICAO_ROTULO.items()],
    }


@router.get("/casos/{caso_id}/fatos/posicoes/status", response_model=PosicoesStatusOut)
def status_posicoes(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    return fatos_posicoes.status_extracao(db, caso_id)


@router.post("/casos/{caso_id}/fatos/posicoes/extrair", response_model=PosicoesStatusOut, status_code=status.HTTP_202_ACCEPTED)
def extrair_posicoes(
    caso_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    forcar: bool = Query(False, description="Relê também as peças já lidas"),
    limite_pecas: int | None = Query(None, ge=1),
    db: Session = Depends(get_db),
):
    """Lê, com IA, as posições que cada autor assume nas peças narrativas ainda não lidas."""
    _get_caso(db, caso_id)
    atual = fatos_posicoes.status_extracao(db, caso_id)
    if atual["estado"] == "rodando":
        return atual
    background_tasks.add_task(fatos_posicoes.extrair_caso, caso_id, forcar, limite_pecas)
    atual["estado"] = "rodando"
    atual["mensagem"] = "Iniciando…"
    return atual


@router.get("/casos/{caso_id}/fatos/posicoes/matriz", response_model=MatrizPosicoesOut)
def matriz_posicoes(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    return fatos_posicoes.matriz(db, caso_id)


@router.get("/casos/{caso_id}/fatos/posicoes/contradicoes", response_model=ContradicoesOut)
def contradicoes_posicoes(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    return fatos_posicoes.contradicoes(db, caso_id)


@router.get("/casos/{caso_id}/fatos/posicoes/conflitos-advogados", response_model=ConflitosAdvogadosOut)
def conflitos_de_advogados(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    """Advogados que representam partes com posições opostas no mesmo tema."""
    _get_caso(db, caso_id)
    return fatos_posicoes.conflitos_advogados(db, caso_id)


@router.get("/casos/{caso_id}/fatos/posicoes", response_model=PosicoesListaOut)
def listar_posicoes(
    caso_id: uuid.UUID, tema: str | None = None, posicao: str | None = None, participante: str | None = None,
    status_posicao: str | None = Query(None, alias="status"), q: str | None = None, db: Session = Depends(get_db),
):
    _get_caso(db, caso_id)
    return fatos_posicoes.listar(db, caso_id, {"tema": tema, "posicao": posicao, "participante": participante, "status": status_posicao, "q": q})


@router.patch("/casos/{caso_id}/fatos/posicoes/{fato_id}", response_model=PosicaoOut)
def atualizar_posicao(caso_id: uuid.UUID, fato_id: uuid.UUID, data: PosicaoUpdateIn, db: Session = Depends(get_db)):
    """Valida, corrige (posição/tema/nota) ou rejeita uma posição extraída."""
    _get_caso(db, caso_id)
    try:
        return fatos_posicoes.atualizar(db, caso_id, fato_id, posicao=data.posicao, tema=data.tema, status=data.status,
                                        nota=data.nota, nota_definida="nota" in data.model_fields_set)
    except fatos_posicoes.PosicaoErro as exc:
        db.rollback()
        raise HTTPException(status_code=404 if "não encontrada" in str(exc) else 422, detail=str(exc))


# ── Mapa de entidades (ativo × passivo) e cenários de recuperação ─────────────

@router.get("/casos/{caso_id}/mapa-entidades", response_model=MapaEntidadesOut)
def mapa_de_entidades(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    """Ativo × passivo por entidade/grupo, com o valor mais sustentado, as alternativas e as peças de origem."""
    _get_caso(db, caso_id)
    return mapa_entidades.mapa(db, caso_id)


@router.get("/casos/{caso_id}/cenarios/sugestoes", response_model=list[SugestaoLinhaOut])
def sugestoes_de_linhas(caso_id: uuid.UUID, q: str | None = None, db: Session = Depends(get_db)):
    """Valores do banco de fatos que podem virar linha de um cenário."""
    _get_caso(db, caso_id)
    return cenarios.sugestoes(db, caso_id, q)


@router.get("/casos/{caso_id}/cenarios", response_model=list[CenarioOut])
def listar_cenarios(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    return cenarios.listar(db, caso_id)


@router.post("/casos/{caso_id}/cenarios", response_model=CenarioOut, status_code=status.HTTP_201_CREATED)
def criar_cenario(caso_id: uuid.UUID, data: CenarioCreateIn, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    try:
        return cenarios.criar(db, caso_id, data.nome, [l.model_dump() for l in data.linhas], data.notas)
    except cenarios.CenarioErro as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/casos/{caso_id}/cenarios/{cenario_id}/duplicar", response_model=CenarioOut, status_code=status.HTTP_201_CREATED)
def duplicar_cenario(caso_id: uuid.UUID, cenario_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    try:
        return cenarios.duplicar(db, caso_id, cenario_id)
    except cenarios.CenarioErro as exc:
        db.rollback()
        raise HTTPException(status_code=404 if "não encontrado" in str(exc) else 422, detail=str(exc))


@router.put("/casos/{caso_id}/cenarios/{cenario_id}", response_model=CenarioOut)
def atualizar_cenario(caso_id: uuid.UUID, cenario_id: uuid.UUID, data: CenarioUpdateIn, db: Session = Depends(get_db)):
    """Salva o nome, as notas e/ou a lista COMPLETA de linhas (a planilha inteira)."""
    _get_caso(db, caso_id)
    try:
        return cenarios.atualizar(db, caso_id, cenario_id, nome=data.nome, notas=data.notas, notas_definida="notas" in data.model_fields_set,
                                  linhas=None if data.linhas is None else [l.model_dump() for l in data.linhas])
    except cenarios.CenarioErro as exc:
        db.rollback()
        raise HTTPException(status_code=404 if "não encontrado" in str(exc) else 422, detail=str(exc))


@router.delete("/casos/{caso_id}/cenarios/{cenario_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_cenario(caso_id: uuid.UUID, cenario_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    try:
        cenarios.excluir(db, caso_id, cenario_id)
    except cenarios.CenarioErro as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/casos/{caso_id}/pastas-drive", response_model=PastasDriveOut)
def pastas_drive(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    return export_md_drive.links_pastas(db, caso_id)


@router.get("/casos/{caso_id}/exportar-md-drive", response_model=ExportMdStatusOut)
def status_exportar_md_drive(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_caso(db, caso_id)
    return export_md_drive.status_exportacao(db, caso_id)


@router.post("/casos/{caso_id}/exportar-md-drive", response_model=ExportMdStatusOut, status_code=status.HTTP_202_ACCEPTED)
def exportar_md_drive(
    caso_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    limite: int | None = Query(None, ge=1, le=5000, description="Máximo de envios (amostra)"),
    forcar: bool = Query(False, description="Reenvia mesmo o que não mudou"),
    db: Session = Depends(get_db),
):
    caso = _get_caso(db, caso_id)
    if not caso.processo_id:
        raise HTTPException(status_code=422, detail="Este caso não está vinculado a um processo (a pasta do Drive depende dele).")
    atual = export_md_drive.status_exportacao(db, caso_id)
    if atual["estado"] == "rodando":
        return atual
    background_tasks.add_task(export_md_drive.exportar_caso, caso.id, limite, forcar)
    atual["estado"] = "rodando"
    atual["mensagem"] = "Iniciando…"
    return atual


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
        # O que mudou nas peças vai pro .md do Drive (só casos já exportados; nunca lança).
        export_md_drive.agendar_exportacao(caso_id)


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
            total = reagrupar_pecas_jusbr(db, caso)
            caso.ultimo_sync_status = "ok"
            caso.ultimo_sync_mensagem = f"{total} peça(s) reagrupada(s) (petição/anexo)."
            caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
            db.commit()
    except Exception as exc:
        # Nunca tenta recuperar e reaproveitar `db` aqui: já reproduzimos ao
        # vivo um caso em que db.rollback() "funcionava" (sem lançar) e a
        # query seguinte na MESMA sessão falhava de novo com
        # PendingRollbackError — a conexão pode ficar irrecuperável de
        # verdade, não só com a transação abortada. _forcar_status_erro
        # sempre abre uma sessão nova, comprovadamente confiável.
        logger.exception("Autos IA: reagrupar do caso %s travou de forma inesperada", caso_id)
        _forcar_status_erro(caso_id, f"Interrompida por um erro inesperado: {exc}")
    finally:
        db.close()
        # O que mudou nas peças vai pro .md do Drive (só casos já exportados; nunca lança).
        export_md_drive.agendar_exportacao(caso_id)


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


def _executar_recalcular_ids_em_background(caso_id: uuid.UUID) -> None:
    from datetime import datetime, timezone
    db = SessionLocal()
    try:
        caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
        if caso:
            atualizadas, reconectadas = recalcular_ids_processuais(db, caso)
            caso.ultimo_sync_status = "ok"
            caso.ultimo_sync_mensagem = (
                f"{atualizadas} peça(s) com ID corrigido, {reconectadas} referência(s) reconectada(s)."
            )
            caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
            db.commit()
    except Exception as exc:
        # Mesmo cuidado do reagrupar logo acima: nunca tenta recuperar `db`
        # depois de uma falha — _forcar_status_erro abre sessão nova.
        logger.exception("Autos IA: recalcular-ids do caso %s travou de forma inesperada", caso_id)
        _forcar_status_erro(caso_id, f"Interrompida por um erro inesperado: {exc}")
    finally:
        db.close()
        # O que mudou nas peças vai pro .md do Drive (só casos já exportados; nunca lança).
        export_md_drive.agendar_exportacao(caso_id)


@router.post("/casos/{caso_id}/recalcular-ids", response_model=CasoOut, status_code=status.HTTP_202_ACCEPTED)
def recalcular_ids_agora(caso_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Corrige id_processual das peças já importadas usando o documento_id que o
    jus.br já entrega pronto no andamento, e reconecta referências que dependiam
    disso — 100% local, sem IA nem rede, e sem mexer em peca_pai_id/tipo (ao
    contrário de /reagrupar, isso preserva qualquer reorganização manual feita
    pelo usuário via tornar-principal/anexar-a/desvincular)."""
    caso = _get_caso(db, caso_id)
    if caso.ultimo_sync_status == "processando":
        raise HTTPException(status_code=422, detail="Já há uma sincronização/reagrupamento em andamento.")
    caso.ultimo_sync_status = "processando"
    caso.ultimo_sync_mensagem = None
    db.commit()
    db.refresh(caso)
    background_tasks.add_task(_executar_recalcular_ids_em_background, caso.id)
    return caso


def _executar_importacao_existentes_em_background(caso_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
        if caso:
            importar_apenas_existentes(db, caso)
    except Exception as exc:
        # Rede de segurança: importar_apenas_existentes já trata falha e
        # rollback internamente, mas se mesmo assim algo escapar (ex.: a
        # própria busca do caso falhar), sem isso o caso ficava preso em
        # "processando" pra sempre. Mesmo padrão do resto do módulo.
        logger.exception("Autos IA: importar-existentes do caso %s travou de forma inesperada", caso_id)
        _forcar_status_erro(caso_id, f"Interrompida por um erro inesperado: {exc}")
    finally:
        db.close()
        # O que mudou nas peças vai pro .md do Drive (só casos já exportados; nunca lança).
        export_md_drive.agendar_exportacao(caso_id)


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


def _executar_resumir_pendentes_em_background(caso_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
        if caso:
            resumir_pendentes_agora(db, caso)
    except Exception as exc:
        logger.exception("Autos IA: resumir-pendentes do caso %s travou de forma inesperada", caso_id)
        _forcar_status_erro(caso_id, f"Interrompida por um erro inesperado: {exc}")
    finally:
        db.close()
        # O que mudou nas peças vai pro .md do Drive (só casos já exportados; nunca lança).
        export_md_drive.agendar_exportacao(caso_id)


@router.post("/casos/{caso_id}/resumir-pendentes", response_model=CasoOut, status_code=status.HTTP_202_ACCEPTED)
def resumir_pendentes_endpoint(caso_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Só resume o backlog de peças já lidas (texto extraído, já viraram peça)
    mas ainda sem resumo por IA — sem consultar jus.br/PDPJ nem ler nenhum
    andamento novo. Útil depois de uma sincronização grande interrompida no
    meio da leitura, pra não esperar reler o resto dos documentos pendentes
    só pra processar o que já foi lido."""
    caso = _get_caso(db, caso_id)
    if caso.ultimo_sync_status == "processando":
        raise HTTPException(status_code=422, detail="Já há uma sincronização em andamento.")
    caso.ultimo_sync_status = "processando"
    caso.ultimo_sync_mensagem = None
    db.commit()
    db.refresh(caso)
    background_tasks.add_task(_executar_resumir_pendentes_em_background, caso.id)
    return caso


def _executar_reler_pendentes_em_background(caso_id: uuid.UUID) -> None:
    from datetime import datetime, timezone
    db = SessionLocal()
    try:
        caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
        if caso:
            sucesso, falha = reler_pecas_pendentes(db, caso)
            caso.ultimo_sync_status = "cancelado" if caso.sync_cancelar else "ok"
            caso.ultimo_sync_mensagem = (
                f"{sucesso} peça(s) relida(s) com sucesso" + (f", {falha} falharam de novo." if falha else ".")
                if (sucesso or falha) else "Nenhuma peça com falha de leitura pendente."
            )
            caso.sync_etapa = None
            caso.sync_total_itens = None
            caso.sync_itens_processados = None
            caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
            db.commit()
    except Exception as exc:
        logger.exception("Autos IA: reler-pendentes do caso %s travou de forma inesperada", caso_id)
        _forcar_status_erro(caso_id, f"Interrompida por um erro inesperado: {exc}")
    finally:
        db.close()
        # O que mudou nas peças vai pro .md do Drive (só casos já exportados; nunca lança).
        export_md_drive.agendar_exportacao(caso_id)


@router.post("/casos/{caso_id}/reler-pendentes", response_model=CasoOut, status_code=status.HTTP_202_ACCEPTED)
def reler_pendentes_endpoint(caso_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Reler (baixar de novo do Drive + resumir de novo) TODAS as peças deste
    caso que ficaram com falha de leitura registrada — inclui as que já
    viraram "resumida" com um resumo genérico (a IA não falhou, só recebeu
    pouco texto pra trabalhar). Sequencial, uma peça de cada vez, pra não
    sobrecarregar rede/IA de uma vez só."""
    caso = _get_caso(db, caso_id)
    if caso.ultimo_sync_status == "processando":
        raise HTTPException(status_code=422, detail="Já há uma sincronização em andamento.")
    caso.ultimo_sync_status = "processando"
    caso.ultimo_sync_mensagem = None
    db.commit()
    db.refresh(caso)
    background_tasks.add_task(_executar_reler_pendentes_em_background, caso.id)
    return caso


@router.get("/casos/{caso_id}/pecas-pendentes-resumo")
def contar_pendentes_resumo_endpoint(caso_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    caso = _get_caso(db, caso_id)
    return {"pendentes": contar_pecas_pendentes_resumo(db, caso)}


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
    caso.sync_detalhe = None
    db.commit()
    db.refresh(caso)
    return caso


@router.post("/casos/{caso_id}/pular-documento-atual", response_model=CasoOut)
def pular_documento_atual(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    """Pula só o documento que está sendo lido/OCR'd agora — ao contrário de
    cancelar-sync (para tudo), a sincronização continua para o próximo
    documento. Útil pra um documento grande demais (centenas de páginas)
    sem interromper o resto. A peça desse documento fica marcada como
    "leitura pulada" (o link pro Drive continua lá pra ler depois manualmente
    — ver POST /pecas/{id}/reler-completo)."""
    caso = _get_caso(db, caso_id)
    if caso.ultimo_sync_status != "processando":
        raise HTTPException(status_code=422, detail="Não há sincronização em andamento.")
    caso.sync_pular_atual = True
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
    except Exception as exc:
        # Rede de segurança: reclassificar_caso já trata falha e rollback
        # internamente, mas se mesmo assim algo escapar, sem isso o caso
        # ficava preso em "processando" pra sempre. Mesmo padrão do resto do
        # módulo (ver _executar_sync_em_background).
        logger.exception("Autos IA: reclassificar do caso %s travou de forma inesperada", caso_id)
        _forcar_status_erro(caso_id, f"Interrompida por um erro inesperado: {exc}")
    finally:
        db.close()
        # O que mudou nas peças vai pro .md do Drive (só casos já exportados; nunca lança).
        export_md_drive.agendar_exportacao(caso_id)


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
        offset=max(0, offset), limite=limit, sem_texto=True,
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
        advogado_responsavel=peca.advogado_responsavel,
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
    sem precisar ler o resumo de cada um.

    Ordena por dia (data_andamento) e, dentro do dia, pela hora real de
    protocolo (protocolado_em) quando ela existe — é o que de fato distingue
    petição/decisão dos documentos que vieram junto na mesma hora — com
    pagina_inicio como desempate final entre itens da mesma hora (ou sem
    hora nenhuma). O cuidado é só no que falta hora de protocolo: em vez de
    cair pra meia-noite do dia (que empurrava o item pro INÍCIO do dia mesmo
    sendo, pela página, um dos ÚLTIMOS daquele lote — reproduzido de verdade
    no Apex: os 3 últimos andamentos de 25/09, sem hora registrada, apareciam
    antes de itens com página bem menor do mesmo dia), ele fica no fim do dia
    em ordem crescente (e, simetricamente, no topo em ordem decrescente) —
    geralmente são mesmo andamentos administrativos que fecham o dia
    (disponibilização no DJ, decurso de prazo etc.), não o contrário."""
    _get_caso(db, caso_id)
    limit = max(1, min(limit, 200))

    base = (
        db.query(AutosIAPeca)
        .options(defer(AutosIAPeca.texto_md))
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
            AutosIAPeca.advogado_responsavel.ilike(termo),
            AutosIAPeca.id_processual.ilike(termo),
            func.array_to_string(AutosIAPeca.keywords_usuario, " ").ilike(termo),
            AndamentoProcesso.arquivo_nome.ilike(termo),
        ))
    if ordem == "asc":
        base = base.order_by(
            AndamentoProcesso.data_andamento.asc().nulls_last(),
            AndamentoProcesso.protocolado_em.asc().nulls_last(),
            AutosIAPeca.pagina_inicio.asc(),
        )
    else:
        base = base.order_by(
            AndamentoProcesso.data_andamento.desc().nulls_last(),
            AndamentoProcesso.protocolado_em.desc().nulls_first(),
            # pagina_inicio SEMPRE crescente, mesmo aqui: ele só desempata
            # principais de mesmo dia+hora (mesmo lote de submissão) — a
            # ordem decrescente é dos LOTES entre si (o mais recente primeiro),
            # nunca de "quem" veio primeiro DENTRO do mesmo lote. Invertido
            # aqui mostraria documento antes da petição que o originou sempre
            # que os dois batessem no mesmo timestamp — exatamente o efeito
            # que não é desejado (petição 13/doc 14/doc 15 tem que aparecer
            # nessa ordem, nunca 15-14-13, mesmo com o lote 10-11-12 vindo
            # depois por inteiro).
            AutosIAPeca.pagina_inicio.asc(),
        )
    principais = base.offset(max(0, offset)).limit(limit).all()

    anexos: list[AutosIAPeca] = []
    if principais:
        anexos = (
            db.query(AutosIAPeca)
            .options(defer(AutosIAPeca.texto_md))
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


@router.get("/alertas/config", response_model=AlertaConfigOut)
def obter_config_alertas(db: Session = Depends(get_db)):
    """Interruptor e destinatários dos alertas de novo andamento (global, vale pra todos os casos)."""
    from app.services.autos_ia import alertas
    cfg = alertas.obter_config(db)
    return AlertaConfigOut(ativo=cfg.ativo, email_padrao=alertas.emails_master(db), emails_extras=list(cfg.emails_extras or []))


@router.put("/alertas/config", response_model=AlertaConfigOut)
def atualizar_config_alertas(data: AlertaConfigUpdate, db: Session = Depends(get_db)):
    from app.services.autos_ia import alertas
    cfg = alertas.obter_config(db)
    if data.ativo is not None:
        cfg.ativo = data.ativo
    if data.emails_extras is not None:
        try:
            cfg.emails_extras = alertas.normalizar_emails_extras(data.emails_extras)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    db.refresh(cfg)
    return AlertaConfigOut(ativo=cfg.ativo, email_padrao=alertas.emails_master(db), emails_extras=list(cfg.emails_extras or []))


@router.post("/casos/{caso_id}/alerta-teste")
def enviar_alerta_teste_endpoint(caso_id: uuid.UUID, ultimas: int = 5, db: Session = Depends(get_db)):
    """Dispara o alerta de "novo andamento" (e-mail + Telegram) com os últimos
    protocolos do caso, só pra conferir o visual e a entrega. Não marca nada como
    enviado — os alertas reais seguem normalmente depois da próxima sincronização."""
    from app.services.autos_ia.alertas import enviar_alerta_teste
    return enviar_alerta_teste(db, _get_caso(db, caso_id), ultimas=ultimas)


@router.get("/casos/{caso_id}/advogados-responsaveis", response_model=list[str])
def listar_advogados_responsaveis(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    """Nomes de advogado já usados nas anotações deste caso — alimenta a
    sugestão do campo (evita "Dr. Fulano" e "Fulano" virarem dois filtros)."""
    _get_caso(db, caso_id)
    linhas = (
        db.query(AutosIAPeca.advogado_responsavel)
        .filter(AutosIAPeca.caso_id == caso_id, AutosIAPeca.advogado_responsavel.isnot(None))
        .distinct()
        .all()
    )
    return sorted({nome for (nome,) in linhas if nome}, key=str.casefold)


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
    export_md_drive.agendar_exportacao(peca.caso_id, [peca.id])
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
    export_md_drive.agendar_exportacao(peca.caso_id, [peca.id])
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


@router.post("/pecas/{peca_id}/tornar-principal", response_model=PecaOut)
def tornar_principal(peca_id: uuid.UUID, db: Session = Depends(get_db)):
    """Promove uma peça hoje marcada como anexo a principal do seu grupo — o
    antigo principal e os demais anexos passam a ser anexos DELA. Correção
    manual pra quando o agrupamento automático (por hora de protocolo/tipo)
    escolhe o membro errado como principal — pedido do Lucas depois de achar
    mais um caso assim mesmo após o fix automático."""
    peca = db.query(AutosIAPeca).filter(AutosIAPeca.id == peca_id).first()
    if not peca:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if peca.peca_pai_id is None:
        return peca  # já é principal, nada a fazer
    antigo_pai_id = peca.peca_pai_id
    irmaos = (
        db.query(AutosIAPeca)
        .filter(AutosIAPeca.peca_pai_id == antigo_pai_id, AutosIAPeca.id != peca.id)
        .all()
    )
    peca.peca_pai_id = None
    db.flush()  # garante peca.id "livre" antes de outras linhas apontarem pra ele
    antigo_pai = db.query(AutosIAPeca).filter(AutosIAPeca.id == antigo_pai_id).first()
    if antigo_pai:
        antigo_pai.peca_pai_id = peca.id
    for irmao in irmaos:
        irmao.peca_pai_id = peca.id
    db.commit()
    db.refresh(peca)
    return peca


@router.post("/pecas/{peca_id}/anexar-a/{peca_pai_id}", response_model=PecaOut)
def anexar_a(peca_id: uuid.UUID, peca_pai_id: uuid.UUID, db: Session = Depends(get_db)):
    """Vincula manualmente `peca` como anexo de `peca_pai` — pra quando o
    agrupamento automático nunca colocou as duas no mesmo grupo (datas/horas
    de protocolo muito distantes, por exemplo). Só é permitido anexar a uma
    peça que já seja principal (sem pai) — evita cadeias de 3+ níveis, que a
    tela de Documentos não foi desenhada pra mostrar. Se `peca` já tinha seus
    próprios anexos, eles são promovidos a anexos direto de `peca_pai`
    também (achatado), em vez de ficarem órfãos."""
    if peca_id == peca_pai_id:
        raise HTTPException(status_code=422, detail="Uma peça não pode ser anexo dela mesma.")
    peca = db.query(AutosIAPeca).filter(AutosIAPeca.id == peca_id).first()
    peca_pai = db.query(AutosIAPeca).filter(AutosIAPeca.id == peca_pai_id).first()
    if not peca or not peca_pai:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if peca.caso_id != peca_pai.caso_id:
        raise HTTPException(status_code=422, detail="As duas peças precisam ser do mesmo caso.")
    if peca_pai.peca_pai_id is not None:
        raise HTTPException(
            status_code=422,
            detail="Só é possível anexar a uma peça que já seja principal (sem pai).",
        )
    filhos_de_peca = db.query(AutosIAPeca).filter(AutosIAPeca.peca_pai_id == peca.id).all()
    for filho in filhos_de_peca:
        filho.peca_pai_id = peca_pai.id
    peca.peca_pai_id = peca_pai.id
    db.commit()
    db.refresh(peca)
    return peca


@router.post("/pecas/{peca_id}/desvincular", response_model=PecaOut)
def desvincular_peca(peca_id: uuid.UUID, db: Session = Depends(get_db)):
    """Desfaz o vínculo de anexo — a peça volta a ser principal (independente),
    sem apagar nada. Contrapartida manual de anexar_a/tornar_principal."""
    peca = db.query(AutosIAPeca).filter(AutosIAPeca.id == peca_id).first()
    if not peca:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    peca.peca_pai_id = None
    db.commit()
    db.refresh(peca)
    return peca


def _executar_reler_peca_em_background(peca_id: uuid.UUID) -> None:
    db = SessionLocal()
    try:
        peca = db.query(AutosIAPeca).filter(AutosIAPeca.id == peca_id).first()
        if not peca:
            return
        caso_id = peca.caso_id
        try:
            reler_peca(db, peca)
        except Exception as exc:
            peca.status = "erro"
            peca.erro_mensagem = str(exc)[:2000]
            db.commit()
        # Texto/resumo novos → atualiza o .md desta peça no Drive (no lugar, sem duplicar).
        export_md_drive.agendar_exportacao(caso_id, [peca_id])
    finally:
        db.close()


@router.post("/pecas/{peca_id}/reler", response_model=PecaOut, status_code=status.HTTP_202_ACCEPTED)
def reler_peca_agora(peca_id: uuid.UUID, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Rebaixa e reprocessa só esta peça (Drive + IA) — pra quando a leitura
    original falhou ou ficou incompleta. Nunca mexe em outras peças, nem
    reprocessa o caso inteiro."""
    peca = db.query(AutosIAPeca).filter(AutosIAPeca.id == peca_id).first()
    if not peca:
        raise HTTPException(status_code=404, detail="Peça não encontrada")
    if not peca.andamento_id:
        raise HTTPException(status_code=422, detail="Releitura só é suportada para peças importadas do jus.br.")
    peca.status = "pendente_resumo"
    peca.erro_mensagem = None
    db.commit()
    db.refresh(peca)
    background_tasks.add_task(_executar_reler_peca_em_background, peca.id)
    return peca


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
    # texto_md (23 MB num caso grande) não faz parte do grafo — ver buscar_pecas.
    pecas = (
        db.query(AutosIAPeca)
        .options(defer(AutosIAPeca.texto_md))
        .filter(AutosIAPeca.caso_id == caso_id)
        .all()
    )
    referencias = db.query(AutosIAReferencia).filter(AutosIAReferencia.caso_id == caso_id).all()
    andamento_ids = [p.andamento_id for p in pecas if p.andamento_id]
    links_drive = dict(
        db.query(AndamentoProcesso.id, AndamentoProcesso.arquivo_drive_link)
        .filter(AndamentoProcesso.id.in_(andamento_ids))
        .all()
    ) if andamento_ids else {}

    nos = []
    for p in pecas:
        no = GrafoNo.model_validate(p, from_attributes=True)
        no.arquivo_drive_link = links_drive.get(p.andamento_id)
        nos.append(no)
    return GrafoOut(
        nos=nos,
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
