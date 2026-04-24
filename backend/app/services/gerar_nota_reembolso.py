"""
Gerador de PDF da Nota de Reembolso de Despesas.
Layout baseado no modelo Pimenta Judice Advogados Associados.
"""
from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from pathlib import Path

from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_LOGO_PATH = Path(__file__).parent.parent.parent / "logo.png"

# ── Cores ─────────────────────────────────────────────────────────────────────
PRETO = colors.HexColor("#1a1a1a")
CINZA_MEDIO = colors.HexColor("#555555")
CINZA_CLARO = colors.HexColor("#888888")
AMARELO_DESTAQUE = colors.HexColor("#f5c518")
TABELA_HEADER = colors.HexColor("#2c2c2c")
TABELA_LINHA = colors.HexColor("#f0f0f0")

# ── Constantes do escritório (fixas) ──────────────────────────────────────────
ESCRITORIO_NOME = "Pimenta Judice Advogados Associados"
ESCRITORIO_CNPJ = "10.901.611/0001-64"
ESCRITORIO_NOME_COMPLETO = "Pimenta Judice Advogados Associados SC"
BANCO = "Banco Inter SA (077)"
AGENCIA = "0001"
CONTA = "1812719-3"
PHONE = "+1 (310) 383-3828 / +55 (11) 5196-5950"
EMAIL_ESC = "pj@pimentajudice.com.br"
ENDERECOS = "333 S. Grand Av, Los Angeles, California  |  Rua João da Cruz, 25, Vitória/ES  |  Av. Engenheiro L. Carlos Berrini, 105, São Paulo/SP"
ASSINANTE_ADM = "MONIELLY MOREIRA VIEIRA\nAdministrativo"
ADVOGADO = "Lucas Pimenta Judice\nOAB/ES 14.477"

MESES_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


def _fmt_data(d: date) -> str:
    return f"{d.day} de {MESES_PT[d.month]} de {d.year}"


def _fmt_valor(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _estilos():
    base = getSampleStyleSheet()

    def s(name, **kw):
        return ParagraphStyle(name, **kw)

    return {
        "titulo": s("titulo", fontSize=20, fontName="Helvetica-Bold",
                    alignment=TA_CENTER, textColor=PRETO, spaceAfter=2),
        "subtitulo": s("subtitulo", fontSize=20, fontName="Helvetica-Bold",
                       alignment=TA_CENTER, textColor=PRETO, spaceAfter=14),
        "esc_bold": s("esc_bold", fontSize=10, fontName="Helvetica-Bold",
                      textColor=PRETO, spaceAfter=1),
        "esc_normal": s("esc_normal", fontSize=10, fontName="Helvetica",
                        textColor=PRETO, spaceAfter=1),
        "label_right": s("label_right", fontSize=10, fontName="Helvetica-Bold",
                         alignment=TA_RIGHT, textColor=PRETO, spaceAfter=2),
        "body": s("body", fontSize=10, fontName="Helvetica",
                  alignment=TA_JUSTIFY, textColor=PRETO, leading=16, spaceAfter=10),
        "table_header": s("th", fontSize=9, fontName="Helvetica-Bold",
                          alignment=TA_CENTER, textColor=colors.white),
        "table_cell": s("td", fontSize=9, fontName="Helvetica",
                        alignment=TA_LEFT, textColor=PRETO),
        "table_cell_c": s("tdc", fontSize=9, fontName="Helvetica",
                          alignment=TA_CENTER, textColor=PRETO),
        "table_valor": s("tdv", fontSize=9, fontName="Helvetica",
                         alignment=TA_RIGHT, textColor=PRETO),
        "table_total_label": s("ttl", fontSize=10, fontName="Helvetica-Bold",
                               alignment=TA_RIGHT, textColor=PRETO),
        "table_total_valor": s("ttv", fontSize=10, fontName="Helvetica-Bold",
                               alignment=TA_RIGHT, textColor=PRETO),
        "nota": s("nota", fontSize=9, fontName="Helvetica-Oblique",
                  textColor=CINZA_MEDIO, spaceAfter=6),
        "banco_titulo": s("btitulo", fontSize=10, fontName="Helvetica-Bold",
                          alignment=TA_CENTER, textColor=PRETO, spaceAfter=3),
        "banco_linha": s("blinha", fontSize=10, fontName="Helvetica",
                         alignment=TA_CENTER, textColor=PRETO, spaceAfter=2),
        "footer": s("footer", fontSize=8, fontName="Helvetica",
                    textColor=CINZA_CLARO),
        "footer_right": s("footer_r", fontSize=8, fontName="Helvetica",
                          alignment=TA_RIGHT, textColor=CINZA_CLARO),
        "compliance_titulo": s("ct", fontSize=11, fontName="Helvetica-Bold",
                               textColor=PRETO, spaceAfter=10),
        "compliance_body": s("cb", fontSize=10, fontName="Helvetica",
                             alignment=TA_JUSTIFY, textColor=PRETO,
                             leading=16, spaceAfter=10),
        "assinante": s("ass", fontSize=10, fontName="Helvetica",
                       alignment=TA_CENTER, textColor=PRETO, spaceAfter=2),
        "assinante_bold": s("assb", fontSize=10, fontName="Helvetica-Bold",
                            alignment=TA_CENTER, textColor=PRETO, spaceAfter=2),
        "logo_grande": s("logo", fontSize=22, fontName="Helvetica-Bold",
                         textColor=PRETO, spaceAfter=0),
        "logo_sub": s("logosub", fontSize=8, fontName="Helvetica",
                      textColor=CINZA_CLARO, spaceAfter=0,
                      letterSpacing=2),
    }


def _footer_table(st):
    """Rodapé com telefone/email à esq e endereços à dir."""
    esq = Paragraph(f"<b>Phone:</b> {PHONE}<br/><b>Email:</b> {EMAIL_ESC}", st["footer"])
    dir_ = Paragraph(ENDERECOS.replace("|", "<br/>"), st["footer_right"])
    t = Table([[esq, dir_]], colWidths=[9 * cm, 10.5 * cm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _logo_block(st):
    """Bloco do logo (texto estilizado — substitua por Image se tiver o arquivo)."""
    logo = Paragraph("PIMENTA<br/>JUDICE", st["logo_grande"])
    sub = Paragraph("ADVOGADOS ASSOCIADOS", st["logo_sub"])
    t = Table([[logo]], colWidths=[6 * cm])
    t.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (0, 0), 0)]))
    return [logo, sub]


