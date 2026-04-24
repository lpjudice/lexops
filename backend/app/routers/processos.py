import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.processo import Processo, processo_clientes as assoc_table
from app.schemas.processo import ProcessoClienteIn, ProcessoClienteOut, ProcessoCreate, ProcessoOut, ProcessoUpdate

UPLOADS_DIR = Path("/app/uploads/processos")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/processos", tags=["processos"])


def _sync_litisconsorcio(processo: Processo, clientes_in: list[ProcessoClienteIn], db: Session) -> None:
    """Replace litisconsórcio association entries for a processo."""
    db.execute(assoc_table.delete().where(assoc_table.c.processo_id == processo.id))
    for ci in clientes_in:
        db.execute(assoc_table.insert().values(
            processo_id=processo.id,
            cliente_id=ci.cliente_id,
            polo=ci.polo,
            principal=ci.principal,
        ))


def _processo_to_out(p: Processo, db: Session) -> ProcessoOut:
    """Build ProcessoOut from column attrs only (avoids ORM relationship validation issues)."""
    cols = {c.key: getattr(p, c.key) for c in sa_inspect(Processo).column_attrs}
    out = ProcessoOut.model_validate(cols)
    out.clientes_litisconsorcio = _enrich_litisconsorcio(p, db)
    return out


def _enrich_litisconsorcio(processo: Processo, db: Session) -> list[ProcessoClienteOut]:
    """Load litisconsórcio data with client names."""
    from app.models.cliente import Cliente
    rows = db.execute(
        assoc_table.select().where(assoc_table.c.processo_id == processo.id)
    ).fetchall()
    result = []
    for row in rows:
        cliente = db.query(Cliente).filter(Cliente.id == row.cliente_id).first()
        if cliente:
            result.append(ProcessoClienteOut(
                cliente_id=row.cliente_id,
                nome=cliente.nome,
                polo=row.polo,
                principal=row.principal,
            ))
    return result


@router.get("/", response_model=list[ProcessoOut])
def listar_processos(
    cliente_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    estado: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Processo)
    if cliente_id:
        q = q.filter(Processo.cliente_id == cliente_id)
    if status:
        q = q.filter(Processo.status == status)
    if estado:
        q = q.filter(Processo.estado == estado)
    processos = q.order_by(Processo.created_at.desc()).all()
    # Enrich with litisconsórcio
    result = []
    for p in processos:
        result.append(_processo_to_out(p, db))
    return result


@router.post("/", response_model=ProcessoOut, status_code=status.HTTP_201_CREATED)
def criar_processo(data: ProcessoCreate, db: Session = Depends(get_db)):
    litis_in = data.clientes_litisconsorcio
    dump = data.model_dump(exclude={"clientes_litisconsorcio"})
    processo = Processo(**dump)
    db.add(processo)
    db.commit()
    db.refresh(processo)
    if litis_in:
        _sync_litisconsorcio(processo, litis_in, db)
        db.commit()
    # Cria subpasta no Dropbox
    try:
        from app.models.cliente import Cliente
        from app.services.pasta_cliente import pasta_processo as _pasta_proc
        cliente = db.query(Cliente).filter(Cliente.id == processo.cliente_id).first()
        if cliente and processo.numero_cnj:
            _pasta_proc(cliente.nome, processo.numero_cnj)
    except Exception:
        pass
    return _processo_to_out(processo, db)


@router.get("/{processo_id}", response_model=ProcessoOut)
def obter_processo(processo_id: uuid.UUID, db: Session = Depends(get_db)):
    processo = db.query(Processo).filter(Processo.id == processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    return _processo_to_out(processo, db)


@router.patch("/{processo_id}", response_model=ProcessoOut)
def atualizar_processo(
    processo_id: uuid.UUID, data: ProcessoUpdate, db: Session = Depends(get_db)
):
    processo = db.query(Processo).filter(Processo.id == processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    fields = data.model_dump(exclude_unset=True)
    litis_in = fields.pop("clientes_litisconsorcio", None)
    for field, value in fields.items():
        setattr(processo, field, value)
    db.commit()
    db.refresh(processo)
    if litis_in is not None:
        _sync_litisconsorcio(processo, [ProcessoClienteIn(**ci) if isinstance(ci, dict) else ci for ci in litis_in], db)
        db.commit()
    return _processo_to_out(processo, db)


@router.delete("/{processo_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_processo(processo_id: uuid.UUID, db: Session = Depends(get_db)):
    processo = db.query(Processo).filter(Processo.id == processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    db.delete(processo)
    db.commit()


# ── Documentos PDF ────────────────────────────────────────────────────────────

def _pasta_processo(processo_id: uuid.UUID) -> Path:
    p = UPLOADS_DIR / str(processo_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


@router.post("/{processo_id}/upload-pdf")
async def upload_pdf(
    processo_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    processo = db.query(Processo).filter(Processo.id == processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos")

    pasta = _pasta_processo(processo_id)
    dest = pasta / file.filename
    content = await file.read()
    dest.write_bytes(content)

    # Copia para pasta Dropbox e Google Drive do cliente
    try:
        from app.models.cliente import Cliente
        from app.services.pasta_cliente import pasta_processo as _pasta_proc, salvar_arquivo
        cliente = db.query(Cliente).filter(Cliente.id == processo.cliente_id).first()
        if cliente and processo.numero_cnj:
            salvar_arquivo(_pasta_proc(cliente.nome, processo.numero_cnj), file.filename, content)
            try:
                from app.services.google_drive import upload_arquivo
                upload_arquivo(content, file.filename, cliente.nome, processo.numero_cnj)
            except Exception:
                pass
    except Exception:
        pass

    return {"filename": file.filename, "size": len(content)}


@router.get("/{processo_id}/documentos")
def listar_documentos(processo_id: uuid.UUID, db: Session = Depends(get_db)):
    processo = db.query(Processo).filter(Processo.id == processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    pasta = UPLOADS_DIR / str(processo_id)
    if not pasta.exists():
        return []
    return [
        {"filename": f.name, "size": f.stat().st_size}
        for f in sorted(pasta.iterdir())
        if f.suffix.lower() == ".pdf"
    ]


@router.delete("/{processo_id}/documentos/{filename}")
def remover_documento(
    processo_id: uuid.UUID, filename: str, db: Session = Depends(get_db)
):
    processo = db.query(Processo).filter(Processo.id == processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    f = UPLOADS_DIR / str(processo_id) / filename
    if not f.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    f.unlink()
    return {"ok": True}


# ── Chat Gemini ───────────────────────────────────────────────────────────────

from pydantic import BaseModel


class ChatRequest(BaseModel):
    pergunta: str
    historico: list[dict] = []


@router.post("/{processo_id}/chat")
def chat_com_processo(
    processo_id: uuid.UUID,
    body: ChatRequest,
    db: Session = Depends(get_db),
):
    """Chat com Gemini usando os PDFs do processo como contexto."""
    processo = db.query(Processo).filter(Processo.id == processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    pasta = UPLOADS_DIR / str(processo_id)
    pdf_paths = sorted(
        [str(f) for f in pasta.iterdir() if f.suffix.lower() == ".pdf"]
    ) if pasta.exists() else []

    from app.services.gemini_chat import chat_processo
    resposta = chat_processo(
        pergunta=body.pergunta,
        historico=body.historico,
        pdf_paths=pdf_paths,
    )
    return {"resposta": resposta}
