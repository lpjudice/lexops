"""Andamentos router — list, sync, mark-read."""
from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
import logging
import os
import threading
import uuid
import mimetypes
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.dependencies import get_current_user
from app.models.andamento import AndamentoProcesso
from app.models.processo import Processo
from app.models.processo_parte import ProcessoParte
from app.schemas.andamento import AndamentoOut, SincronizacaoResult

router = APIRouter(prefix="/andamentos", tags=["andamentos"],
                   dependencies=[Depends(get_current_user)])
logger = logging.getLogger(__name__)


class BatchSyncBody(BaseModel):
    processo_ids: list[str]


class RelatorioLoteItem(BaseModel):
    processo_id: str
    novos: int = 0


class RelatorioLoteBody(BaseModel):
    items: list[RelatorioLoteItem]


class DiagnosticoBody(BaseModel):
    token: str
    numero_cnj: str


class ImportarJusBRBody(BaseModel):
    payload: str   # raw JSON string pasted from DevTools Response tab


class JusBRSyncBody(BaseModel):
    token: str | None = None


class BatchJusBRSyncBody(BaseModel):
    processo_ids: list[str]
    token: str | None = None


class JusBRSessionBody(BaseModel):
    capture: str


class JusBRSyncJobStart(BaseModel):
    job_id: str


class JusBRSyncJobStatus(BaseModel):
    job_id: str
    status: str
    stage: str
    message: str | None = None
    total: int = 0
    processed: int = 0
    uploaded: int = 0
    result: SincronizacaoResult | None = None
    error: str | None = None
    started_at: datetime
    updated_at: datetime


class JusBRBatchJobStatus(BaseModel):
    job_id: str
    status: str                  # rodando | concluido | erro
    stage: str
    message: str | None = None
    total: int = 0               # total de processos no lote
    processed: int = 0           # processos já finalizados
    current_index: int = 0       # índice (1-based) do processo em andamento
    current_cnj: str | None = None
    current_total: int = 0       # documentos detectados no processo atual
    current_processed: int = 0   # documentos processados no processo atual
    current_uploaded: int = 0    # documentos enviados ao Drive no processo atual
    results: list[SincronizacaoResult] = []
    error: str | None = None
    started_at: datetime
    updated_at: datetime


_sync_jobs: dict[str, dict] = {}
_sync_jobs_lock = threading.Lock()


def _job_result_from_log(log, processo: Processo) -> dict:
    return {
        "processo_id": str(log.processo_id),
        "tribunal": log.tribunal,
        "status": log.status,
        "novos_andamentos": log.novos_andamentos,
        "mensagem": log.mensagem,
        "ultimo_andamento_data": processo.ultimo_andamento_data,
        "documentos_baixados": int(getattr(log, "docs_enviados", 0) or 0),
        "documentos_total": int(getattr(log, "docs_total", 0) or 0),
    }


def _set_job(job_id: str, **updates) -> None:
    with _sync_jobs_lock:
        job = _sync_jobs.get(job_id)
        if not job:
            return
        job.update(updates)
        job["updated_at"] = datetime.now(timezone.utc)


# Quantas rodadas o job pode re-executar sozinho para terminar de baixar
# documentos que faltaram (0 ou 1 desliga o auto-continuar).
_AUTO_CONTINUE_ROUNDS = int(os.getenv("JUSBR_AUTO_CONTINUE_ROUNDS", "6"))


def _erro_transitorio(msg: str | None) -> bool:
    low = (msg or "").lower()
    return any(
        k in low
        for k in ("indispon", "503", "502", "504", "timeout", "temporariamente",
                  "tente novamente", "conectar", "tempo")
    )


async def _atualizar_parte_contraria(
    processo: Processo, db: Session, token: str | None, session_data: dict | None,
) -> None:
    """Busca as partes do processo no PDPJ e atualiza `processo.parte_contraria`.

    Aditivo ao sync de andamentos: usa o coletor independente do PDPJ
    (processo_partes_collector — não mexe no orchestrator/pdpj travados) e
    nunca deixa uma falha aqui derrubar a sincronização principal. Sempre
    sobrescreve com o que vier do jus.br, mesmo que o campo já tenha sido
    editado à mão (comportamento escolhido pelo Lucas).
    """
    from app.services.processo_partes_collector import fetch_resumo
    from app.services.processo_partes_store import identificar_cliente_e_contraria, salvar_partes

    tok = token or (session_data or {}).get("token")
    if not tok:
        return
    try:
        resumo = await fetch_resumo(processo.numero_cnj, tok)
        if not resumo or not resumo.get("partes"):
            return
        salvar_partes(db, processo_id=processo.id, partes=resumo["partes"])
        _cliente, contraria = identificar_cliente_e_contraria(db, processo)
        if contraria:
            processo.parte_contraria = contraria
            db.commit()
    except Exception:
        logger.warning(
            "auto-popular parte_contraria falhou para %s", processo.numero_cnj, exc_info=True
        )