def gerar_pdf(
    cliente_nome: str,
    cliente_cpf_cnpj: str | None,
    titulo: str,
    data_emissao: date,
    data_vencimento: date | None,
    itens: list[dict],   # [{data, descricao, natureza, documento_comprobatorio, valor}]
    total: float,
    drive_folder_link: str | None = None,
) -> bytes:
    """
    Gera o PDF da Nota de Reembolso e retorna os bytes.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2.5 * cm,
        title="Nota de Reembolso de Despesas",
    )

    st = _estilos()
    largura_util = A4[0] - 5 * cm  # 19cm - 5cm margens = 14cm... not quite
    # A4 width = 21cm, margins 2.5+2.5 = 5cm, usable = 16cm
    W = 16 * cm

    story: list = []

    # ── PÁGINA 1 ──────────────────────────────────────────────────────────────

    # Logo + título lado a lado (logo esq, título centro-dir)
    if _LOGO_PATH.exists():
        logo_cell = Image(str(_LOGO_PATH), width=4.5 * cm, height=2 * cm, kind="proportional")
    else:
        logo_p = Paragraph("<b>PIMENTA<br/>JUDICE</b>", ParagraphStyle(
            "lp", fontSize=18, fontName="Helvetica-Bold", textColor=PRETO, leading=20))
        logo_sub_p = Paragraph("ADVOGADOS ASSOCIADOS", ParagraphStyle(
            "lsp", fontSize=7, fontName="Helvetica", textColor=CINZA_CLARO,
            letterSpacing=1.5))
        logo_cell = Table([[logo_p], [logo_sub_p]], colWidths=[5 * cm])

    titulo_p = Paragraph("NOTA DE REEMBOLSO<br/>DE DESPESAS", ParagraphStyle(
        "tp", fontSize=18, fontName="Helvetica-Bold", textColor=PRETO,
        alignment=TA_CENTER, leading=24))

    header_tbl = Table(
        [[logo_cell, titulo_p]],
        colWidths=[5 * cm, W - 5 * cm],
    )
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=CINZA_CLARO))
    story.append(Spacer(1, 14))

    # Bloco escritório (esq) + projeto/data (dir)
    esc_lines = [
        Paragraph(f"<b>{ESCRITORIO_NOME}</b>", st["esc_bold"]),
        Paragraph(f"CNPJ: {ESCRITORIO_CNPJ}", st["esc_normal"]),
        Spacer(1, 8),
        Paragraph(f"<b>Cliente:</b> {cliente_nome}", st["esc_normal"]),
    ]
    if cliente_cpf_cnpj:
        esc_lines.append(Paragraph(f"<b>CPF/CNPJ:</b> {cliente_cpf_cnpj}", st["esc_normal"]))

    proj_lines = [
        Paragraph(f"<b>Projeto / Processo:</b> {titulo}", st["label_right"]),
        Paragraph(f"<b>Data de Emissão da Nota de Reembolso:</b> {_fmt_data(data_emissao)}",
                  st["label_right"]),
    ]

    esc_tbl = Table([[esc_lines, proj_lines]], colWidths=[8 * cm, W - 8 * cm])
    esc_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(esc_tbl)
    story.append(Spacer(1, 20))

    # Parágrafo intro
    story.append(Paragraph(
        "A presente Nota de Reembolso de Despesas tem por objeto a restituição de valores adiantados pelo "
        "Escritório, em nome e no exclusivo interesse do Cliente, no contexto da execução dos serviços "
        "advocatícios contratados, conforme autorizado contratualmente e em estrita observância às normas "
        "legais e fiscais aplicáveis.",
        st["body"]
    ))
    story.append(Spacer(1, 8))

    # Tabela de itens
    tabela_titulo = Paragraph(
        "<b>Discriminação das Despesas Reembolsáveis</b>",
        ParagraphStyle("dt", fontSize=11, fontName="Helvetica-Bold",
                       alignment=TA_CENTER, textColor=PRETO, spaceAfter=6)
    )
    story.append(tabela_titulo)
    story.append(Spacer(1, 4))

    col_widths = [2.2 * cm, 5.2 * cm, 2.8 * cm, 3.6 * cm, 2.2 * cm]

    def th(txt):
        return Paragraph(txt, st["table_header"])

    def td(txt):
        return Paragraph(str(txt), st["table_cell"])

    def tdc(txt):
        return Paragraph(str(txt), st["table_cell_c"])

    def tdv(txt):
        return Paragraph(str(txt), st["table_valor"])

    header_row = [th("Data"), th("Descrição"), th("Natureza"),
                  th("Documento Comprobatório"), th("Valor (R$)")]

    rows = [header_row]
    for it in itens:
        d = it["data"]
        data_str = d.strftime("%d/%m/%Y") if hasattr(d, "strftime") else str(d)
        rows.append([
            tdc(data_str),
            td(it["descricao"]),
            tdc(it["natureza"]),
            tdc(it.get("documento_comprobatorio") or "—"),
            tdv(_fmt_valor(float(it["valor"]))),
        ])

    # Linha de total
    rows.append([
        Paragraph("", st["table_cell"]),
        Paragraph("", st["table_cell"]),
        Paragraph("", st["table_cell"]),
        Paragraph("<b>Total a Reembolsar  &gt;&gt;&gt;&gt;&gt;&gt;</b>", st["table_total_label"]),
        Paragraph(f"<b>{_fmt_valor(total)}</b>", st["table_total_valor"]),
    ])

    tabela = Table(rows, colWidths=col_widths, repeatRows=1)
    n = len(rows)
    tabela.setStyle(TableStyle([
        # Cabeçalho
        ("BACKGROUND", (0, 0), (-1, 0), TABELA_HEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        # Linhas alternadas
        *[("BACKGROUND", (0, i), (-1, i), TABELA_LINHA) for i in range(2, n - 1, 2)],
        # Linha total
        ("BACKGROUND", (0, n - 1), (-1, n - 1), colors.white),
        ("LINEABOVE", (0, n - 1), (-1, n - 1), 1, PRETO),
        # Grid
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.white),
        ("GRID", (0, 1), (-1, n - 2), 0.3, colors.HexColor("#e0e0e0")),
    ]))
    story.append(tabela)
    story.append(Spacer(1, 14))

    # Notas sobre documentos
    if drive_folder_link:
        story.append(Paragraph(
            f'<i>Todos os documentos comprobatórios encontram-se anexos à presente nota e disponíveis em: '
            f'<link href="{drive_folder_link}" color="#00b090">Google Drive</link></i>',
            st["nota"]
        ))
    else:
        story.append(Paragraph(
            "<i>Todos os documentos comprobatórios encontram-se anexos à presente nota.</i>",
            st["nota"]
        ))

    # Parágrafo de pagamento
    venc_str = f" até {_fmt_data(data_vencimento)}" if data_vencimento else ""
    story.append(Paragraph(
        f"As despesas acima não possuem natureza remuneratória, não integram honorários advocatícios e não "
        f"representam receita do Escritório, constituindo mero reembolso de valores despendidos. "
        f"O pagamento a ser realizado{venc_str}, por meio de [TED / PIX / Transferência bancária], "
        f"para a seguinte conta:",
        st["body"]
    ))
    story.append(Spacer(1, 8))

    # Dados bancários (caixa centralizada)
    banco_data = [
        [Paragraph(f"<b>{ESCRITORIO_NOME_COMPLETO}</b>", st["banco_titulo"])],
        [Paragraph(f"CNPJ: {ESCRITORIO_CNPJ} (chave PIX)", st["banco_linha"])],
        [Paragraph(BANCO, st["banco_linha"])],
        [Paragraph(f"Agência: {AGENCIA}", st["banco_linha"])],
        [Paragraph(f"Conta Corrente: {CONTA}", st["banco_linha"])],
    ]
    banco_tbl = Table(banco_data, colWidths=[W * 0.6])
    banco_tbl.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BOX", (0, 0), (-1, -1), 0.5, CINZA_CLARO),
    ]))
    # Centrar no W
    outer = Table([[banco_tbl]], colWidths=[W])
    outer.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (0, 0), 0),
        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
    ]))
    story.append(outer)
    story.append(Spacer(1, 20))

    # Rodapé página 1
    story.append(HRFlowable(width="100%", thickness=1.5, color=PRETO))
    story.append(Spacer(1, 6))
    story.append(_footer_table(st))

    # ── PÁGINA 2 ──────────────────────────────────────────────────────────────
    from reportlab.platypus import PageBreak
    story.append(PageBreak())

    # Logo página 2
    if _LOGO_PATH.exists():
        story.append(Image(str(_LOGO_PATH), width=3.5 * cm, height=1.5 * cm, kind="proportional"))
    else:
        logo2 = Paragraph("<b>PIMENTA<br/>JUDICE</b>", ParagraphStyle(
            "lp2", fontSize=14, fontName="Helvetica-Bold", textColor=PRETO, leading=16))
        logo2_sub = Paragraph("ADVOGADOS ASSOCIADOS", ParagraphStyle(
            "lsp2", fontSize=7, fontName="Helvetica", textColor=CINZA_CLARO, letterSpacing=1.5))
        story.append(logo2)
        story.append(logo2_sub)
    story.append(Spacer(1, 24))

    # Cláusula de Compliance
    story.append(Paragraph("<b>Cláusula de Compliance Fiscal e Contábil</b>", st["compliance_titulo"]))
    story.append(Spacer(1, 4))

    compliance_textos = [
        "Os valores ora reembolsados não se sujeitam à incidência de ISS, IRRF, PIS, COFINS, CSLL ou IBS/CBS, "
        "por não configurarem prestação de serviços nem acréscimo patrimonial ao Escritório, nos termos da "
        "legislação tributária aplicável e da jurisprudência consolidada.",

        "A presente Nota de Reembolso possui natureza exclusivamente indenizatória, sendo emitida em "
        "conformidade com as melhores práticas de compliance fiscal, contábil e regulatório, inclusive para "
        "fins de auditoria interna e externa.",

        "Eventual retenção tributária indevida por parte do Cliente não altera a natureza jurídica do "
        "reembolso, podendo ser objeto de ajuste, compensação ou restituição, conforme aplicável.",

        "Esta Nota de Reembolso é emitida para fins exclusivamente administrativos e contábeis, "
        "mantendo-se íntegros e inalterados os termos do contrato de prestação de serviços advocatícios "
        "firmado entre as partes.",
    ]
    for txt in compliance_textos:
        story.append(Paragraph(txt, st["compliance_body"]))

    story.append(Spacer(1, 20))

    # Cidade/data
    story.append(Paragraph(
        f"Vitória/ES, {_fmt_data(data_emissao)}.",
        ParagraphStyle("cdata", fontSize=10, fontName="Helvetica", textColor=PRETO, spaceAfter=40)
    ))

    story.append(Spacer(1, 40))

    # Assinaturas
    adm_block = [
        Paragraph("_" * 36, st["assinante"]),
        Paragraph(ASSINANTE_ADM.split("\n")[0], st["assinante_bold"]),
        Paragraph(ASSINANTE_ADM.split("\n")[1], st["assinante"]),
    ]
    adv_block = [
        Paragraph("_" * 36, st["assinante"]),
        Paragraph("<b>Advogado Responsável</b>", st["assinante"]),
        Paragraph(ADVOGADO.split("\n")[0], st["assinante"]),
        Paragraph(ADVOGADO.split("\n")[1], st["assinante"]),
    ]
    sig_tbl = Table([[adm_block, adv_block]], colWidths=[W / 2, W / 2])
    sig_tbl.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sig_tbl)
    story.append(Spacer(1, 30))

    # Rodapé página 2
    story.append(HRFlowable(width="100%", thickness=1.5, color=PRETO))
    story.append(Spacer(1, 6))
    story.append(_footer_table(st))

    doc.build(story)
    return buf.getvalue()
