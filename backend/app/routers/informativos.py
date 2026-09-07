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
    OptOutRequest,
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


@router.get("/destinatarios-por-fonte")
def destinatarios_por_fonte(db: Session = Depends(get_db)):
    return informativo_service.listar_destinatarios_por_fonte(db)


@router.get("/assinantes")
def listar_assinantes(db: Session = Depends(get_db)):
    from app.models.informativo import InformativoAssinante
    from app.models.usuario import Usuario
    itens = db.query(InformativoAssinante).order_by(InformativoAssinante.created_at.desc()).all()
    nomes_usuario = {u.id: u.nome for u in db.query(Usuario.id, Usuario.nome).all()}
    return [
        {
            "id": str(a.id), "email": a.email, "nome": a.nome, "ativo": a.ativo,
            "created_at": a.created_at.isoformat(), "fonte": a.fonte,
            "criado_por": nomes_usuario.get(a.criado_por_usuario_id) if a.criado_por_usuario_id else None,
        }
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


class AssinanteNomeRequest(BaseModel):
    nome: str | None = None


@router.patch("/assinantes/{assinante_id}")
def editar_nome_assinante(assinante_id: uuid.UUID, payload: AssinanteNomeRequest, db: Session = Depends(get_db)):
    """Corrige/preenche o nome de quem se inscreveu pelo formulário público
    (o form não pede nome) — não muda e-mail nem fonte."""
    from app.models.informativo import InformativoAssinante
    assinante = db.get(InformativoAssinante, assinante_id)
    if not assinante:
        raise HTTPException(status_code=404, detail="Assinante não encontrado")
    assinante.nome = (payload.nome or "").strip() or None
    db.commit()
    return {"ok": True}


class AssinanteManualRequest(BaseModel):
    email: str
    nome: str | None = None


@router.post("/assinantes", status_code=201)
def criar_assinante_manual(
    payload: AssinanteManualRequest, db: Session = Depends(get_db), usuario=Depends(get_current_user)
):
    """Adiciona um e-mail/destinatário manualmente (fora do formulário
    público do site) — usado pra cadastro avulso na tela de E-mails."""
    from app.models.informativo import InformativoAssinante

    email = (payload.email or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="E-mail inválido.")
    existente = db.query(InformativoAssinante).filter(InformativoAssinante.email == email).first()
    if existente:
        if payload.nome:
            existente.nome = payload.nome
        existente.ativo = True
        db.commit()
        return {"ok": True, "novo": False}
    db.add(InformativoAssinante(
        email=email, nome=(payload.nome or None), fonte="manual", criado_por_usuario_id=usuario.id,
    ))
    db.commit()
    return {"ok": True, "novo": True}


class ImportarAssinantesRequest(BaseModel):
    itens: list[AssinanteManualRequest]


@router.post("/assinantes/importar")
def importar_assinantes(
    payload: ImportarAssinantesRequest, db: Session = Depends(get_db), usuario=Depends(get_current_user)
):
    """Importação em lote — usada pelo textarea de colar CSV (o front já
    parseia e manda [{email, nome}, ...])."""
    from app.models.informativo import InformativoAssinante

    existentes = {a.email: a for a in db.query(InformativoAssinante).all()}
    criados = atualizados = invalidos = 0
    for item in payload.itens:
        email = (item.email or "").strip().lower()
        if not email or "@" not in email:
            invalidos += 1
            continue
        if email in existentes:
            if item.nome:
                existentes[email].nome = item.nome
            atualizados += 1
        else:
            nova = InformativoAssinante(email=email, nome=(item.nome or None), fonte="csv", criado_por_usuario_id=usuario.id)
            db.add(nova)
            existentes[email] = nova
            criados += 1
    db.commit()
    return {"criados": criados, "atualizados": atualizados, "invalidos": invalidos}


@router.post("/assinantes/importar-arquivo")
async def importar_assinantes_arquivo(
    file: UploadFile = File(...), db: Session = Depends(get_db), usuario=Depends(get_current_user)
):
    """Importação a partir de planilha Excel (.xlsx/.xls) ou CSV — identifica
    as colunas de e-mail/nome pelo cabeçalho (aceita variações comuns)."""
    import csv
    import io
    from app.models.informativo import InformativoAssinante

    nome_arquivo = (file.filename or "").lower()
    content = await file.read()

    linhas: list[dict[str, str]] = []
    if nome_arquivo.endswith((".xlsx", ".xls")):
        import openpyxl
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content))
            ws = wb.active
        except Exception:
            raise HTTPException(status_code=400, detail="Arquivo Excel inválido.")
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise HTTPException(status_code=400, detail="Planilha vazia.")
        headers = [str(c or "").strip().lower() for c in rows[0]]
        for row in rows[1:]:
            linhas.append({headers[i]: str(v).strip() if v is not None else "" for i, v in enumerate(row) if i < len(headers)})
    elif nome_arquivo.endswith(".csv"):
        texto = content.decode("utf-8-sig", errors="ignore")
        reader = csv.DictReader(io.StringIO(texto))
        linhas = [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader]
    else:
        raise HTTPException(status_code=400, detail="Envie um arquivo .xlsx, .xls ou .csv.")

    def _campo(row: dict, *chaves: str) -> str:
        for k in chaves:
            if k in row and row[k]:
                return row[k]
        return ""

    existentes = {a.email: a for a in db.query(InformativoAssinante).all()}
    criados = atualizados = invalidos = 0
    for row in linhas:
        email = _campo(row, "email", "e-mail", "e_mail").strip().lower()
        nome = _campo(row, "nome", "name")
        if not email or "@" not in email:
            invalidos += 1
            continue
        if email in existentes:
            if nome:
                existentes[email].nome = nome
            atualizados += 1
        else:
            nova = InformativoAssinante(email=email, nome=(nome or None), fonte="xls", criado_por_usuario_id=usuario.id)
            db.add(nova)
            existentes[email] = nova
            criados += 1
    db.commit()
    return {"criados": criados, "atualizados": atualizados, "invalidos": invalidos}


