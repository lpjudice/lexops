import uuid
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cliente import Cliente
from app.models.financeiro import Honorario, Recebimento
from app.schemas.financeiro import (
    HonorarioCreate, HonorarioOut, HonorarioUpdate,
    RecebimentoCreate, RecebimentoOut,
    ResumoCliente, ResumoFinanceiro, ResumoMensal,
)

router = APIRouter(prefix="/financeiro", tags=["financeiro"])


# ── Honorários ────────────────────────────────────────────────────────────────

@router.get("/honorarios/", response_model=list[HonorarioOut])
def listar_honorarios(
    cliente_id: uuid.UUID | None = None,
    status: str | None = None,
    pendente_assinatura: bool | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Honorario)
    if cliente_id:
        q = q.filter(Honorario.cliente_id == cliente_id)
    if status:
        q = q.filter(Honorario.status == status)
    if pendente_assinatura is not None:
        q = q.filter(Honorario.pendente_assinatura == pendente_assinatura)
    return q.order_by(Honorario.created_at.desc()).all()


@router.post("/honorarios/", response_model=HonorarioOut, status_code=status.HTTP_201_CREATED)
def criar_honorario(data: HonorarioCreate, db: Session = Depends(get_db)):
    h = Honorario(**data.model_dump())
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


@router.get("/honorarios/{honorario_id}", response_model=HonorarioOut)
def obter_honorario(honorario_id: uuid.UUID, db: Session = Depends(get_db)):
    h = db.query(Honorario).filter(Honorario.id == honorario_id).first()
    if not h:
        raise HTTPException(status_code=404, detail="Honorário não encontrado")
    return h


