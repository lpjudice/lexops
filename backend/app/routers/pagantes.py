"""Router /pagantes — cadastro e listagem de pagantes (tomadores de NF).

Um pagante pode ser cadastrado manualmente (antes de qualquer NF) ou nascer
automaticamente ao emitir uma NF. A listagem agrega totais de NF por pagante.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.pagante import Pagante
from app.models.nota_fiscal import NotaFiscal
from app.models.cliente import Cliente

router = APIRouter(prefix="/pagantes", tags=["pagantes"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class PaganteIn(BaseModel):
    nome: str
    cpf_cnpj: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cod_municipio: Optional[str] = None
    cep: Optional[str] = None
    cliente_id: Optional[uuid.UUID] = None
    observacoes: Optional[str] = None


class PaganteOut(BaseModel):
    id: uuid.UUID
    nome: str
    cpf_cnpj: Optional[str]
    email: Optional[str]
    telefone: Optional[str]
    logradouro: Optional[str]
    numero: Optional[str]
    complemento: Optional[str]
    bairro: Optional[str]
    cod_municipio: Optional[str]
    cep: Optional[str]
    cliente_id: Optional[uuid.UUID]
    cliente_nome: Optional[str] = None
    observacoes: Optional[str]
    origem: str
    # Agregados de NF
    qtd_nfs: int = 0
    valor_total: float = 0.0

    model_config = {"from_attributes": True}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _so_digitos(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    d = "".join(c for c in s if c.isdigit())
    return d or None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("", response_model=list[PaganteOut])
def listar_pagantes(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Lista todos os pagantes com agregados de NF (qtd, total) e nome do cliente vinculado."""
    pagantes = db.query(Pagante).all()

    # Mapa de cliente_id → nome
    clientes = {c.id: c.nome for c in db.query(Cliente.id, Cliente.nome).all()}
    # Match adicional: cliente por cpf_cnpj (para pagantes sem cliente_id explícito)
    clientes_por_doc = {}
    for c in db.query(Cliente.id, Cliente.nome, Cliente.cpf_cnpj).all():
        if c.cpf_cnpj:
            clientes_por_doc[_so_digitos(c.cpf_cnpj)] = (c.id, c.nome)

    # Agregados de NF por cpf_cnpj (somente emitidas, não canceladas)
    agg = (
        db.query(
            NotaFiscal.tomador_cpf_cnpj.label("doc"),
            func.count(NotaFiscal.id).label("qtd"),
            func.coalesce(func.sum(NotaFiscal.valor_servicos), 0).label("total"),
        )
        .filter(NotaFiscal.status == "emitida")
        .group_by(NotaFiscal.tomador_cpf_cnpj)
        .all()
    )
    agg_map = {row.doc: (row.qtd, float(row.total)) for row in agg}

    out = []
    for p in pagantes:
        doc = p.cpf_cnpj
        qtd, total = agg_map.get(doc, (0, 0.0))
        # Resolve nome do cliente: por cliente_id explícito, senão por documento
        cli_nome = None
        cli_id = p.cliente_id
        if cli_id and cli_id in clientes:
            cli_nome = clientes[cli_id]
        elif doc and _so_digitos(doc) in clientes_por_doc:
            cli_id, cli_nome = clientes_por_doc[_so_digitos(doc)]
        item = PaganteOut.model_validate(p)
        item.qtd_nfs = qtd
        item.valor_total = total
        item.cliente_id = cli_id
        item.cliente_nome = cli_nome
        out.append(item)

    out.sort(key=lambda x: x.valor_total, reverse=True)
    return out


@router.post("", response_model=PaganteOut, status_code=201)
def criar_pagante(body: PaganteIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    doc = _so_digitos(body.cpf_cnpj)
    if doc:
        existente = db.query(Pagante).filter(Pagante.cpf_cnpj == doc).first()
        if existente:
            raise HTTPException(409, f"Já existe um pagante com este CPF/CNPJ: {existente.nome}")
    pag = Pagante(
        nome=body.nome,
        cpf_cnpj=doc,
        email=body.email,
        telefone=_so_digitos(body.telefone),
        logradouro=body.logradouro,
        numero=body.numero,
        complemento=body.complemento,
        bairro=body.bairro,
        cod_municipio=body.cod_municipio,
        cep=_so_digitos(body.cep),
        cliente_id=body.cliente_id,
        observacoes=body.observacoes,
        origem="manual",
    )
    db.add(pag)
    db.commit()
    db.refresh(pag)
    return PaganteOut.model_validate(pag)


@router.patch("/{pagante_id}", response_model=PaganteOut)
def atualizar_pagante(pagante_id: uuid.UUID, body: PaganteIn,
                      db: Session = Depends(get_db), _=Depends(get_current_user)):
    pag = db.query(Pagante).filter(Pagante.id == pagante_id).first()
    if not pag:
        raise HTTPException(404, "Pagante não encontrado")
    pag.nome = body.nome
    pag.cpf_cnpj = _so_digitos(body.cpf_cnpj)
    pag.email = body.email
    pag.telefone = _so_digitos(body.telefone)
    pag.logradouro = body.logradouro
    pag.numero = body.numero
    pag.complemento = body.complemento
    pag.bairro = body.bairro
    pag.cod_municipio = body.cod_municipio
    pag.cep = _so_digitos(body.cep)
    pag.cliente_id = body.cliente_id
    pag.observacoes = body.observacoes
    db.commit()
    db.refresh(pag)
    return PaganteOut.model_validate(pag)


@router.delete("/{pagante_id}")
def deletar_pagante(pagante_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(get_current_user)):
    pag = db.query(Pagante).filter(Pagante.id == pagante_id).first()
    if not pag:
        raise HTTPException(404, "Pagante não encontrado")
    db.delete(pag)
    db.commit()
    return {"deletado": True}
