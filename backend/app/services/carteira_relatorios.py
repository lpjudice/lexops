import os
from io import BytesIO
from datetime import datetime
from typing import List, Tuple
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable, KeepTogether, Image,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, inch
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from sqlalchemy.orm import Session

from app.models.carteira import (
    CarteiraCliente,
    CarteiraDebenturePosicao,
    CarteiraDebentureadotEmissao,
    CarteiraImobiliarioPosicao,
    CarteiraImobiliarioEmpreendimento,
    CarteiraFundoPosicao,
    CarteiraFundoReferencia,
)

# ── Paleta do site ───────────────────────────────────────────────────────
TEAL        = colors.HexColor('#0d9488')
TEAL_LIGHT  = colors.HexColor('#f0fdfa')
DARK        = colors.HexColor('#1F2937')
GRAY_MID    = colors.HexColor('#6B7280')
GRAY_LIGHT  = colors.HexColor('#F9FAFB')
AMBER       = colors.HexColor('#f59e0b')
BLUE        = colors.HexColor('#3B82F6')
WHITE       = colors.white


def _brl(v) -> str:
    v = v or 0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v) -> str:
    if v is None:
        return "-"
    return f"{v:.1f}%".replace(".", ",")


def _slugify(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return s.lower().replace(' ', '_')[:40]


def _make_styles():
    base = getSampleStyleSheet()
    return {
        'title': ParagraphStyle('ct', parent=base['Heading1'],
            fontSize=20, textColor=WHITE, fontName='Helvetica-Bold',
            spaceAfter=0, spaceBefore=0, leading=24),
        'subtitle': ParagraphStyle('cs', parent=base['Normal'],
            fontSize=10, textColor=TEAL_LIGHT, fontName='Helvetica',
            spaceAfter=0, spaceBefore=0),
        'section': ParagraphStyle('csec', parent=base['Normal'],
            fontSize=10, textColor=WHITE, fontName='Helvetica-Bold',
            spaceAfter=0, spaceBefore=0),
        'normal': ParagraphStyle('cn', parent=base['Normal'],
            fontSize=9, textColor=DARK, fontName='Helvetica', leading=13),
        'small': ParagraphStyle('csm', parent=base['Normal'],
            fontSize=8, textColor=GRAY_MID, fontName='Helvetica'),
        'kpi_label': ParagraphStyle('ckl', parent=base['Normal'],
            fontSize=8, textColor=GRAY_MID, fontName='Helvetica', spaceAfter=2),
        'kpi_value': ParagraphStyle('ckv', parent=base['Normal'],
            fontSize=14, textColor=DARK, fontName='Helvetica-Bold'),
    }


def _section_header(label: str, color=TEAL) -> Table:
    t = Table([[Paragraph(label, ParagraphStyle(
        'sh', fontSize=9, textColor=WHITE, fontName='Helvetica-Bold',
    ))]], colWidths=[170*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), color),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    return t


def _data_table(headers: list, rows: list, col_widths: list, color=TEAL) -> Table:
    data = [headers] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), color),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, GRAY_LIGHT]),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, color),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
    ]
    # Bold last row if it's a total row
    if rows and rows[-1] and str(rows[-1][0]).startswith('TOTAL'):
        i = len(data) - 1
        style += [
            ('BACKGROUND', (0, i), (-1, i), colors.HexColor('#E5E7EB')),
            ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
        ]
    t.setStyle(TableStyle(style))
    return t


_LOGO_PATH = os.path.join(os.path.dirname(__file__), '../assets/logo_dark.png')
_FOOTER_TEXT = "Lucas Pimenta Judice  |  OAB/ES 14.477  |  pj@pimentajudice.com.br  |  +55 (11) 5196-5950  |  Vitoria/ES · Sao Paulo/SP"

DARK_HDR   = colors.HexColor('#1a1a1a')
TEAL_LINE  = TEAL


