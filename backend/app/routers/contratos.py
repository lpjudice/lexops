import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.contrato import Contrato, Signatario
from app.schemas.contrato import (
    AplicarContratantesRequest, ContratoCreate, ContratoOut, ContratoUpdate,
    GerarPdfRequest, SignatarioCreate, SignatarioOut,
)
from app.services import clicksign

UPLOADS_DIR = Path("/app/uploads/contratos")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/contratos", tags=["contratos"],
                   dependencies=[Depends(get_current_user)])


def _duplicar_assinado_para_drive(db: Session, contrato: Contrato, pdf_bytes: bytes, nome_arquivo: str) -> tuple[str | None, str | None]:
    """
    Sobe o PDF final assinado para a pasta do cliente (LexOps/{cliente}/Contratos) e para
    a pasta mestra (LexOps/Contratos/{cliente}), que reúne todos os contratos finalizados
    da plataforma. Retorna (link_cliente, link_master); qualquer um pode vir None se o
    Drive não estiver conectado ou o upload falhar.
    """
    from app.models.cliente import Cliente
    from app.services.google_drive import upload_arquivo, upload_arquivo_raiz

    cliente = db.query(Cliente).filter(Cliente.id == contrato.cliente_id).first()
    if not cliente:
        return None, None

    link_cliente = None
    link_master = None
    try:
        link_cliente = upload_arquivo(pdf_bytes, nome_arquivo, cliente.nome, "Contratos")
    except Exception:
        pass
    try:
        link_master = upload_arquivo_raiz(pdf_bytes, nome_arquivo, subpath=["Contratos", cliente.nome], mimetype="application/pdf")
    except Exception:
        pass
    return link_cliente, link_master


def _parse_iso(ts: str | None):
    """Converte um timestamp ISO do ClickSign em datetime (tolerante ao sufixo 'Z')."""
    if not ts:
        return None
    from datetime import datetime
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _extrair_assinados(doc: dict) -> tuple[dict, dict]:
    """
    A partir da resposta do GET documento do ClickSign, retorna dois mapas
    (por signer_key e por email minúsculo) apontando para o timestamp de
    assinatura (ISO string) — a presença da chave já indica que assinou.

    Combina dois sinais para robustez: o objeto ``signature`` presente em cada
    signer que já assinou e os eventos ``name == "sign"``.
    """
    por_key: dict[str, str | None] = {}
    por_email: dict[str, str | None] = {}

    for s in doc.get("signers") or []:
        if s.get("signature"):
            sig_obj = s.get("signature") or {}
            ts = sig_obj.get("signed_at") or sig_obj.get("created_at")
            if s.get("key"):
                por_key[s["key"]] = ts
            if s.get("email"):
                por_email[s["email"].lower()] = ts

    for ev in doc.get("events") or []:
        if (ev.get("name") or "").lower() != "sign":
            continue
        ts = ev.get("occurred_at")
        data = ev.get("data") or {}
        candidatos = []
        if isinstance(data.get("signer"), dict):
            candidatos.append(data["signer"])
        for sg in data.get("signers") or []:
            if isinstance(sg, dict):
                candidatos.append(sg)
        if isinstance(data.get("user"), dict):
            candidatos.append(data["user"])
        for cand in candidatos:
            if cand.get("key"):
                por_key.setdefault(cand["key"], ts)
            if cand.get("email"):
                por_email.setdefault(cand["email"].lower(), ts)

    return por_key, por_email


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


@router.get("/pasta-mestra")
def obter_pasta_mestra():
    """Link da pasta mestra /Contratos na raiz do Drive (duplica todos os contratos finalizados)."""
    from app.services.google_drive import get_folder_link_raiz
    return {"link": get_folder_link_raiz(["Contratos"])}


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
    try:
        from app.models.cliente import Cliente
        from app.services.google_drive import deletar_arquivo
        cliente = db.query(Cliente).filter(Cliente.id == c.cliente_id).first()
        if cliente:
            for arq in c.arquivos or []:
                filename = arq.get("filename")
                if filename:
                    deletar_arquivo(cliente.nome, "Contratos", filename)
    except Exception:
        pass
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
        drive_link = None
        try:
            from app.models.cliente import Cliente
            cliente = db.query(Cliente).filter(Cliente.id == c.cliente_id).first()
            if cliente:
                from app.services.google_drive import upload_arquivo
                drive_link = upload_arquivo(conteudo_bytes, arquivo.filename, cliente.nome, "Contratos")
        except Exception:
            pass
        if drive_link:
            lista[-1]["drive_link"] = drive_link

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
            try:
                from app.models.cliente import Cliente
                from app.services.google_drive import deletar_arquivo
                cliente = db.query(Cliente).filter(Cliente.id == c.cliente_id).first()
                if cliente:
                    deletar_arquivo(cliente.nome, "Contratos", filename)
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


