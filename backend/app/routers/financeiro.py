import uuid
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.cliente import Cliente
from app.models.financeiro import Honorario, Parcela, Recebimento
from app.schemas.financeiro import (
    HonorarioCreate, HonorarioOut, HonorarioUpdate,
    ParcelaInput, ParcelaOut, ParcelaPagar, ParcelaUpdate,
    RecebimentoCreate, RecebimentoOut,
    ResumoCliente, ResumoFinanceiro, ResumoMensal,
)

# Auth obrigatória em todo o módulo financeiro (antes os endpoints estavam abertos).
router = APIRouter(prefix="/financeiro", tags=["financeiro"],
                   dependencies=[Depends(get_current_user)])


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
    parcelas_in = data.parcelas or []
    payload = data.model_dump(exclude={"parcelas"})
    if parcelas_in:
        # Com cronograma: valor_total = soma das parcelas; vencimento simples = 1ª parcela.
        payload["valor_total"] = round(sum(float(p.valor) for p in parcelas_in), 2)
        payload["data_vencimento"] = min(p.data_vencimento for p in parcelas_in)
    h = Honorario(**payload)
    db.add(h)
    db.flush()
    for p in parcelas_in:
        db.add(Parcela(
            honorario_id=h.id, numero=p.numero, valor=p.valor,
            data_vencimento=p.data_vencimento, observacao=p.observacao,
        ))
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


# ── Parcelas ──────────────────────────────────────────────────────────────────

def _recalc_status_honorario(h: Honorario) -> None:
    """Deriva o status do recebível dos recebimentos (pagar parcela cria recebimento)."""
    total_rec = sum(float(r.valor) for r in h.recebimentos)
    if total_rec <= 0:
        h.status = "pendente"
    elif total_rec < float(h.valor_total):
        h.status = "parcial"
    else:
        h.status = "pago"


def _sync_valor_total(h: Honorario) -> None:
    """Quando há cronograma, o valor_total do recebível acompanha a soma das parcelas."""
    if h.parcelas:
        h.valor_total = round(sum(float(p.valor) for p in h.parcelas), 2)


@router.post("/honorarios/{honorario_id}/parcelas/", response_model=ParcelaOut,
             status_code=status.HTTP_201_CREATED)
def adicionar_parcela(honorario_id: uuid.UUID, data: ParcelaInput, db: Session = Depends(get_db)):
    h = db.query(Honorario).filter(Honorario.id == honorario_id).first()
    if not h:
        raise HTTPException(status_code=404, detail="Honorário não encontrado")
    p = Parcela(honorario_id=honorario_id, numero=data.numero, valor=data.valor,
                data_vencimento=data.data_vencimento, observacao=data.observacao)
    db.add(p)
    db.flush()
    db.refresh(h)
    _sync_valor_total(h)
    db.commit()
    db.refresh(p)
    return p


