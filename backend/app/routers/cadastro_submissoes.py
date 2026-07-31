"""Revisão e aprovação das submissões de autocadastro (Fase 3, autenticado).

Aqui — e SÓ aqui — o que o cliente enviou vira dado real em `clientes`. Cada
submissão pendente mostra um diff (valor atual → valor novo) e o Lucas escolhe
aprovar (aplicando os campos aceitos) ou rejeitar. Na aprovação, anexos em
staging sobem pro Drive do cliente.
"""
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.cadastro_link import ClienteCadastroSubmissao
from app.models.cliente import Cliente
from app.models.usuario import Usuario
from app.routers.cadastro_publico import CAMPOS_COMUNS, CAMPOS_PF, CAMPOS_PJ

router = APIRouter(
    prefix="/cadastro-submissoes", tags=["cadastro-submissoes"],
    dependencies=[Depends(get_current_user)],
)

# Campos DATE que precisam de parse antes de gravar no modelo.
CAMPOS_DATA = {"data_nascimento"}


def _campos_do_tipo(tipo: str) -> set[str]:
    return CAMPOS_COMUNS | (CAMPOS_PF if tipo == "PF" else CAMPOS_PJ)


def _valor_atual(cliente: Cliente | None, campo: str):
    if cliente is None:
        return None
    val = getattr(cliente, campo, None)
    return val.isoformat() if hasattr(val, "isoformat") else val


def _sub_resumo(sub: ClienteCadastroSubmissao, db: Session) -> dict:
    alvo = (
        db.query(Cliente).filter(Cliente.id == sub.cliente_id_alvo).first()
        if sub.cliente_id_alvo else None
    )
    dados = sub.dados or {}
    return {
        "id": str(sub.id),
        "tipo": sub.tipo,
        "status": sub.status,
        "is_update": sub.cliente_id_alvo is not None,
        "cliente_alvo_id": str(sub.cliente_id_alvo) if sub.cliente_id_alvo else None,
        "cliente_alvo_nome": alvo.nome if alvo else None,
        "nome_enviado": dados.get("nome"),
        "cpf_cnpj_enviado": dados.get("cpf_cnpj"),
        "qtd_anexos": len(sub.anexos or []),
        "consentimento_em": sub.consentimento_em.isoformat() if sub.consentimento_em else None,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
    }


@router.get("")
def listar_submissoes(status: str = "pendente", db: Session = Depends(get_db)):
    q = db.query(ClienteCadastroSubmissao)
    if status:
        q = q.filter(ClienteCadastroSubmissao.status == status)
    subs = q.order_by(ClienteCadastroSubmissao.created_at.desc()).all()
    return [_sub_resumo(s, db) for s in subs]


@router.get("/{sub_id}")
def obter_submissao(sub_id: uuid.UUID, db: Session = Depends(get_db)):
    sub = db.query(ClienteCadastroSubmissao).filter(ClienteCadastroSubmissao.id == sub_id).first()
    if not sub:
        raise HTTPException(404, "Submissão não encontrada")
    alvo = (
        db.query(Cliente).filter(Cliente.id == sub.cliente_id_alvo).first()
        if sub.cliente_id_alvo else None
    )
    dados = sub.dados or {}
    # Diff campo-a-campo (só campos válidos do tipo enviado).
    campos_validos = _campos_do_tipo(sub.tipo)
    diff = []
    for campo in campos_validos:
        novo = dados.get(campo)
        atual = _valor_atual(alvo, campo)
        if novo in (None, "") and atual in (None, ""):
            continue
        diff.append({
            "campo": campo,
            "atual": atual,
            "novo": novo,
            "mudou": (novo or "") != (atual or ""),
        })
    diff.sort(key=lambda d: d["campo"])
    return {
        **_sub_resumo(sub, db),
        "tipo": sub.tipo,
        "dados": dados,   # valores crus enviados (pré-preenchem o form editável)
        "diff": diff,
        "anexos": [{"filename": a.get("filename"), "mime": a.get("mime")} for a in (sub.anexos or [])],
        "consentimento_texto": sub.consentimento_texto,
        "ip": sub.ip,
    }


class AprovarPayload(BaseModel):
    # Valores finais (já editados pelo revisor). None = usa os enviados na submissão.
    dados: dict | None = None
    # PF/PJ escolhido no momento da aprovação. None = tipo da submissão.
    tipo: str | None = None
    # Destino: criar cliente novo, ou atualizar um cliente específico.
    criar_novo: bool = False
    cliente_id_alvo: uuid.UUID | None = None