@router.patch("/honorarios/{honorario_id}", response_model=HonorarioOut)
def atualizar_honorario(
    honorario_id: uuid.UUID, data: HonorarioUpdate, db: Session = Depends(get_db)
):
    h = db.query(Honorario).filter(Honorario.id == honorario_id).first()
    if not h:
        raise HTTPException(status_code=404, detail="Honorário não encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(h, field, value)
    db.commit()
    db.refresh(h)
    return h


@router.delete("/honorarios/{honorario_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_honorario(honorario_id: uuid.UUID, db: Session = Depends(get_db)):
    h = db.query(Honorario).filter(Honorario.id == honorario_id).first()
    if not h:
        raise HTTPException(status_code=404, detail="Honorário não encontrado")
    db.delete(h)
    db.commit()


# ── Recebimentos ──────────────────────────────────────────────────────────────

@router.post("/honorarios/{honorario_id}/recebimentos/",
             response_model=RecebimentoOut, status_code=status.HTTP_201_CREATED)
def adicionar_recebimento(
    honorario_id: uuid.UUID, data: RecebimentoCreate, db: Session = Depends(get_db)
):
    h = db.query(Honorario).filter(Honorario.id == honorario_id).first()
    if not h:
        raise HTTPException(status_code=404, detail="Honorário não encontrado")

    rec = Recebimento(honorario_id=honorario_id, **data.model_dump())
    db.add(rec)
    db.flush()
    db.refresh(h)

    # Atualiza status automaticamente
    total_rec = sum(float(r.valor) for r in h.recebimentos)
    if total_rec >= float(h.valor_total):
        h.status = "pago"
    elif total_rec > 0:
        h.status = "parcial"

    db.commit()
    db.refresh(rec)
    return rec


@router.delete("/honorarios/{honorario_id}/recebimentos/{rec_id}",
               status_code=status.HTTP_204_NO_CONTENT)
def remover_recebimento(
    honorario_id: uuid.UUID, rec_id: uuid.UUID, db: Session = Depends(get_db)
):
    rec = db.query(Recebimento).filter(
        Recebimento.id == rec_id,
        Recebimento.honorario_id == honorario_id,
    ).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recebimento não encontrado")
    db.delete(rec)
    db.flush()

    # Recalcula status
    h = db.query(Honorario).filter(Honorario.id == honorario_id).first()
    if h:
        total_rec = sum(float(r.valor) for r in h.recebimentos if r.id != rec_id)
        if total_rec <= 0:
            h.status = "pendente"
        elif total_rec < float(h.valor_total):
            h.status = "parcial"
        else:
            h.status = "pago"

    db.commit()


# ── Resumo financeiro ─────────────────────────────────────────────────────────

@router.get("/resumo/", response_model=ResumoFinanceiro)
def resumo_financeiro(db: Session = Depends(get_db)):
    honorarios = db.query(Honorario).filter(
        Honorario.status != "cancelado"
    ).all()

    from datetime import timedelta
    hoje = date.today()
    d30 = hoje + timedelta(days=30)
    d60 = hoje + timedelta(days=60)
    d90 = hoje + timedelta(days=90)

    # Pendente de assinatura: não entra nos totais (mostrado separado na UI)
    total_contratado = sum(float(h.valor_total) for h in honorarios if not h.pendente_assinatura)
    total_recebido = sum(h.total_recebido for h in honorarios if not h.pendente_assinatura)
    total_pendente = sum(h.saldo_pendente for h in honorarios if h.status != "pago" and not h.pendente_assinatura)
    total_vencido = sum(
        h.saldo_pendente
        for h in honorarios
        if h.status in ("pendente", "parcial")
        and h.data_vencimento
        and h.data_vencimento < hoje
    )

    # A vencer por faixa (vencimento futuro)
    a_vencer_30 = sum(
        h.saldo_pendente
        for h in honorarios
        if h.status in ("pendente", "parcial")
        and h.data_vencimento
        and hoje <= h.data_vencimento <= d30
    )
    a_vencer_60 = sum(
        h.saldo_pendente
        for h in honorarios
        if h.status in ("pendente", "parcial")
        and h.data_vencimento
        and d30 < h.data_vencimento <= d60
    )
    a_vencer_90 = sum(
        h.saldo_pendente
        for h in honorarios
        if h.status in ("pendente", "parcial")
        and h.data_vencimento
        and d60 < h.data_vencimento <= d90
    )

    # Por cliente
    por_cliente_map: dict[uuid.UUID, dict] = defaultdict(lambda: {
        "total_contratado": 0.0, "total_recebido": 0.0
    })
    for h in honorarios:
        if h.pendente_assinatura:
            continue
        por_cliente_map[h.cliente_id]["total_contratado"] += float(h.valor_total)
        por_cliente_map[h.cliente_id]["total_recebido"] += h.total_recebido

    clientes_map = {
        c.id: c.nome
        for c in db.query(Cliente).filter(
            Cliente.id.in_(list(por_cliente_map.keys()))
        ).all()
    }

    por_cliente = [
        ResumoCliente(
            cliente_id=cid,
            cliente_nome=clientes_map.get(cid, "—"),
            total_contratado=vals["total_contratado"],
            total_recebido=vals["total_recebido"],
            saldo_pendente=vals["total_contratado"] - vals["total_recebido"],
        )
        for cid, vals in sorted(
            por_cliente_map.items(),
            key=lambda x: x[1]["total_contratado"],
            reverse=True,
        )
    ]

    # Por mês (últimos 12 meses de recebimentos)
    por_mes_map: dict[tuple[int, int], float] = defaultdict(float)
    for h in honorarios:
        for rec in h.recebimentos:
            key = (rec.data_recebimento.year, rec.data_recebimento.month)
            por_mes_map[key] += float(rec.valor)

    por_mes = [
        ResumoMensal(ano=ano, mes=mes, total_recebido=total)
        for (ano, mes), total in sorted(por_mes_map.items())
    ][-12:]  # últimos 12 meses

    # Reembolsos
    from app.models.reembolso import Reembolso
    reembolsos = db.query(Reembolso).all()
    total_reembolsos_pendentes = sum(
        float(r.total) for r in reembolsos
        if r.status in ("rascunho", "aguardando_pagamento", "enviado")
    )
    total_reembolsos_pagos = sum(
        float(r.total) for r in reembolsos if r.status == "pago"
    )

    # Projeção de êxito: sum(valor_causa × percentual_exito/100) para honorários tipo "exito"
    projecao_exito = sum(
        float(h.valor_causa) * (float(h.percentual_exito) / 100)
        for h in honorarios
        if h.tipo == "exito"
        and h.valor_causa is not None
        and h.percentual_exito is not None
        and h.status not in ("cancelado", "pago")
    )

    return ResumoFinanceiro(
        total_contratado=total_contratado,
        total_recebido=total_recebido,
        total_pendente=total_pendente,
        total_vencido=total_vencido,
        total_reembolsos_pendentes=total_reembolsos_pendentes,
        total_reembolsos_pagos=total_reembolsos_pagos,
        projecao_exito=projecao_exito,
        a_vencer_30=a_vencer_30,
        a_vencer_60=a_vencer_60,
        a_vencer_90=a_vencer_90,
        por_cliente=por_cliente,
        por_mes=por_mes,
    )