@router.patch("/parcelas/{parcela_id}", response_model=ParcelaOut)
def editar_parcela(parcela_id: uuid.UUID, data: ParcelaUpdate, db: Session = Depends(get_db)):
    p = db.query(Parcela).filter(Parcela.id == parcela_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Parcela não encontrada")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    db.flush()
    h = db.query(Honorario).filter(Honorario.id == p.honorario_id).first()
    if h:
        db.refresh(h)
        _sync_valor_total(h)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/parcelas/{parcela_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover_parcela(parcela_id: uuid.UUID, db: Session = Depends(get_db)):
    p = db.query(Parcela).filter(Parcela.id == parcela_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Parcela não encontrada")
    hid = p.honorario_id
    # solta recebimentos vinculados (não apaga o pagamento; só desvincula da parcela)
    for rec in db.query(Recebimento).filter(Recebimento.parcela_id == p.id).all():
        rec.parcela_id = None
    db.delete(p)
    db.flush()
    h = db.query(Honorario).filter(Honorario.id == hid).first()
    if h:
        db.refresh(h)
        _sync_valor_total(h)
    db.commit()


@router.post("/parcelas/{parcela_id}/pagar", response_model=ParcelaOut)
def pagar_parcela(parcela_id: uuid.UUID, data: ParcelaPagar, db: Session = Depends(get_db)):
    """Marca a parcela como paga: cria um Recebimento vinculado (a NF é emitida por recebimento)."""
    p = db.query(Parcela).filter(Parcela.id == parcela_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Parcela não encontrada")
    if p.status == "pago":
        raise HTTPException(status_code=400, detail="Parcela já está paga")
    valor = float(data.valor) if data.valor is not None else float(p.valor)
    rec = Recebimento(
        honorario_id=p.honorario_id, parcela_id=p.id, valor=valor,
        data_recebimento=data.data_recebimento or date.today(),
        forma_pagamento=data.forma_pagamento, observacao=data.observacao,
    )
    db.add(rec)
    p.status = "pago"
    p.data_pagamento = rec.data_recebimento
    db.flush()
    h = db.query(Honorario).filter(Honorario.id == p.honorario_id).first()
    if h:
        db.refresh(h)
        _recalc_status_honorario(h)
    db.commit()
    db.refresh(p)
    return p


@router.post("/parcelas/{parcela_id}/reabrir", response_model=ParcelaOut)
def reabrir_parcela(parcela_id: uuid.UUID, db: Session = Depends(get_db)):
    """Desfaz o pagamento: remove o(s) recebimento(s) gerados por esta parcela."""
    p = db.query(Parcela).filter(Parcela.id == parcela_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Parcela não encontrada")
    for rec in db.query(Recebimento).filter(Recebimento.parcela_id == p.id).all():
        db.delete(rec)
    p.status = "pendente"
    p.data_pagamento = None
    db.flush()
    h = db.query(Honorario).filter(Honorario.id == p.honorario_id).first()
    if h:
        db.refresh(h)
        _recalc_status_honorario(h)
    db.commit()
    db.refresh(p)
    return p


# ── Cobrança (envio manual) ───────────────────────────────────────────────────

@router.post("/honorarios/{honorario_id}/enviar-cobranca")
def enviar_cobranca_manual(honorario_id: uuid.UUID, db: Session = Depends(get_db)):
    """Envia agora o e-mail de cobrança (com PDF) das parcelas vencidas deste recebível.
    Ignora o opt-in e o dedup diário — é o botão 'enviar cobrança' da tela."""
    from app.services.cobranca_lembretes import enviar_cobrancas
    resultado = enviar_cobrancas(db, forcar=True, honorario_id=honorario_id)
    if resultado["enviados"] == 0 and resultado["erros"]:
        raise HTTPException(status_code=502, detail="; ".join(resultado["erros"])[:300])
    if resultado["enviados"] == 0 and resultado["pulados"]:
        raise HTTPException(status_code=400, detail="Sem e-mail de destino (defina o e-mail do cliente ou o e-mail de cobrança).")
    if resultado["enviados"] == 0:
        raise HTTPException(status_code=400, detail="Nenhuma parcela pendente para cobrar (todas pagas?).")
    return resultado


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


@router.get("/fluxo-caixa/")
def fluxo_caixa(db: Session = Depends(get_db)):
    """Entradas reais por mês (caixa) + crédito a receber (futuro).

    Fonte da verdade da entrada = RECEBIMENTO (PIX/caixa). A NF é o documento
    fiscal: quando conciliada a um recebimento (nf.recebimento_id), aparece como
    selo 'NF ✓' na MESMA linha — nunca como linha nova (evita dupla contagem).
    NF paga SEM recebimento conciliado = linha própria 'só NF (a conciliar)'.
    """
    from app.models.nota_fiscal import NotaFiscal
    cli_nome = {c.id: c.nome for c in db.query(Cliente.id, Cliente.nome).all()}

    # Mapa recebimento_id → NF conciliada (selo na linha de caixa)
    nfs_conciliadas = (db.query(NotaFiscal)
                       .filter(NotaFiscal.recebimento_id.isnot(None)).all())
    rec_to_nf = {nf.recebimento_id: nf for nf in nfs_conciliadas}

    meses: dict[str, dict] = defaultdict(lambda: {"entradas": [], "total": 0.0})

    honorarios = db.query(Honorario).filter(Honorario.status != "cancelado").all()
    for h in honorarios:
        for rec in h.recebimentos:
            comp = rec.data_recebimento.strftime("%Y-%m")
            nf_sel = rec_to_nf.get(rec.id)
            meses[comp]["entradas"].append({
                "data": rec.data_recebimento.isoformat(),
                "descricao": h.descricao,
                "cliente": cli_nome.get(h.cliente_id, "—"),
                "valor": float(rec.valor),
                "forma": rec.forma_pagamento,
                "origem": "recebimento",
                # Selo de conciliação fiscal
                "nf_conciliada": (f"#{nf_sel.numero_nfse}" if nf_sel and nf_sel.numero_nfse else None),
                "nf_tomador": (nf_sel.tomador_nome if nf_sel else None),
                "nf_id": (str(nf_sel.id) if nf_sel else None),
            })
            meses[comp]["total"] += float(rec.valor)

    # NFs pagas NÃO conciliadas a um recebimento = linha própria "só NF (a conciliar)"
    nfs_pagas = (db.query(NotaFiscal)
                 .filter(NotaFiscal.pago.is_(True),
                         NotaFiscal.status == "emitida",
                         NotaFiscal.recebimento_id.is_(None))
                 .all())
    for nf in nfs_pagas:
        d = nf.data_pagamento or nf.data_emissao
        if not d:
            continue
        comp = d.strftime("%Y-%m")
        meses[comp]["entradas"].append({
            "data": d.isoformat(),
            "descricao": f"NFS-e {nf.numero_nfse or ''} — {(nf.descricao_servico or '')[:60]}",
            "cliente": nf.tomador_nome,
            "valor": float(nf.valor_servicos),
            "forma": "nf",
            "origem": "nf_so",
            "nf_id": str(nf.id),
        })
        meses[comp]["total"] += float(nf.valor_servicos)

    # ── SAÍDAS (dinheiro que saiu do caixa) = despesas reais do escritório ──────
    # Inclui adiantamentos de reembolso (despesas ligadas a um reembolso), pois o
    # dinheiro deixou a conta — assim a soma do caixa bate com o extrato do banco.
    from app.models.backoffice import FiscalDespesa
    saidas_por_mes: dict[str, dict] = defaultdict(lambda: {"itens": [], "total": 0.0})
    for d in db.query(FiscalDespesa).all():
        dt = d.data
        comp = dt.strftime("%Y-%m") if dt else (d.mes or "")
        if not comp:
            continue
        eh_reemb = bool(d.reembolso_ids)
        saidas_por_mes[comp]["itens"].append({
            "data": dt.isoformat() if dt else f"{comp}-01",
            "descricao": d.descricao or d.fornecedor,
            "fornecedor": d.fornecedor,
            "categoria": d.categoria,
            "valor": float(d.valor),
            "eh_reembolso": eh_reemb,
        })
        saidas_por_mes[comp]["total"] += float(d.valor)

    todos_meses = sorted(set(meses) | set(saidas_por_mes), reverse=True)
    meses_list = []
    for k in todos_meses:
        ent = meses.get(k, {"entradas": [], "total": 0.0})
        sai = saidas_por_mes.get(k, {"itens": [], "total": 0.0})
        meses_list.append({
            "competencia": k,
            "total": round(ent["total"], 2),            # total de entradas
            "total_saidas": round(sai["total"], 2),
            "saldo": round(ent["total"] - sai["total"], 2),
            "entradas": sorted(ent["entradas"], key=lambda x: x["data"], reverse=True),
            "saidas": sorted(sai["itens"], key=lambda x: x["data"], reverse=True),
        })

    # Crédito a receber (futuro)
    cred_itens = []
    cred_hon = 0.0
    for h in honorarios:
        if h.status in ("pendente", "parcial") and h.saldo_pendente > 0 and not h.pendente_assinatura:
            cred_hon += h.saldo_pendente
            cred_itens.append({
                "tipo": "honorario", "descricao": h.descricao,
                "cliente": cli_nome.get(h.cliente_id, "—"),
                "valor": round(h.saldo_pendente, 2),
                "vencimento": h.data_vencimento.isoformat() if h.data_vencimento else None,
            })
    nfs_nao_pagas = (db.query(NotaFiscal)
                     .filter(NotaFiscal.pago.is_(False),
                             NotaFiscal.status == "emitida",
                             NotaFiscal.honorario_id.is_(None),
                             NotaFiscal.honorario_compensacao_id.is_(None))
                     .all())
    cred_nfs = 0.0
    for nf in nfs_nao_pagas:
        cred_nfs += float(nf.valor_servicos)
        cred_itens.append({
            "tipo": "nf", "descricao": f"NFS-e {nf.numero_nfse or ''} — {nf.tomador_nome}",
            "cliente": nf.tomador_nome, "valor": float(nf.valor_servicos),
            "vencimento": None, "nf_id": str(nf.id),
        })

    return {
        "meses": meses_list,
        "credito_a_receber": {
            "total": round(cred_hon + cred_nfs, 2),
            "honorarios_pendentes": round(cred_hon, 2),
            "nfs_nao_pagas": round(cred_nfs, 2),
            "itens": sorted(cred_itens, key=lambda x: x["valor"], reverse=True),
        },
    }
