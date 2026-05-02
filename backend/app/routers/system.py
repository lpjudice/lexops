"""
System utilities: abrir pasta no Finder, info da máquina, acessos confidenciais.
"""
import subprocess
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.usuario import Usuario

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/abrir-pasta")
def abrir_pasta(path: str = Query(..., description="Caminho da pasta a abrir no Finder")):
    """
    Abre uma pasta no Finder do macOS.
    Funciona apenas quando o backend roda no host (não em Docker).
    """
    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Pasta não encontrada: {path}")
    try:
        subprocess.Popen(["open", str(p)])
        return {"ok": True, "path": str(p)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pasta-cliente-path")
def pasta_cliente_path(nome: str = Query(...)):
    """Retorna o caminho macOS da pasta de um cliente."""
    from app.services.pasta_cliente import caminho_host
    return {"path": caminho_host(nome)}


@router.get("/acesso-confidencial")
def acesso_confidencial(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """
    Visão geral de quem tem acesso a itens confidenciais por cliente.
    Apenas super_admin.
    """
    from app.models.anotacao import Anotacao
    from app.models.cliente import Cliente
    from app.models.reuniao import Reuniao
    from app.models.tarefa import Tarefa

    if usuario.role != "super_admin":
        raise HTTPException(status_code=403, detail="Apenas super admin pode acessar esta visão")

    # Cache de nomes de usuários
    _usuario_cache: dict[str, str] = {}

    def resolve_nome(uid_str: str) -> str | None:
        if uid_str in _usuario_cache:
            return _usuario_cache[uid_str]
        try:
            u = db.query(Usuario).filter(Usuario.id == uuid.UUID(uid_str)).first()
            if u:
                _usuario_cache[uid_str] = u.nome
                return u.nome
        except (ValueError, TypeError):
            pass
        return None

    # Agrupa por cliente_id → {cliente_nome, itens}
    grupos: dict[str, dict[str, Any]] = {}

    def get_grupo(cliente_id: str | None) -> dict[str, Any]:
        key = str(cliente_id) if cliente_id else "__sem_cliente__"
        if key not in grupos:
            nome_cliente = "Sem cliente"
            if cliente_id:
                c = db.query(Cliente).filter(Cliente.id == uuid.UUID(cliente_id)).first()
                nome_cliente = c.nome if c else str(cliente_id)
            grupos[key] = {"cliente_nome": nome_cliente, "itens": []}
        return grupos[key]

    def build_usuarios(acesso_list: list[str] | None) -> list[dict[str, str]]:
        result = []
        for entry in (acesso_list or []):
            if entry.startswith("req:"):
                continue
            nome = resolve_nome(entry)
            if nome:
                result.append({"id": entry, "nome": nome})
        return result

    # Tarefas confidenciais
    tarefas = db.query(Tarefa).filter(Tarefa.confidencial.is_(True)).all()
    for t in tarefas:
        usuarios_acesso = build_usuarios(t.usuarios_com_acesso)
        if not usuarios_acesso:
            continue
        grupo = get_grupo(str(t.cliente_id) if t.cliente_id else None)
        grupo["itens"].append({
            "tipo": "tarefa",
            "titulo": t.titulo,
            "usuarios": usuarios_acesso,
            "id": str(t.id),
        })

    # Reuniões confidenciais
    reunioes = db.query(Reuniao).filter(Reuniao.confidencial.is_(True)).all()
    for r in reunioes:
        usuarios_acesso = build_usuarios(r.usuarios_com_acesso)
        if not usuarios_acesso:
            continue
        grupo = get_grupo(str(r.cliente_id) if r.cliente_id else None)
        grupo["itens"].append({
            "tipo": "reuniao",
            "titulo": r.titulo,
            "usuarios": usuarios_acesso,
            "id": str(r.id),
        })

    # Anotações confidenciais (only if model has usuarios_com_acesso)
    try:
        anotacoes = db.query(Anotacao).filter(Anotacao.confidencial.is_(True)).all()
        for a in anotacoes:
            raw_acesso = getattr(a, "usuarios_com_acesso", None)
            usuarios_acesso = build_usuarios(raw_acesso)
            if not usuarios_acesso:
                continue
            grupo = get_grupo(str(a.cliente_id) if a.cliente_id else None)
            grupo["itens"].append({
                "tipo": "anotacao",
                "titulo": a.titulo or "Anotação",
                "usuarios": usuarios_acesso,
                "id": str(a.id),
            })
    except Exception:
        pass

    return [v for v in grupos.values() if v["itens"]]
