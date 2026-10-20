"""Responsáveis — lista unificada de gente que pode ser atribuída a
tarefas/prazos/cards: usuários do sistema (sincronizados automaticamente,
ver `usuarios.py`) e responsáveis "manuais" (advogados/terceiros sem login).

As colunas `responsavel`/`responsavel_email` em Tarefa/Prazo/TarefaCard
continuam existindo como cópia denormalizada (nome/email) — todo código que
já lê esses campos continua funcionando sem mudança. `responsavel_id` é a
referência de verdade usada pra evitar duplicidade e permitir mesclagem.
"""
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.prazo import Prazo
from app.models.responsavel import Responsavel
from app.models.tarefa import Tarefa
from app.models.tarefa_card import TarefaCard
from app.services import telegram_api

router = APIRouter(prefix="/responsaveis", tags=["responsaveis"],
                   dependencies=[Depends(get_current_user)])

CATEGORIAS_VALIDAS = {"advogado", "terceiro", "colaborador", "financeiro"}

# Prefixo do parâmetro /start do bot — o webhook (routers/telegram.py) usa o mesmo.
VINCULO_PREFIXO = "resp_"


def _resp_para_dict(r: Responsavel) -> dict:
    return {
        "id": str(r.id),
        "nome": r.nome,
        "email": r.email,
        "telefone": r.telefone,
        "oab_numero": r.oab_numero,
        "oab_uf": r.oab_uf,
        "categoria": r.categoria,
        "usuario_id": str(r.usuario_id) if r.usuario_id else None,
        "eh_usuario_sistema": r.usuario_id is not None,
        "ativo": r.ativo,
        "telegram_vinculado": bool(r.telegram_chat_id),
    }


@router.get("")
def listar_responsaveis(
    q: str | None = None,
    categoria: str | None = None,
    apenas_ativos: bool = True,
    db: Session = Depends(get_db),
):
    query = db.query(Responsavel)
    if apenas_ativos:
        query = query.filter(Responsavel.ativo.is_(True))
    if categoria:
        query = query.filter(Responsavel.categoria == categoria)
    if q:
        termo = f"%{q.lower()}%"
        query = query.filter(
            (Responsavel.nome.ilike(termo)) | (Responsavel.email.ilike(termo))
        )
    responsaveis = query.order_by(Responsavel.nome).all()
    return [_resp_para_dict(r) for r in responsaveis]


class ResponsavelCreate(BaseModel):
    nome: str
    email: str | None = None
    telefone: str | None = None
    oab_numero: str | None = None
    oab_uf: str | None = None
    categoria: str = "terceiro"


@router.post("", status_code=201)
def criar_responsavel(body: ResponsavelCreate, db: Session = Depends(get_db)):
    if not body.nome.strip():
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    if body.categoria not in CATEGORIAS_VALIDAS:
        raise HTTPException(status_code=400, detail=f"Categoria inválida — use uma de {sorted(CATEGORIAS_VALIDAS)}")

    resp = Responsavel(
        nome=body.nome.strip(),
        email=(body.email or "").strip() or None,
        telefone=(body.telefone or "").strip() or None,
        oab_numero=(body.oab_numero or "").strip() or None,
        oab_uf=(body.oab_uf or "").strip().upper() or None,
        categoria=body.categoria,
    )
    db.add(resp)
    db.commit()
    db.refresh(resp)
    return _resp_para_dict(resp)


class ResponsavelUpdate(BaseModel):
    nome: str | None = None
    email: str | None = None
    telefone: str | None = None
    oab_numero: str | None = None
    oab_uf: str | None = None
    categoria: str | None = None
    ativo: bool | None = None