def _aplicar_valor(cliente: Cliente, campo: str, valor):
    if campo in CAMPOS_DATA and valor:
        try:
            valor = date.fromisoformat(str(valor)[:10])
        except ValueError:
            return  # data inválida: ignora em vez de quebrar
    setattr(cliente, campo, valor)


def _subir_anexos(sub: ClienteCadastroSubmissao, nome_cliente: str) -> None:
    from app.services.google_drive import upload_arquivo
    for a in (sub.anexos or []):
        caminho = a.get("path")
        filename = a.get("filename")
        if not caminho or not filename:
            continue
        p = Path(caminho)
        if not p.exists():
            continue
        try:
            upload_arquivo(
                p.read_bytes(), filename, nome_cliente, "Documentos",
                a.get("mime") or "application/octet-stream",
            )
            p.unlink(missing_ok=True)
        except Exception:
            # Drive pode não estar autenticado; não bloqueia a aprovação.
            pass


@router.post("/{sub_id}/aprovar")
def aprovar_submissao(
    sub_id: uuid.UUID,
    payload: AprovarPayload,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    sub = db.query(ClienteCadastroSubmissao).filter(ClienteCadastroSubmissao.id == sub_id).first()
    if not sub:
        raise HTTPException(404, "Submissão não encontrada")
    if sub.status != "pendente":
        raise HTTPException(409, f"Submissão já {sub.status}")

    # Tipo final (o revisor pode corrigir PF↔PJ).
    tipo = (payload.tipo or sub.tipo or "").upper()
    if tipo not in ("PF", "PJ"):
        raise HTTPException(400, "Tipo inválido")

    # Valores finais: os editados pelo revisor, ou os enviados na submissão.
    dados = payload.dados if payload.dados is not None else (sub.dados or {})
    campos_validos = _campos_do_tipo(tipo)
    aplicaveis = {
        k: v for k, v in dados.items()
        if k in campos_validos and v not in (None, "")
    }

    # Destino: novo cliente, cliente escolhido, ou (default) o alvo da submissão.
    if payload.criar_novo:
        alvo_id = None
    elif payload.cliente_id_alvo is not None:
        alvo_id = payload.cliente_id_alvo
    else:
        alvo_id = sub.cliente_id_alvo

    if alvo_id:
        cliente = db.query(Cliente).filter(Cliente.id == alvo_id).first()
        if not cliente:
            raise HTTPException(404, "Cliente-alvo não existe mais")
        cliente.tipo = tipo  # corrige/garante PF↔PJ (evita dados misturados)
        for campo, valor in aplicaveis.items():
            _aplicar_valor(cliente, campo, valor)
        criado = False
    else:
        nome = aplicaveis.get("nome") or (dados.get("nome") if isinstance(dados, dict) else None)
        if not nome:
            raise HTTPException(400, "Sem nome — não é possível criar cliente")
        from app.routers.clientes import _gerar_projeto
        projeto_nome, worktree_nome = _gerar_projeto(nome)
        cliente = Cliente(
            nome=nome, tipo=tipo, origem_cadastro="autocadastro",
            projeto_nome=projeto_nome, worktree_nome=worktree_nome,
        )
        for campo, valor in aplicaveis.items():
            if campo == "nome":
                continue
            _aplicar_valor(cliente, campo, valor)
        db.add(cliente)
        criado = True

    sub.status = "aprovado"
    sub.revisado_em = datetime.now(timezone.utc)
    sub.revisado_por_id = user.id
    db.commit()
    db.refresh(cliente)

    # Efeitos colaterais no Drive (best-effort, fora da transação).
    if criado:
        try:
            from app.services.google_drive import ensure_cliente_folder
            ensure_cliente_folder(cliente.nome)
        except Exception:
            pass
    _subir_anexos(sub, cliente.nome)

    return {"ok": True, "cliente_id": str(cliente.id), "criado": criado}


@router.post("/{sub_id}/rejeitar")
def rejeitar_submissao(
    sub_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    sub = db.query(ClienteCadastroSubmissao).filter(ClienteCadastroSubmissao.id == sub_id).first()
    if not sub:
        raise HTTPException(404, "Submissão não encontrada")
    if sub.status != "pendente":
        raise HTTPException(409, f"Submissão já {sub.status}")
    sub.status = "rejeitado"
    sub.revisado_em = datetime.now(timezone.utc)
    sub.revisado_por_id = user.id
    db.commit()
    return {"ok": True}
