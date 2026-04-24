import io
import re
import unicodedata
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cliente import Cliente
from app.models.processo import Processo
from app.schemas.cliente import ClienteCreate, ClienteOut, ClienteUpdate, ClienteWithProcessos
from app.schemas.processo import ProcessoOut

UPLOADS_DIR = Path("/app/uploads/clientes")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/clientes", tags=["clientes"])


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"[-\s]+", "-", text).strip("-")


def _gerar_projeto(nome: str) -> tuple[str, str]:
    projeto_nome = f"{nome} — Contexto Jurídico"
    worktree_nome = f"cliente-{_slugify(nome)}"
    return projeto_nome, worktree_nome


def _pasta_cliente(cliente_id: uuid.UUID) -> Path:
    p = UPLOADS_DIR / str(cliente_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[ClienteOut])
def listar_clientes(db: Session = Depends(get_db)):
    return db.query(Cliente).order_by(Cliente.nome).all()


@router.post("/", response_model=ClienteOut, status_code=status.HTTP_201_CREATED)
def criar_cliente(data: ClienteCreate, db: Session = Depends(get_db)):
    projeto_nome, worktree_nome = _gerar_projeto(data.nome)
    cliente = Cliente(**data.model_dump(), projeto_nome=projeto_nome, worktree_nome=worktree_nome)
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    # Cria pasta no Dropbox (silencioso se não disponível)
    try:
        from app.services.pasta_cliente import pasta_cliente as _pasta_dropbox
        _pasta_dropbox(cliente.nome)
    except Exception:
        pass
    return cliente


