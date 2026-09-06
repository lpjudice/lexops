import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.informativo import Informativo
from app.schemas.informativo import (
    InformativoAtualizar,
    InformativoCriar,
    InformativoOut,
    PublicarResponse,
    SincronizarResponse,
    ValidarCitacoesResponse,
)
from app.services import informativo_service

router = APIRouter(
    prefix="/informativos",
    tags=["informativos"],
    dependencies=[Depends(get_current_user)],
)


def _get(db: Session, informativo_id: uuid.UUID) -> Informativo:
    informativo = db.get(Informativo, informativo_id)
    if not informativo:
        raise HTTPException(status_code=404, detail="Informativo não encontrado")
    return informativo


@router.get("", response_model=list[InformativoOut])
def listar(db: Session = Depends(get_db)):
    return (
        db.query(Informativo)
        .order_by(Informativo.mes_referencia.desc())
        .all()
    )


@router.get("/responsavel-padrao")
def responsavel_padrao(db: Session = Depends(get_db)):
    padrao = informativo_service.resolver_responsavel_padrao(db)
    if not padrao:
        return None
    return {"id": str(padrao.id), "nome": padrao.nome, "email": padrao.email}


@router.get("/{informativo_id}", response_model=InformativoOut)
def obter(informativo_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get(db, informativo_id)


@router.post("", response_model=InformativoOut, status_code=201)
def criar(payload: InformativoCriar, db: Session = Depends(get_db)):
    try:
        return informativo_service.criar_informativo(
            db,
            mes_referencia=payload.mes_referencia,
            titulo=payload.titulo,
            responsavel_id=payload.responsavel_id,
            tema_resumido=payload.tema_resumido,
            tema_sugestao_id=payload.tema_sugestao_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao criar informativo: {exc}")


@router.patch("/{informativo_id}", response_model=InformativoOut)
def atualizar(informativo_id: uuid.UUID, payload: InformativoAtualizar, db: Session = Depends(get_db)):
    informativo = _get(db, informativo_id)
    dados = payload.model_dump(exclude_unset=True)
    for campo, valor in dados.items():
        setattr(informativo, campo, valor)
    db.commit()
    db.refresh(informativo)
    return informativo


@router.delete("/{informativo_id}", status_code=204)
def excluir(informativo_id: uuid.UUID, db: Session = Depends(get_db)):
    informativo = _get(db, informativo_id)
    db.delete(informativo)
    db.commit()


@router.post("/{informativo_id}/upload", response_model=InformativoOut)
def upload_arquivo(informativo_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db)):
    informativo = _get(db, informativo_id)
    conteudo = file.file.read()
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    try:
        informativo_service.upload_arquivo_referencia(
            informativo, conteudo, file.filename or "arquivo", file.content_type or "application/octet-stream"
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    db.commit()
    db.refresh(informativo)
    return informativo


@router.post("/{informativo_id}/sincronizar-doc", response_model=SincronizarResponse)
def sincronizar_doc(informativo_id: uuid.UUID, db: Session = Depends(get_db)):
    informativo = _get(db, informativo_id)
    try:
        texto = informativo_service.sincronizar_do_doc(informativo)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return SincronizarResponse(conteudo_texto=texto)


@router.post("/{informativo_id}/validar-citacoes", response_model=ValidarCitacoesResponse)
def validar_citacoes(informativo_id: uuid.UUID, db: Session = Depends(get_db)):
    informativo = _get(db, informativo_id)
    try:
        citacoes = informativo_service.validar_citacoes(informativo)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao validar citações: {exc}")
    db.commit()
    return ValidarCitacoesResponse(citacoes=citacoes)


@router.get("/{informativo_id}/preview-html")
def preview_html(informativo_id: uuid.UUID, db: Session = Depends(get_db)):
    from fastapi import Response
    informativo = _get(db, informativo_id)
    if not (informativo.conteudo_texto or "").strip():
        raise HTTPException(status_code=400, detail="Sincronize o texto do Doc antes de pré-visualizar.")
    html = informativo_service.gerar_html(informativo, para_pdf=False)
    return Response(content=html, media_type="text/html; charset=utf-8")


@router.post("/{informativo_id}/publicar", response_model=PublicarResponse)
def publicar(informativo_id: uuid.UUID, db: Session = Depends(get_db)):
    informativo = _get(db, informativo_id)
    try:
        resultado = informativo_service.publicar(db, informativo)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao publicar: {exc}")
    db.commit()
    return PublicarResponse(**resultado)