# ── Leitura de contratantes por IA ───────────────────────────────────────────

def _so_digitos(v: str | None) -> str:
    return "".join(ch for ch in (v or "") if ch.isdigit())


def _primeiro_pdf_path(c: Contrato) -> Path | None:
    """Caminho local do PDF principal do contrato (para enviar à IA)."""
    for arq in (c.arquivos or []):
        p = Path(arq.get("path", ""))
        if p.exists() and p.suffix.lower() == ".pdf":
            return p
    if c.arquivo_path:
        p = Path(c.arquivo_path)
        if p.exists():
            return p
    return None


@router.post("/{contrato_id}/ler-contratantes")
def ler_contratantes(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Lê o PDF anexado ao contrato com a IA e retorna os contratantes extraídos,
    já com candidatos de cliente existente (match por CPF/CNPJ e por nome).
    NÃO grava nada — só devolve sugestões para a tela de revisão decidir.
    """
    from app.models.cliente import Cliente
    from app.services.ia_contrato import extrair_contratantes

    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    pdf = _primeiro_pdf_path(c)
    if not pdf:
        raise HTTPException(status_code=400, detail="Nenhum PDF anexado para ler. Faça o upload do contrato primeiro.")

    resultado = extrair_contratantes(pdf.read_bytes(), "application/pdf")
    if resultado.get("erro"):
        raise HTTPException(status_code=502, detail=resultado["erro"])

    todos = db.query(Cliente).all()
    saida = []
    for ext in resultado.get("contratantes", []):
        cpf_dig = _so_digitos(ext.get("cpf_cnpj"))
        nome_l = (ext.get("nome") or "").strip().lower()
        candidatos = []
        for cli in todos:
            match = None
            if cpf_dig and _so_digitos(cli.cpf_cnpj) == cpf_dig:
                match = "cpf"
            elif nome_l and cli.nome and (
                nome_l == cli.nome.strip().lower()
                or nome_l in cli.nome.strip().lower()
                or cli.nome.strip().lower() in nome_l
            ):
                match = "nome"
            if match:
                candidatos.append({
                    "id": str(cli.id), "nome": cli.nome, "tipo": cli.tipo,
                    "cpf_cnpj": cli.cpf_cnpj, "email": cli.email,
                    "incompleto": bool(cli.incompleto), "match": match,
                })
        # cpf antes de nome
        candidatos.sort(key=lambda x: 0 if x["match"] == "cpf" else 1)
        saida.append({"extraido": ext, "candidatos": candidatos})

    return {"contratantes": saida}


def _preencher_vazios(cli, dados: dict, db: Session) -> None:
    """Preenche apenas os campos VAZIOS do cliente a partir de `dados` (merge não-destrutivo)."""
    from app.models.cliente import Cliente
    cpf = (dados.get("cpf_cnpj") or "").strip()
    if not cli.cpf_cnpj and cpf:
        ja = db.query(Cliente).filter(Cliente.cpf_cnpj == cpf, Cliente.id != cli.id).first()
        if not ja:
            cli.cpf_cnpj = cpf
    for campo in ("email", "telefone", "endereco", "estado_civil", "profissao"):
        valor = (dados.get(campo) or "").strip()
        if valor and not getattr(cli, campo, None):
            setattr(cli, campo, valor)


@router.post("/{contrato_id}/aplicar-contratantes", response_model=ContratoOut)
def aplicar_contratantes(
    contrato_id: uuid.UUID, body: AplicarContratantesRequest, db: Session = Depends(get_db)
):
    """
    Aplica as decisões da tela de revisão: atualiza clientes existentes (só campos
    vazios), cria novos (incompletos = pendentes de revisão), vincula o contrato ao
    contratante principal e anota os co-contratantes nas observações desse cliente.
    """
    from app.models.cliente import Cliente

    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")

    processados: list[tuple[Cliente, bool]] = []  # (cliente, is_principal)
    for dec in body.decisoes:
        if dec.acao == "ignorar":
            continue

        dados = dec.model_dump()
        if dec.acao == "atualizar":
            if not dec.cliente_id:
                raise HTTPException(status_code=400, detail=f"Cliente não informado para atualizar '{dec.nome}'.")
            cli = db.query(Cliente).filter(Cliente.id == dec.cliente_id).first()
            if not cli:
                raise HTTPException(status_code=404, detail=f"Cliente {dec.cliente_id} não encontrado.")
            _preencher_vazios(cli, dados, db)
        else:  # criar
            cli = Cliente(nome=dec.nome.strip(), tipo=dec.tipo, incompleto=True)
            db.add(cli)
            db.flush()  # garante id p/ checagem de unicidade em _preencher_vazios
            _preencher_vazios(cli, dados, db)

        if dec.diferenciador and dec.diferenciador.strip():
            nota = f"[contrato] {dec.diferenciador.strip()}"
            cli.observacoes = (cli.observacoes + "\n" + nota).strip() if cli.observacoes else nota

        processados.append((cli, dec.principal))

    if not processados:
        raise HTTPException(status_code=400, detail="Nenhuma decisão aplicável (todos ignorados).")

    # Contratante principal: o marcado, senão o primeiro processado.
    principal = next((cli for cli, is_p in processados if is_p), processados[0][0])

    # Anota co-contratantes no cadastro do principal.
    outros = [cli.nome for cli, _ in processados if cli is not principal]
    if outros:
        nota = f"[contrato] Mesmo contrato de: {', '.join(outros)}"
        principal.observacoes = (principal.observacoes + "\n" + nota).strip() if principal.observacoes else nota

    if body.vincular_contrato:
        c.cliente_id = principal.id

    db.commit()
    db.refresh(c)
    return c


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

    drive_link = None
    try:
        from app.models.cliente import Cliente
        cliente = db.query(Cliente).filter(Cliente.id == c.cliente_id).first()
        if cliente:
            from app.services.google_drive import upload_arquivo
            drive_link = upload_arquivo(pdf_bytes, nome_arquivo, cliente.nome, "Contratos")
    except Exception:
        pass

    # Pré-preenchimento reverso: os dados do contrato preenchem os campos VAZIOS do
    # cadastro do cliente (nunca sobrescreve o que já existe). Assim, um cliente criado
    # "só com o nome" pelo próprio contrato já chega à revisão com CPF/e-mail/endereço.
    try:
        from app.models.cliente import Cliente
        cli = db.query(Cliente).filter(Cliente.id == c.cliente_id).first()
        if cli:
            mudou = False
            novo_cpf = (body.contratante_cpf_cnpj or "").strip()
            if not cli.cpf_cnpj and novo_cpf:
                # respeita a unicidade de cpf_cnpj
                ja_usado = db.query(Cliente).filter(
                    Cliente.cpf_cnpj == novo_cpf, Cliente.id != cli.id
                ).first()
                if not ja_usado:
                    cli.cpf_cnpj = novo_cpf
                    mudou = True
            novo_email = (body.contratante_email or "").strip()
            if not cli.email and novo_email:
                cli.email = novo_email
                mudou = True
            novo_end = (body.contratante_endereco or "").strip()
            if not cli.endereco and novo_end:
                cli.endereco = novo_end
                mudou = True
            if mudou:
                db.commit()
    except Exception:
        db.rollback()

    lista = list(c.arquivos or [])
    lista.append({"filename": nome_arquivo, "path": str(destino), "clicksign_key": None, "drive_link": drive_link})
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


@router.post("/{contrato_id}/finalizar-assinado-manual", response_model=ContratoOut)
def finalizar_assinado_manual(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Finaliza um contrato já assinado fora do sistema (ex: assinatura física ou por outro
    meio), a partir do(s) PDF(s) já anexados — sem passar pelo ClickSign e sem notificar
    ou reenviar nada ao cliente. Marca status="assinado" + assinatura_manual=True e
    duplica o PDF final para a pasta do cliente e para a pasta mestra /Contratos no Drive.
    """
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    if c.status != "rascunho":
        raise HTTPException(status_code=400, detail="Só é possível finalizar contratos em rascunho")

    arquivos_atuais = list(c.arquivos or [])
    if not arquivos_atuais and c.arquivo_path:
        arquivos_atuais = [{"filename": Path(c.arquivo_path).name, "path": c.arquivo_path}]
    if not arquivos_atuais:
        raise HTTPException(status_code=400, detail="Anexe o PDF já assinado antes de finalizar")

    # Mescla múltiplos PDFs em um único arquivo final, como no envio ao ClickSign
    if len(arquivos_atuais) > 1:
        try:
            from pypdf import PdfWriter
            writer = PdfWriter()
            for arq in arquivos_atuais:
                writer.append(arq["path"])
            nome_final = f"contrato_{contrato_id.hex[:8]}_assinado.pdf"
            path_final = UPLOADS_DIR / nome_final
            with open(path_final, "wb") as fout:
                writer.write(fout)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao mesclar PDFs: {e}")
    else:
        path_final = Path(arquivos_atuais[0]["path"])
        nome_final = arquivos_atuais[0].get("filename") or path_final.name

    pdf_bytes = path_final.read_bytes()
    c.arquivo_assinado_path = str(path_final)
    c.status = "assinado"
    c.assinatura_manual = True

    link_cliente, link_master = _duplicar_assinado_para_drive(db, c, pdf_bytes, nome_final)
    if link_cliente:
        c.drive_link_cliente = link_cliente
    if link_master:
        c.drive_link_master = link_master

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


@router.post("/{contrato_id}/sincronizar-status", response_model=ContratoOut)
def sincronizar_status_clicksign(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    Consulta o status REAL do documento no ClickSign e reconcilia o estado local
    (útil quando o webhook não chegou: contrato assinado no ClickSign mas ainda
    "Pendente" no sistema). Atualiza cada signatário e o status do contrato; se
    já estiver fechado, baixa/arquiva o PDF assinado e limpa a pendência do
    honorário vinculado.
    """
    from datetime import datetime, timezone

    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato não encontrado")
    if not c.clicksign_document_key:
        raise HTTPException(status_code=400, detail="Contrato não foi enviado ao ClickSign (sem documento vinculado).")

    doc = clicksign.status_documento(c.clicksign_document_key)
    if doc is None:
        raise HTTPException(status_code=502, detail="Não foi possível consultar o status no ClickSign.")

    doc_status = (doc.get("status") or "").lower()

    if doc_status == "canceled":
        c.status = "cancelado"
        db.commit()
        db.refresh(c)
        return c

    por_key, por_email = _extrair_assinados(doc)

    for sig in c.signatarios:
        assinou = False
        ts = None
        if sig.clicksign_signer_key and sig.clicksign_signer_key in por_key:
            assinou, ts = True, por_key[sig.clicksign_signer_key]
        elif sig.email and sig.email.lower() in por_email:
            assinou, ts = True, por_email[sig.email.lower()]
        elif doc_status == "closed":
            assinou = True
        if assinou and sig.status_assinatura != "assinado":
            sig.status_assinatura = "assinado"
            sig.assinado_em = _parse_iso(ts) or datetime.now(timezone.utc)

    signatarios = list(c.signatarios)
    todos_assinaram = bool(signatarios) and all(s.status_assinatura == "assinado" for s in signatarios)
    algum_assinou = any(s.status_assinatura == "assinado" for s in signatarios)

    if doc_status == "closed" or todos_assinaram:
        c.status = "assinado"
        if doc_status == "closed":
            _baixar_e_arquivar_assinado_clicksign(db, c, c.clicksign_document_key)
        try:
            from app.models.financeiro import Honorario
            h = db.query(Honorario).filter(Honorario.contrato_id == contrato_id).first()
            if h:
                h.pendente_assinatura = False
        except Exception:
            pass
    elif algum_assinou:
        c.status = "parcialmente_assinado"

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
            _baixar_e_arquivar_assinado_clicksign(db, contrato, doc_key)
        else:
            contrato.status = "parcialmente_assinado"

    elif nome_evento == "cancel":
        contrato.status = "cancelado"

    elif nome_evento == "close":
        contrato.status = "assinado"
        _baixar_e_arquivar_assinado_clicksign(db, contrato, doc_key)

    db.commit()
    return {"ok": True}


def _baixar_e_arquivar_assinado_clicksign(db: Session, contrato: Contrato, doc_key: str) -> None:
    """
    Baixa o PDF final assinado do ClickSign (se ainda não baixado) e o duplica no Drive
    — pasta do cliente e pasta mestra /Contratos. Idempotente: não baixa/reenvia de novo
    se `arquivo_assinado_path` já estiver preenchido (evita duplicar em múltiplos eventos
    de webhook para o mesmo documento, ex: "sign" do último signatário + "close").
    """
    if contrato.arquivo_assinado_path:
        return
    pdf_bytes = clicksign.baixar_documento_assinado(doc_key)
    if not pdf_bytes:
        return
    nome_arquivo = f"{contrato.id}_assinado.pdf"
    path_assinado = UPLOADS_DIR / nome_arquivo
    path_assinado.write_bytes(pdf_bytes)
    contrato.arquivo_assinado_path = str(path_assinado)

    link_cliente, link_master = _duplicar_assinado_para_drive(db, contrato, pdf_bytes, nome_arquivo)
    if link_cliente:
        contrato.drive_link_cliente = link_cliente
    if link_master:
        contrato.drive_link_master = link_master


# ── Download do PDF assinado ──────────────────────────────────────────────────

@router.get("/{contrato_id}/download-assinado")
def download_assinado(contrato_id: uuid.UUID, db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    c = db.query(Contrato).filter(Contrato.id == contrato_id).first()
    if not c or not c.arquivo_assinado_path:
        raise HTTPException(status_code=404, detail="PDF assinado não disponível")
    return FileResponse(c.arquivo_assinado_path, media_type="application/pdf", filename=f"contrato_{contrato_id}_assinado.pdf")