@router.patch("/{responsavel_id}")
def atualizar_responsavel(responsavel_id: uuid.UUID, body: ResponsavelUpdate, db: Session = Depends(get_db)):
    resp = db.query(Responsavel).filter(Responsavel.id == responsavel_id).first()
    if not resp:
        raise HTTPException(status_code=404, detail="Responsável não encontrado")

    # Nome/email de um responsável vinculado a usuário do sistema só mudam
    # pela tela de Usuários — aqui daria conflito com o login/auth.
    if resp.usuario_id and (body.nome is not None or body.email is not None):
        raise HTTPException(status_code=400, detail="Nome e email de um usuário do sistema se editam em Usuários")

    if body.categoria is not None and body.categoria not in CATEGORIAS_VALIDAS:
        raise HTTPException(status_code=400, detail=f"Categoria inválida — use uma de {sorted(CATEGORIAS_VALIDAS)}")

    if body.nome is not None:
        resp.nome = body.nome.strip()
    if body.email is not None:
        resp.email = body.email.strip() or None
    if body.telefone is not None:
        resp.telefone = body.telefone.strip() or None
    if body.oab_numero is not None:
        resp.oab_numero = body.oab_numero.strip() or None
    if body.oab_uf is not None:
        resp.oab_uf = body.oab_uf.strip().upper() or None
    if body.categoria is not None:
        resp.categoria = body.categoria
    if body.ativo is not None:
        resp.ativo = body.ativo

    db.commit()
    db.refresh(resp)
    return _resp_para_dict(resp)


@router.post("/{responsavel_id}/telegram/vinculo")
def gerar_vinculo_telegram(responsavel_id: uuid.UUID, db: Session = Depends(get_db)):
    """Gera um link de uso único (t.me/<bot>?start=resp_<token>) pra pessoa abrir no
    Telegram e vincular o próprio chat — o bot não pode iniciar conversa sozinho,
    então sem isso não há DM. Gerar de novo invalida o link anterior."""
    resp = db.query(Responsavel).filter(Responsavel.id == responsavel_id).first()
    if not resp:
        raise HTTPException(status_code=404, detail="Responsável não encontrado")
    username = telegram_api.bot_username()
    if not username:
        raise HTTPException(status_code=503, detail="Bot do Telegram indisponível (token não configurado ou sem resposta)")
    resp.telegram_vinculo_token = secrets.token_urlsafe(16)
    db.commit()
    return {"link": f"https://t.me/{username}?start={VINCULO_PREFIXO}{resp.telegram_vinculo_token}"}


@router.delete("/{responsavel_id}/telegram")
def desvincular_telegram(responsavel_id: uuid.UUID, db: Session = Depends(get_db)):
    resp = db.query(Responsavel).filter(Responsavel.id == responsavel_id).first()
    if not resp:
        raise HTTPException(status_code=404, detail="Responsável não encontrado")
    resp.telegram_chat_id = None
    resp.telegram_vinculo_token = None
    db.commit()
    return _resp_para_dict(resp)


class MesclarRequest(BaseModel):
    sobrevivente_id: uuid.UUID
    mesclados: list[uuid.UUID]


@router.post("/mesclar")
def mesclar_responsaveis(body: MesclarRequest, db: Session = Depends(get_db)):
    """Reatribui tarefas/prazos/cards dos responsáveis mesclados pro
    sobrevivente (FK + cópia denormalizada de nome/email) e remove os
    duplicados. Nunca mescla um responsável vinculado a usuário do sistema —
    esse só some junto com o usuário."""
    sobrevivente = db.query(Responsavel).filter(Responsavel.id == body.sobrevivente_id).first()
    if not sobrevivente:
        raise HTTPException(status_code=404, detail="Responsável sobrevivente não encontrado")

    ids_mesclados = [i for i in body.mesclados if i != sobrevivente.id]
    if not ids_mesclados:
        raise HTTPException(status_code=400, detail="Informe ao menos um responsável pra mesclar")

    mesclados = db.query(Responsavel).filter(Responsavel.id.in_(ids_mesclados)).all()
    if any(r.usuario_id for r in mesclados):
        raise HTTPException(status_code=400, detail="Não é possível mesclar um responsável vinculado a um usuário do sistema")

    ids_str = [str(r.id) for r in mesclados]

    for Model in (Tarefa, Prazo, TarefaCard):
        rows = db.query(Model).filter(Model.responsavel_id.in_(ids_mesclados)).all()
        for row in rows:
            row.responsavel_id = sobrevivente.id
            row.responsavel = sobrevivente.nome
            if hasattr(row, "responsavel_email"):
                row.responsavel_email = sobrevivente.email

    for r in mesclados:
        db.delete(r)

    db.commit()
    return {"ok": True, "sobrevivente_id": str(sobrevivente.id), "mesclados": ids_str}