async def _sincronizar_jusbr_com_retomada(processo, db, token, session_data, progress_callback):
    """Sincroniza e re-executa automaticamente enquanto faltarem documentos E
    houver progresso. A dedup é idempotente, então cada rodada pula o que já foi
    baixado e continua de onde parou. Para em erro permanente (auth/permissão)
    ou quando uma rodada não baixa nada de novo (evita loop infinito)."""
    from app.services.consulta_processual.orchestrator import sincronizar_processo_jusbr as _sync
    from app.services.consulta_processual.pdpj import PROCESS_DELAY_SECONDS

    ultimo_log = None
    prev_enviados = -1
    rounds = max(1, _AUTO_CONTINUE_ROUNDS)
    for rodada in range(rounds):
        log = await _sync(
            processo, db, token=token, session_data=session_data,
            progress_callback=progress_callback,
        )
        db.refresh(processo)
        ultimo_log = log
        total = int(getattr(log, "docs_total", 0) or 0)
        enviados = int(getattr(log, "docs_enviados", 0) or 0)

        if log.status == "erro":
            if _erro_transitorio(log.mensagem) and rodada < rounds - 1:
                await asyncio.sleep(PROCESS_DELAY_SECONDS or 1.5)
                continue
            break  # erro permanente → propaga o log de erro
        if total <= 0 or enviados >= total:
            break  # nada pendente
        if enviados <= prev_enviados:
            break  # rodada sem progresso → para
        prev_enviados = enviados
        await asyncio.sleep(PROCESS_DELAY_SECONDS or 1.5)

    if ultimo_log is not None and ultimo_log.status != "erro":
        await _atualizar_parte_contraria(processo, db, token, session_data)
    return ultimo_log


def _run_jusbr_sync_job(job_id: str, processo_id: uuid.UUID, token: str | None = None) -> None:
    from app.services.consulta_processual.jusbr_session import load_session
    from app.services.consulta_processual.orchestrator import sincronizar_processo_jusbr as _sync

    db = SessionLocal()
    try:
        processo = db.query(Processo).filter(Processo.id == processo_id).first()
        if not processo:
            _set_job(job_id, status="erro", stage="erro", error="Processo não encontrado")
            return

        session_data = load_session() if not token else None
        if not token and not session_data:
            _set_job(job_id, status="erro", stage="erro", error="Sessao do jus.br nao configurada.")
            return

        def progress(payload: dict) -> None:
            _set_job(
                job_id,
                stage=payload.get("stage") or "processando",
                message=payload.get("message"),
                total=int(payload.get("total") or 0),
                processed=int(payload.get("processed") or 0),
                uploaded=int(payload.get("uploaded") or 0),
            )

        log = asyncio.run(_sincronizar_jusbr_com_retomada(processo, db, token, session_data, progress))
        db.refresh(processo)
        _set_job(
            job_id,
            status="concluido",
            stage="finalizado",
            message="Sincronização concluída.",
            result=_job_result_from_log(log, processo),
        )
    except Exception as exc:
        _set_job(job_id, status="erro", stage="erro", error=str(exc), message="Falha ao sincronizar jus.br.")
    finally:
        db.close()


