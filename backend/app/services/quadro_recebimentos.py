"""Quadro de recebimentos por cliente × mês (programados à frente ou realizados para trás)
e o PDF de extrato correspondente.

- sentido "futuro": parcelas em aberto (e recebíveis sem cronograma, pelo vencimento) nos
  próximos N meses a partir de hoje; o que já venceu e não foi pago vai na coluna "Em atraso".
  Recebíveis aguardando assinatura ficam de fora (ainda não são receita certa).
- sentido "passado": recebimentos efetivamente lançados nos últimos N meses (mês atual incluso).
"""
from __future__ import annotations

import io
import os
from collections import defaultdict
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.financeiro import Honorario

MESES_PT = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "logo.png")


def _add_mes(ano: int, mes: int, n: int) -> tuple[int, int]:
    i = ano * 12 + (mes - 1) + n
    return i // 12, i % 12 + 1


def montar_quadro(
    db: Session, sentido: str, meses: int, hoje: date | None = None, cliente_id=None,
) -> dict:
    hoje = hoje or date.today()
    if sentido == "futuro":
        colunas = [_add_mes(hoje.year, hoje.month, i) for i in range(meses)]
    else:
        colunas = [_add_mes(hoje.year, hoje.month, -(meses - 1) + i) for i in range(meses)]
    idx = {c: i for i, c in enumerate(colunas)}

    q = db.query(Honorario).filter(Honorario.status != "cancelado")
    if cliente_id:
        q = q.filter(Honorario.cliente_id == cliente_id)
    honorarios = q.all()

    por_cliente: dict = defaultdict(lambda: {"valores": [0.0] * meses, "atrasado": 0.0, "itens": []})
    alem = 0.0  # programado depois do horizonte (só informativo)

    def _add(cid, data, valor, descricao, detalhe):
        nonlocal alem
        reg = por_cliente[cid]
        atrasado = False
        if sentido == "futuro" and data < hoje:
            reg["atrasado"] += valor
            atrasado = True
        else:
            i = idx.get((data.year, data.month))
            if i is None:
                if sentido == "futuro" and data > hoje:
                    alem += valor
                return
            reg["valores"][i] += valor
        reg["itens"].append({
            "data": data, "descricao": descricao, "detalhe": detalhe,
            "valor": round(valor, 2), "atrasado": atrasado,
        })

    for h in honorarios:
        if sentido == "futuro":
            if h.pendente_assinatura or h.status not in ("pendente", "parcial"):
                continue
            if h.parcelas:
                total = len(h.parcelas)
                for p in h.parcelas:
                    if p.status == "pendente":
                        _add(h.cliente_id, p.data_vencimento, float(p.valor), h.descricao, f"parcela {p.numero}/{total}")
            elif h.data_vencimento and h.saldo_pendente > 0:
                _add(h.cliente_id, h.data_vencimento, float(h.saldo_pendente), h.descricao, "")
        else:
            numeros = {p.id: (p.numero, len(h.parcelas)) for p in h.parcelas}
            for rec in h.recebimentos:
                det = ""
                if rec.parcela_id in numeros:
                    n, t = numeros[rec.parcela_id]
                    det = f"parcela {n}/{t}"
                _add(h.cliente_id, rec.data_recebimento, float(rec.valor), h.descricao, det)

    nomes = {
        c.id: c.nome
        for c in db.query(Cliente).filter(Cliente.id.in_(list(por_cliente.keys()) or [None])).all()
    }
    clientes = []
    for cid, reg in por_cliente.items():
        reg["itens"].sort(key=lambda it: it["data"])
        clientes.append({
            "cliente_id": cid,
            "cliente_nome": nomes.get(cid, "—"),
            "atrasado": round(reg["atrasado"], 2),
            "valores": [round(v, 2) for v in reg["valores"]],
            "total": round(reg["atrasado"] + sum(reg["valores"]), 2),
            "itens": reg["itens"],
        })
    clientes.sort(key=lambda c: (-c["total"], c["cliente_nome"].lower()))

    cons_vals = [round(sum(c["valores"][i] for c in clientes), 2) for i in range(meses)]
    cons_atr = round(sum(c["atrasado"] for c in clientes), 2)
    return {
        "sentido": sentido,
        "meses": meses,
        "colunas": [{"ano": a, "mes": m} for a, m in colunas],
        "consolidado": {
            "atrasado": cons_atr, "valores": cons_vals,
            "total": round(cons_atr + sum(cons_vals), 2),
        },
        "alem_do_periodo": round(alem, 2),
        "clientes": clientes,
    }


# ── PDF ────────────────────────────────────────────────────────────────────