@router.post("/opt-out", status_code=204)
def opt_out_manual(payload: OptOutRequest, db: Session = Depends(get_db)):
    """Descadastra um e-mail (Cliente, Contato ou Assinante) da newsletter
    por escolha do Lucas — continua listado na tela, só marcado."""
    try:
        informativo_service.opt_out_manual(db, payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/opt-out/excluir", status_code=204)
def excluir_email(payload: OptOutRequest, db: Session = Depends(get_db)):
    """Some com o e-mail da tela de E-mails por completo (além de nunca mais
    receber). Não apaga o Cliente/Contato em si."""
    try:
        informativo_service.excluir_email_completamente(db, payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/opt-out/reativar", status_code=204)
def reativar_email(payload: OptOutRequest, db: Session = Depends(get_db)):
    """Desfaz opt-out/exclusão manual — volta a receber e a aparecer normal."""
    informativo_service.reativar_email(db, payload.email)


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
    """Soft-delete — o número já foi atribuído e não deve ser reaproveitado
    por um informativo novo, então a linha fica marcada como "excluido" (a
    tela mostra cinza/riscado) em vez de sumir do banco. Guarda o status
    anterior pra "Restaurar" voltar exatamente pro estado de antes (inclusive
    reaparecendo nos links públicos se estava publicado)."""
    from datetime import datetime, timezone
    informativo = _get(db, informativo_id)
    informativo.status_anterior_exclusao = informativo.status
    informativo.status = "excluido"
    informativo.excluido_em = datetime.now(timezone.utc)
    db.commit()


@router.post("/{informativo_id}/restaurar", response_model=InformativoOut)
def restaurar(informativo_id: uuid.UUID, db: Session = Depends(get_db)):
    """Desfaz a exclusão — volta pro status de antes (publicado, rascunho
    etc.), sem precisar recriar do zero."""
    informativo = _get(db, informativo_id)
    if informativo.status != "excluido":
        raise HTTPException(status_code=400, detail="Este informativo não está excluído.")
    informativo.status = informativo.status_anterior_exclusao or "rascunho"
    informativo.status_anterior_exclusao = None
    informativo.excluido_em = None
    db.commit()
    db.refresh(informativo)
    return informativo


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


class CorpoManualRequest(BaseModel):
    texto: str


@router.post("/{informativo_id}/definir-corpo-manual", response_model=SincronizarResponse)
def definir_corpo_manual(informativo_id: uuid.UUID, payload: CorpoManualRequest, db: Session = Depends(get_db)):
    """Grava um texto pronto (colado, não gerado por IA) como corpo — sem
    chamar a IA. Segue a mesma esteira de checagem/publicação de sempre; o
    texto só muda se "Reescrever" for pedido explicitamente depois."""
    informativo = _get(db, informativo_id)
    try:
        texto, citacoes = informativo_service.definir_corpo_manual(informativo, payload.texto)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao gravar o texto: {exc}")
    db.commit()
    return SincronizarResponse(conteudo_texto=texto, citacoes=citacoes)


@router.post("/{informativo_id}/upload-pdf-manual", response_model=SincronizarResponse)
async def upload_pdf_manual(informativo_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Sobe um PDF já pronto (feito fora do sistema) — extrai o texto e grava
    como corpo, exatamente como "colar texto pronto". Segue dali a mesma
    esteira de sempre (checagem, preview, publicar), e "publicar" sempre
    reexporta o Google Doc — que já vai ter esse texto, com o timbrado do
    modelo."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo PDF.")
    informativo = _get(db, informativo_id)
    conteudo = await file.read()
    try:
        from pypdf import PdfReader
        import io as _io
        paginas_pdf = PdfReader(_io.BytesIO(conteudo)).pages
        texto = "\n\n".join((p.extract_text() or "").strip() for p in paginas_pdf).strip()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Não consegui ler o PDF: {exc}")
    if not texto:
        raise HTTPException(status_code=400, detail="Não encontrei texto no PDF (pode ser um PDF só de imagem/escaneado).")
    try:
        texto, citacoes = informativo_service.definir_corpo_manual(informativo, texto)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao gravar o texto: {exc}")
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


@router.get("/{informativo_id}/resumo-perguntas")
def resumo_perguntas(informativo_id: uuid.UUID, db: Session = Depends(get_db)):
    """Resumo + perguntas-teaser lidos do Doc — usado pra montar o texto
    padrão de WhatsApp no front (mesmo conteúdo do e-mail da newsletter)."""
    informativo = _get(db, informativo_id)
    resumo = perguntas = None
    if informativo.google_doc_id:
        from app.services.google_docs import ler_perguntas_documento, ler_resumo_documento
        try:
            resumo = ler_resumo_documento(informativo.google_doc_id)
        except Exception:
            resumo = None
        try:
            perguntas = ler_perguntas_documento(informativo.google_doc_id)
        except Exception:
            perguntas = []
    return {"resumo": resumo, "perguntas": perguntas or []}


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