def _run_jusbr_batch_job(job_id: str, processo_ids: list[str], token: str | None = None) -> None:
    """Sincroniza vários processos via jus.br em background, com progresso e pausa
    entre cada processo para não estourar o rate limit do PDPJ."""
    from app.services.consulta_processual.jusbr_session import load_session
    from app.services.consulta_processual.orchestrator import sincronizar_processo_jusbr as _sync
    from app.services.consulta_processual.pdpj import PROCESS_DELAY_SECONDS

    db = SessionLocal()
    try:
        session_data = load_session() if not token else None
        if not token and not session_data:
            _set_job(job_id, status="erro", stage="erro", error="Sessao do jus.br nao configurada.")
            return

        async def _run_all() -> None:
            for indice, pid in enumerate(processo_ids):
                # Pausa entre processos (exceto o primeiro).
                if indice > 0 and PROCESS_DELAY_SECONDS > 0:
                    await asyncio.sleep(PROCESS_DELAY_SECONDS)

                try:
                    pid_uuid = uuid.UUID(pid)
                except ValueError:
                    _append_batch_result(job_id, {
                        "processo_id": pid, "tribunal": None, "status": "erro",
                        "novos_andamentos": 0, "mensagem": "ID de processo inválido",
                        "ultimo_andamento_data": None,
                    }, indice + 1, None)
                    continue

                processo = db.query(Processo).filter(Processo.id == pid_uuid).first()
                if not processo:
                    _append_batch_result(job_id, {
                        "processo_id": pid, "tribunal": None, "status": "erro",
                        "novos_andamentos": 0, "mensagem": "Processo não encontrado",
                        "ultimo_andamento_data": None,
                    }, indice + 1, None)
                    continue

                cnj = processo.numero_cnj
                _set_job(
                    job_id,
                    stage="processando",
                    current_index=indice + 1,
                    current_cnj=cnj,
                    current_total=0,
                    current_processed=0,
                    current_uploaded=0,
                    message=f"Sincronizando {indice + 1}/{len(processo_ids)}: {cnj or pid}",
                )

                def _progresso_processo(payload: dict) -> None:
                    _set_job(
                        job_id,
                        stage=payload.get("stage") or "processando",
                        current_total=int(payload.get("total") or 0),
                        current_processed=int(payload.get("processed") or 0),
                        current_uploaded=int(payload.get("uploaded") or 0),
                    )

                try:
                    log = await _sincronizar_jusbr_com_retomada(
                        processo, db, token, session_data, _progresso_processo
                    )
                    db.refresh(processo)
                    _append_batch_result(job_id, _job_result_from_log(log, processo), indice + 1, cnj)
                except Exception as exc:  # noqa: BLE001
                    _append_batch_result(job_id, {
                        "processo_id": pid, "tribunal": getattr(processo, "tribunal", None),
                        "status": "erro", "novos_andamentos": 0, "mensagem": str(exc),
                        "ultimo_andamento_data": None,
                    }, indice + 1, cnj)

        asyncio.run(_run_all())
        _set_job(
            job_id,
            status="concluido",
            stage="finalizado",
            current_cnj=None,
            message="Sincronização do lote concluída.",
        )
    except Exception as exc:  # noqa: BLE001
        _set_job(job_id, status="erro", stage="erro", error=str(exc), message="Falha ao sincronizar lote jus.br.")
    finally:
        db.close()


def _append_batch_result(job_id: str, result: dict, current_index: int, current_cnj: str | None) -> None:
    with _sync_jobs_lock:
        job = _sync_jobs.get(job_id)
        if not job:
            return
        job.setdefault("results", []).append(result)
        job["processed"] = len(job["results"])
        job["current_index"] = current_index
        job["current_cnj"] = current_cnj
        job["updated_at"] = datetime.now(timezone.utc)


# ── List andamentos for a process ────────────────────────────────────────────

def _filtro_fonte(query, fonte: str | None):
    """Filter andamentos by source: 'jusbr' → JusBR/* rows, 'datajud' → everything else."""
    if fonte == "jusbr":
        return query.filter(AndamentoProcesso.fonte.ilike("JusBR%"))
    if fonte == "datajud":
        return query.filter(~AndamentoProcesso.fonte.ilike("JusBR%"))
    return query


