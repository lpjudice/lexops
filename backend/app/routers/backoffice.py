"""Router /backoffice — módulo de decisão tributária e lançamentos fiscais."""
from __future__ import annotations

import uuid
import calendar
from datetime import date, datetime, timezone, timedelta


def _fim_do_mes(mes: str) -> str:
    """Devolve o último dia do mês YYYY-MM como YYYY-MM-DD (respeita mês curto/bissexto)."""
    ano, m = int(mes[:4]), int(mes[5:7])
    ultimo = calendar.monthrange(ano, m)[1]
    return f"{mes}-{ultimo:02d}"
from typing import Any

import base64
import json
import re

import anthropic
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.backoffice import (
    DespesaRecorrente, FiscalDespesa, FiscalFolha, FiscalFornecedor,
    FiscalMes, FiscalReceita, RegraCredito,
)
from app.models.config_fiscal import ConfigFiscal
from app.models.nota_fiscal import NotaFiscal
from app.models.reembolso import ItemReembolso, Reembolso
from app.services.fiscal_engine import EntradaMes, PremissasMes, calcular

router = APIRouter(prefix="/backoffice", tags=["backoffice"])
BRT = timezone(timedelta(hours=-3))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_config(db: Session) -> ConfigFiscal:
    cfg = db.get(ConfigFiscal, 1)
    if not cfg:
        raise HTTPException(400, "Config Fiscal não configurado")
    return cfg


def _get_or_create_mes(mes: str, db: Session) -> FiscalMes:
    obj = db.query(FiscalMes).filter_by(mes=mes).first()
    if not obj:
        obj = FiscalMes(mes=mes)
        db.add(obj)
        db.flush()
    return obj


def _premissas(mes_obj: FiscalMes, cfg: ConfigFiscal) -> PremissasMes:
    ibs_saida = float(mes_obj.ibs_full_pct or cfg.ibs_pct or 0)
    cbs_saida = float(mes_obj.cbs_full_pct or cfg.cbs_pct or 0)
    reducao = float(mes_obj.reducao_setorial_pct if mes_obj.reducao_setorial_pct is not None else 30.0)
    ibs_entrada = ibs_saida / (1 - reducao / 100) if reducao < 100 else ibs_saida
    cbs_entrada = cbs_saida / (1 - reducao / 100) if reducao < 100 else cbs_saida
    return PremissasMes(
        rbt12=float(cfg.rbt12 or 0),
        aliquota_iss=float(cfg.aliquota_iss or 2.0),
        ibs_saida_pct=ibs_saida,
        cbs_saida_pct=cbs_saida,
        ibs_entrada_pct=round(ibs_entrada, 4),
        cbs_entrada_pct=round(cbs_entrada, 4),
        credito_modo=mes_obj.credito_modo or "integral",
    )


def _entrada(mes: str, mes_obj: FiscalMes, db: Session) -> EntradaMes:
    receitas = db.query(FiscalReceita).filter_by(mes=mes).all()
    folha = db.query(FiscalFolha).filter_by(mes=mes).first()
    despesas = db.query(FiscalDespesa).filter_by(mes=mes).all()

    receita_total = sum(float(r.valor) for r in receitas)
    receita_pj_regular = sum(float(r.valor) for r in receitas if r.tipo_cliente == "pj_regular" and r.credito_interesse)
    retencoes = sum(float(r.retencoes) for r in receitas)
    despesas_total = sum(float(d.valor) for d in despesas)
    despesas_elegiveis = sum(float(d.valor) for d in despesas if d.tem_nota and d.elegivel)

    # Reembolsos cancelados = perda real = entram como despesa para a decisão tributária
    perdas_reemb = (
        db.query(ItemReembolso)
        .join(Reembolso, ItemReembolso.reembolso_id == Reembolso.id)
        .filter(
            Reembolso.status == "cancelado",
            ItemReembolso.data.between(f"{mes}-01", _fim_do_mes(mes)),
        )
        .all()
    )
    despesas_total += sum(float(i.valor) for i in perdas_reemb)
    # Presume elegível com nota se houver documento comprobatório
    despesas_elegiveis += sum(
        float(i.valor) for i in perdas_reemb
        if (i.documento_comprobatorio or i.comprovante_path)
    )

    f = folha
    return EntradaMes(
        receita_total=receita_total,
        receita_pj_regular=receita_pj_regular,
        folha_salarios=float(f.salarios) if f else 0,
        folha_prolabore=float(f.prolabore) if f else 0,
        folha_inss_patronal=float(f.inss_patronal) if f else 0,
        folha_fgts=float(f.fgts) if f else 0,
        folha_beneficios=float(f.beneficios) if f else 0,
        folha_outros=float(f.outros) if f else 0,
        despesas_total=despesas_total,
        despesas_elegiveis=despesas_elegiveis,
        retencoes_sofridas=retencoes,
    )


