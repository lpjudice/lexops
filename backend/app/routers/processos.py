import uuid
import mimetypes
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.processo import Processo, processo_clientes as assoc_table
from app.schemas.processo import ProcessoClienteIn, ProcessoClienteOut, ProcessoCreate, ProcessoOut, ProcessoUpdate
from app.services.consulta_processual.cnj import inferir_tribunal_pelo_cnj, normalizar_tribunal

UPLOADS_DIR = Path("/app/uploads/processos")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/processos", tags=["processos"])


TRIBUNAL_ESTADO_MAP = {
    "TJES": "ES",
    "TJSP": "SP",
    "TJAM": "AM",
    "TJRJ": "RJ",
}


class ProcessoJusbrPrefillOut(BaseModel):
    numero_cnj: str
    estado: str
    tribunal: str | None = None
    orgao_julgador_tipo: str | None = None
    vara: str | None = None
    comarca: str | None = None
    materia: str | None = None
    objeto: str | None = None
    serventia: str | None = None
    foro: str | None = None
    sistema_juridico: str | None = None
    grau: str | None = None
    grau_texto: str | None = None
    status: str = "ativo"
    polo: str | None = None
    cliente_nome_sugerido: str | None = None
    parte_ativa_principal: str | None = None
    parte_passiva_principal: str | None = None
    resumo_encontrado: str | None = None


def _extract_tramitacao_principal(data: dict) -> dict:
    tramitacoes = data.get("tramitacoes")
    if isinstance(tramitacoes, list) and tramitacoes:
        return next((t for t in tramitacoes if isinstance(t, dict) and t.get("ativo") is True), tramitacoes[0]) or {}
    return {}


def _split_orgao_julgador(nome: str | None) -> tuple[str | None, str | None, str | None]:
    if not nome:
        return None, None, None
    nome = nome.strip()
    numero = None
    tipo = None
    serventia = nome
    base = nome.split(" - ", 1)[0].strip()
    patterns = [
        ("vara", r"^(\d+)[ªº]?\s+VARA\b\s*(.*)$"),
        ("camara", r"^(\d+)[ªº]?\s+C[ÂA]MARA\b\s*(.*)$"),
        ("turma", r"^(\d+)[ªº]?\s+TURMA\b\s*(.*)$"),
        ("secao", r"^(\d+)[ªº]?\s+SE[ÇC][AÃ]O\b\s*(.*)$"),
    ]
    for candidate, pattern in patterns:
        match = re.match(pattern, base, flags=re.IGNORECASE)
        if match:
            tipo = candidate
            numero = match.group(1)
            serventia = match.group(2).strip() or base
            break
    if tipo is None:
        up = base.upper()
        if "ÓRGÃO ESPECIAL" in up or "ORGAO ESPECIAL" in up:
            tipo = "orgao_especial"
            serventia = base
        elif "PLENO" in up:
            tipo = "pleno"
            serventia = base
        elif "GABINETE" in up or "DESEMBARGADOR" in up or "RELATOR" in up:
            tipo = "gabinete"
            serventia = base
        elif "CÂMARA" in up or "CAMARA" in up:
            tipo = "camara"
            serventia = base
        elif "TURMA" in up:
            tipo = "turma"
            serventia = base
        elif "VARA" in up:
            tipo = "vara"
            serventia = base
        else:
            tipo = "outro"
            serventia = base
    if " - " in serventia:
        serventia = serventia.split(" - ", 1)[0].strip()
    return tipo, numero, serventia or None


def _inferir_grau(tribunal: str | None, orgao_tipo: str | None, orgao_nome: str | None) -> tuple[str | None, str | None]:
    tribunal_up = str(tribunal or "").upper()
    if tribunal_up == "STJ":
        return "stj", None
    if tribunal_up == "STF":
        return "stf", None
    nome_up = str(orgao_nome or "").upper()
    if orgao_tipo in {"camara", "turma", "pleno", "orgao_especial", "gabinete", "secao"}:
        return "2grau", None
    if "2º GRAU" in nome_up or "2 GRAU" in nome_up or "SEGUNDO GRAU" in nome_up:
        return "2grau", None
    if orgao_tipo == "vara":
        return "1grau", None
    return None, orgao_nome


def _extract_comarca_foro(nome: str | None) -> tuple[str | None, str | None]:
    if not nome or " - " not in nome:
        return None, None
    comarca = nome.split(" - ")[-1].strip().title()
    return comarca or None, None


def _first_nome_parte(partes: list[dict], polo: str) -> str | None:
    for parte in partes:
        if isinstance(parte, dict) and parte.get("polo") == polo and parte.get("nome"):
            return str(parte["nome"])
    return None