@router.get("/processo/{processo_id}", response_model=list[AndamentoOut])
def listar_andamentos(
    processo_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    fonte: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(AndamentoProcesso).filter(AndamentoProcesso.processo_id == processo_id)
    q = _filtro_fonte(q, fonte)
    return (
        q.order_by(
            AndamentoProcesso.data_andamento.desc().nullslast(),
            AndamentoProcesso.created_at.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/processo/{processo_id}/count")
def contar_andamentos(
    processo_id: uuid.UUID,
    fonte: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q_base = db.query(AndamentoProcesso).filter(AndamentoProcesso.processo_id == processo_id)
    total = _filtro_fonte(q_base, fonte).count()
    nao_lidos = _filtro_fonte(q_base, fonte).filter(
        AndamentoProcesso.lido == False  # noqa: E712
    ).count()
    return {"total": total, "nao_lidos": nao_lidos}


# ── Mark all as read ─────────────────────────────────────────────────────────

@router.post("/processo/{processo_id}/marcar-lidos", status_code=status.HTTP_204_NO_CONTENT)
def marcar_lidos(processo_id: uuid.UUID, db: Session = Depends(get_db)):
    db.query(AndamentoProcesso).filter(
        AndamentoProcesso.processo_id == processo_id,
        AndamentoProcesso.lido == False,  # noqa: E712
    ).update({"lido": True})
    p = db.query(Processo).filter(Processo.id == processo_id).first()
    if p:
        p.andamentos_nao_lidos = 0
    db.commit()


# ── Dashboard: avisos de andamentos novos ─────────────────────────────────────

@router.get("/dashboard/avisos")
def dashboard_avisos(db: Session = Depends(get_db)):
    """Resumo dos andamentos não lidos por processo, pro card na home."""
    from sqlalchemy import func as sql_func
    from app.models.cliente import Cliente

    # Conta direto na tabela de andamentos (mais confiável que o cache no Processo)
    sub = (
        db.query(
            AndamentoProcesso.processo_id.label("pid"),
            sql_func.count(AndamentoProcesso.id).label("qtd"),
            sql_func.max(AndamentoProcesso.data_andamento).label("mais_recente"),
        )
        .filter(AndamentoProcesso.lido.is_(False))
        .group_by(AndamentoProcesso.processo_id)
        .subquery()
    )

    rows = (
        db.query(Processo, Cliente.nome, sub.c.qtd, sub.c.mais_recente)
        .join(Cliente, Cliente.id == Processo.cliente_id)
        .join(sub, sub.c.pid == Processo.id)
        .order_by(sub.c.mais_recente.desc().nullslast())
        .all()
    )

    items = []
    total_andamentos = 0
    for p, nome_cliente, qtd, mais_recente in rows:
        total_andamentos += int(qtd)
        items.append({
            "processo_id": str(p.id),
            "numero_cnj": p.numero_cnj,
            "cliente_nome": nome_cliente,
            "tribunal": p.tribunal,
            "vara": p.vara,
            "qtd_nao_lidos": int(qtd),
            "mais_recente": mais_recente.isoformat() if mais_recente else None,
            "ultimo_desc": (p.ultimo_andamento_desc or "")[:200],
        })

    return {
        "total_processos": len(items),
        "total_andamentos": total_andamentos,
        "items": items,
    }


@router.post("/dashboard/marcar-lidos-lote")
def dashboard_marcar_lote(body: dict, db: Session = Depends(get_db)):
    """Marca lido em vários processos (ou todos) de uma vez.

    Body: {"processo_ids": ["uuid", ...]} ou {"all": true}
    """
    if (body or {}).get("all"):
        # Marca tudo
        db.query(AndamentoProcesso).filter(
            AndamentoProcesso.lido.is_(False)
        ).update({"lido": True}, synchronize_session=False)
        db.query(Processo).filter(Processo.andamentos_nao_lidos > 0).update(
            {Processo.andamentos_nao_lidos: 0}, synchronize_session=False
        )
        db.commit()
        return {"ok": True, "scope": "all"}

    ids = (body or {}).get("processo_ids") or []
    if not ids:
        raise HTTPException(status_code=422, detail="Informe processo_ids ou all=true.")
    db.query(AndamentoProcesso).filter(
        AndamentoProcesso.processo_id.in_(ids),
        AndamentoProcesso.lido.is_(False),
    ).update({"lido": True}, synchronize_session=False)
    db.query(Processo).filter(Processo.id.in_(ids)).update(
        {Processo.andamentos_nao_lidos: 0}, synchronize_session=False
    )
    db.commit()
    return {"ok": True, "scope": "lote", "qtd": len(ids)}


@router.get("/arquivo/{andamento_id}")
def abrir_arquivo_andamento(andamento_id: uuid.UUID, db: Session = Depends(get_db)):
    andamento = db.query(AndamentoProcesso).filter(AndamentoProcesso.id == andamento_id).first()
    if not andamento:
        raise HTTPException(status_code=404, detail="Andamento não encontrado")

    if andamento.arquivo_drive_link:
        return RedirectResponse(andamento.arquivo_drive_link)

    if andamento.arquivo_path:
        caminho = Path(andamento.arquivo_path)
        if caminho.exists():
            media_type = mimetypes.guess_type(str(caminho))[0] or "application/octet-stream"
            return FileResponse(
                caminho,
                media_type=media_type,
                filename=andamento.arquivo_nome or caminho.name,
            )

    raise HTTPException(status_code=404, detail="Arquivo não encontrado para este andamento")


# ── Sync single process ───────────────────────────────────────────────────────

@router.post("/processo/{processo_id}/sincronizar", response_model=SincronizacaoResult)
async def sincronizar_processo(processo_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.services.consulta_processual.orchestrator import sincronizar_processo as _sync

    p = db.query(Processo).filter(Processo.id == processo_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    log = await _sync(p, db)
    db.refresh(p)
    return SincronizacaoResult(
        processo_id=str(log.processo_id),
        tribunal=log.tribunal,
        status=log.status,
        novos_andamentos=log.novos_andamentos,
        mensagem=log.mensagem,
        ultimo_andamento_data=p.ultimo_andamento_data,
    )


# ── Batch sync ────────────────────────────────────────────────────────────────

@router.post("/sincronizar-batch", response_model=list[SincronizacaoResult])
async def sincronizar_batch(body: BatchSyncBody, db: Session = Depends(get_db)):
    from app.services.consulta_processual.orchestrator import sincronizar_batch as _batch

    raw = await _batch(body.processo_ids, db)
    return [
        SincronizacaoResult(
            processo_id=r["processo_id"],
            tribunal=r.get("tribunal"),
            status=r["status"],
            novos_andamentos=r.get("novos_andamentos", 0),
            mensagem=r.get("mensagem"),
        )
        for r in raw
    ]


# ── Relatório PDF do lote ─────────────────────────────────────────────────────

@router.post("/relatorio-lote")
def gerar_relatorio_lote_endpoint(body: RelatorioLoteBody, db: Session = Depends(get_db)):
    """
    Gera um PDF com os processos que tiveram andamento novo no lote (os 10
    últimos andamentos de cada, destacando os novos e com hyperlink ao arquivo),
    salva em Drive raiz/"Andamentos em Batch" e retorna o link + o PDF (base64).
    """
    from app.services.andamentos_pdf import gerar_relatorio_lote
    from app.services import google_drive

    epoch = datetime.min.replace(tzinfo=timezone.utc)
    processos_data: list[dict] = []
    for item in body.items:
        try:
            pid = uuid.UUID(item.processo_id)
        except (ValueError, AttributeError, TypeError):
            continue
        proc = db.query(Processo).filter(Processo.id == pid).first()
        if not proc:
            continue
        andamentos = (
            db.query(AndamentoProcesso)
            .filter(AndamentoProcesso.processo_id == pid)
            .order_by(
                AndamentoProcesso.data_andamento.desc().nullslast(),
                AndamentoProcesso.created_at.desc(),
            )
            .limit(10)
            .all()
        )
        # "Novo" = os `item.novos` andamentos mais recentes por created_at entre
        # os exibidos (os recém-inseridos pelo lote).
        novos_n = max(0, min(item.novos or 0, len(andamentos)))
        novos_ids: set = set()
        if novos_n:
            por_created = sorted(andamentos, key=lambda a: a.created_at or epoch, reverse=True)
            novos_ids = {a.id for a in por_created[:novos_n]}
        # Partes (autor = polo ATIVO, réu = polo PASSIVO) coletadas via PDPJ.
        partes = (
            db.query(ProcessoParte)
            .filter(ProcessoParte.processo_id == pid)
            .order_by(ProcessoParte.ordem)
            .all()
        )
        autores = [pt.nome for pt in partes if (pt.polo or "").upper() == "ATIVO"]
        reus = [pt.nome for pt in partes if (pt.polo or "").upper() == "PASSIVO"]
        processos_data.append({
            "cnj": proc.numero_cnj,
            "cliente": proc.cliente.nome if proc.cliente else None,
            "tribunal": proc.tribunal,
            "vara": proc.vara,
            "materia": proc.materia,
            "autores": autores,
            "reus": reus,
            "andamentos": [
                {
                    "data": a.data_andamento,
                    "tipo": a.tipo,
                    "descricao": a.descricao,
                    "arquivo_nome": a.arquivo_nome,
                    "arquivo_drive_link": a.arquivo_drive_link,
                    "novo": a.id in novos_ids,
                }
                for a in andamentos
            ],
        })

    if not processos_data:
        raise HTTPException(status_code=400, detail="Nenhum processo válido para o relatório.")

    gerado = datetime.now()
    pdf_bytes = gerar_relatorio_lote(processos_data, gerado)
    filename = f"Andamentos_lote_{gerado.strftime('%Y-%m-%d_%H%M')}.pdf"

    drive_link = None
    try:
        drive_link = google_drive.upload_pdf_raiz(pdf_bytes, filename)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao salvar relatorio de lote no Drive: %s", exc)

    return {
        "drive_link": drive_link,
        "filename": filename,
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
    }


# ── JusBR sync (single) ───────────────────────────────────────────────────────

@router.post("/processo/{processo_id}/sincronizar-jusbr", response_model=SincronizacaoResult)
async def sincronizar_jusbr(
    processo_id: uuid.UUID,
    body: JusBRSyncBody,
    db: Session = Depends(get_db),
):
    from app.services.consulta_processual.orchestrator import sincronizar_processo_jusbr as _sync
    from app.services.consulta_processual.jusbr_session import load_session

    p = db.query(Processo).filter(Processo.id == processo_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    session_data = load_session() if not body.token else None
    if not body.token and not session_data:
        raise HTTPException(status_code=400, detail="Sessao do jus.br nao configurada.")

    log = await _sync(p, db, token=body.token, session_data=session_data)
    db.refresh(p)
    if log.status != "erro":
        await _atualizar_parte_contraria(p, db, body.token, session_data)
    return SincronizacaoResult(
        processo_id=str(log.processo_id),
        tribunal=log.tribunal,
        status=log.status,
        novos_andamentos=log.novos_andamentos,
        mensagem=log.mensagem,
        ultimo_andamento_data=p.ultimo_andamento_data,
    )


@router.post("/processo/{processo_id}/sincronizar-jusbr-job", response_model=JusBRSyncJobStart)
def iniciar_sincronizacao_jusbr(
    processo_id: uuid.UUID,
    body: JusBRSyncBody,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    from app.services.consulta_processual.jusbr_session import load_session

    p = db.query(Processo).filter(Processo.id == processo_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    session_data = load_session() if not body.token else None
    if not body.token and not session_data:
        raise HTTPException(status_code=400, detail="Sessao do jus.br nao configurada.")

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with _sync_jobs_lock:
        _sync_jobs[job_id] = {
            "job_id": job_id,
            "status": "rodando",
            "stage": "fila",
            "message": "Sincronização iniciada...",
            "total": 0,
            "processed": 0,
            "uploaded": 0,
            "result": None,
            "error": None,
            "started_at": now,
            "updated_at": now,
        }
    background_tasks.add_task(_run_jusbr_sync_job, job_id, processo_id, body.token)
    return {"job_id": job_id}


@router.get("/sincronizar-jusbr-job/{job_id}", response_model=JusBRSyncJobStatus)
def status_sincronizacao_jusbr(job_id: str):
    with _sync_jobs_lock:
        job = _sync_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Sincronização não encontrada")
        return dict(job)


# ── JusBR batch sync ──────────────────────────────────────────────────────────

@router.post("/sincronizar-batch-jusbr", response_model=list[SincronizacaoResult])
async def sincronizar_batch_jusbr(
    body: BatchJusBRSyncBody,
    db: Session = Depends(get_db),
):
    import asyncio
    from app.services.consulta_processual.orchestrator import sincronizar_processo_jusbr as _sync
    from app.services.consulta_processual.jusbr_session import load_session
    from app.services.consulta_processual.pdpj import PROCESS_DELAY_SECONDS

    session_data = load_session() if not body.token else None
    if not body.token and not session_data:
        raise HTTPException(status_code=400, detail="Sessao do jus.br nao configurada.")

    results = []
    for indice, pid in enumerate(body.processo_ids):
        try:
            pid_uuid = uuid.UUID(pid)
        except ValueError:
            results.append(SincronizacaoResult(
                processo_id=pid, tribunal=None, status="erro",
                novos_andamentos=0, mensagem="ID de processo inválido",
            ))
            continue
        p = db.query(Processo).filter(Processo.id == pid_uuid).first()
        if not p:
            results.append(SincronizacaoResult(
                processo_id=pid, tribunal=None, status="erro",
                novos_andamentos=0, mensagem="Processo não encontrado",
            ))
            continue
        # Pausa entre processos para não estourar o rate limit do PDPJ.
        if indice > 0 and PROCESS_DELAY_SECONDS > 0:
            await asyncio.sleep(PROCESS_DELAY_SECONDS)
        log = await _sync(p, db, token=body.token, session_data=session_data)
        db.refresh(p)
        if log.status != "erro":
            await _atualizar_parte_contraria(p, db, body.token, session_data)
        results.append(SincronizacaoResult(
            processo_id=str(log.processo_id),
            tribunal=log.tribunal,
            status=log.status,
            novos_andamentos=log.novos_andamentos,
            mensagem=log.mensagem,
            ultimo_andamento_data=p.ultimo_andamento_data,
        ))
    return results


@router.post("/sincronizar-batch-jusbr-job", response_model=JusBRSyncJobStart)
def iniciar_sincronizacao_batch_jusbr(
    body: BatchJusBRSyncBody,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    from app.services.consulta_processual.jusbr_session import load_session

    session_data = load_session() if not body.token else None
    if not body.token and not session_data:
        raise HTTPException(status_code=400, detail="Sessao do jus.br nao configurada.")

    if not body.processo_ids:
        raise HTTPException(status_code=400, detail="Nenhum processo informado.")

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    with _sync_jobs_lock:
        _sync_jobs[job_id] = {
            "job_id": job_id,
            "status": "rodando",
            "stage": "fila",
            "message": "Sincronização do lote iniciada...",
            "total": len(body.processo_ids),
            "processed": 0,
            "current_index": 0,
            "current_cnj": None,
            "current_total": 0,
            "current_processed": 0,
            "current_uploaded": 0,
            "results": [],
            "error": None,
            "started_at": now,
            "updated_at": now,
        }
    background_tasks.add_task(_run_jusbr_batch_job, job_id, body.processo_ids, body.token)
    return {"job_id": job_id}


@router.get("/sincronizar-batch-jusbr-job/{job_id}", response_model=JusBRBatchJobStatus)
def status_sincronizacao_batch_jusbr(job_id: str):
    with _sync_jobs_lock:
        job = _sync_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Sincronização não encontrada")
        return dict(job)


@router.get("/jusbr/session")
def obter_sessao_jusbr():
    from app.services.consulta_processual.jusbr_session import session_status

    return session_status()


@router.post("/jusbr/session")
def configurar_sessao_jusbr(body: JusBRSessionBody):
    from app.services.consulta_processual.jusbr_session import save_session_from_capture, session_status

    try:
        save_session_from_capture(body.capture)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return session_status()


@router.delete("/jusbr/session")
def limpar_sessao_jusbr():
    from app.services.consulta_processual.jusbr_session import clear_session

    clear_session()
    return {"ok": True}


# ── PKCE com offline_access (sessão perene, sem colar token manualmente) ─────

@router.post("/jusbr/pkce/start")
def iniciar_pkce():
    """Gera URL de autorização gov.br (PKCE + offline_access) e state_id."""
    from app.services.lexops_pkce import build_login_url

    return build_login_url()


@router.post("/jusbr/pkce/finish")
def finalizar_pkce(body: dict):
    """Recebe {state_id, pasted_url} e troca por tokens; salva sessão id=1."""
    from app.services.lexops_pkce import exchange_code

    state_id = (body or {}).get("state_id") or ""
    pasted = (body or {}).get("pasted_url") or (body or {}).get("code") or ""
    if not state_id or not pasted:
        raise HTTPException(status_code=422, detail="state_id e pasted_url são obrigatórios.")
    try:
        return exchange_code(state_id, pasted)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ── JusBR import from pasted Response JSON ───────────────────────────────────

@router.post("/processo/{processo_id}/importar-jusbr", response_model=SincronizacaoResult)
async def importar_jusbr(
    processo_id: uuid.UUID,
    body: ImportarJusBRBody,
    db: Session = Depends(get_db),
):
    """Parse a raw JSON pasted from DevTools Network → Response and save andamentos."""
    import json
    from datetime import date, datetime, timezone
    from app.models.andamento import AndamentoProcesso, SincronizacaoLog

    p = db.query(Processo).filter(Processo.id == processo_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    # ── Parse raw JSON ────────────────────────────────────────────────────────
    try:
        data = json.loads(body.payload.strip())
    except Exception:
        raise HTTPException(status_code=422, detail="JSON inválido. Copie o conteúdo completo da aba Response.")

    # ── Extract movimentos from any known shape ───────────────────────────────
    def find_list(obj, *keys):
        for k in keys:
            v = obj.get(k) if isinstance(obj, dict) else None
            if isinstance(v, list) and v:
                return v
        return None

    root = data
    # Unwrap content/data wrapper
    if isinstance(data, dict):
        root = (
            find_list(data, "content", "data", "processos", "items")
            or data
        )

    # If root is a list, take first item that looks like a process
    if isinstance(root, list):
        root = root[0] if root else {}

    movimentos_raw = (
        find_list(root, "movimentos", "andamentos", "movements", "movimentos")
        or []
    )

    # Sometimes movimentos are nested inside processo object
    if not movimentos_raw and isinstance(root, dict):
        for val in root.values():
            if isinstance(val, dict):
                movimentos_raw = find_list(val, "movimentos", "andamentos") or []
                if movimentos_raw:
                    break

    if not movimentos_raw:
        return SincronizacaoResult(
            processo_id=str(processo_id),
            tribunal=p.tribunal,
            status="nenhum",
            novos_andamentos=0,
            mensagem=(
                "Nenhuma lista de movimentos encontrada no JSON colado. "
                "Verifique se copiou a resposta correta (deve conter 'movimentos' ou 'andamentos')."
            ),
        )

    # ── Parse date ────────────────────────────────────────────────────────────
    def parse_data(raw):
        if not raw:
            return None
        for prefix_len in (10, 19, 24, 27):
            try:
                return datetime.fromisoformat(str(raw)[:prefix_len].replace("Z", "+00:00")).date()
            except Exception:
                pass
        return None

    def mov_desc(m):
        partes = []
        for k in ("nome", "descricao", "tipo", "complemento", "tituloDocumento", "title"):
            v = m.get(k)
            if v and isinstance(v, str):
                partes.append(v.strip())
        for doc_key in ("documento", "doc", "arquivo"):
            doc = m.get(doc_key)
            if isinstance(doc, dict):
                doc_nome = doc.get("nome") or doc.get("nomeArquivo") or doc.get("filename") or ""
                if doc_nome:
                    partes.append(doc_nome)
                break
        return " — ".join(dict.fromkeys(p for p in partes if p))

    # ── Save new andamentos ───────────────────────────────────────────────────
    log = SincronizacaoLog(
        processo_id=p.id,
        tribunal=p.tribunal,
        status="ok",
        novos_andamentos=0,
        iniciado_em=datetime.now(timezone.utc),
    )
    db.add(log)

    novos = 0
    for m in movimentos_raw:
        dt = parse_data(
            m.get("dataHora") or m.get("dataMovimento") or m.get("data") or m.get("datahora")
        )
        desc = mov_desc(m)
        tipo = m.get("nome") or m.get("tipo")
        if not desc:
            continue

        h = AndamentoProcesso.calcular_hash(str(p.id), str(dt) if dt else None, desc)
        if db.query(AndamentoProcesso).filter(AndamentoProcesso.hash_unico == h).first():
            continue

        db.add(AndamentoProcesso(
            processo_id=p.id,
            data_andamento=dt,
            descricao=desc[:2000],
            tipo=tipo,
            fonte="JusBR/colado",
            grau=m.get("grau"),
            hash_unico=h,
            lido=False,
            notificado=False,
        ))
        novos += 1

    if novos > 0:
        validas = [m for m in movimentos_raw if m.get("dataHora") or m.get("dataMovimento") or m.get("data")]
        if validas:
            mais_recente = max(validas, key=lambda m: m.get("dataHora") or m.get("dataMovimento") or m.get("data") or "")
            dt_recente = parse_data(mais_recente.get("dataHora") or mais_recente.get("dataMovimento") or mais_recente.get("data"))
            if dt_recente and (p.ultimo_andamento_data is None or dt_recente > p.ultimo_andamento_data):
                p.ultimo_andamento_data = dt_recente
                desc_recente = mov_desc(mais_recente)
                p.ultimo_andamento_desc = desc_recente[:500]
        p.andamentos_nao_lidos = (p.andamentos_nao_lidos or 0) + novos

    p.ultimo_check = datetime.now(timezone.utc)
    p.tentativas_falha = 0
    log.novos_andamentos = novos
    log.status = "ok" if novos > 0 else "nenhum"
    log.mensagem = None if novos > 0 else "Nenhum andamento novo (já registrados anteriormente)."
    log.finalizado_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(p)

    return SincronizacaoResult(
        processo_id=str(p.id),
        tribunal=p.tribunal,
        status=log.status,
        novos_andamentos=novos,
        mensagem=log.mensagem,
        ultimo_andamento_data=p.ultimo_andamento_data,
    )


# ── JusBR diagnostic (dev) ────────────────────────────────────────────────────

@router.post("/diagnostico-jusbr")
async def diagnostico_jusbr(body: DiagnosticoBody):
    """Probe PDPJ API with various endpoint patterns and return raw responses for debugging."""
    import httpx, re

    PDPJ_BASE = "https://portaldeservicos.pdpj.jus.br/api"
    numero_norm = re.sub(r"\D", "", body.numero_cnj)
    headers = {"Authorization": f"Bearer {body.token}", "Accept": "application/json"}

    probes: list[dict] = []

    async with httpx.AsyncClient(timeout=15) as client:
        candidates = [
            ("GET", f"{PDPJ_BASE}/processos", {"numeroProcesso": body.numero_cnj}),
            ("GET", f"{PDPJ_BASE}/processos", {"numeroProcesso": numero_norm}),
            ("GET", f"{PDPJ_BASE}/processos", {"numero": body.numero_cnj}),
            ("GET", f"{PDPJ_BASE}/processos", {"numero": numero_norm}),
            ("GET", f"{PDPJ_BASE}/processos/{body.numero_cnj}", {}),
            ("GET", f"{PDPJ_BASE}/processos/{numero_norm}", {}),
            ("GET", f"{PDPJ_BASE}/processo", {"numeroProcesso": body.numero_cnj}),
            ("GET", f"{PDPJ_BASE}/processo/{body.numero_cnj}", {}),
        ]
        for method, url, params in candidates:
            try:
                resp = await client.request(method, url, headers=headers, params=params or None)
                body_text = resp.text[:800]
            except Exception as e:
                body_text = f"ERRO: {e}"
                resp = None

            probes.append({
                "url": url,
                "params": params,
                "status": resp.status_code if resp else None,
                "body": body_text,
            })

    return {"probes": probes}
