"""Autocadastro de cliente — endpoints PÚBLICOS (sem autenticação).

Protegido por token opaco no link. NUNCA escreve em `clientes`: todo envio vira
uma submissão em staging (status 'pendente') que o Lucas aprova depois (Fase 3).
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cadastro_link import ClienteCadastroLink, ClienteCadastroSubmissao
from app.models.cliente import Cliente

router = APIRouter(prefix="/publico", tags=["publico-cadastro"])

STAGING_DIR = Path("/app/uploads/cadastro_submissoes")

# Texto de consentimento exibido no formulário (carimbado na submissão p/ LGPD).
CONSENTIMENTO_TEXTO = (
    "Autorizo o tratamento dos dados pessoais informados neste formulário para "
    "as finalidades de cadastro e prestação de serviços jurídicos pelo escritório, "
    "nos termos da Lei nº 13.709/2018 (LGPD)."
)

# Campos cadastrais aceitos no envio (whitelist — descarta qualquer outra chave).
CAMPOS_COMUNS = {"nome", "cpf_cnpj", "email", "telefone", "whatsapp", "observacoes",
                 "cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf"}
CAMPOS_PF = {"data_nascimento", "rg", "estado_civil", "profissao", "empresas_vinculadas"}
CAMPOS_PJ = {"nome_fantasia", "responsavel_nome", "responsavel_cpf",
             "responsavel_email", "responsavel_telefone"}
MAX_ANEXOS = 5
MAX_ANEXO_BYTES = 15 * 1024 * 1024  # 15 MB por arquivo


def _so_digitos(v: str | None) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", v or "")


def _link_por_token(db: Session, token: str) -> ClienteCadastroLink:
    if not token or len(token) < 8:
        raise HTTPException(404, "Link inválido")
    link = db.query(ClienteCadastroLink).filter(ClienteCadastroLink.token == token).first()
    if not link or link.revogado:
        raise HTTPException(404, "Link inválido ou revogado")
    if link.expira_em and link.expira_em < datetime.now(timezone.utc):
        raise HTTPException(410, "Este link expirou")
    return link


def _contexto_form(db: Session, link: ClienteCadastroLink | None) -> dict:
    """Contexto do formulário. link=None => link genérico (captação de novo)."""
    resp: dict = {
        "ok": True,
        "is_update": bool(link and link.cliente_id),
        "rotulo": link.rotulo if link else None,
        "consentimento_texto": CONSENTIMENTO_TEXTO,
        "tipo_sugerido": None,
        "prefill": {},
    }
    if link and link.cliente_id:
        cli = db.query(Cliente).filter(Cliente.id == link.cliente_id).first()
        if cli:
            resp["tipo_sugerido"] = cli.tipo
            campos = CAMPOS_COMUNS | CAMPOS_PF | CAMPOS_PJ
            prefill = {}
            for c in campos:
                val = getattr(cli, c, None)
                if val is not None:
                    prefill[c] = val.isoformat() if hasattr(val, "isoformat") else val
            resp["prefill"] = prefill
    return resp


@router.get("/cadastro")
def obter_formulario_generico(db: Session = Depends(get_db)):
    """Link genérico de captação (sem token) — sempre cadastro novo."""
    return _contexto_form(db, None)


@router.get("/cadastro/{token}")
def obter_formulario(token: str, db: Session = Depends(get_db)):
    """Convite atrelado a um cliente (token secreto) — pré-preenche os dados atuais."""
    return _contexto_form(db, _link_por_token(db, token))


async def _processar_submissao(
    link: ClienteCadastroLink | None,
    request: Request,
    payload: str,
    files: list[UploadFile],
    db: Session,
) -> dict:
    try:
        raw = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(400, "Dados inválidos")
    if not isinstance(raw, dict):
        raise HTTPException(400, "Dados inválidos")

    tipo = (raw.get("tipo") or "").upper()
    if tipo not in ("PF", "PJ"):
        raise HTTPException(400, "Informe se é Pessoa Física ou Jurídica")
    if not (raw.get("nome") or "").strip():
        raise HTTPException(400, "O nome é obrigatório")
    if not raw.get("consentimento"):
        raise HTTPException(400, "É necessário aceitar o termo de consentimento (LGPD)")

    permitidos = CAMPOS_COMUNS | (CAMPOS_PF if tipo == "PF" else CAMPOS_PJ)
    dados = {k: v for k, v in raw.items() if k in permitidos and v not in (None, "")}

    # Alvo: convite atrelado a cliente, senão casa por CPF/CNPJ. Nulo = cadastro novo.
    cliente_id_alvo = link.cliente_id if link else None
    if cliente_id_alvo is None:
        doc = _so_digitos(dados.get("cpf_cnpj"))
        if doc:
            for cli in db.query(Cliente).filter(Cliente.cpf_cnpj.isnot(None)).all():
                if _so_digitos(cli.cpf_cnpj) == doc:
                    cliente_id_alvo = cli.id
                    break

    sub_id = uuid.uuid4()

    # Anexos opcionais → pasta de staging (movidos pro Drive só na aprovação).
    anexos: list[dict] = []
    if files:
        pasta = STAGING_DIR / str(sub_id)
        pasta.mkdir(parents=True, exist_ok=True)
        for f in files[:MAX_ANEXOS]:
            if not f.filename:
                continue
            conteudo = await f.read()
            if len(conteudo) > MAX_ANEXO_BYTES:
                raise HTTPException(413, f"Arquivo {f.filename} excede 15 MB")
            nome_seguro = re.sub(r"[^\w.\-]", "_", f.filename)
            destino = pasta / nome_seguro
            destino.write_bytes(conteudo)
            anexos.append({"filename": nome_seguro, "path": str(destino), "mime": f.content_type})

    sub = ClienteCadastroSubmissao(
        id=sub_id,
        link_id=link.id if link else None,
        cliente_id_alvo=cliente_id_alvo,
        tipo=tipo,
        dados=dados,
        anexos=anexos,
        consentimento=True,
        consentimento_texto=CONSENTIMENTO_TEXTO,
        consentimento_em=datetime.now(timezone.utc),
        ip=(request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        status="pendente",
    )
    db.add(sub)
    if link:
        link.usos = (link.usos or 0) + 1
    db.commit()
    return {"ok": True, "is_update": cliente_id_alvo is not None}


@router.post("/cadastro", status_code=201)
async def submeter_generico(
    request: Request,
    payload: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    return await _processar_submissao(None, request, payload, files, db)


@router.post("/cadastro/{token}", status_code=201)
async def submeter_formulario(
    token: str,
    request: Request,
    payload: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    link = _link_por_token(db, token)
    return await _processar_submissao(link, request, payload, files, db)
