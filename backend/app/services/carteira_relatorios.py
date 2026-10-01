from io import BytesIO
from datetime import datetime
from typing import List, Tuple
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable, KeepTogether,
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


class CarteiraRelatoriosService:

    @staticmethod
    def gerar_pdf_cliente(db: Session, cliente_id: int) -> Tuple[bytes, str]:
        cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
        if not cliente:
            raise ValueError("Cliente nao encontrado")

        nome_cliente = cliente.nome or f"Cliente {cliente_id}"

        debentures = db.query(CarteiraDebenturePosicao).filter(
            CarteiraDebenturePosicao.cliente_id == cliente_id
        ).all()
        imobiliario = db.query(CarteiraImobiliarioPosicao).filter(
            CarteiraImobiliarioPosicao.cliente_id == cliente_id
        ).all()
        fundos = db.query(CarteiraFundoPosicao).filter(
            CarteiraFundoPosicao.cliente_id == cliente_id
        ).all()

        # Lookups para nomes reais
        emissao_map = {e.id: e for e in db.query(CarteiraDebentureadotEmissao).all()}
        emp_map = {e.id: e for e in db.query(CarteiraImobiliarioEmpreendimento).all()}
        fundo_map = {f.id: f for f in db.query(CarteiraFundoReferencia).all()}

        st = _make_styles()

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=15*mm, rightMargin=15*mm,
            topMargin=15*mm, bottomMargin=15*mm,
        )

        story = []

        # ── Cabeçalho ────────────────────────────────────────────────
        header_data = [[
            Paragraph("CARTEIRA DE ATIVOS", st['title']),
            Paragraph(f"{nome_cliente}\nData: {datetime.now().strftime('%d/%m/%Y')}", st['subtitle']),
        ]]
        header_table = Table(header_data, colWidths=[100*mm, 70*mm])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), TEAL),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('LEFTPADDING', (0, 0), (0, -1), 12),
            ('RIGHTPADDING', (-1, 0), (-1, -1), 12),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 8*mm))

        # ── KPIs resumo ───────────────────────────────────────────────
        total_deb = sum(d.valor_aplicado or 0 for d in debentures)
        total_imob = sum(i.valor_total_compromissado or 0 for i in imobiliario)
        total_fundo = sum(f.valor_aplicado or 0 for f in fundos)
        total_fin = total_deb + total_fundo
        total_geral = total_imob + total_fin

        kpi_rows = [[
            _build_kpi("TOTAL GERAL", _brl(total_geral), DARK),
            _build_kpi("IMOBILIARIO", _brl(total_imob), AMBER),
            _build_kpi("FINANCEIRO", _brl(total_fin), TEAL),
            _build_kpi("ATIVOS", str(len(debentures) + len(imobiliario) + len(fundos)), BLUE),
        ]]
        kpi_table = Table(kpi_rows, colWidths=[42.5*mm, 42.5*mm, 42.5*mm, 42.5*mm])
        kpi_table.setStyle(TableStyle([
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 6*mm))

        # ── Seção Debêntures ──────────────────────────────────────────
        if debentures:
            story.append(_section_header(f"DEBENTURES ({len(debentures)} posicoes  |  {_brl(total_deb)})"))
            story.append(Spacer(1, 1*mm))

            rows = []
            for d in debentures:
                emissao = emissao_map.get(d.emissao_id)
                nome_emissao = emissao.nome_serie if emissao else f"#{d.emissao_id}"
                rows.append([
                    d.numero_cautela or '-',
                    nome_emissao,
                    _brl(d.valor_aplicado),
                    _brl(d.valor_atual_estimado) if d.valor_atual_estimado else '-',
                    d.status_resgate or 'Ativo',
                ])
            rows.append([
                'TOTAL', '',
                _brl(total_deb),
                _brl(sum(d.valor_atual_estimado or d.valor_aplicado or 0 for d in debentures)),
                '',
            ])

            story.append(_data_table(
                ['Cautela', 'Emissao', 'Aplicado', 'Atual Estim.', 'Status'],
                rows,
                [30*mm, 55*mm, 30*mm, 30*mm, 25*mm],
                color=TEAL,
            ))
            story.append(Spacer(1, 5*mm))

        # ── Seção Imobiliário ─────────────────────────────────────────
        if imobiliario:
            story.append(_section_header(f"IMOBILIARIO ({len(imobiliario)} posicoes  |  {_brl(total_imob)})", color=AMBER))
            story.append(Spacer(1, 1*mm))

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
                'TOTAL',
                _brl(total_imob),
                _brl(sum(i.valor_efetivamente_investido or 0 for i in imobiliario)),
                '',
            ])

            story.append(_data_table(
                ['Empreendimento', 'Comprometido', 'Investido', '% Part.'],
                rows,
                [65*mm, 35*mm, 35*mm, 35*mm],
                color=AMBER,
            ))
            story.append(Spacer(1, 5*mm))

        # ── Seção Fundos ──────────────────────────────────────────────
        if fundos:
            story.append(_section_header(f"FUNDOS ({len(fundos)} posicoes  |  {_brl(total_fundo)})", color=BLUE))
            story.append(Spacer(1, 1*mm))

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
                'TOTAL',
                _brl(total_fundo),
                _brl(sum(f.valor_atual_estimado or f.valor_aplicado or 0 for f in fundos)),
                '',
            ])

            story.append(_data_table(
                ['Fundo', 'Aplicado', 'Atual Estim.', 'Data Aplic.'],
                rows,
                [65*mm, 35*mm, 35*mm, 35*mm],
                color=BLUE,
            ))
            story.append(Spacer(1, 5*mm))

        # ── Rodapé ────────────────────────────────────────────────────
        story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#E5E7EB')))
        story.append(Spacer(1, 2*mm))
        story.append(Paragraph(
            f"Pimenta Judice Advogados  |  Carteira gerada em {datetime.now().strftime('%d/%m/%Y as %H:%M')}  |  Confidencial",
            ParagraphStyle('footer', fontSize=7, textColor=GRAY_MID, fontName='Helvetica', alignment=1)
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