def _sync_receitas_nf(mes: str, db: Session) -> int:
    """Importa NFs emitidas no mês que ainda não estão em FiscalReceita."""
    nfs = (
        db.query(NotaFiscal)
        .filter(NotaFiscal.competencia == mes, NotaFiscal.status.in_(["emitida", "autorizada"]))
        .all()
    )
    adicionadas = 0
    for nf in nfs:
        existe = db.query(FiscalReceita).filter_by(nota_fiscal_id=nf.id).first()
        if existe:
            continue
        # Heurística de tipo_cliente pelo CNPJ/CPF do tomador
        cpf_cnpj = (nf.tomador_cpf_cnpj or "").replace(".", "").replace("-", "").replace("/", "")
        tipo = "pj_regular" if len(cpf_cnpj) == 14 else "pf"

        rec = FiscalReceita(
            mes=mes,
            nota_fiscal_id=nf.id,
            cliente_nome=nf.tomador_nome or "",
            tipo_cliente=tipo,
            valor=float(nf.valor_servicos or 0),
            retencoes=float(
                (nf.retencao_ir or 0) + (nf.retencao_inss or 0)
                + (nf.retencao_csll or 0) + (nf.retencao_cofins or 0)
                + (nf.retencao_pis or 0)
            ),
            credito_interesse=(tipo == "pj_regular"),
            modo_tributacao="embutido",
            is_manual=False,
        )
        db.add(rec)
        adicionadas += 1
    db.flush()
    return adicionadas


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/decisao/{mes}")
def get_decisao(mes: str, _=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    cfg = _get_config(db)
    mes_obj = _get_or_create_mes(mes, db)
    sincronizadas = _sync_receitas_nf(mes, db)
    db.commit()

    premissas = _premissas(mes_obj, cfg)
    entrada = _entrada(mes, mes_obj, db)
    resultado = calcular(entrada, premissas)

    def _linha_dict(r) -> dict:
        l = r.linha
        return {
            "nome": r.nome,
            "slug": r.slug,
            "ranking": r.ranking,
            "carga_efetiva_pct": r.carga_efetiva_pct,
            "credito_cliente": round(r.credito_cliente, 2),
            "obs": r.obs,
            "breakdown": {
                "das": round(l.das, 2),
                "pis": round(l.pis, 2),
                "cofins": round(l.cofins, 2),
                "irpj": round(l.irpj, 2),
                "csll": round(l.csll, 2),
                "iss": round(l.iss, 2),
                "ibs_bruto": round(l.ibs_bruto, 2),
                "cbs_bruto": round(l.cbs_bruto, 2),
                "credito_ibs": round(l.credito_ibs, 2),
                "credito_cbs": round(l.credito_cbs, 2),
                "ibs_liquido": round(l.ibs_liquido, 2),
                "cbs_liquido": round(l.cbs_liquido, 2),
                "inss_patronal": round(l.inss_patronal, 2),
                "fgts": round(l.fgts, 2),
                "total_tributos": round(l.total_tributos, 2),
                "total_com_folha": round(l.total_com_folha, 2),
            },
        }

    return {
        "mes": mes,
        "vencedor": resultado.vencedor.slug,
        "regimes": [_linha_dict(r) for r in resultado.regimes],
        "totais": {k: round(float(v), 2) for k, v in resultado.totais.items()},
        "premissas": {
            "rbt12": premissas.rbt12,
            "aliquota_iss": premissas.aliquota_iss,
            "ibs_saida_pct": premissas.ibs_saida_pct,
            "cbs_saida_pct": premissas.cbs_saida_pct,
            "ibs_entrada_pct": premissas.ibs_entrada_pct,
            "cbs_entrada_pct": premissas.cbs_entrada_pct,
            "credito_modo": premissas.credito_modo,
            "override_ativo": mes_obj.ibs_full_pct is not None,
        },
        "nfs_sincronizadas": sincronizadas,
    }


@router.get("/lancamentos/{mes}")
def get_lancamentos(mes: str, _=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    from app.models.usuario import Usuario as _U
    mes_obj = _get_or_create_mes(mes, db)
    db.commit()
    receitas = db.query(FiscalReceita).filter_by(mes=mes).order_by(FiscalReceita.created_at).all()
    despesas = db.query(FiscalDespesa).filter_by(mes=mes).order_by(FiscalDespesa.data.desc().nullslast(), FiscalDespesa.created_at).all()
    folha = db.query(FiscalFolha).filter_by(mes=mes).first()
    cfg = _get_config(db)
    premissas = _premissas(mes_obj, cfg)
    aliq_total_pct = round(premissas.ibs_entrada_pct + premissas.cbs_entrada_pct, 3)
    fator_global = 0.5 if premissas.credito_modo == "parcial" else 1.0
    aliq_efetiva_pct = round(aliq_total_pct * fator_global, 3)

    def _credito_despesa(d: FiscalDespesa) -> dict:
        if not d.tem_nota or not d.elegivel:
            return {"ibs": 0.0, "cbs": 0.0, "total": 0.0}
        ibs = float(d.valor) * premissas.ibs_entrada_pct / 100 * fator_global
        cbs = float(d.valor) * premissas.cbs_entrada_pct / 100 * fator_global
        return {"ibs": round(ibs, 2), "cbs": round(cbs, 2), "total": round(ibs + cbs, 2)}

    # Cache de nomes de usuários para o chip "cadastrado por"
    user_ids = {d.criado_por_id for d in despesas if d.criado_por_id}
    users_map = {}
    if user_ids:
        for u in db.query(_U).filter(_U.id.in_(user_ids)).all():
            users_map[u.id] = u.nome

    despesas_resp = [
        {
            "id": str(d.id),
            "categoria": d.categoria,
            "fornecedor": d.fornecedor,
            "descricao": d.descricao,
            "valor": float(d.valor),
            "data": d.data.isoformat() if d.data else None,
            "tem_nota": d.tem_nota,
            "elegivel": d.elegivel,
            "base_legal": d.base_legal,
            "status": d.status,
            "last_check": d.last_check,
            "credito": _credito_despesa(d),
            "alq_iva_pct": aliq_efetiva_pct if (d.tem_nota and d.elegivel) else 0,
            "origem": "manual",
            "reembolso_status": None,
            "reembolso_id": None,
            "reembolso_titulo": None,
            "cliente_nome": None,
            "drive_link": d.drive_link,
            "criado_por_nome": users_map.get(d.criado_por_id),
        }
        for d in despesas
    ]

    # Reembolsos: agrupar por reembolso_id (pasta = card de reembolso).
    # Cancelado = "perda" → entra na linha-pai do grupo com flag de crédito.
    # Demais status → grupo "em trânsito" só para visualização (sem crédito).
    itens_reemb = (
        db.query(ItemReembolso, Reembolso)
        .join(Reembolso, ItemReembolso.reembolso_id == Reembolso.id)
        .filter(ItemReembolso.data.between(f"{mes}-01", _fim_do_mes(mes)))
        .order_by(Reembolso.id, ItemReembolso.data)
        .all()
    )
    # Cliente lookup
    from app.models.cliente import Cliente as _C
    cli_ids = {r.cliente_id for _, r in itens_reemb}
    cli_map = {c.id: c.nome for c in db.query(_C).filter(_C.id.in_(cli_ids)).all()} if cli_ids else {}

    grupos: dict[uuid.UUID, dict] = {}
    for item, reemb in itens_reemb:
        is_perda = reemb.status == "cancelado"
        valor_f = float(item.valor)
        if is_perda:
            tem_nota_v = bool(item.documento_comprobatorio or item.comprovante_path)
            elegivel_v = True
            ibs = valor_f * premissas.ibs_entrada_pct / 100 * fator_global if elegivel_v and tem_nota_v else 0
            cbs = valor_f * premissas.cbs_entrada_pct / 100 * fator_global if elegivel_v and tem_nota_v else 0
            credito = {"ibs": round(ibs, 2), "cbs": round(cbs, 2), "total": round(ibs + cbs, 2)}
            alq_iva = aliq_efetiva_pct if (elegivel_v and tem_nota_v) else 0
        else:
            tem_nota_v = False
            elegivel_v = False
            credito = {"ibs": 0.0, "cbs": 0.0, "total": 0.0}
            alq_iva = 0

        child = {
            "id": f"reemb:{item.id}",
            "categoria": item.natureza,
            "fornecedor": (item.descricao[:80] if item.descricao else "—"),
            "descricao": item.descricao,
            "valor": valor_f,
            "data": item.data.isoformat() if item.data else None,
            "tem_nota": tem_nota_v,
            "elegivel": elegivel_v,
            "base_legal": "Reembolso cancelado (perda)" if is_perda else "Reembolso em trânsito",
            "status": "perda" if is_perda else "transito",
            "last_check": None,
            "credito": credito,
            "alq_iva_pct": alq_iva,
            "origem": "reembolso",
            "reembolso_status": reemb.status,
            "reembolso_id": str(reemb.id),
            "reembolso_titulo": reemb.titulo,
            "cliente_nome": cli_map.get(reemb.cliente_id),
            "drive_link": reemb.drive_link,
            "criado_por_nome": None,
        }
        g = grupos.setdefault(reemb.id, {
            "id": f"reembgrp:{reemb.id}",
            "origem": "reembolso_grupo",
            "reembolso_id": str(reemb.id),
            "reembolso_titulo": reemb.titulo,
            "reembolso_status": reemb.status,
            "cliente_nome": cli_map.get(reemb.cliente_id),
            "drive_link": reemb.drive_link,
            "valor_total": 0.0,
            "credito_total": 0.0,
            "itens": [],
            "data_inicio": None,
            "data_fim": None,
        })
        g["valor_total"] += valor_f
        g["credito_total"] += credito["total"]
        if item.data:
            iso = item.data.isoformat()
            if not g["data_inicio"] or iso < g["data_inicio"]:
                g["data_inicio"] = iso
            if not g["data_fim"] or iso > g["data_fim"]:
                g["data_fim"] = iso
        g["itens"].append(child)

    grupos_resp = list(grupos.values())

    return {
        "mes": mes,
        "receitas": [
            {
                "id": str(r.id),
                "cliente_nome": r.cliente_nome,
                "tipo_cliente": r.tipo_cliente,
                "valor": float(r.valor),
                "retencoes": float(r.retencoes),
                "credito_interesse": r.credito_interesse,
                "modo_tributacao": r.modo_tributacao,
                "is_manual": r.is_manual,
                "nota_fiscal_id": str(r.nota_fiscal_id) if r.nota_fiscal_id else None,
            }
            for r in receitas
        ],
        "folha": {
            "salarios": float(folha.salarios) if folha else 0,
            "prolabore": float(folha.prolabore) if folha else 0,
            "inss_patronal": float(folha.inss_patronal) if folha else 0,
            "rat": float(folha.rat) if folha else 0,
            "fgts": float(folha.fgts) if folha else 0,
            "beneficios": float(folha.beneficios) if folha else 0,
            "outros": float(folha.outros) if folha else 0,
        },
        "despesas": despesas_resp,
        "reembolso_grupos": grupos_resp,
        "aliq_iva_total_pct": aliq_total_pct,
        "aliq_iva_efetiva_pct": aliq_efetiva_pct,
    }


# ── Salvar folha ──────────────────────────────────────────────────────────────

class FolhaIn(BaseModel):
    salarios: float = 0
    prolabore: float = 0
    inss_patronal: float = 0
    rat: float = 0
    fgts: float = 0
    beneficios: float = 0
    outros: float = 0


@router.put("/folha/{mes}")
def upsert_folha(mes: str, body: FolhaIn, _=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    _get_or_create_mes(mes, db)
    folha = db.query(FiscalFolha).filter_by(mes=mes).first()
    if not folha:
        folha = FiscalFolha(mes=mes)
        db.add(folha)
    for k, v in body.model_dump().items():
        setattr(folha, k, v)
    db.commit()
    return {"ok": True}


# ── Salvar despesa ────────────────────────────────────────────────────────────

class DespesaIn(BaseModel):
    categoria: str
    fornecedor: str
    descricao: str | None = None
    valor: float
    data: date | None = None  # se vier, o mes é derivado dela
    tem_nota: bool = True
    elegivel: bool = False
    base_legal: str | None = None
    status: str = "novo"
    drive_link: str | None = None


@router.post("/despesas/{mes}")
def add_despesa(mes: str, body: DespesaIn, user=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    # Se vier data, ela define o mês — caso contrário usa o mês da URL
    mes_real = body.data.strftime("%Y-%m") if body.data else mes
    _get_or_create_mes(mes_real, db)
    d = FiscalDespesa(
        mes=mes_real,
        categoria=body.categoria,
        fornecedor=body.fornecedor,
        descricao=body.descricao,
        valor=body.valor,
        data=body.data,
        tem_nota=body.tem_nota,
        elegivel=body.elegivel,
        base_legal=body.base_legal or "LC 214/2025",
        status=body.status,
        criado_por_id=getattr(user, "id", None),
        drive_link=body.drive_link,
    )
    db.add(d)
    db.commit()
    return {"id": str(d.id), "mes": mes_real}


@router.patch("/despesas/{id}")
def patch_despesa(id: uuid.UUID, body: dict, _=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    d = db.get(FiscalDespesa, id)
    if not d:
        raise HTTPException(404, "Despesa não encontrada")
    allowed = {"categoria", "fornecedor", "descricao", "valor", "data", "tem_nota", "elegivel", "base_legal", "status", "drive_link"}
    for k, v in body.items():
        if k in allowed:
            # Se a data muda, ajusta o mês
            if k == "data" and v:
                d.mes = date.fromisoformat(v).strftime("%Y-%m") if isinstance(v, str) else v.strftime("%Y-%m")
                _get_or_create_mes(d.mes, db)
            setattr(d, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/despesas/{id}")
def delete_despesa(id: uuid.UUID, _=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    d = db.get(FiscalDespesa, id)
    if not d:
        raise HTTPException(404)
    db.delete(d)
    db.commit()
    return {"ok": True}


# ── Receita manual ────────────────────────────────────────────────────────────

class ReceitaIn(BaseModel):
    cliente_nome: str
    tipo_cliente: str = "pj_regular"
    valor: float
    retencoes: float = 0
    credito_interesse: bool = False
    modo_tributacao: str = "embutido"


@router.post("/receitas/{mes}")
def add_receita(mes: str, body: ReceitaIn, _=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    _get_or_create_mes(mes, db)
    r = FiscalReceita(mes=mes, is_manual=True, **body.model_dump())
    db.add(r)
    db.commit()
    return {"id": str(r.id)}


@router.delete("/receitas/{id}")
def delete_receita(id: uuid.UUID, _=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    r = db.get(FiscalReceita, id)
    if not r:
        raise HTTPException(404)
    if not r.is_manual:
        raise HTTPException(400, "Receitas importadas de NF não podem ser removidas aqui — cancele a NF")
    db.delete(r)
    db.commit()
    return {"ok": True}


# ── Premissas override do mês ─────────────────────────────────────────────────

class PremissasIn(BaseModel):
    ibs_full_pct: float | None = None
    cbs_full_pct: float | None = None
    reducao_setorial_pct: float | None = None
    credito_modo: str = "integral"


@router.put("/premissas/{mes}")
def upsert_premissas(mes: str, body: PremissasIn, _=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    obj = _get_or_create_mes(mes, db)
    obj.ibs_full_pct = body.ibs_full_pct
    obj.cbs_full_pct = body.cbs_full_pct
    obj.reducao_setorial_pct = body.reducao_setorial_pct
    obj.credito_modo = body.credito_modo
    db.commit()
    return {"ok": True}


# ── Visão anual ───────────────────────────────────────────────────────────────

@router.get("/anual")
def get_anual(_=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    cfg = _get_config(db)
    meses = db.query(FiscalMes).order_by(FiscalMes.mes).all()
    resultado = []
    for m in meses:
        premissas = _premissas(m, cfg)
        entrada = _entrada(m.mes, m, db)
        if entrada.receita_total == 0:
            continue
        calc = calcular(entrada, premissas)
        resultado.append({
            "mes": m.mes,
            "vencedor": calc.vencedor.slug,
            "vencedor_nome": calc.vencedor.nome,
            "receita_total": round(entrada.receita_total, 2),
            "credito_total": round(calc.totais["credito_total"], 2),
            "carga_efetiva_pct": calc.vencedor.carga_efetiva_pct,
        })
    return resultado


# ── Catálogo de regras ────────────────────────────────────────────────────────

@router.get("/regras")
def list_regras(_=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    regras = db.query(RegraCredito).order_by(RegraCredito.categoria).all()
    return [
        {
            "id": str(r.id),
            "categoria": r.categoria,
            "descricao": r.descricao,
            "base_legal": r.base_legal,
            "status": r.status,
            "elegivel": r.elegivel,
            "last_check": r.last_check,
            "next_check": r.next_check,
            "notas": r.notas,
        }
        for r in regras
    ]


class RegraIn(BaseModel):
    categoria: str
    descricao: str | None = None
    base_legal: str = "LC 214/2025"
    fundamento_complementar: str | None = None
    status: str = "pendente"
    elegivel: bool = False
    last_check: str | None = None
    next_check: str | None = None
    notas: str | None = None


@router.post("/regras")
def create_regra(body: RegraIn, _=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    r = RegraCredito(**body.model_dump())
    db.add(r)
    db.commit()
    return {"id": str(r.id)}


@router.post("/seed-mock")
def seed_mock(_=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    """Seed temporário de 2 meses mock para teste. REMOVER após uso."""
    for mes in ("2026-04", "2026-05"):
        if db.query(FiscalMes).filter_by(mes=mes).first():
            continue
        db.add(FiscalMes(mes=mes, ibs_full_pct=0.1, cbs_full_pct=0.9, reducao_setorial_pct=30.0, credito_modo="integral"))

    db.flush()

    folha_abril = {"salarios": 54000, "prolabore": 16000, "inss_patronal": 14000, "rat": 1800, "fgts": 5100, "beneficios": 6900, "outros": 0}
    folha_maio  = {"salarios": 61000, "prolabore": 18000, "inss_patronal": 15500, "rat": 2100, "fgts": 5800, "beneficios": 7900, "outros": 0}
    for mes, dados in [("2026-04", folha_abril), ("2026-05", folha_maio)]:
        if not db.query(FiscalFolha).filter_by(mes=mes).first():
            db.add(FiscalFolha(mes=mes, **dados))

    despesas = [
        # abril
        ("2026-04", "Software jurídico",       "Legal Tech One",      8400,  True,  True,  "LC 214/2025",         "validado",  "2026-02"),
        ("2026-04", "Marketing / publicidade",  "Studio Trinta",      12000,  True,  True,  "LC 214/2025",         "revalidar", "2025-10"),
        ("2026-04", "Correspondentes",          "Rede Processual",    18600,  True,  True,  "LC 214/2025",         "validado",  "2026-01"),
        ("2026-04", "Aluguel",                  "Imobiliária Centro",  9800,  True,  False, "Tese sensível",       "pendente",  None),
        ("2026-04", "Energia elétrica",         "Concessionária",      3600,  True,  True,  "LC 214/2025",         "validado",  "2026-03"),
        # maio
        ("2026-05", "Software jurídico",        "Legal Tech One",      8400,  True,  True,  "LC 214/2025",         "validado",  "2026-02"),
        ("2026-05", "Marketing / publicidade",  "Studio Trinta",      14000,  True,  True,  "LC 214/2025",         "revalidar", "2025-11"),
        ("2026-05", "Correspondentes",          "Rede Processual",    22400,  True,  True,  "LC 214/2025",         "validado",  "2026-01"),
        ("2026-05", "Energia elétrica",         "Concessionária",      3900,  True,  True,  "LC 214/2025",         "validado",  "2026-03"),
        ("2026-05", "Internet",                 "Fibra Empresas",       980,  True,  True,  "LC 214/2025",         "novo",      None),
        ("2026-05", "Aluguel",                  "Imobiliária Centro",  9800,  True,  False, "Tese sensível",       "pendente",  None),
        ("2026-05", "Despesas com clientes",    "Diversos",            4200,  False, False, "Sem documento hábil", "pendente",  None),
        ("2026-05", "Contabilidade",            "Escritório Fischer",  3500,  True,  True,  "LC 214/2025",         "validado",  "2026-01"),
        ("2026-05", "Telefonia",                "Vivo Empresas",        890,  True,  True,  "LC 214/2025",         "novo",      None),
    ]
    for (mes, cat, forn, val, nota, eleg, base, status, check) in despesas:
        db.add(FiscalDespesa(mes=mes, categoria=cat, fornecedor=forn, valor=val,
                             tem_nota=nota, elegivel=eleg, base_legal=base,
                             status=status, last_check=check))

    db.commit()
    return {"ok": True, "meses": ["2026-04", "2026-05"]}


@router.patch("/regras/{id}")
def patch_regra(id: uuid.UUID, body: dict, _=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    r = db.get(RegraCredito, id)
    if not r:
        raise HTTPException(404)
    allowed = {"status", "elegivel", "base_legal", "fundamento_complementar", "last_check", "next_check", "notas"}
    for k, v in body.items():
        if k in allowed:
            setattr(r, k, v)
    db.commit()
    return {"ok": True}


# ── Fornecedores conhecidos ───────────────────────────────────────────────────

@router.get("/fornecedores")
def list_fornecedores(_=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    rows = db.query(FiscalFornecedor).order_by(FiscalFornecedor.nome).all()
    return [{"id": str(r.id), "nome": r.nome, "cnpj": r.cnpj, "categoria_padrao": r.categoria_padrao} for r in rows]


class FornecedorIn(BaseModel):
    nome: str
    cnpj: str | None = None
    categoria_padrao: str | None = None


@router.post("/fornecedores")
def upsert_fornecedor(body: FornecedorIn, _=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    existing = db.query(FiscalFornecedor).filter_by(nome=body.nome).first()
    if existing:
        existing.cnpj = body.cnpj or existing.cnpj
        existing.categoria_padrao = body.categoria_padrao or existing.categoria_padrao
        db.commit()
        return {"id": str(existing.id), "updated": True}
    f = FiscalFornecedor(**body.model_dump())
    db.add(f)
    db.commit()
    return {"id": str(f.id), "updated": False}


@router.get("/categorias")
def list_categorias(_=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    from sqlalchemy import distinct
    cats = db.query(distinct(FiscalDespesa.categoria)).order_by(FiscalDespesa.categoria).all()
    return [c[0] for c in cats]


# ── Despesas recorrentes ──────────────────────────────────────────────────────

@router.get("/recorrentes")
def list_recorrentes(_=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    rows = db.query(DespesaRecorrente).filter_by(ativa=True).order_by(DespesaRecorrente.categoria).all()
    return [
        {
            "id": str(r.id), "categoria": r.categoria, "fornecedor": r.fornecedor,
            "descricao": r.descricao, "valor_padrao": float(r.valor_padrao),
            "tem_nota": r.tem_nota, "elegivel": r.elegivel,
        }
        for r in rows
    ]


class RecorrenteIn(BaseModel):
    categoria: str
    fornecedor: str
    descricao: str | None = None
    valor_padrao: float = 0
    tem_nota: bool = True
    elegivel: bool = False


@router.post("/recorrentes")
def create_recorrente(body: RecorrenteIn, _=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    r = DespesaRecorrente(**body.model_dump())
    db.add(r)
    db.commit()
    return {"id": str(r.id)}


@router.patch("/recorrentes/{id}")
def patch_recorrente(id: uuid.UUID, body: dict, _=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    r = db.get(DespesaRecorrente, id)
    if not r:
        raise HTTPException(404)
    allowed = {"categoria", "fornecedor", "descricao", "valor_padrao", "tem_nota", "elegivel", "ativa"}
    for k, v in body.items():
        if k in allowed:
            setattr(r, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/recorrentes/{id}")
def delete_recorrente(id: uuid.UUID, _=Depends(get_current_user), db: Session = Depends(get_db)) -> Any:
    r = db.get(DespesaRecorrente, id)
    if not r:
        raise HTTPException(404)
    r.ativa = False
    db.commit()
    return {"ok": True}


# ── Lançamento em lote ────────────────────────────────────────────────────────

class DespesaBatchItem(BaseModel):
    categoria: str
    fornecedor: str
    descricao: str | None = None
    valor: float
    data: date | None = None  # se vier, define o mês da despesa
    tem_nota: bool = True
    elegivel: bool = False
    base_legal: str = "LC 214/2025"
    status: str = "novo"


@router.post("/despesas/batch/{mes}")
def add_despesas_batch(
    mes: str,
    items: list[DespesaBatchItem],
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Insere despesas em lote. O mês de cada despesa vem da SUA data (não da URL),
    para que um extrato de maio caia em maio mesmo que o filtro esteja em junho."""
    ids = []
    meses_criados: set[str] = set()
    for item in items:
        dados = item.model_dump()
        d_data = dados.get("data")
        mes_real = d_data.strftime("%Y-%m") if d_data else mes
        if mes_real not in meses_criados:
            _get_or_create_mes(mes_real, db)
            meses_criados.add(mes_real)
        d = FiscalDespesa(mes=mes_real, criado_por_id=getattr(user, "id", None), **dados)
        db.add(d)
        db.flush()
        ids.append(str(d.id))
    db.commit()
    return {"ids": ids, "count": len(ids), "meses": sorted(meses_criados)}


# ── Parse de extrato bancário com IA ─────────────────────────────────────────

_PARSE_PROMPT = """\
Você está analisando um extrato bancário de um ESCRITÓRIO DE ADVOCACIA.
Extraia TODAS as SAÍDAS de dinheiro (débitos, "Pix enviado", "Pagamento efetuado",
"TED enviada", tarifas relevantes).

REGRAS:
- IGNORE entradas (depósitos, "Pix recebido", crédito) — só saídas.
- IGNORE saldos do dia (linhas "Saldo do dia") — não são transações.
- IGNORE transferências para o próprio CNPJ/CPF do titular (pro-labore via Pix para o próprio sócio).
- IGNORE estornos e movimentações puramente internas (saldo bloqueado etc).
- Limpe o nome do fornecedor: remova "Cp :NNNNNNNN-" no início, remova ":", aspas, e o tipo
  ("Pix enviado", "Pagamento efetuado"). Exemplo: 'Pix enviado: "Cp :28127603-TRIBUNAL DE JUSTICA..."'
  vira fornecedor = "TRIBUNAL DE JUSTIÇA DO ES" (limpo, capitalizado, sem números de identificador).
- O valor deve ser positivo (number), sem sinal de menos.
- A data está no cabeçalho da seção do dia ("5 de Maio de 2026"). Use YYYY-MM-DD.

Categorias possíveis (escolha a mais provável para um escritório de advocacia):
"Software jurídico (SaaS)", "Marketing / publicidade", "Correspondentes / parceiros forenses",
"Honorários periciais", "Honorários de outros advogados", "Aluguel comercial",
"Condomínio comercial", "Energia elétrica", "Internet", "Telefonia fixa / móvel",
"Material de escritório", "Contabilidade", "Despesas de clientes (reembolsáveis)",
"Combustível", "Uber / táxi", "IPTU / IPVA / tributos", "Despesas pessoais",
"Brindes / presentes", "Doações", "Refeições com clientes", "Outros".

Para PIX a TRIBUNAL DE JUSTIÇA, custas processuais, ONR, SEFAZ, RECEITA FEDERAL, DGFIN →
categoria "IPTU / IPVA / tributos" ou "Despesas de clientes (reembolsáveis)" conforme contexto.

Retorne APENAS um JSON array. Sem markdown. Sem comentários. Sem texto antes/depois.

Formato de cada item:
{"fornecedor":"...","valor":NNNN.NN,"data":"YYYY-MM-DD","descricao":"...","categoria":"..."}"""


# NOTA: caminho fora de "/despesas/..." para não colidir com POST /despesas/{mes} (add_despesa),
# que é registrado antes e capturaria "parse-extrato" como se fosse um mês.
@router.post("/extrato/parse")
async def parse_extrato(
    file: UploadFile = File(...),
    _=Depends(get_current_user),
) -> Any:
    import logging
    logger = logging.getLogger(__name__)

    content = await file.read()
    if not content:
        raise HTTPException(400, "Arquivo vazio")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "Arquivo muito grande (> 20MB). Divida o PDF em partes menores.")

    ct = (file.content_type or "").lower()
    filename = file.filename or ""
    is_pdf = ct == "application/pdf" or filename.lower().endswith(".pdf")
    b64 = base64.b64encode(content).decode()

    if is_pdf:
        media_block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    else:
        media_type = ct if ct.startswith("image/") else "image/jpeg"
        media_block = {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}

    client = anthropic.Anthropic()
    try:
        resp = client.messages.create(
            # Sonnet é mais robusto que Haiku para PDFs com várias páginas
            model="claude-sonnet-4-6",
            max_tokens=8192,
            messages=[{
                "role": "user",
                "content": [media_block, {"type": "text", "text": _PARSE_PROMPT}],
            }],
        )
    except anthropic.BadRequestError as e:
        logger.warning("parse_extrato BadRequestError: %s", e)
        raise HTTPException(400, f"Claude recusou o arquivo: {str(e)[:200]}")
    except anthropic.APIStatusError as e:
        logger.warning("parse_extrato APIStatusError: %s", e)
        raise HTTPException(502, f"Falha na API Claude ({e.status_code}): {str(e)[:200]}")
    except Exception as e:
        logger.exception("parse_extrato erro inesperado")
        raise HTTPException(500, f"Erro inesperado: {type(e).__name__}: {str(e)[:200]}")

    text = (resp.content[0].text if resp.content else "").strip()
    if not text:
        raise HTTPException(502, "Claude retornou resposta vazia.")

    try:
        linhas = json.loads(text)
    except Exception:
        m = re.search(r"\[.*\]", text, re.DOTALL)
        if not m:
            logger.warning("parse_extrato: sem JSON na resposta. Resposta: %s", text[:500])
            raise HTTPException(
                422,
                f"Claude não retornou JSON. Possível causa: PDF sem texto extraível, "
                f"resposta cortada (tokens), ou imagem sem OCR legível. Início da resposta: "
                f"{text[:200]}"
            )
        try:
            linhas = json.loads(m.group())
        except Exception as e:
            logger.warning("parse_extrato: JSON inválido. Erro: %s", e)
            raise HTTPException(422, f"JSON inválido retornado por Claude: {e}")

    if not isinstance(linhas, list):
        raise HTTPException(422, "Resposta não é uma lista de despesas.")

    return {"linhas": linhas, "total": len(linhas)}


# ── Upload de comprovante para Drive ──────────────────────────────────────────

from fastapi import File, Form, UploadFile


# NOTA: fora de "/despesas/..." para não colidir com POST /despesas/{mes}.
@router.post("/comprovante/upload")
async def upload_comprovante(
    file: UploadFile = File(...),
    mes: str = Form(...),
    _=Depends(get_current_user),
):
    """Salva o arquivo em /Backoffice/Despesas/{mes}/ no Drive e devolve o link."""
    from app.services.google_drive import upload_arquivo_raiz
    conteudo = await file.read()
    if not conteudo:
        raise HTTPException(400, "Arquivo vazio")
    if len(conteudo) > 25 * 1024 * 1024:
        raise HTTPException(413, "Arquivo > 25MB")
    nome = file.filename or "comprovante"
    mime = file.content_type or "application/octet-stream"
    link = upload_arquivo_raiz(
        conteudo=conteudo,
        nome_arquivo=nome,
        subpath=["Backoffice", "Despesas", mes],
        mimetype=mime,
    )
    if not link:
        raise HTTPException(502, "Falha ao enviar ao Drive — verifique a autenticação Google")
    return {"link": link, "filename": nome}


# ── Classificação IA de despesa (LC 214/2025) ─────────────────────────────────

class ClassificarIn(BaseModel):
    categoria: str
    fornecedor: str | None = None
    descricao: str | None = None
    valor: float = 0
    respostas: dict | None = None  # respostas às clarificações de uma chamada anterior


_CLASSIFY_PROMPT = """\
Você é um especialista em Reforma Tributária brasileira (LC 214/2025 — IBS/CBS).
Classifique se a despesa abaixo gera crédito de IBS/CBS para um escritório de advocacia.

Despesa:
- Categoria: {categoria}
- Fornecedor: {fornecedor}
- Descrição: {descricao}
- Valor: R$ {valor:.2f}
- Respostas a clarificações anteriores: {respostas}

Regras-chave da LC 214/2025 para advocacia:
- Crédito AMPLO na aquisição de bens/serviços que sejam INSUMOS da atividade-fim (art. 47 LC 214)
- Insumos da advocacia: software jurídico, correspondentes, honorários periciais, bases de
  jurisprudência, marketing/publicidade, aluguel comercial, energia/água/internet/telefonia,
  material de escritório, contabilidade, segurança, limpeza
- NÃO geram crédito: aluguel residencial, despesas pessoais, multas, IPVA, IPTU residencial,
  doações, brindes, alimentação pessoal, bens de uso/consumo pessoal (art. 57 LC 214)
- Casos AMBÍGUOS que exigem clarificação (faça perguntas para o usuário):
  * Combustível / Uber: É deslocamento profissional (audiência, cliente)? Sim → elegível
  * Refeição/Alimentação: É com cliente em reunião profissional? Sim → elegível como insumo
  * Hospedagem/passagem: É viagem a trabalho? Sim → elegível
  * Despesas reembolsáveis pelo cliente: É despesa do escritório ou repassada ao cliente?
    Se reembolsada, NÃO gera crédito (é receita futura, não insumo).
  * Hardware/eletrônico: É exclusivo do escritório ou misto pessoal/empresa? Misto não permite.
  * Aluguel: Comercial dedicado ou home office? Home office só permite proporção do uso empresarial.
- Sem NF/documento hábil → NÃO gera crédito (art. 28 LC 214)
- Alíquotas 2026 (cheias, antes da redução setorial): IBS = 0,1%, CBS = 0,9%
- Advocacia tem 30% de redução setorial na SAÍDA, mas crédito de ENTRADA é cheio (alíq. do fornecedor)

Se a categoria for ambígua E ainda não houver respostas suficientes, retorne JSON com
"perguntas" preenchido para coletar informações. Caso contrário, classifique normalmente.

Responda APENAS um JSON com:
{{
  "elegivel": true|false,
  "base_legal": "art. da LC 214/2025 ou regra aplicável (max 100 chars)",
  "aliquota_ibs_pct": 0.1,
  "aliquota_cbs_pct": 0.9,
  "credito_estimado": valor numérico do crédito esperado (ibs+cbs sobre o valor),
  "confianca": "alta|media|baixa",
  "observacao": "breve justificativa (max 120 chars)",
  "perguntas": [
    {{ "id": "uso_profissional", "pergunta": "...", "opcoes": ["Sim","Não","Misto"] }}
  ]
}}
"perguntas" é OPCIONAL — retorne array vazio [] ou omita se a classificação já está clara.
Sem markdown, sem comentários adicionais."""


@router.post("/classificar-despesa")
def classificar_despesa(body: ClassificarIn, _=Depends(get_current_user)) -> Any:
    client = anthropic.Anthropic()
    prompt = _CLASSIFY_PROMPT.format(
        categoria=body.categoria,
        fornecedor=body.fornecedor or "—",
        descricao=body.descricao or "—",
        valor=body.valor,
        respostas=json.dumps(body.respostas, ensure_ascii=False) if body.respostas else "—",
    )
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    try:
        data = json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        data = json.loads(m.group()) if m else {"elegivel": False, "base_legal": "—", "credito_estimado": 0, "confianca": "baixa", "observacao": "Falha ao classificar"}
    return data


# ── Sincronização de NFs migrada para o módulo Notas Fiscais (ver fiscalApi.sincronizarDfe).