@router.get("/{cliente_id}", response_model=ClienteWithProcessos)
def obter_cliente(cliente_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.routers.processos import _processo_to_out
    from sqlalchemy import inspect as _sa_inspect

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Build response manually so ProcessoOut.clientes_litisconsorcio is correctly serialized
    cliente_cols = {c.key: getattr(cliente, c.key) for c in _sa_inspect(Cliente).column_attrs}
    processos_out = [_processo_to_out(p, db) for p in cliente.processos]
    return {**cliente_cols, "processos": processos_out}


@router.patch("/{cliente_id}", response_model=ClienteOut)
def atualizar_cliente(
    cliente_id: uuid.UUID, data: ClienteUpdate, db: Session = Depends(get_db)
):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    # Renomeia pasta Dropbox ANTES de atualizar o banco
    if data.nome and data.nome != cliente.nome:
        try:
            from app.services.pasta_cliente import renomear_pasta_cliente
            renomear_pasta_cliente(cliente.nome, data.nome)
        except Exception:
            pass
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(cliente, field, value)
    # Atualiza projeto se nome mudou
    if data.nome:
        cliente.projeto_nome, cliente.worktree_nome = _gerar_projeto(data.nome)
    db.commit()
    db.refresh(cliente)
    return cliente


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_cliente(cliente_id: uuid.UUID, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    db.delete(cliente)
    db.commit()


# ── Documentos PDF ────────────────────────────────────────────────────────────

@router.post("/{cliente_id}/upload-pdf")
async def upload_pdf(
    cliente_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos")

    pasta = _pasta_cliente(cliente_id)
    dest = pasta / file.filename
    content = await file.read()
    dest.write_bytes(content)
    # Salva cópia na pasta Dropbox
    try:
        from app.services.pasta_cliente import pasta_tipo, salvar_arquivo
        salvar_arquivo(pasta_tipo(cliente.nome, "uploads"), file.filename, content)
    except Exception:
        pass
    return {"filename": file.filename, "size": len(content)}


@router.get("/{cliente_id}/documentos")
def listar_documentos(cliente_id: uuid.UUID, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Arquivos do servidor (uploads)
    pasta = UPLOADS_DIR / str(cliente_id)
    server_docs = []
    if pasta.exists():
        server_docs = [
            {"filename": f.name, "size": f.stat().st_size, "subpasta": None}
            for f in sorted(pasta.iterdir())
            if f.suffix.lower() in (".pdf", ".md", ".txt")
        ]

    # Arquivos do Dropbox
    try:
        from app.services.pasta_cliente import listar_arquivos
        dropbox_docs = listar_arquivos(cliente.nome)
    except Exception:
        dropbox_docs = []

    # Merge e deduplica por nome de arquivo
    nomes_server = {d["filename"] for d in server_docs}
    merged = list(server_docs)
    for arq in dropbox_docs:
        if arq["nome"] not in nomes_server:
            merged.append({
                "filename": arq["nome"],
                "size": arq["tamanho"],
                "subpasta": arq.get("subpasta"),
            })

    return merged


@router.delete("/{cliente_id}/documentos/{filename}")
def remover_documento(
    cliente_id: uuid.UUID, filename: str, db: Session = Depends(get_db)
):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    f = UPLOADS_DIR / str(cliente_id) / filename
    if not f.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    f.unlink()
    return {"ok": True}


# ── Batch processos via XLS ──────────────────────────────────────────────────

COLUNAS_TEMPLATE = [
    "numero_cnj", "vara", "comarca", "estado", "tribunal",
    "materia", "fase", "status", "polo", "objeto",
]

ESTADOS_VALIDOS = {"ES", "SP", "AM", "RJ", "outro"}
FASES_VALIDAS = {"conhecimento", "recursal", "execucao", "cumprimento_sentenca", "outro", ""}
STATUS_VALIDOS = {"ativo", "suspenso", "arquivado", "encerrado", ""}
POLOS_VALIDOS = {
    "autor", "reu", "litisconsorte", "assistente", "opoente",
    "interveniente", "perito", "avaliador", "interessado", "outro", "",
}


@router.get("/{cliente_id}/processos/template-xls")
def download_template_processos(cliente_id: uuid.UUID, db: Session = Depends(get_db)):
    """Retorna um arquivo Excel com o cabeçalho padrão para importação em lote."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Processos"

    # Cabeçalho
    headers = COLUNAS_TEMPLATE
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1D1E20", end_color="1D1E20", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")

    # Linha de exemplo
    exemplo = [
        "0000000-00.0000.0.00.0000",  # numero_cnj
        "1ª Vara Cível",              # vara
        "Vitória",                    # comarca
        "ES",                         # estado (ES/SP/AM/RJ/outro)
        "TJES",                       # tribunal
        "Direito Civil",              # materia
        "conhecimento",               # fase
        "ativo",                      # status
        "autor",                      # polo
        "Ação de indenização",        # objeto
    ]
    for col, val in enumerate(exemplo, 1):
        ws.cell(row=2, column=col, value=val)

    # Ajusta largura das colunas
    for col in ws.columns:
        max_len = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[col[0].column_letter].width = max_len + 4

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=processos_{cliente_id}.xlsx"},
    )


@router.post("/{cliente_id}/processos/batch", response_model=list[ProcessoOut])
async def importar_processos_batch(
    cliente_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Importa processos em lote a partir de um arquivo Excel."""
    import openpyxl

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Apenas arquivos Excel (.xlsx) são aceitos")

    content = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content))
        ws = wb.active
    except Exception:
        raise HTTPException(status_code=400, detail="Arquivo Excel inválido")

    # Mapeia cabeçalhos
    headers = [str(c.value or "").strip().lower() for c in next(ws.iter_rows(min_row=1, max_row=1))]
    if "numero_cnj" not in headers:
        raise HTTPException(status_code=400, detail="Coluna 'numero_cnj' não encontrada — use o template")

    criados = []
    erros = []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        if all(v is None or str(v).strip() == "" for v in row):
            continue
        values = {headers[i]: str(v).strip() if v is not None else "" for i, v in enumerate(row) if i < len(headers)}

        cnj = values.get("numero_cnj", "")
        if not cnj:
            erros.append(f"Linha {row_idx}: numero_cnj vazio")
            continue

        # Verifica duplicata
        if db.query(Processo).filter(Processo.numero_cnj == cnj).first():
            erros.append(f"Linha {row_idx}: {cnj} já existe")
            continue

        estado_raw = values.get("estado", "ES")
        if estado_raw not in ESTADOS_VALIDOS:
            estado_raw = "outro"

        fase_raw = values.get("fase", "") or None
        if fase_raw and fase_raw not in FASES_VALIDAS:
            fase_raw = "outro"

        status_raw = values.get("status", "ativo") or "ativo"
        if status_raw not in STATUS_VALIDOS:
            status_raw = "ativo"

        polo_raw = values.get("polo", "") or None
        if polo_raw and polo_raw not in POLOS_VALIDOS:
            polo_raw = "outro"

        proc = Processo(
            cliente_id=cliente_id,
            numero_cnj=cnj,
            vara=values.get("vara") or None,
            comarca=values.get("comarca") or None,
            estado=estado_raw,
            tribunal=values.get("tribunal") or None,
            materia=values.get("materia") or None,
            fase=fase_raw,
            status=status_raw,
            polo=polo_raw,
            objeto=values.get("objeto") or None,
        )
        db.add(proc)
        criados.append(proc)

    if erros and not criados:
        raise HTTPException(status_code=422, detail="; ".join(erros))

    db.commit()
    for p in criados:
        db.refresh(p)

    # Cria subpastas no Dropbox para os processos criados
    try:
        from app.services.pasta_cliente import pasta_processo as _pasta_proc
        for p in criados:
            if p.numero_cnj:
                _pasta_proc(cliente.nome, p.numero_cnj)
    except Exception:
        pass

    return criados


# ── Proposta PDF ─────────────────────────────────────────────────────────────

class PropostaRequest(BaseModel):
    projeto_tipo: str = "PPS"
    valor: str = ""
    condicao_pagamento: str = ""
    intro_texto: str = ""
    anamnese_resumo: str = ""
    blocos_extras: dict | None = None  # {bloco_nome: [item, ...]}


@router.post("/{cliente_id}/proposta")
def gerar_proposta(
    cliente_id: uuid.UUID,
    body: PropostaRequest,
    db: Session = Depends(get_db),
):
    from datetime import date
    from app.services.proposta_pdf import gerar_proposta as _gerar

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    pdf_bytes = _gerar(
        cliente_nome=cliente.nome,
        projeto_tipo=body.projeto_tipo,
        valor=body.valor,
        condicao_pagamento=body.condicao_pagamento,
        intro_texto=body.intro_texto,
        anamnese_resumo=body.anamnese_resumo,
        data_proposta=date.today(),
        blocos_extras=body.blocos_extras,
    )

    # Salva proposta em uploads/clientes/{id}/
    pasta = _pasta_cliente(cliente_id)
    from datetime import datetime
    nome_arquivo = f"Proposta_{body.projeto_tipo}_{datetime.today().strftime('%Y%m%d')}.pdf"
    (pasta / nome_arquivo).write_bytes(pdf_bytes)

    # Salva cópia no Dropbox
    try:
        from app.services.pasta_cliente import pasta_tipo, salvar_arquivo
        salvar_arquivo(pasta_tipo(cliente.nome, "contratos"), nome_arquivo, pdf_bytes)
    except Exception:
        pass

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )


# ── Chat IA ───────────────────────────────────────────────────────────────────

class ChatClienteRequest(BaseModel):
    pergunta: str
    historico: list[dict] = []
    modelo: str = "claude"


@router.post("/{cliente_id}/chat")
def chat_cliente(
    cliente_id: uuid.UUID,
    body: ChatClienteRequest,
    db: Session = Depends(get_db),
):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    n_processos = len(cliente.processos)
    contexto = (
        f"Nome: {cliente.nome}, Tipo: {cliente.tipo}"
        + (f", Email: {cliente.email}" if cliente.email else "")
        + (f", Telefone: {cliente.telefone}" if cliente.telefone else "")
        + f", Processos vinculados: {n_processos}"
        + (f", Observações: {cliente.observacoes}" if cliente.observacoes else "")
    )

    from app.services.ia_cliente import chat
    # Sempre usa Gemini para contexto completo do Dropbox
    resposta = chat(
        modelo="gemini",
        pergunta=body.pergunta,
        historico=body.historico,
        cliente_id=str(cliente_id),
        contexto=contexto,
        nome_cliente=cliente.nome,
    )
    return {"resposta": resposta}


# ── Emails ────────────────────────────────────────────────────────────────────

class EmailSyncRequest(BaseModel):
    conta_google: str = "master"  # "master" or str(usuario_id)


class EmailOut(BaseModel):
    id: uuid.UUID
    gmail_message_id: str
    conta_google: str
    conta_email: str | None
    remetente: str | None
    destinatarios: str | None
    assunto: str | None
    snippet: str | None
    thread_id: str | None
    data: str | None  # ISO datetime string
    lido: bool
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/{cliente_id}/emails", response_model=list[EmailOut])
def listar_emails(cliente_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.models.email_cliente import EmailCliente
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    emails = (
        db.query(EmailCliente)
        .filter(EmailCliente.cliente_id == cliente_id)
        .order_by(EmailCliente.data.desc().nullslast())
        .all()
    )
    return [
        {
            "id": e.id,
            "gmail_message_id": e.gmail_message_id,
            "conta_google": e.conta_google,
            "conta_email": e.conta_email,
            "remetente": e.remetente,
            "destinatarios": e.destinatarios,
            "assunto": e.assunto,
            "snippet": e.snippet,
            "thread_id": e.thread_id,
            "data": e.data.isoformat() if e.data else None,
            "lido": e.lido,
            "created_at": e.created_at.isoformat(),
        }
        for e in emails
    ]


@router.post("/{cliente_id}/emails/sync")
def sincronizar_emails(cliente_id: uuid.UUID, body: EmailSyncRequest, db: Session = Depends(get_db)):
    from app.services.gmail_sync import sync_emails_for_client

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Collect client email addresses to search Gmail for
    emails_cliente: list[str] = []
    if cliente.email:
        emails_cliente.append(cliente.email)

    result = sync_emails_for_client(
        cliente_id=str(cliente_id),
        conta_google=body.conta_google,
        db_session=db,
        emails_cliente=emails_cliente,
    )

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.post("/{cliente_id}/pasta-arquivos/refresh")
def refresh_pasta_arquivos(cliente_id: uuid.UUID, db: Session = Depends(get_db)):
    """Returns all files in the client's Dropbox folder (including manually added)."""
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    from app.services.pasta_cliente import listar_arquivos
    return listar_arquivos(cliente.nome)
