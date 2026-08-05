import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.cliente import Cliente
from app.models.patrimonio import (
    PatrimonioAnexo,
    PatrimonioBem,
    PatrimonioCadeiaElo,
    PatrimonioSocio,
)
from app.schemas.patrimonio import (
    AnexoOut,
    BemCreate,
    BemOut,
    BemUpdate,
    CadeiaEloCreate,
    CadeiaEloOut,
    CadeiaEloUpdate,
    SocioCreate,
    SocioOut,
    SocioUpdate,
)

router = APIRouter(
    prefix="/patrimonio",
    tags=["patrimonio"],
    dependencies=[Depends(get_current_user)],
)

DRIVE_SUBFOLDER = "Patrimônio"


def _safe(nome: str) -> str:
    return re.sub(r'[/\\:*?"<>|]', "", nome or "").strip()


def _bem_folder(bem: PatrimonioBem) -> str:
    """Nome da subpasta do bem dentro de Patrimônio/ no Drive."""
    partes = [_safe(bem.nome) or "bem"]
    if bem.numero_matricula:
        partes.append(f"mat {_safe(bem.numero_matricula)}")
    nome = " - ".join(partes)
    return nome[:120]


def _mime_de(ext: str) -> str:
    ext = ext.lower()
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext in (".doc", ".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/pdf"


def _get_bem(bem_id: uuid.UUID, db: Session) -> PatrimonioBem:
    bem = db.query(PatrimonioBem).filter(PatrimonioBem.id == bem_id).first()
    if not bem:
        raise HTTPException(status_code=404, detail="Bem não encontrado")
    return bem


def _cliente_nome(bem: PatrimonioBem, db: Session) -> str | None:
    c = db.query(Cliente).filter(Cliente.id == bem.cliente_id).first()
    return c.nome if c else None


# ── Bens ─────────────────────────────────────────────────────────────────────
@router.get("/", response_model=list[BemOut])
def listar_bens(
    cliente_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
):
    return (
        db.query(PatrimonioBem)
        .filter(PatrimonioBem.cliente_id == cliente_id)
        .order_by(PatrimonioBem.ordem.asc().nullslast(), PatrimonioBem.created_at.desc())
        .all()
    )


class ReordenarPayload(BaseModel):
    ordem: list[uuid.UUID]  # ids dos bens na nova ordem


@router.post("/reordenar")
def reordenar_bens(
    payload: ReordenarPayload,
    cliente_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
):
    """Aplica a nova ordem (lista de ids) aos bens do cliente."""
    bens = {
        str(b.id): b
        for b in db.query(PatrimonioBem).filter(PatrimonioBem.cliente_id == cliente_id).all()
    }
    for i, bem_id in enumerate(payload.ordem):
        bem = bens.get(str(bem_id))
        if bem:
            bem.ordem = i
    db.commit()
    return {"ok": True}


def _bens_do_cliente(cliente_id: uuid.UUID, db: Session) -> tuple[str, list[PatrimonioBem]]:
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    bens = (
        db.query(PatrimonioBem)
        .filter(PatrimonioBem.cliente_id == cliente_id)
        .order_by(PatrimonioBem.ordem.asc().nullslast(), PatrimonioBem.created_at.desc())
        .all()
    )
    return cliente.nome, bens


@router.get("/export/xls")
def exportar_xls(cliente_id: uuid.UUID = Query(...), db: Session = Depends(get_db)):
    from app.services.patrimonio_export import gerar_xls
    nome, bens = _bens_do_cliente(cliente_id, db)
    conteudo = gerar_xls(nome, bens)
    fname = f"Patrimonio - {_safe(nome)}.xlsx"
    return Response(
        content=conteudo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/export/pdf")
def exportar_pdf(cliente_id: uuid.UUID = Query(...), db: Session = Depends(get_db)):
    from app.services.patrimonio_export import gerar_pdf
    nome, bens = _bens_do_cliente(cliente_id, db)
    conteudo = gerar_pdf(nome, bens)
    fname = f"Patrimonio - {_safe(nome)}.pdf"
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/extrair-escritura")
def extrair_escritura_endpoint(file: UploadFile = File(...)):
    """Lê uma escritura/matrícula (PDF ou imagem) via IA e devolve os campos
    extraídos + o trecho de origem de cada um. NÃO persiste o arquivo — o upload
    para o Drive só acontece quando o usuário salvar o bem."""
    conteudo = file.file.read()
    filename = (file.filename or "").lower()
    mime = file.content_type or ""
    if not mime or mime == "application/octet-stream":
        if filename.endswith(".pdf"):
            mime = "application/pdf"
        elif filename.endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        elif filename.endswith(".png"):
            mime = "image/png"
        elif filename.endswith(".webp"):
            mime = "image/webp"
    from app.services.escritura_ia import extrair_escritura
    resultado = extrair_escritura(conteudo, mime)
    if resultado.get("erro"):
        raise HTTPException(status_code=502, detail=resultado["erro"])
    return resultado


@router.post("/", response_model=BemOut, status_code=status.HTTP_201_CREATED)
def criar_bem(data: BemCreate, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.id == data.cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    bem = PatrimonioBem(**data.model_dump())
    db.add(bem)
    db.commit()
    db.refresh(bem)
    return bem


@router.get("/{bem_id}", response_model=BemOut)
def obter_bem(bem_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_bem(bem_id, db)


@router.patch("/{bem_id}", response_model=BemOut)
def atualizar_bem(bem_id: uuid.UUID, data: BemUpdate, db: Session = Depends(get_db)):
    bem = _get_bem(bem_id, db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(bem, field, value)
    db.commit()
    db.refresh(bem)
    return bem


@router.delete("/{bem_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_bem(bem_id: uuid.UUID, db: Session = Depends(get_db)):
    bem = _get_bem(bem_id, db)
    db.delete(bem)
    db.commit()


# ── Anexos do bem ────────────────────────────────────────────────────────────
@router.post("/{bem_id}/anexos", response_model=AnexoOut, status_code=status.HTTP_201_CREATED)
def upload_anexo(
    bem_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    bem = _get_bem(bem_id, db)
    conteudo = file.file.read()
    filename = file.filename or "documento.pdf"
    ext = Path(filename).suffix or ".pdf"
    mime = _mime_de(ext)

    drive_link: str | None = None
    try:
        from app.services.google_drive import upload_arquivo
        nome_cliente = _cliente_nome(bem, db)
        if nome_cliente:
            drive_link = upload_arquivo(
                conteudo, filename, nome_cliente, DRIVE_SUBFOLDER, mime,
                sub_subfolder=_bem_folder(bem),
            )
    except Exception:
        pass

    anexo = PatrimonioAnexo(bem_id=bem.id, filename=filename, drive_link=drive_link, mime=mime)
    db.add(anexo)
    db.commit()
    db.refresh(anexo)
    return anexo


@router.delete("/{bem_id}/anexos/{anexo_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_anexo(bem_id: uuid.UUID, anexo_id: uuid.UUID, db: Session = Depends(get_db)):
    bem = _get_bem(bem_id, db)
    anexo = (
        db.query(PatrimonioAnexo)
        .filter(PatrimonioAnexo.id == anexo_id, PatrimonioAnexo.bem_id == bem_id)
        .first()
    )
    if not anexo:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    try:
        from app.services.google_drive import deletar_arquivo
        nome_cliente = _cliente_nome(bem, db)
        if nome_cliente:
            deletar_arquivo(nome_cliente, DRIVE_SUBFOLDER, anexo.filename, sub_subfolder=_bem_folder(bem))
    except Exception:
        pass
    db.delete(anexo)
    db.commit()


# ── Cadeia sucessória ────────────────────────────────────────────────────────
@router.post("/{bem_id}/cadeia", response_model=CadeiaEloOut, status_code=status.HTTP_201_CREATED)
def criar_elo(bem_id: uuid.UUID, data: CadeiaEloCreate, db: Session = Depends(get_db)):
    bem = _get_bem(bem_id, db)
    elo = PatrimonioCadeiaElo(bem_id=bem.id, **data.model_dump())
    db.add(elo)
    db.commit()
    db.refresh(elo)
    return elo


@router.patch("/{bem_id}/cadeia/{elo_id}", response_model=CadeiaEloOut)
def atualizar_elo(
    bem_id: uuid.UUID, elo_id: uuid.UUID, data: CadeiaEloUpdate, db: Session = Depends(get_db)
):
    elo = (
        db.query(PatrimonioCadeiaElo)
        .filter(PatrimonioCadeiaElo.id == elo_id, PatrimonioCadeiaElo.bem_id == bem_id)
        .first()
    )
    if not elo:
        raise HTTPException(status_code=404, detail="Elo não encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(elo, field, value)
    db.commit()
    db.refresh(elo)
    return elo


@router.delete("/{bem_id}/cadeia/{elo_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_elo(bem_id: uuid.UUID, elo_id: uuid.UUID, db: Session = Depends(get_db)):
    elo = (
        db.query(PatrimonioCadeiaElo)
        .filter(PatrimonioCadeiaElo.id == elo_id, PatrimonioCadeiaElo.bem_id == bem_id)
        .first()
    )
    if not elo:
        raise HTTPException(status_code=404, detail="Elo não encontrado")
    if elo.arquivo_nome:
        bem = _get_bem(bem_id, db)
        try:
            from app.services.google_drive import deletar_arquivo
            nome_cliente = _cliente_nome(bem, db)
            if nome_cliente:
                deletar_arquivo(
                    nome_cliente, DRIVE_SUBFOLDER, elo.arquivo_nome,
                    sub_subfolder=_bem_folder(bem),
                )
        except Exception:
            pass
    db.delete(elo)
    db.commit()


@router.post("/{bem_id}/cadeia/{elo_id}/anexo", response_model=CadeiaEloOut)
def upload_anexo_elo(
    bem_id: uuid.UUID,
    elo_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    bem = _get_bem(bem_id, db)
    elo = (
        db.query(PatrimonioCadeiaElo)
        .filter(PatrimonioCadeiaElo.id == elo_id, PatrimonioCadeiaElo.bem_id == bem_id)
        .first()
    )
    if not elo:
        raise HTTPException(status_code=404, detail="Elo não encontrado")

    conteudo = file.file.read()
    filename = file.filename or "documento.pdf"
    ext = Path(filename).suffix or ".pdf"
    mime = _mime_de(ext)

    drive_link: str | None = None
    try:
        from app.services.google_drive import upload_arquivo
        nome_cliente = _cliente_nome(bem, db)
        if nome_cliente:
            drive_link = upload_arquivo(
                conteudo, filename, nome_cliente, DRIVE_SUBFOLDER, mime,
                sub_subfolder=_bem_folder(bem),
            )
    except Exception:
        pass

    elo.arquivo_nome = filename
    elo.drive_link = drive_link
    db.commit()
    db.refresh(elo)
    return elo


# ── Sócios (bem móvel = cota social) ─────────────────────────────────────────
@router.post("/{bem_id}/socios", response_model=SocioOut, status_code=status.HTTP_201_CREATED)
def criar_socio(bem_id: uuid.UUID, data: SocioCreate, db: Session = Depends(get_db)):
    bem = _get_bem(bem_id, db)
    socio = PatrimonioSocio(bem_id=bem.id, **data.model_dump())
    db.add(socio)
    db.commit()
    db.refresh(socio)
    return socio


@router.patch("/{bem_id}/socios/{socio_id}", response_model=SocioOut)
def atualizar_socio(
    bem_id: uuid.UUID, socio_id: uuid.UUID, data: SocioUpdate, db: Session = Depends(get_db)
):
    socio = (
        db.query(PatrimonioSocio)
        .filter(PatrimonioSocio.id == socio_id, PatrimonioSocio.bem_id == bem_id)
        .first()
    )
    if not socio:
        raise HTTPException(status_code=404, detail="Sócio não encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(socio, field, value)
    db.commit()
    db.refresh(socio)
    return socio


@router.delete("/{bem_id}/socios/{socio_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_socio(bem_id: uuid.UUID, socio_id: uuid.UUID, db: Session = Depends(get_db)):
    socio = (
        db.query(PatrimonioSocio)
        .filter(PatrimonioSocio.id == socio_id, PatrimonioSocio.bem_id == bem_id)
        .first()
    )
    if not socio:
        raise HTTPException(status_code=404, detail="Sócio não encontrado")
    db.delete(socio)
    db.commit()