def _logo_header(nome_cliente: str, data_str: str) -> Table:
    """Logo à esquerda, info do cliente à direita"""
    try:
        logo = Image(_LOGO_PATH, width=52*mm, height=14*mm)
        logo.hAlign = 'LEFT'
        logo_cell = logo
    except Exception:
        logo_cell = Paragraph(
            "PIMENTA JUDICE",
            ParagraphStyle('lgfb', fontSize=14, fontName='Helvetica-Bold', textColor=TEAL),
        )

    info = Table(
        [[Paragraph("RELATORIO DE CARTEIRA", ParagraphStyle('rth', fontSize=9, fontName='Helvetica-Bold', textColor=DARK, spaceAfter=2))],
         [Paragraph(nome_cliente, ParagraphStyle('rtc', fontSize=11, fontName='Helvetica-Bold', textColor=TEAL, spaceAfter=1))],
         [Paragraph(f"Emitido em {data_str}", ParagraphStyle('rtd', fontSize=8, fontName='Helvetica', textColor=GRAY_MID))]],
        colWidths=[90*mm],
    )
    info.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    t = Table([[logo_cell, info]], colWidths=[80*mm, 90*mm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (0, -1), 0), ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
    ]))
    return t


def _section_title(label: str, color=TEAL) -> list:
    """Título de seção elegante: texto colorido + linha horizontal"""
    return [
        Paragraph(label, ParagraphStyle('st', fontSize=9, fontName='Helvetica-Bold', textColor=color, spaceAfter=2, spaceBefore=4)),
        HRFlowable(width='100%', thickness=1, color=color, spaceAfter=3),
    ]


def _elegant_table(headers: list, rows: list, col_widths: list, color=TEAL) -> Table:
    """Tabela elegante: header escuro, linhas alternadas, sem bordas pesadas"""
    data = [headers] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), DARK_HDR),
        ('TEXTCOLOR', (0, 0), (-1, 0), WHITE),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, colors.HexColor('#f9fafb')]),
        ('LINEBELOW', (0, 0), (-1, 0), 0, WHITE),
        ('LINEBELOW', (0, 1), (-1, -2), 0.3, colors.HexColor('#e5e7eb')),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]
    # última linha em bold (total)
    if rows and str(rows[-1][0]).startswith('TOTAL'):
        i = len(data) - 1
        style += [
            ('BACKGROUND', (0, i), (-1, i), DARK_HDR),
            ('TEXTCOLOR', (0, i), (-1, i), WHITE),
            ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
        ]
    t.setStyle(TableStyle(style))
    return t


