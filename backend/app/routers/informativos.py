import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.informativo import Informativo
from app.schemas.informativo import (
    DestinatariosPreview,
    InformativoAtualizar,
    InformativoCriar,
    InformativoOut,
    NewsletterResponse,
    PublicarResponse,
    ReescreverRequest,
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


@router.get("/assinantes")
def listar_assinantes(db: Session = Depends(get_db)):
    from app.models.informativo import InformativoAssinante
    itens = db.query(InformativoAssinante).order_by(InformativoAssinante.created_at.desc()).all()
    return [
        {"id": str(a.id), "email": a.email, "nome": a.nome, "ativo": a.ativo, "created_at": a.created_at.isoformat()}
        for a in itens
    ]


@router.delete("/assinantes/{assinante_id}", status_code=204)
def excluir_assinante(assinante_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.models.informativo import InformativoAssinante
    assinante = db.get(InformativoAssinante, assinante_id)
    if not assinante:
        raise HTTPException(status_code=404, detail="Assinante não encontrado")
    db.delete(assinante)
    db.commit()


@router.get("/config/template")
def obter_template(db: Session = Depends(get_db)):
    cfg = informativo_service.obter_config(db)
    return {"template_doc_link": cfg.template_doc_link}


class ResponsavelPadraoRequest(BaseModel):
    responsavel_id: uuid.UUID | None = None


@router.patch("/config/responsavel-padrao")
def atualizar_responsavel_padrao(payload: ResponsavelPadraoRequest, db: Session = Depends(get_db)):
    resp = informativo_service.definir_responsavel_padrao(db, payload.responsavel_id)
    if not resp:
        return None
    return {"id": str(resp.id), "nome": resp.nome, "email": resp.email}


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
    if "autorizado" in dados:
        from datetime import datetime, timezone
        informativo.autorizado_em = datetime.now(timezone.utc) if dados["autorizado"] else None
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


@router.post("/{informativo_id}/gerar-rascunho-ia", response_model=SincronizarResponse)
def gerar_rascunho_ia(informativo_id: uuid.UUID, db: Session = Depends(get_db)):
    informativo = _get(db, informativo_id)
    try:
        texto, citacoes = informativo_service.gerar_rascunho_e_gravar(informativo)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao gerar rascunho: {exc}")
    db.commit()
    return SincronizarResponse(conteudo_texto=texto, citacoes=citacoes)


@router.post("/{informativo_id}/reescrever-ia", response_model=SincronizarResponse)
def reescrever_ia(informativo_id: uuid.UUID, payload: ReescreverRequest, db: Session = Depends(get_db)):
    informativo = _get(db, informativo_id)
    try:
        texto, citacoes = informativo_service.reescrever_com_apontamentos(informativo, payload.instrucoes)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao reescrever: {exc}")
    db.commit()
    return SincronizarResponse(conteudo_texto=texto, citacoes=citacoes)


@router.post("/{informativo_id}/sincronizar-doc", response_model=SincronizarResponse)
def sincronizar_doc(informativo_id: uuid.UUID, db: Session = Depends(get_db)):
    informativo = _get(db, informativo_id)
    try:
        texto, citacoes = informativo_service.sincronizar_do_doc(informativo)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    db.commit()
    return SincronizarResponse(conteudo_texto=texto, citacoes=citacoes)


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
    try:
        html = informativo_service.preview_doc_html(informativo)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(content=html, media_type="text/html; charset=utf-8")


@router.get("/{informativo_id}/newsletter/destinatarios", response_model=DestinatariosPreview)
def newsletter_destinatarios(informativo_id: uuid.UUID, db: Session = Depends(get_db)):
    _get(db, informativo_id)
    destinatarios = informativo_service.listar_destinatarios_newsletter(db)
    exemplos = [f"{nome} <{email}>" if nome else email for email, nome in destinatarios[:5]]
    return DestinatariosPreview(total=len(destinatarios), exemplos=exemplos)


class NewsletterTesteRequest(BaseModel):
    email: str


@router.post("/{informativo_id}/newsletter/teste")
def newsletter_teste(informativo_id: uuid.UUID, payload: NewsletterTesteRequest, db: Session = Depends(get_db)):
    informativo = _get(db, informativo_id)
    try:
        informativo_service.enviar_newsletter_teste(informativo, payload.email)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao enviar teste: {exc}")
    return {"ok": True}


@router.post("/{informativo_id}/newsletter/enviar", response_model=NewsletterResponse)
def newsletter_enviar(informativo_id: uuid.UUID, db: Session = Depends(get_db)):
    informativo = _get(db, informativo_id)
    try:
        resultado = informativo_service.enviar_newsletter(db, informativo)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao enviar newsletter: {exc}")
    return NewsletterResponse(**resultado)


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
