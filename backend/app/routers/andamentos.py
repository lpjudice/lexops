"""Andamentos router — list, sync, mark-read."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import threading
import uuid
import mimetypes
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models.andamento import AndamentoProcesso
from app.models.processo import Processo
from app.schemas.andamento import AndamentoOut, SincronizacaoResult

router = APIRouter(prefix="/andamentos", tags=["andamentos"])


class BatchSyncBody(BaseModel):
    processo_ids: list[str]


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
    }


def _set_job(job_id: str, **updates) -> None:
    with _sync_jobs_lock:
        job = _sync_jobs.get(job_id)
        if not job:
            return
        job.update(updates)
        job["updated_at"] = datetime.now(timezone.utc)


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

        log = asyncio.run(_sync(processo, db, token=token, session_data=session_data, progress_callback=progress))
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
        results.append(SincronizacaoResult(
            processo_id=str(log.processo_id),
            tribunal=log.tribunal,
            status=log.status,
            novos_andamentos=log.novos_andamentos,
            mensagem=log.mensagem,
            ultimo_andamento_data=p.ultimo_andamento_data,
        ))
    return results


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