def _brl(v: float) -> str:
    return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _num(v: float) -> str:
    return "—" if not v else f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _dt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def gerar_pdf_quadro(quadro: dict, cliente_filtro: str | None = None) -> bytes:
    futuro = quadro["sentido"] == "futuro"
    meses = quadro["meses"]
    colunas = quadro["colunas"]
    clientes = quadro["clientes"]
    hoje = date.today()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.4 * cm, bottomMargin=1.4 * cm,
        title="Extrato de recebimentos",
    )
    escuro = colors.HexColor("#374151")
    verde = colors.HexColor("#2f6f5e")
    venc_fg = colors.HexColor("#a2585e")
    venc_bg = colors.HexColor("#fbeeee")
    borda = colors.HexColor("#e5e7eb")
    titulo = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=14, leading=18, alignment=TA_CENTER, textColor=escuro, spaceAfter=2)
    sub = ParagraphStyle("s", fontName="Helvetica", fontSize=9, leading=12, alignment=TA_CENTER, textColor=colors.HexColor("#6b7280"), spaceAfter=8)
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10.5, textColor=verde, spaceBefore=10, spaceAfter=4)
    cel = ParagraphStyle("c", fontName="Helvetica", fontSize=7.5, leading=9)
    cel_b = ParagraphStyle("cb", parent=cel, fontName="Helvetica-Bold")

    el = []
    if os.path.exists(_LOGO_PATH):
        try:
            logo = Image(_LOGO_PATH, width=38 * mm, height=13 * mm, kind="proportional")
            logo.hAlign = "CENTER"
            el.append(logo)
            el.append(Spacer(1, 0.25 * cm))
        except Exception:
            pass
    c0, c1 = colunas[0], colunas[-1]
    periodo = f"{MESES_PT[c0['mes'] - 1]}/{c0['ano']} a {MESES_PT[c1['mes'] - 1]}/{c1['ano']}"
    rot = (f"Recebimentos programados — próximos {meses} meses" if futuro
           else f"Extrato de recebimentos — últimos {meses} meses")
    el.append(Paragraph(rot, titulo))
    escopo = f" · Cliente: {cliente_filtro}" if cliente_filtro else ""
    el.append(Paragraph(f"Período: {periodo}{escopo} · Emitido em {_dt(hoje)}", sub))

    cons = quadro["consolidado"]
    resumo = [["Recebido no período" if not futuro else "Programado no período", _brl(sum(cons["valores"]))]]
    if futuro:
        resumo.append(["Em atraso (vencido e não pago)", _brl(cons["atrasado"])])
        resumo.append(["Total geral (programado + em atraso)", _brl(cons["total"])])
        if quadro["alem_do_periodo"]:
            resumo.append(["Programado após o período", _brl(quadro["alem_do_periodo"])])
    rt = Table(resumo, colWidths=[7 * cm, 4 * cm], hAlign="LEFT")
    rt.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9), ("FONT", (1, 0), (1, -1), "Helvetica-Bold", 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("GRID", (0, 0), (-1, -1), 0.4, borda),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    el.append(rt)

    # Matriz cliente × mês
    el.append(Paragraph("Visão por cliente e mês", h2))
    cab = ["Cliente"] + (["Em atraso"] if futuro else []) + [f"{MESES_PT[c['mes'] - 1]}/{str(c['ano'])[2:]}" for c in colunas] + ["Total"]
    linhas = [cab]
    for c in clientes:
        linhas.append([Paragraph(c["cliente_nome"], cel)] + ([_num(c["atrasado"])] if futuro else [])
                      + [_num(v) for v in c["valores"]] + [_num(c["total"])])
    linhas.append([Paragraph("CONSOLIDADO", cel_b)] + ([_num(cons["atrasado"])] if futuro else [])
                  + [_num(v) for v in cons["valores"]] + [_num(cons["total"])])
    util = landscape(A4)[0] - 3 * cm
    n_extra = 3 if futuro else 2
    larg_nome = 5.2 * cm
    larg_num = (util - larg_nome - (0.4 * cm)) / (meses + n_extra - 1)
    larg = [larg_nome] + [larg_num] * (meses + n_extra - 1)
    mt = Table(linhas, colWidths=larg, repeatRows=1)
    est = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5),
        ("FONT", (1, 1), (-1, -1), "Helvetica", 7.5),
        ("BACKGROUND", (0, 0), (-1, 0), escuro), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, borda),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#fafafa")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ecf3f1")),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 7.5),
        ("FONT", (-1, 1), (-1, -1), "Helvetica-Bold", 7.5),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if futuro:
        est += [("TEXTCOLOR", (1, 1), (1, -1), venc_fg)]
    mt.setStyle(TableStyle(est))
    el.append(mt)

    # Extrato detalhado por cliente
    el.append(Paragraph("Extrato detalhado", h2))
    for c in clientes:
        bloco = [["Data", "Descrição", "Detalhe", "Valor"]]
        for it in c["itens"]:
            situ = " (em atraso)" if it["atrasado"] else ""
            bloco.append([_dt(it["data"]), Paragraph(it["descricao"], cel), (it["detalhe"] + situ).strip(), _brl(it["valor"])])
        bloco.append(["", "", "Subtotal", _brl(c["total"])])
        bt = Table(bloco, colWidths=[2.4 * cm, 13 * cm, 4.2 * cm, 3.6 * cm], repeatRows=1, hAlign="LEFT")
        be = [
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7.5), ("FONT", (0, 1), (-1, -1), "Helvetica", 7.5),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6b7280")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.4, borda),
            ("FONT", (2, -1), (-1, -1), "Helvetica-Bold", 7.5),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ]
        for i, it in enumerate(c["itens"], start=1):
            if it["atrasado"]:
                be.append(("BACKGROUND", (0, i), (-1, i), venc_bg))
        bt.setStyle(TableStyle(be))
        el.append(Paragraph(f"<b>{c['cliente_nome']}</b>", ParagraphStyle("cn", fontName="Helvetica", fontSize=9, spaceBefore=6, spaceAfter=2)))
        el.append(bt)
        el.append(Spacer(1, 0.1 * cm))
    if not clientes:
        el.append(Paragraph("Nenhum lançamento no período.", cel))

    def _rodape(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#9ca3af"))
        canvas.drawRightString(landscape(A4)[0] - 1.5 * cm, 0.8 * cm, f"Página {d.page}")
        canvas.restoreState()

    doc.build(el, onFirstPage=_rodape, onLaterPages=_rodape)
    return buf.getvalue()