def _map_processo_jusbr_prefill(data: dict, numero_cnj: str) -> ProcessoJusbrPrefillOut:
    tramitacao = _extract_tramitacao_principal(data)
    tribunal = data.get("siglaTribunal") or (tramitacao.get("tribunal") or {}).get("sigla")
    estado = TRIBUNAL_ESTADO_MAP.get(str(tribunal or "").upper(), "outro")
    orgao = tramitacao.get("orgaoJulgador") or {}
    orgao_nome = orgao.get("nome") if isinstance(orgao, dict) else None
    orgao_tipo, vara, serventia = _split_orgao_julgador(orgao_nome)
    grau, grau_texto = _inferir_grau(tribunal, orgao_tipo, orgao_nome)
    comarca, foro = _extract_comarca_foro(orgao_nome)
    assuntos = tramitacao.get("assunto") if isinstance(tramitacao.get("assunto"), list) else []
    classes = tramitacao.get("classe") if isinstance(tramitacao.get("classe"), list) else []
    partes = tramitacao.get("partes") if isinstance(tramitacao.get("partes"), list) else []
    materia = next((a.get("descricao") for a in assuntos if isinstance(a, dict) and a.get("descricao")), None)
    classe_desc = next((c.get("descricao") for c in classes if isinstance(c, dict) and c.get("descricao")), None)
    objeto = " — ".join([v for v in [classe_desc, materia] if v]) or None
    parte_ativa = _first_nome_parte(partes, "ATIVO")
    parte_passiva = _first_nome_parte(partes, "PASSIVO")
    resumo = f"{tribunal or 'Tribunal'} • {classe_desc or 'Classe não informada'}"
    if materia:
        resumo += f" • {materia}"
    return ProcessoJusbrPrefillOut(
        numero_cnj=numero_cnj,
        estado=estado,
        tribunal=tribunal,
        orgao_julgador_tipo=orgao_tipo,
        vara=vara,
        comarca=comarca,
        materia=materia,
        objeto=objeto,
        serventia=serventia,
        foro=foro,
        sistema_juridico="pje",
        grau=grau,
        grau_texto=grau_texto,
        status="ativo" if tramitacao.get("ativo") is not False else "suspenso",
        polo=None,
        cliente_nome_sugerido=parte_ativa,
        parte_ativa_principal=parte_ativa,
        parte_passiva_principal=parte_passiva,
        resumo_encontrado=resumo,
    )


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


def _normalizar_payload_processo(fields: dict) -> dict:
    numero_cnj = fields.get("numero_cnj")
    tribunal = fields.get("tribunal")

    tribunal_norm = normalizar_tribunal(tribunal) if tribunal else ""
    tribunal_inferido = inferir_tribunal_pelo_cnj(numero_cnj) if numero_cnj else None

    if tribunal_norm:
        fields["tribunal"] = tribunal_norm
    elif tribunal_inferido:
        fields["tribunal"] = tribunal_inferido

    return fields




@router.get('/preencher-jusbr/{numero_cnj}', response_model=ProcessoJusbrPrefillOut)
async def preencher_processo_via_jusbr(numero_cnj: str):
    from app.services.consulta_processual.cnj import inferir_tribunal_pelo_cnj
    from app.services.consulta_processual.jusbr_session import load_session
    from app.services.consulta_processual.pdpj import buscar_processo_pdpj_raw

    session_data = load_session()
    if not session_data:
        raise HTTPException(status_code=400, detail='Sessao do jus.br nao configurada.')

    tribunal = inferir_tribunal_pelo_cnj(numero_cnj) or ''
    processo = await buscar_processo_pdpj_raw(numero_cnj, tribunal, session_data=session_data)
    if not processo:
        raise HTTPException(status_code=404, detail='Processo nao encontrado no jus.br com a sessao atual.')
    return _map_processo_jusbr_prefill(processo, numero_cnj)

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
    dump = _normalizar_payload_processo(dump)
    processo = Processo(**dump)
    db.add(processo)
    db.commit()
    db.refresh(processo)
    if litis_in:
        _sync_litisconsorcio(processo, litis_in, db)
        db.commit()
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
    fields = _normalizar_payload_processo(fields)
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

    drive_link = None

    # Envia para o Google Drive do cliente.
    try:
        from app.models.cliente import Cliente
        cliente = db.query(Cliente).filter(Cliente.id == processo.cliente_id).first()
        if cliente and processo.numero_cnj:
            try:
                from app.services.google_drive import upload_arquivo
                drive_link = upload_arquivo(
                    content,
                    file.filename,
                    cliente.nome,
                    processo.numero_cnj,
                    file.content_type or mimetypes.guess_type(file.filename)[0] or "application/pdf",
                    sub_subfolder="Documentos",
                )
            except Exception:
                pass
    except Exception:
        pass

    return {"filename": file.filename, "size": len(content), "drive_link": drive_link}


@router.get("/{processo_id}/documentos")
def listar_documentos(processo_id: uuid.UUID, db: Session = Depends(get_db)):
    processo = db.query(Processo).filter(Processo.id == processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    pasta = UPLOADS_DIR / str(processo_id)
    local_docs = [
        {"filename": f.name, "size": f.stat().st_size, "source": "local"}
        for f in sorted(pasta.iterdir())
        if f.suffix.lower() == ".pdf"
    ] if pasta.exists() else []

    drive_docs = []
    try:
        from app.models.cliente import Cliente
        from app.services.google_drive import listar_arquivos
        cliente = db.query(Cliente).filter(Cliente.id == processo.cliente_id).first()
        if cliente and processo.numero_cnj:
            drive_docs = listar_arquivos(cliente.nome, processo.numero_cnj, sub_subfolder="Documentos")
    except Exception:
        drive_docs = []

    nomes_drive = {d["filename"] for d in drive_docs}
    return [*drive_docs, *[doc for doc in local_docs if doc["filename"] not in nomes_drive]]


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
