import io
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, get_optional_user
from app.models.anotacao import Anotacao
from app.models.cliente import Cliente
from app.models.contrato import Contrato
from app.models.processo import Processo
from app.models.reuniao import Reuniao
from app.models.tarefa import Tarefa
from app.models.usuario import Usuario
from app.schemas.reuniao import (
    ConfirmarAcoesRequest,
    PedidoAcesso,
    ReuniaoCreate,
    ReuniaoOut,
    ReuniaoUpdate,
    SolicitarAcessoResponse,
)

router = APIRouter(prefix="/reunioes", tags=["reunioes"])


def _pode_ver_conteudo(r: Reuniao, usuario: Usuario | None) -> bool:
    """Returns True if the user can see full meeting content (not restricted view)."""
    if not r.confidencial:
        return True
    if usuario is None:
        return False
    if usuario.role == "super_admin":
        return True
    if r.criado_por_id and str(usuario.id) == str(r.criado_por_id):
        return True
    acesso = r.usuarios_com_acesso or []
    return str(usuario.id) in acesso


def _enrich(r: Reuniao, db: Session, usuario: Usuario | None = None) -> ReuniaoOut:
    pode_ver = _pode_ver_conteudo(r, usuario)
    is_creator = usuario and r.criado_por_id and str(usuario.id) == str(r.criado_por_id)
    can_manage = usuario and (usuario.role == "super_admin" or is_creator)

    out = ReuniaoOut.model_validate(r)
    out.acesso_restrito = not pode_ver

    if not pode_ver:
        # Mask sensitive content for restricted users
        out.transcricao_texto = None
        out.resumo_ia = None
        out.acoes_sugeridas = None
        out.drive_tldr_file_id = None
        out.drive_transcricao_file_id = None
        out.drive_notas_file_id = None
        out.titulo = "Reunião confidencial"

    if r.cliente_id:
        c = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
        if c:
            out.cliente_nome = c.nome

    if r.processo_id:
        p = db.query(Processo).filter(Processo.id == r.processo_id).first()
        if p:
            out.processo_numero = p.numero_cnj

    if r.criado_por_id:
        u = db.query(Usuario).filter(Usuario.id == r.criado_por_id).first()
        if u:
            out.criado_por_nome = u.nome

    # Populate pending access requests for creator / super_admin
    if can_manage:
        pedidos: list[PedidoAcesso] = []
        granted: list[dict] = []
        for entry in (r.usuarios_com_acesso or []):
            if entry.startswith("req:"):
                uid_str = entry[4:]
                try:
                    uid = uuid.UUID(uid_str)
                    req_user = db.query(Usuario).filter(Usuario.id == uid).first()
                    if req_user:
                        pedidos.append(PedidoAcesso(usuario_id=uid_str, nome=req_user.nome))
                except (ValueError, TypeError):
                    pass
            else:
                try:
                    granted_user = db.query(Usuario).filter(Usuario.id == uuid.UUID(entry)).first()
                    if granted_user:
                        granted.append({"id": entry, "nome": granted_user.nome})
                except (ValueError, TypeError):
                    pass
        out.pedidos_acesso = pedidos
        out.usuarios_com_acesso_nomes = granted

    # Compute ja_solicitou for the current user
    if usuario is not None:
        req_marker = f"req:{str(usuario.id)}"
        out.ja_solicitou = req_marker in (r.usuarios_com_acesso or [])

    return out


