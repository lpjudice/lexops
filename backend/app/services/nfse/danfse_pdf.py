"""Gera um PDF da DANFSe a partir do XML da NFS-e Nacional.

O governo não expõe o PDF oficial via API (endpoint /danfse retorna 501). Este
gerador monta um Documento Auxiliar (DANFSe) próprio com todos os dados legais
da nota + chave de acesso + link de verificação na consulta pública.
"""
from __future__ import annotations

import io
import re
from datetime import datetime

from lxml import etree
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
)

import os
_LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "logo.png")

NS = {"n": "http://www.sped.fazenda.gov.br/nfse"}


def _txt(root, *paths) -> str:
    for p in paths:
        els = root.xpath(p, namespaces=NS)
        if els:
            v = els[0]
            return (v.text if hasattr(v, "text") else str(v)) or ""
    return ""


def _fmt_doc(doc: str) -> str:
    d = re.sub(r"\D", "", doc or "")
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return doc or ""


def _fmt_moeda(v: str) -> str:
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return v or "—"


def _fmt_dt(v: str) -> str:
    if not v:
        return "—"
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return v


def gerar_danfse_pdf(xml_nfse: str, chave_acesso: str, prefixo_numero: str = "",
                     carga_media_pct: float = 16.33) -> bytes:
    """Recebe o XML da NFS-e e a chave; devolve os bytes do PDF."""
    root = etree.fromstring(xml_nfse.encode() if isinstance(xml_nfse, str) else xml_nfse)

    # Dados principais
    numero = _txt(root, "//n:nNFSe", "//nNFSe")
    # Prefixo com zero-pad (ex.: PJ150 + 17 → PJ150017)
    numero_exib = (f"{prefixo_numero}{str(numero).zfill(3)}"
                   if prefixo_numero and numero else (numero or ""))
    # Número da DPS (sequência interna do emitente, diferente do nº da NFS-e)
    numero_dps = _txt(root, "//n:nDPS", "//nDPS")
    serie_dps = _txt(root, "//n:serie", "//serie")
    dh_proc = _txt(root, "//n:dhProc", "//dhProc")
    cod_verif = chave_acesso
    # Emitente
    emit_cnpj = _txt(root, "//n:emit/n:CNPJ", "//emit/CNPJ")
    emit_nome = _txt(root, "//n:emit/n:xNome", "//emit/xNome")
    emit_lgr = _txt(root, "//n:emit//n:xLgr", "//emit//xLgr")
    emit_nro = _txt(root, "//n:emit//n:nro", "//emit//nro")
    emit_bairro = _txt(root, "//n:emit//n:xBairro", "//emit//xBairro")
    emit_uf = _txt(root, "//n:emit//n:UF", "//emit//UF")
    emit_cep = _txt(root, "//n:emit//n:CEP", "//emit//CEP")
    loc_emi = _txt(root, "//n:xLocEmi", "//xLocEmi")
    # Tomador (vem da DPS embutida)
    toma_cnpj = _txt(root, "//n:toma/n:CNPJ", "//toma/CNPJ")
    toma_cpf = _txt(root, "//n:toma/n:CPF", "//toma/CPF")
    toma_doc = toma_cnpj or toma_cpf
    toma_nome = _txt(root, "//n:toma/n:xNome", "//toma/xNome")
    toma_email = _txt(root, "//n:toma/n:email", "//toma/email")
    # Serviço
    desc_serv = _txt(root, "//n:cServ/n:xDescServ", "//cServ/xDescServ")
    trib_nac = _txt(root, "//n:xTribNac", "//xTribNac") or _txt(root, "//n:cServ/n:cTribNac", "//cServ/cTribNac")
    # Valores
    v_serv = _txt(root, "//n:vServPrest/n:vServ", "//vServPrest/vServ")
    v_liq = _txt(root, "//n:vLiq", "//vLiq") or v_serv
    v_iss = _txt(root, "//n:vISSQN", "//vISSQN")
    p_aliq = _txt(root, "//n:pAliqAplic", "//pAliqAplic")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
        title=f"DANFSe {numero}",
    )

    teal = colors.HexColor("#00B090")
    dark = colors.HexColor("#1f2937")
    gray = colors.HexColor("#6b7280")

    st_titulo = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=14, textColor=dark, leading=16)
    st_sub = ParagraphStyle("s", fontName="Helvetica", fontSize=8, textColor=gray, leading=10)
    st_label = ParagraphStyle("l", fontName="Helvetica-Bold", fontSize=7, textColor=teal, leading=9)
    st_val = ParagraphStyle("v", fontName="Helvetica", fontSize=9, textColor=dark, leading=12)
    st_desc = ParagraphStyle("d", fontName="Helvetica", fontSize=9, textColor=dark, leading=13)
    st_chave = ParagraphStyle("c", fontName="Helvetica", fontSize=8, textColor=dark, leading=11)

    elems = []

    # Cabeçalho com logo (se existir)
    titulo_cell = [
        Paragraph("DANFSe — Documento Auxiliar da NFS-e", st_titulo),
        Paragraph("Nota Fiscal de Serviço eletrônica — Padrão Nacional", st_sub),
    ]
    if os.path.exists(_LOGO_PATH):
        try:
            logo = Image(_LOGO_PATH, width=42 * mm, height=21 * mm, kind="proportional")
            cab_logo = Table([[logo, titulo_cell]], colWidths=[48 * mm, 132 * mm])
            cab_logo.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]))
            elems.append(cab_logo)
        except Exception:
            elems.extend(titulo_cell)
    else:
        elems.extend(titulo_cell)
    elems.append(Spacer(1, 6 * mm))

    # Faixa: número NFS-e / número DPS / emissão / município
    dps_exib = numero_dps or "—"
    if numero_dps and serie_dps:
        dps_exib = f"{numero_dps} (série {serie_dps})"
    cab = Table([[
        Paragraph("NÚMERO DA NFS-e", st_label),
        Paragraph("NÚMERO DA DPS", st_label),
        Paragraph("COMPETÊNCIA / EMISSÃO", st_label),
        Paragraph("MUNICÍPIO EMISSOR", st_label),
    ], [
        Paragraph(f"<b>{numero_exib or '—'}</b>", st_val),
        Paragraph(dps_exib, st_val),
        Paragraph(_fmt_dt(dh_proc), st_val),
        Paragraph(loc_emi or "—", st_val),
    ]], colWidths=[42 * mm, 38 * mm, 50 * mm, 50 * mm])
    cab.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, teal),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecfdf5")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elems.append(cab)
    elems.append(Spacer(1, 4 * mm))

    def bloco(titulo, linhas):
        dados = [[Paragraph(titulo, st_label)]]
        for lab, val in linhas:
            dados.append([Paragraph(f"<b>{lab}:</b> {val}", st_val)])
        t = Table(dados, colWidths=[180 * mm])
        t.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f3f4f6")),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        return t

    endereco_emit = ", ".join([x for x in [emit_lgr, emit_nro, emit_bairro,
                                           f"{loc_emi}/{emit_uf}" if emit_uf else loc_emi,
                                           f"CEP {emit_cep}" if emit_cep else ""] if x])
    elems.append(bloco("PRESTADOR DO SERVIÇO", [
        ("Nome", emit_nome), ("CNPJ", _fmt_doc(emit_cnpj)), ("Endereço", endereco_emit),
    ]))
    elems.append(Spacer(1, 3 * mm))
    elems.append(bloco("TOMADOR DO SERVIÇO", [
        ("Nome", toma_nome), ("CPF/CNPJ", _fmt_doc(toma_doc)),
        ("E-mail", toma_email or "—"),
    ]))
    elems.append(Spacer(1, 3 * mm))

    # Serviço
    serv_t = Table([
        [Paragraph("DESCRIÇÃO DO SERVIÇO", st_label)],
        [Paragraph(desc_serv or "—", st_desc)],
        [Paragraph(f"<b>Código de tributação nacional:</b> {trib_nac}", st_val)],
    ], colWidths=[180 * mm])
    serv_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f3f4f6")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elems.append(serv_t)
    elems.append(Spacer(1, 3 * mm))

    # Valores
    val_t = Table([[
        Paragraph("VALOR DO SERVIÇO", st_label),
        Paragraph("ALÍQUOTA ISS", st_label),
        Paragraph("VALOR ISS", st_label),
        Paragraph("VALOR LÍQUIDO", st_label),
    ], [
        Paragraph(_fmt_moeda(v_serv), st_val),
        Paragraph(f"{p_aliq}%" if p_aliq else "—", st_val),
        Paragraph(_fmt_moeda(v_iss) if v_iss else "—", st_val),
        Paragraph(f"<b>{_fmt_moeda(v_liq)}</b>", st_val),
    ]], colWidths=[45 * mm, 45 * mm, 45 * mm, 45 * mm])
    val_t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, teal),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ecfdf5")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    elems.append(val_t)
    elems.append(Spacer(1, 3 * mm))

    # Tributos totais aproximados (Lei 12.741/2012 — Lei da Transparência)
    try:
        base_trib = float(v_serv or v_liq or 0)
    except Exception:
        base_trib = 0.0
    val_trib = base_trib * float(carga_media_pct) / 100
    st_trib = ParagraphStyle("tr", fontName="Helvetica", fontSize=8, textColor=gray, leading=11)
    elems.append(Paragraph(
        f"Tributos totais incidentes (aproximado, Lei 12.741/2012): "
        f"<b>{carga_media_pct:.2f}%</b> = {_fmt_moeda(val_trib)} — fonte IBPT.", st_trib,
    ))
    elems.append(Spacer(1, 4 * mm))

    # Chave de acesso + verificação
    elems.append(Paragraph("CHAVE DE ACESSO", st_label))
    elems.append(Paragraph(" ".join(re.findall(r".{1,4}", cod_verif)), st_chave))
    elems.append(Spacer(1, 2 * mm))
    elems.append(Paragraph(
        f'Consulte a autenticidade em: '
        f'<a href="https://www.nfse.gov.br/consultapublica"><font color="#00B090">'
        f'www.nfse.gov.br/consultapublica</font></a>',
        st_sub,
    ))
    elems.append(Spacer(1, 5 * mm))

    # Bloco de pagamento
    st_paglabel = ParagraphStyle("pl", fontName="Helvetica-Bold", fontSize=9, textColor=teal, leading=12)
    st_pag = ParagraphStyle("pg", fontName="Helvetica", fontSize=9, textColor=dark, leading=13)
    pag = Table([
        [Paragraph("PAGAMENTO", st_paglabel)],
        [Paragraph("<b>PIX</b> (chave CNPJ): 10.901.611/0001-64", st_pag)],
        [Paragraph("<b>TED/Transferência:</b> Banco Inter (077) · Agência 0001 · "
                   "Conta corrente 1812719-3", st_pag)],
        [Paragraph("Favorecido: Pimenta Judice Advogados Associados", st_pag)],
    ], colWidths=[180 * mm])
    pag.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, teal),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#ecfdf5")),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elems.append(pag)

    elems.append(Spacer(1, 4 * mm))
    elems.append(Paragraph(
        "Documento auxiliar gerado pelo LexOps a partir do XML oficial da NFS-e. "
        "Não substitui o documento fiscal; a validade jurídica é confirmada pela "
        "consulta pública no portal nacional.", st_sub,
    ))

    doc.build(elems)
    return buf.getvalue()
