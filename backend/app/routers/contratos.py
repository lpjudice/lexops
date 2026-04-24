import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.contrato import Contrato, Signatario
from app.schemas.contrato import (
    ContratoCreate, ContratoOut, ContratoUpdate, GerarPdfRequest,
    SignatarioCreate, SignatarioOut,
)
from app.services import clicksign

UPLOADS_DIR = Path("/app/uploads/contratos")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/contratos", tags=["contratos"])


# ── CRUD básico ───────────────────────────────────────────────────────────────

@router.get("/", response_model=list[ContratoOut])
def listar_contratos(
    cliente_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Contrato)
    if cliente_id:
        q = q.filter(Contrato.cliente_id == cliente_id)
    return q.order_by(Contrato.created_at.desc()).all()


@router.post("/", response_model=ContratoOut, status_code=status.HTTP_201_CREATED)
def criar_contrato(data: ContratoCreate, db: Session = Depends(get_db)):
    contrato = Contrato(**data.model_dump())
    db.add(contrato)
    db.commit()
    db.refresh(contrato)
    return contrato


@router.get("/{contrato_id}", response_model=ContratoOut)
def obter_contrato(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    return c


@router.patch("/{contrato_id}", response_model=ContratoOut)
def atualizar_contrato(
    contrato_id: uuid.UUID, data: ContratoUpdate, db: Session = Depends(get_db)
):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(c, field, value)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{contrato_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_contrato(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    # Marcar honorários vinculados como órfãos para validação
    from app.models.financeiro import Honorario
    for h in db.query(Honorario).filter(Honorario.contrato_id == c.id).all():
        h.contrato_orfao = True
        h.contrato_id = None
    db.delete(c)
    db.commit()


# ── Upload de PDF (suporta múltiplos) ────────────────────────────────────────

@router.post("/{contrato_id}/upload", response_model=ContratoOut)
async def upload_pdf(
    contrato_id: uuid.UUID,
    arquivos: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    lista = list(c.arquivos or [])
    for arquivo in arquivos:
        if not arquivo.filename:
            continue
        nome_arquivo = f"{contrato_id}_{uuid.uuid4().hex[:8]}_{arquivo.filename}"
        destino = UPLOADS_DIR / nome_arquivo
        conteudo_bytes = arquivo.file.read()
        destino.write_bytes(conteudo_bytes)
        lista.append({"filename": arquivo.filename, "path": str(destino), "clicksign_key": None})
        # Mantém arquivo_path legado apontando para o primeiro arquivo
        if not c.arquivo_path:
            c.arquivo_path = str(destino)
        # Salva cópia no Dropbox + Drive
        try:
            from app.models.cliente import Cliente
            from app.services.pasta_cliente import pasta_tipo, salvar_arquivo
            cliente = db.query(Cliente).filter(Cliente.id == c.cliente_id).first()
            if cliente:
                salvar_arquivo(pasta_tipo(cliente.nome, "contratos"), arquivo.filename, conteudo_bytes)
                try:
                    from app.services.google_drive import upload_arquivo
                    upload_arquivo(conteudo_bytes, arquivo.filename, cliente.nome, "Contratos")
                except Exception:
                    pass
        except Exception:
            pass

    c.arquivos = lista
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{contrato_id}/arquivo", response_model=ContratoOut)
def remover_arquivo(
    contrato_id: uuid.UUID,
    filename: str,
    db: Session = Depends(get_db),
):
    """Remove um arquivo específico da lista de arquivos do contrato."""
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    if c.status != "rascunho":
        raise HTTPException(status_code=400, detail="Não é possível remover arquivos após o envio")

    nova_lista = [a for a in (c.arquivos or []) if a.get("filename") != filename]
    # Tenta apagar o arquivo físico
    for arq in (c.arquivos or []):
        if arq.get("filename") == filename:
            try:
                Path(arq["path"]).unlink(missing_ok=True)
            except Exception:
                pass
    c.arquivos = nova_lista
    c.arquivo_path = nova_lista[0]["path"] if nova_lista else None
    db.commit()
    db.refresh(c)
    return c


@router.get("/{contrato_id}/arquivo/{filename}")
def ver_arquivo(contrato_id: uuid.UUID, filename: str, db: Session = Depends(get_db)):
    """Serve o arquivo PDF para visualização."""
    from fastapi.responses import FileResponse
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    for arq in (c.arquivos or []):
        if arq.get("filename") == filename:
            path = Path(arq["path"])
            if path.exists():
                return FileResponse(str(path), media_type="application/pdf", filename=filename)
    raise HTTPException(status_code=404, detail="Arquivo não encontrado")


# ── Geração de PDF do contrato ────────────────────────────────────────────────

@router.post("/{contrato_id}/gerar-pdf", response_model=ContratoOut)
async def gerar_pdf_contrato(
    contrato_id: uuid.UUID,
    body: GerarPdfRequest,
    db: Session = Depends(get_db),
):
    """Gera o PDF do contrato de honorários e o adiciona à lista de arquivos."""
    from datetime import date as date_type
    from app.services.contrato_pdf import gerar_contrato

    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    data_contrato = None
    if body.data_contrato:
        try:
            data_contrato = date_type.fromisoformat(body.data_contrato)
        except ValueError:
            pass

    pdf_bytes = gerar_contrato(
        contratante_nome=body.contratante_nome,
        contratante_qualificacao=body.contratante_qualificacao,
        contratante_cpf_cnpj=body.contratante_cpf_cnpj,
        contratante_endereco=body.contratante_endereco,
        contratante_email=body.contratante_email,
        objeto_tipo=body.objeto_tipo,
        objeto_texto_livre=body.objeto_texto_livre,
        valor_honorarios=body.valor_honorarios,
        data_vencimento=body.data_vencimento,
        condicao_pagamento=body.condicao_pagamento,
        percentual_exito=body.percentual_exito,
        data_contrato=data_contrato,
    )

    nome_arquivo = f"Contrato_{body.contratante_nome.replace(' ', '_')}_{contrato_id.hex[:8]}.pdf"
    destino = UPLOADS_DIR / nome_arquivo
    destino.write_bytes(pdf_bytes)

    # Salva cópia no Dropbox + Drive do cliente
    try:
        from app.models.cliente import Cliente
        from app.services.pasta_cliente import pasta_tipo, salvar_arquivo
        cliente = db.query(Cliente).filter(Cliente.id == c.cliente_id).first()
        if cliente:
            salvar_arquivo(pasta_tipo(cliente.nome, "contratos"), nome_arquivo, pdf_bytes)
            try:
                from app.services.google_drive import upload_arquivo
                upload_arquivo(pdf_bytes, nome_arquivo, cliente.nome, "Contratos")
            except Exception:
                pass
    except Exception:
        pass

    lista = list(c.arquivos or [])
    lista.append({"filename": nome_arquivo, "path": str(destino), "clicksign_key": None})
    c.arquivos = lista
    c.arquivo_path = str(destino)
    db.commit()
    db.refresh(c)

    # Auto-cria/atualiza lançamento no financeiro vinculado a este contrato
    try:
        import re as _re
        from app.models.financeiro import Honorario
        from datetime import date as _date

        # Usa valor numérico se disponível, senão faz parse do texto
        if body.valor_honorarios_num is not None:
            valor_float = body.valor_honorarios_num
        else:
            raw = body.valor_honorarios or "0"
            valor_float = float(_re.sub(r'[^\d,]', '', raw).replace(',', '.') or '0')

        exito_pct_str = body.percentual_exito.strip() if body.percentual_exito else None
        eh_exito = bool(exito_pct_str and exito_pct_str not in ("0%", "0", "não haverá êxito"))

        # Parse percentual numérico
        pct_num = body.percentual_exito_num
        if pct_num is None and exito_pct_str:
            try:
                pct_num = float(exito_pct_str.replace('%', '').strip())
            except Exception:
                pct_num = None

        # Verifica se já há honorário vinculado a este contrato
        ja_existe = db.query(Honorario).filter(
            Honorario.contrato_id == contrato_id
        ).first()

        venc = None
        if body.data_vencimento:
            try:
                venc = _date.fromisoformat(body.data_vencimento)
            except Exception:
                pass

        if ja_existe:
            # Atualiza o existente (pode ter sido regenerado o PDF)
            if valor_float > 0:
                ja_existe.valor_total = valor_float
            if body.valor_causa is not None:
                ja_existe.valor_causa = body.valor_causa
            if pct_num is not None:
                ja_existe.percentual_exito = pct_num
            if venc:
                ja_existe.data_vencimento = venc
            db.commit()
        elif valor_float > 0 or eh_exito:
            descricao_h = f"Honorários — {body.objeto_tipo or body.objeto_texto_livre or 'Contrato'}"
            h = Honorario(
                cliente_id=c.cliente_id,
                processo_id=c.processo_id,
                contrato_id=contrato_id,
                descricao=descricao_h,
                tipo="exito" if eh_exito else "fixo",
                valor_total=valor_float,
                valor_causa=body.valor_causa,
                percentual_exito=pct_num,
                data_contrato=data_contrato or _date.today(),
                data_vencimento=venc,
                observacoes=f"Gerado automaticamente pelo contrato.",
                pendente_assinatura=True,  # pendente até confirmação de assinaturas
            )
            db.add(h)
            db.commit()
    except Exception:
        pass

    return c


# ── Signatários ───────────────────────────────────────────────────────────────

@router.post("/{contrato_id}/signatarios", response_model=SignatarioOut, status_code=status.HTTP_201_CREATED)
def adicionar_signatario(
    contrato_id: uuid.UUID, data: SignatarioCreate, db: Session = Depends(get_db)
):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    sig = Signatario(contrato_id=contrato_id, **data.model_dump())
    db.add(sig)
    db.commit()
    db.refresh(sig)
    return sig


@router.delete("/{contrato_id}/signatarios/{sig_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_signatario(contrato_id: uuid.UUID, sig_id: uuid.UUID, db: Session = Depends(get_db)):
    sig = db.query(Signatario).filter(
        Signatario.id == sig_id, Signatario.contrato_id == contrato_id
    ).first()
    if not sig:
        raise HTTPException(status_code=404, detail="Signatário não encontrado")
    db.delete(sig)
    db.commit()


# ── Envio para ClickSign ──────────────────────────────────────────────────────

@router.post("/{contrato_id}/enviar", response_model=ContratoOut)
def enviar_para_assinatura(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    if not c.arquivo_path:
        raise HTTPException(status_code=400, detail="Faça upload do PDF antes de enviar")
    if not c.signatarios:
        raise HTTPException(status_code=400, detail="Adicione ao menos um signatário")

    # Determina lista de arquivos (usa arquivos JSONB se disponível, cai em arquivo_path legado)
    arquivos_para_enviar = list(c.arquivos or [])
    if not arquivos_para_enviar and c.arquivo_path:
        arquivos_para_enviar = [{"filename": Path(c.arquivo_path).name, "path": c.arquivo_path, "clicksign_key": None}]

    erros: list[str] = []

    # 1. Se houver mais de um PDF, mescla em um único arquivo antes do upload.
    #    O ClickSign API v1 não tem envelope multi-doc — um único PDF contém tudo.
    if len(arquivos_para_enviar) > 1:
        try:
            from pypdf import PdfWriter
            writer = PdfWriter()
            for arq in arquivos_para_enviar:
                writer.append(arq["path"])
            nome_merged = f"contrato_{contrato_id.hex[:8]}_completo.pdf"
            path_merged = UPLOADS_DIR / nome_merged
            with open(path_merged, "wb") as fout:
                writer.write(fout)
            arquivos_para_upload = [{"filename": nome_merged, "path": str(path_merged), "clicksign_key": None}]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao mesclar PDFs: {e}")
    else:
        arquivos_para_upload = arquivos_para_enviar

    # 2. Upload do documento (único) para o ClickSign
    arq_principal = arquivos_para_upload[0]
    nome_arq = arq_principal.get("filename", Path(arq_principal["path"]).name)
    try:
        doc_key_principal = clicksign.upload_documento(arq_principal["path"], nome_arq)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Falha no upload para o ClickSign: {e}")

    # Marca a clicksign_key em cada entrada original (todos apontam para o doc mesclado)
    lista_atualizada = [{**arq, "clicksign_key": doc_key_principal} for arq in arquivos_para_enviar]
    c.clicksign_document_key = doc_key_principal
    c.arquivos = lista_atualizada

    # 3. Criar signatários, vincular ao documento e enviar notificação por email
    # ↳ POST /lists vincula mas NÃO envia email; é necessário chamar POST /notifications
    for sig in c.signatarios:
        try:
            signer_key = clicksign.criar_signatario(sig.nome, sig.email)
            sig.clicksign_signer_key = signer_key
            req_key = clicksign.adicionar_signatario_ao_documento(
                doc_key_principal, signer_key, sig.papel
            )
            if req_key:
                sig.clicksign_request_key = req_key          # armazena por signatário
                c.clicksign_request_signature_key = req_key
                clicksign.notificar_signatario(req_key)      # dispara email de convite
        except Exception as e:
            erros.append(f"Signatário '{sig.email}': {e}")

    # (Não chamar /finish — isso fecha o documento permanentemente.
    #  auto_close=True já encerra ao receber todas as assinaturas.)

    if erros:
        import logging
        logging.warning("ClickSign erros parciais: %s", erros)

    c.status = "aguardando_assinatura"
    db.commit()
    db.refresh(c)
    return c


@router.post("/{contrato_id}/confirmar-assinatura", response_model=ContratoOut)
def confirmar_assinatura_manual(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    """Marca contrato como assinado manualmente e remove tag pendente_assinatura do honorário."""
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    c.status = "assinado"
    c.assinatura_manual = True
    # Remove pendência do honorário vinculado
    try:
        from app.models.financeiro import Honorario
        h = db.query(Honorario).filter(Honorario.contrato_id == contrato_id).first()
        if h:
            h.pendente_assinatura = False
    except Exception:
        pass
    db.commit()
    db.refresh(c)
    return c


@router.post("/{contrato_id}/cancelar", response_model=ContratoOut)
def cancelar_contrato_clicksign(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    if c.clicksign_document_key:
        clicksign.cancelar_documento(c.clicksign_document_key)
    c.status = "cancelado"
    db.commit()
    db.refresh(c)
    return c


# ── Webhook ClickSign ─────────────────────────────────────────────────────────

@router.post("/webhook/clicksign")
async def webhook_clicksign(request: Request, db: Session = Depends(get_db)):
    """
    Recebe callbacks do ClickSign sobre eventos de assinatura.
    Atualiza status do contrato e signatários.
    """
    payload = await request.json()
    evento = payload.get("event", {})
    nome_evento = evento.get("name", "")
    doc = payload.get("document", {})
    doc_key = doc.get("key")

    if not doc_key:
        return {"ok": True}

    contrato = db.query(Contrato).filter(Contrato.clicksign_document_key == doc_key).first()
    if not contrato:
        return {"ok": True}

    # Evento: signatário assinou
    if nome_evento == "sign":
        signer_key = evento.get("signer", {}).get("key")
        if signer_key:
            sig = db.query(Signatario).filter(
                Signatario.clicksign_signer_key == signer_key
            ).first()
            if sig:
                from datetime import datetime, timezone
                sig.status_assinatura = "assinado"
                sig.assinado_em = datetime.now(timezone.utc)

        # Verifica se todos assinaram
        todos = db.query(Signatario).filter(Signatario.contrato_id == contrato.id).all()
        if all(s.status_assinatura == "assinado" for s in todos):
            contrato.status = "assinado"

            # Baixa o PDF assinado
            pdf_bytes = clicksign.baixar_documento_assinado(doc_key)
            if pdf_bytes:
                path_assinado = UPLOADS_DIR / f"{contrato.id}_assinado.pdf"
                path_assinado.write_bytes(pdf_bytes)
                contrato.arquivo_assinado_path = str(path_assinado)
        else:
            contrato.status = "parcialmente_assinado"

    elif nome_evento == "cancel":
        contrato.status = "cancelado"

    elif nome_evento == "close":
        contrato.status = "assinado"

    db.commit()
    return {"ok": True}


# ── Download do PDF assinado ──────────────────────────────────────────────────

@router.get("/{contrato_id}/download-assinado")
def download_assinado(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c or not c.arquivo_assinado_path:
        raise HTTPException(status_code=404, detail="PDF assinado não disponível")
    return FileResponse(c.arquivo_assinado_path, media_type="application/pdf", filename=f"contrato_{contrato_id}_assinado.pdf")