@router.get("/", response_model=list[ReuniaoOut])
def listar_reunioes(
    cliente_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    q = db.query(Reuniao)
    if cliente_id:
        q = q.filter(Reuniao.cliente_id == cliente_id)
    if status:
        q = q.filter(Reuniao.status == status)
    reunioes = q.order_by(Reuniao.data_reuniao.desc().nullslast(), Reuniao.created_at.desc()).all()
    return [_enrich(r, db, usuario) for r in reunioes]


@router.post("/", response_model=ReuniaoOut, status_code=status.HTTP_201_CREATED)
def criar_reuniao(
    data: ReuniaoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    reuniao = Reuniao(**data.model_dump())
    if usuario:
        reuniao.criado_por_id = usuario.id
    db.add(reuniao)
    db.commit()
    db.refresh(reuniao)
    return _enrich(reuniao, db, usuario)


@router.post("/sync-drive", response_model=list[ReuniaoOut])
def sync_drive(
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    """Varre as pastas Meet Recordings de todos os usuários com google_tokens e importa novas transcrições."""
    from app.services.ia_reuniao import match_cliente
    from app.services.meet_sync import (
        baixar_conteudo_arquivo,
        extrair_titulo,
        listar_novas_transcricoes,
        _parse_data_reuniao,
    )

    ultima = db.query(Reuniao).filter(Reuniao.fonte == "drive_auto").order_by(Reuniao.created_at.desc()).first()
    ultimo_sync = ultima.created_at.isoformat() if ultima else None

    # Gather tokens from all active users
    usuarios_com_token = db.query(Usuario).filter(
        Usuario.ativo == True,
        Usuario.google_tokens.isnot(None),
    ).all()

    # Also include master account tokens
    user_tokens_list = []
    for u in usuarios_com_token:
        if u.google_tokens:
            user_tokens_list.append({"usuario_id": str(u.id), "tokens": u.google_tokens})

    # Fallback: master account tokens
    try:
        from app.services.google_calendar import _load_tokens
        master = _load_tokens()
        if master:
            user_tokens_list.append({"usuario_id": None, "tokens": master})
    except Exception:
        pass

    if not user_tokens_list:
        return []

    clientes = db.query(Cliente).filter(Cliente.incompleto.is_(False)).all()
    clientes_data = [{"id": str(c.id), "nome": c.nome} for c in clientes]

    criadas = []
    seen_file_ids: set[str] = set()

    for entry in user_tokens_list:
        try:
            arquivos = listar_novas_transcricoes(ultimo_sync=ultimo_sync, tokens=entry["tokens"])
        except Exception:
            continue

        for arq in arquivos:
            fid = arq["file_id"]
            if fid in seen_file_ids:
                continue
            seen_file_ids.add(fid)

            existente = db.query(Reuniao).filter(Reuniao.drive_transcricao_file_id == fid).first()
            if existente:
                continue

            titulo = extrair_titulo(arq["nome"])
            data_reuniao = _parse_data_reuniao(arq["nome"], arq.get("criado_em"))
            conteudo = baixar_conteudo_arquivo(fid, arq["mime_type"], tokens=entry["tokens"])

            match = match_cliente(titulo, clientes_data)
            cliente_id = None
            if match.get("confianca", 0) >= 0.8 and match.get("cliente_id"):
                try:
                    cliente_id = uuid.UUID(match["cliente_id"])
                except (ValueError, TypeError):
                    pass

            criado_por_id = uuid.UUID(entry["usuario_id"]) if entry["usuario_id"] else None
            reuniao = Reuniao(
                titulo=titulo,
                data_reuniao=data_reuniao,
                transcricao_texto=conteudo,
                drive_transcricao_file_id=fid,
                cliente_id=cliente_id,
                criado_por_id=criado_por_id,
                fonte="drive_auto",
                status="pendente",
            )
            db.add(reuniao)
            db.flush()
            criadas.append(reuniao)

    db.commit()
    for r in criadas:
        db.refresh(r)

    return [_enrich(r, db, usuario) for r in criadas]


@router.get("/{reuniao_id}", response_model=ReuniaoOut)
def obter_reuniao(
    reuniao_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    r = db.query(Reuniao).filter(Reuniao.id == reuniao_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    return _enrich(r, db, usuario)


@router.patch("/{reuniao_id}", response_model=ReuniaoOut)
def atualizar_reuniao(
    reuniao_id: uuid.UUID,
    data: ReuniaoUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    r = db.query(Reuniao).filter(Reuniao.id == reuniao_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if not _pode_ver_conteudo(r, usuario):
        raise HTTPException(status_code=403, detail="Acesso restrito a esta reunião")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(r, field, value)
    db.commit()
    db.refresh(r)
    return _enrich(r, db, usuario)


@router.post("/{reuniao_id}/processar", response_model=ReuniaoOut)
def processar_reuniao(
    reuniao_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    """Processa a transcrição com IA: gera TLDR e lista de ações sugeridas."""
    from app.services.ia_reuniao import processar_transcricao

    r = db.query(Reuniao).filter(Reuniao.id == reuniao_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if not _pode_ver_conteudo(r, usuario):
        raise HTTPException(status_code=403, detail="Acesso restrito a esta reunião")
    if not r.transcricao_texto:
        raise HTTPException(status_code=400, detail="Reunião sem texto de transcrição")

    data_ref = r.data_reuniao.date() if r.data_reuniao else None
    resultado = processar_transcricao(r.transcricao_texto, data_ref)

    if "erro" in resultado:
        raise HTTPException(status_code=502, detail=f"Erro ao processar IA: {resultado['erro']}")

    acoes: list[dict] = []

    for tarefa in resultado.get("tarefas", []):
        acoes.append({
            "tipo": "tarefa",
            "aprovada": None,
            "criada": False,
            "confidencial": r.confidencial,
            "titulo": tarefa.get("titulo", ""),
            "descricao": tarefa.get("descricao", ""),
            "data_limite": tarefa.get("data_sugerida"),
            "responsavel": None,
        })

    for contrato in resultado.get("contratos", []):
        acoes.append({
            "tipo": "contrato",
            "aprovada": None,
            "criada": False,
            "confidencial": r.confidencial,
            "titulo": contrato.get("titulo", ""),
            "descricao": contrato.get("descricao", ""),
            "valor_mencionado": contrato.get("valor_mencionado"),
        })

    if resultado.get("anotacao"):
        acoes.append({
            "tipo": "anotacao",
            "aprovada": None,
            "criada": False,
            "confidencial": r.confidencial,
            "titulo": f"Reunião: {r.titulo}",
            "conteudo": resultado["anotacao"],
        })

    r.resumo_ia = resultado.get("resumo", "")
    r.acoes_sugeridas = acoes
    r.status = "em_revisao"
    db.commit()
    db.refresh(r)
    return _enrich(r, db, usuario)


@router.post("/{reuniao_id}/confirmar-acoes", response_model=ReuniaoOut)
def confirmar_acoes(
    reuniao_id: uuid.UUID,
    data: ConfirmarAcoesRequest,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    """Cria no sistema as ações marcadas como aprovada=True."""
    r = db.query(Reuniao).filter(Reuniao.id == reuniao_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if not _pode_ver_conteudo(r, usuario):
        raise HTTPException(status_code=403, detail="Acesso restrito a esta reunião")
    if not r.cliente_id:
        raise HTTPException(status_code=400, detail="Vincule a reunião a um cliente antes de confirmar ações")

    data_base = (r.data_reuniao.date() if r.data_reuniao else date.today())

    # Work on a mutable copy so we can stamp criada=True after each creation
    acoes_result = [dict(a) for a in data.acoes_sugeridas]

    for acao in acoes_result:
        if not acao.get("aprovada"):
            continue
        if acao.get("criada"):  # Already created in a previous confirmation — skip
            continue

        tipo = acao.get("tipo")
        # Per-action confidentiality; falls back to the meeting-level flag
        acao_confidencial: bool = bool(acao.get("confidencial", r.confidencial))

        if tipo == "tarefa":
            data_limite = None
            if acao.get("data_limite"):
                try:
                    data_limite = date.fromisoformat(acao["data_limite"])
                except (ValueError, TypeError):
                    pass
            projeto_id = None
            if acao.get("projeto_id"):
                try:
                    projeto_id = uuid.UUID(str(acao["projeto_id"]))
                except (ValueError, TypeError):
                    pass
            tarefa = Tarefa(
                cliente_id=r.cliente_id,
                processo_id=r.processo_id,
                projeto_id=projeto_id,
                titulo=acao.get("titulo", "Tarefa da reunião"),
                descricao=acao.get("descricao"),
                responsavel=acao.get("responsavel"),
                data_limite=data_limite,
                status="pendente",
                resumo_ia=f"Gerado automaticamente da reunião: {r.titulo}",
                confidencial=acao_confidencial,
                criado_por_id=usuario.id if usuario else None,
            )
            db.add(tarefa)
            acao["criada"] = True

        elif tipo == "contrato":
            contrato = Contrato(
                cliente_id=r.cliente_id,
                processo_id=r.processo_id,
                titulo=acao.get("titulo", "Contrato"),
                descricao=acao.get("descricao"),
                status="rascunho",
                arquivos=[],
            )
            db.add(contrato)
            acao["criada"] = True

        elif tipo == "anotacao":
            anotacao = Anotacao(
                cliente_id=r.cliente_id,
                processo_id=r.processo_id,
                reuniao_id=r.id,
                tipo="reuniao",
                data_evento=data_base,
                titulo=acao.get("titulo"),
                texto=acao.get("conteudo", ""),
                confidencial=acao_confidencial,
            )
            db.add(anotacao)
            acao["criada"] = True

    if r.resumo_ia and r.cliente_id:
        cliente = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
        if cliente:
            try:
                from app.services.meet_sync import salvar_tldr_drive

                data_str = data_base.isoformat()
                nome_arquivo = f"{data_str} - {r.titulo[:80]}.txt"
                conteudo_tldr = f"# {r.titulo}\nData: {data_str}\n\n## Resumo\n{r.resumo_ia}"
                drive_link = salvar_tldr_drive(conteudo_tldr, nome_arquivo, cliente.nome)
                if drive_link:
                    r.drive_tldr_file_id = drive_link
            except Exception:
                pass

    r.acoes_sugeridas = acoes_result
    r.status = "processada"
    db.commit()
    db.refresh(r)
    return _enrich(r, db, usuario)


@router.post("/{reuniao_id}/upload-transcricao", response_model=ReuniaoOut)
async def upload_transcricao(
    reuniao_id: uuid.UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    """Recebe PDF, DOCX ou TXT e extrai o texto como transcrição da reunião."""
    r = db.query(Reuniao).filter(Reuniao.id == reuniao_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if not _pode_ver_conteudo(r, usuario):
        raise HTTPException(status_code=403, detail="Acesso restrito a esta reunião")

    nome = (file.filename or "").lower()
    conteudo = await file.read()
    texto: str | None = None

    if nome.endswith(".txt") or (file.content_type or "").startswith("text/"):
        try:
            texto = conteudo.decode("utf-8")
        except UnicodeDecodeError:
            texto = conteudo.decode("latin-1", errors="replace")

    elif nome.endswith(".pdf") or file.content_type == "application/pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(conteudo))
            texto = "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Não foi possível ler o PDF: {e}")

    elif nome.endswith(".docx") or file.content_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ):
        try:
            from docx import Document
            doc = Document(io.BytesIO(conteudo))
            texto = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Não foi possível ler o DOCX: {e}")

    else:
        raise HTTPException(status_code=415, detail="Formato não suportado. Envie .txt, .pdf ou .docx")

    if not texto or not texto.strip():
        raise HTTPException(status_code=422, detail="O arquivo não contém texto legível")

    r.transcricao_texto = texto.strip()
    db.commit()
    db.refresh(r)
    return _enrich(r, db, usuario)


# ── Confidentiality / access control ─────────────────────────────────────────

@router.post("/{reuniao_id}/solicitar-acesso", response_model=SolicitarAcessoResponse)
def solicitar_acesso(
    reuniao_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Sends an access request notification to the meeting creator and super admins."""
    r = db.query(Reuniao).filter(Reuniao.id == reuniao_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if _pode_ver_conteudo(r, usuario):
        return SolicitarAcessoResponse(ok=True, mensagem="Você já tem acesso a esta reunião.")

    # Log the request in usuarios_com_acesso as a pending marker — prefix "req:" to differentiate
    acesso = list(r.usuarios_com_acesso or [])
    req_marker = f"req:{str(usuario.id)}"
    if req_marker not in acesso:
        acesso.append(req_marker)
        r.usuarios_com_acesso = acesso
        db.commit()

    return SolicitarAcessoResponse(
        ok=True,
        mensagem=f"Solicitação enviada. O criador da reunião e o administrador serão notificados.",
    )


@router.post("/{reuniao_id}/conceder-acesso/{usuario_id}", response_model=ReuniaoOut)
def conceder_acesso(
    reuniao_id: uuid.UUID,
    usuario_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Grant access to a confidential meeting. Only creator or super_admin can do this."""
    r = db.query(Reuniao).filter(Reuniao.id == reuniao_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    is_creator = r.criado_por_id and str(usuario.id) == str(r.criado_por_id)
    if usuario.role != "super_admin" and not is_creator:
        raise HTTPException(status_code=403, detail="Apenas o criador ou super administrador pode conceder acesso")

    alvo = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not alvo:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    acesso = list(r.usuarios_com_acesso or [])
    # Remove pending request marker if present
    req_marker = f"req:{str(usuario_id)}"
    if req_marker in acesso:
        acesso.remove(req_marker)
    uid_str = str(usuario_id)
    if uid_str not in acesso:
        acesso.append(uid_str)
    r.usuarios_com_acesso = acesso
    db.commit()
    db.refresh(r)
    return _enrich(r, db, usuario)


@router.post("/{reuniao_id}/revogar-acesso/{usuario_id}", response_model=ReuniaoOut)
def revogar_acesso(
    reuniao_id: uuid.UUID,
    usuario_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    """Revoke access to a confidential meeting."""
    r = db.query(Reuniao).filter(Reuniao.id == reuniao_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    is_creator = r.criado_por_id and str(usuario.id) == str(r.criado_por_id)
    if usuario.role != "super_admin" and not is_creator:
        raise HTTPException(status_code=403, detail="Apenas o criador ou super administrador pode revogar acesso")

    uid_str = str(usuario_id)
    req_marker = f"req:{uid_str}"
    acesso = [a for a in (r.usuarios_com_acesso or []) if a not in (uid_str, req_marker)]
    r.usuarios_com_acesso = acesso
    db.commit()
    db.refresh(r)
    return _enrich(r, db, usuario)


@router.delete("/{reuniao_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_reuniao(
    reuniao_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(get_optional_user),
):
    r = db.query(Reuniao).filter(Reuniao.id == reuniao_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if not _pode_ver_conteudo(r, usuario):
        raise HTTPException(status_code=403, detail="Acesso restrito a esta reunião")
    db.delete(r)
    db.commit()