class CarteiraRelatoriosService:

    @staticmethod
    def gerar_pdf_cliente(db: Session, cliente_id: int) -> Tuple[bytes, str]:
        cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
        if not cliente:
            raise ValueError("Cliente nao encontrado")

        nome_cliente = cliente.nome or f"Cliente {cliente_id}"
        data_str = datetime.now().strftime('%d/%m/%Y')

        debentures = db.query(CarteiraDebenturePosicao).filter(
            CarteiraDebenturePosicao.cliente_id == cliente_id
        ).all()
        imobiliario = db.query(CarteiraImobiliarioPosicao).filter(
            CarteiraImobiliarioPosicao.cliente_id == cliente_id
        ).all()
        fundos = db.query(CarteiraFundoPosicao).filter(
            CarteiraFundoPosicao.cliente_id == cliente_id
        ).all()

        emissao_map = {e.id: e for e in db.query(CarteiraDebentureadotEmissao).all()}
        emp_map = {e.id: e for e in db.query(CarteiraImobiliarioEmpreendimento).all()}
        fundo_map = {f.id: f for f in db.query(CarteiraFundoReferencia).all()}

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=18*mm, rightMargin=18*mm,
            topMargin=18*mm, bottomMargin=22*mm,
        )

        story = []

        # ── Cabeçalho com logo ────────────────────────────────────────
        story.append(_logo_header(nome_cliente, data_str))
        story.append(Spacer(1, 3*mm))
        story.append(HRFlowable(width='100%', thickness=1.5, color=TEAL, spaceAfter=5))

        # ── KPIs ──────────────────────────────────────────────────────
        total_deb   = sum(d.valor_aplicado or 0 for d in debentures)
        total_imob  = sum(i.valor_total_compromissado or 0 for i in imobiliario)
        total_fundo = sum(f.valor_aplicado or 0 for f in fundos)
        total_fin   = total_deb + total_fundo
        total_geral = total_imob + total_fin
        n_ativos    = len(debentures) + len(imobiliario) + len(fundos)

        kpi_rows = [[
            _build_kpi("TOTAL GERAL", _brl(total_geral), DARK),
            _build_kpi("IMOBILIARIO", _brl(total_imob), AMBER),
            _build_kpi("FINANCEIRO", _brl(total_fin), TEAL),
            _build_kpi("ATIVOS", str(n_ativos), BLUE),
        ]]
        kpi_table = Table(kpi_rows, colWidths=[42.5*mm]*4)
        kpi_table.setStyle(TableStyle([
            ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 6*mm))

        # ── Seção Debêntures ──────────────────────────────────────────
        if debentures:
            for el in _section_title(f"DEBENTURES  —  {len(debentures)} posicoes  |  {_brl(total_deb)}"):
                story.append(el)

            rows = []
            for d in debentures:
                emissao = emissao_map.get(d.emissao_id)
                nome_emissao = emissao.nome_serie if emissao else f"#{d.emissao_id}"
                rows.append([
                    d.numero_cautela or '-',
                    nome_emissao,
                    d.data_aquisicao.strftime('%d/%m/%Y') if d.data_aquisicao else '-',
                    _brl(d.valor_aplicado),
                    _brl(d.valor_atual_estimado) if d.valor_atual_estimado else '-',
                    d.status_resgate or 'Ativo',
                ])
            rows.append([
                'TOTAL', '', '',
                _brl(total_deb),
                _brl(sum(d.valor_atual_estimado or d.valor_aplicado or 0 for d in debentures)),
                '',
            ])
            story.append(_elegant_table(
                ['Cautela', 'Emissao', 'Aquisicao', 'Aplicado', 'Atual Estim.', 'Status'],
                rows, [28*mm, 50*mm, 22*mm, 28*mm, 28*mm, 18*mm], color=TEAL,
            ))
            story.append(Spacer(1, 5*mm))

        # ── Seção Imobiliário ─────────────────────────────────────────
        if imobiliario:
            for el in _section_title(f"IMOBILIARIO  —  {len(imobiliario)} posicoes  |  {_brl(total_imob)}", AMBER):
                story.append(el)

            rows = []
            for i in imobiliario:
                emp = emp_map.get(i.empreendimento_id)
                nome_emp = emp.nome_venda if emp else f"#{i.empreendimento_id}"
                rows.append([
                    nome_emp,
                    _brl(i.valor_total_compromissado),
                    _brl(i.valor_efetivamente_investido),
                    _pct(i.percentual_participacao),
                ])
            rows.append([
                'TOTAL', _brl(total_imob),
                _brl(sum(i.valor_efetivamente_investido or 0 for i in imobiliario)), '',
            ])
            story.append(_elegant_table(
                ['Empreendimento', 'Comprometido', 'Investido', '% Part.'],
                rows, [70*mm, 34*mm, 34*mm, 36*mm], color=AMBER,
            ))
            story.append(Spacer(1, 5*mm))

        # ── Seção Fundos ──────────────────────────────────────────────
        if fundos:
            for el in _section_title(f"FUNDOS  —  {len(fundos)} posicoes  |  {_brl(total_fundo)}", BLUE):
                story.append(el)

            rows = []
            for f in fundos:
                fundo_ref = fundo_map.get(f.fundo_id)
                nome_fundo = fundo_ref.nome_fundo if fundo_ref else f"#{f.fundo_id}"
                rows.append([
                    nome_fundo,
                    _brl(f.valor_aplicado),
                    _brl(f.valor_atual_estimado) if f.valor_atual_estimado else '-',
                    f.data_aplicacao.strftime('%d/%m/%Y') if f.data_aplicacao else '-',
                ])
            rows.append([
                'TOTAL', _brl(total_fundo),
                _brl(sum(f.valor_atual_estimado or f.valor_aplicado or 0 for f in fundos)), '',
            ])
            story.append(_elegant_table(
                ['Fundo', 'Aplicado', 'Atual Estim.', 'Data Aplic.'],
                rows, [70*mm, 34*mm, 34*mm, 36*mm], color=BLUE,
            ))
            story.append(Spacer(1, 5*mm))

        # ── Rodapé ────────────────────────────────────────────────────
        story.append(Spacer(1, 4*mm))
        story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#e5e7eb'), spaceAfter=3))
        story.append(Paragraph(
            _FOOTER_TEXT,
            ParagraphStyle('footer', fontSize=7, textColor=GRAY_MID, fontName='Helvetica', alignment=1),
        ))

        doc.build(story)
        return buffer.getvalue(), nome_cliente

    @staticmethod
    def exportar_xlsx_qualificacao(db: Session, cliente_ids: List[int]) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "Qualificacao"

        headers = ['Cliente', 'Tipo', 'CPF/CNPJ', 'Debentures', 'Imobiliario', 'Fundos', 'Total Aplicado']
        ws.append(headers)

        teal_fill = PatternFill(start_color="0D9488", end_color="0D9488", fill_type="solid")
        white_font = Font(bold=True, color="FFFFFF", size=10)
        thin_border = Border(
            bottom=Side(style='thin', color='E5E7EB'),
        )

        for cell in ws[1]:
            cell.fill = teal_fill
            cell.font = white_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border

        alt_fill = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")

        for idx, cliente_id in enumerate(cliente_ids):
            cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
            if not cliente:
                continue

            n_deb = db.query(CarteiraDebenturePosicao).filter(CarteiraDebenturePosicao.cliente_id == cliente_id).count()
            n_imob = db.query(CarteiraImobiliarioPosicao).filter(CarteiraImobiliarioPosicao.cliente_id == cliente_id).count()
            n_fundo = db.query(CarteiraFundoPosicao).filter(CarteiraFundoPosicao.cliente_id == cliente_id).count()

            from sqlalchemy import func as sqlfunc
            total_apl = (
                (db.query(sqlfunc.sum(CarteiraDebenturePosicao.valor_aplicado))
                    .filter(CarteiraDebenturePosicao.cliente_id == cliente_id).scalar() or 0) +
                (db.query(sqlfunc.sum(CarteiraImobiliarioPosicao.valor_total_compromissado))
                    .filter(CarteiraImobiliarioPosicao.cliente_id == cliente_id).scalar() or 0) +
                (db.query(sqlfunc.sum(CarteiraFundoPosicao.valor_aplicado))
                    .filter(CarteiraFundoPosicao.cliente_id == cliente_id).scalar() or 0)
            )

            row_data = [
                cliente.nome or f"Cliente {cliente_id}",
                cliente.tipo_pessoa or 'PF',
                cliente.cpf or '',
                n_deb, n_imob, n_fundo,
                total_apl,
            ]
            ws.append(row_data)

            row_num = ws.max_row
            if idx % 2 == 1:
                for cell in ws[row_num]:
                    cell.fill = alt_fill
            for cell in ws[row_num]:
                cell.border = thin_border

        ws.column_dimensions['A'].width = 32
        ws.column_dimensions['B'].width = 8
        ws.column_dimensions['C'].width = 18
        ws.column_dimensions['D'].width = 12
        ws.column_dimensions['E'].width = 12
        ws.column_dimensions['F'].width = 12
        ws.column_dimensions['G'].width = 18

        # Format total column as currency
        for row in ws.iter_rows(min_row=2, min_col=7, max_col=7):
            for cell in row:
                cell.number_format = 'R$ #,##0.00'

        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()


def _build_kpi(label: str, value: str, color) -> Table:
    inner = Table(
        [[Paragraph(label, ParagraphStyle('kl', fontSize=7, textColor=color, fontName='Helvetica-Bold', spaceAfter=2))],
         [Paragraph(value, ParagraphStyle('kv', fontSize=11, textColor=DARK, fontName='Helvetica-Bold'))]],
        colWidths=[40*mm],
    )
    inner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), WHITE),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('LINEABOVE', (0, 0), (-1, 0), 2, color),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
    ]))
    outer = Table([[inner]], colWidths=[42.5*mm])
    outer.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 1),
        ('RIGHTPADDING', (0, 0), (-1, -1), 1),
    ]))
    return outer
