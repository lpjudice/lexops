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
from reportlab.lib.units import mm
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

# ── Paleta ───────────────────────────────────────────────────────────────────
DARK        = colors.HexColor('#111111')
DARK_HDR    = colors.HexColor('#1a1a1a')
DARK_CARD   = colors.HexColor('#1F2937')
TEAL        = colors.HexColor('#0d9488')
TEAL_LIGHT  = colors.HexColor('#f0fdfa')
AMBER       = colors.HexColor('#f59e0b')
BLUE        = colors.HexColor('#3B82F6')
GRAY_MID    = colors.HexColor('#6B7280')
GRAY_LIGHT  = colors.HexColor('#F4F4F4')
WHITE       = colors.white
RED         = colors.HexColor('#dc2626')

_LOGO_PATH   = os.path.join(os.path.dirname(__file__), '../assets/logo_dark.png')
_FOOTER_NAME = "Lucas Pimenta Judice  |  OAB/ES 14.477"
_FOOTER_CONTACT = "pj@pimentajudice.com.br   +55 (11) 5196-5950   Vitoria/ES · Sao Paulo/SP"

PAGE_W = 170 * mm   # usable width (A4 - margins 18+18)


def _brl(v) -> str:
    v = v or 0
    return f"R$ {v:,.0f}".replace(",", ".")


def _brl2(v) -> str:
    v = v or 0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v) -> str:
    return "-" if v is None else f"{v:.1f}%".replace(".", ",")


# ── Estilos de parágrafo ─────────────────────────────────────────────────────

def _s(name, **kw) -> ParagraphStyle:
    base = getSampleStyleSheet()['Normal']
    return ParagraphStyle(name, parent=base, **kw)


def _p(text, style) -> Paragraph:
    return Paragraph(text, style)


# ── Blocos reutilizáveis ─────────────────────────────────────────────────────

def _header_block(nome_cliente: str, data_str: str) -> Table:
    """Logo à esquerda, info do documento à direita — exatamente como a referência."""
    try:
        logo = Image(_LOGO_PATH)
        target_w = 40 * mm
        logo.drawWidth = target_w
        logo.drawHeight = target_w * logo.imageHeight / logo.imageWidth
        logo.hAlign = 'LEFT'
        logo_cell = logo
    except Exception:
        logo_cell = _p("PIMENTA JUDICE<br/><font size='6'>ADVOGADOS ASSOCIADOS</font>",
                       _s('lgfb', fontSize=12, fontName='Helvetica-Bold', textColor=DARK))

    info = Table(
        [[_p("Relatorio de Carteira",
             _s('rh1', fontSize=9, fontName='Helvetica-Bold', textColor=DARK, spaceAfter=1))],
         [_p(nome_cliente,
             _s('rh2', fontSize=8, fontName='Helvetica', textColor=GRAY_MID, spaceAfter=1))],
         [_p(data_str,
             _s('rh3', fontSize=8, fontName='Helvetica', textColor=GRAY_MID))]],
        colWidths=[90 * mm],
    )
    info.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    t = Table([[logo_cell, info]], colWidths=[80 * mm, 90 * mm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (0, 0), 0), ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
    ]))
    return t


def _title_row(nome_cliente: str) -> Table:
    """Título grande à esquerda + pill escuro com nome do cliente à direita."""
    title_cell = Table(
        [[_p("CARTEIRA DE INVESTIMENTOS",
             _s('tt1', fontSize=15, fontName='Helvetica-Bold', textColor=DARK, spaceAfter=1))],
         [_p("Posicoes ativas · Relatorio consolidado",
             _s('tt2', fontSize=9, fontName='Helvetica', textColor=GRAY_MID))]],
        colWidths=[110 * mm],
    )
    title_cell.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    nome_upper = nome_cliente.upper()
    pill = Table(
        [[_p(nome_upper, _s('pill', fontSize=9, fontName='Helvetica-Bold', textColor=WHITE))]],
        colWidths=[58 * mm],
    )
    pill.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), DARK),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))

    t = Table([[title_cell, pill]], colWidths=[112 * mm, 58 * mm])
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (0, 0), 0), ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
    ]))
    return t


def _section_hdr(label: str) -> list:
    """ALL CAPS + linha fina escura — estilo da referência."""
    return [
        Spacer(1, 3 * mm),
        _p(label, _s('sh', fontSize=8, fontName='Helvetica-Bold', textColor=DARK,
                     spaceBefore=0, spaceAfter=2, tracking=0.5)),
        HRFlowable(width='100%', thickness=0.8, color=DARK, spaceAfter=3),
    ]


def _kpi_card(label: str, value: str, sub: str = '', dark: bool = False) -> Table:
    bg = DARK if dark else colors.HexColor('#1F2937')
    lbl_color = colors.HexColor('#9CA3AF')
    val_color = WHITE
    sub_color = colors.HexColor('#6B7280') if not dark else colors.HexColor('#9CA3AF')

    rows = [[_p(label, _s('kl', fontSize=7, fontName='Helvetica-Bold',
                           textColor=lbl_color, spaceAfter=3))],
            [_p(value, _s('kv', fontSize=13, fontName='Helvetica-Bold',
                           textColor=val_color, spaceAfter=1))]]
    if sub:
        rows.append([_p(sub, _s('ks', fontSize=7, fontName='Helvetica',
                                 textColor=sub_color))])

    inner = Table(rows, colWidths=[40 * mm])
    inner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg),
        ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('LINEABOVE', (0, 0), (-1, 0), 2, TEAL if not dark else AMBER),
    ]))
    outer = Table([[inner]], colWidths=[42.5 * mm])
    outer.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 1), ('RIGHTPADDING', (0, 0), (-1, -1), 1),
    ]))
    return outer


def _asset_table(headers: list, rows: list, col_widths: list,
                 teal_cols: list = None) -> Table:
    """Tabela com header preto/branco + linhas alternadas + accent teal opcional."""
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
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, GRAY_LIGHT]),
        ('LINEBELOW', (0, 1), (-1, -2), 0.3, colors.HexColor('#e5e7eb')),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]

    if teal_cols:
        for col in teal_cols:
            for r in range(1, len(data)):
                style.append(('TEXTCOLOR', (col, r), (col, r), TEAL))
                style.append(('FONTNAME', (col, r), (col, r), 'Helvetica-Bold'))

    # Linha de total: fundo escuro
    if rows and str(rows[-1][0]).startswith('TOTAL'):
        i = len(data) - 1
        style += [
            ('BACKGROUND', (0, i), (-1, i), DARK_HDR),
            ('TEXTCOLOR', (0, i), (-1, i), WHITE),
            ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
        ]
        if teal_cols:
            for col in teal_cols:
                style.append(('TEXTCOLOR', (col, i), (col, i), TEAL))

    t.setStyle(TableStyle(style))
    return t


def _dark_footer_bar(total_geral: float, exito: float = 0) -> Table:
    """Barra escura de rodapé com total em destaque (estilo INVESTIMENTO da referência)."""
    left_rows = [[_p("TOTAL APLICADO",
                      _s('fl', fontSize=7, fontName='Helvetica-Bold',
                         textColor=colors.HexColor('#9CA3AF'), spaceAfter=2))],
                 [_p(_brl(total_geral),
                      _s('fv', fontSize=20, fontName='Helvetica-Bold',
                         textColor=WHITE, spaceAfter=1))]]
    if exito > 0:
        left_rows.append([_p(f"Expectativa de exito: {_brl(exito)}",
                              _s('fe', fontSize=8, fontName='Helvetica',
                                 textColor=colors.HexColor('#6B7280')))])

    left = Table(left_rows, colWidths=[85 * mm])
    left.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    right = _p(
        "Honorarios calculados sobre valores efetivamente recuperados.<br/>"
        "Valores estimados nao constituem garantia de resultado.",
        _s('fn', fontSize=7, fontName='Helvetica',
           textColor=colors.HexColor('#6B7280'), alignment=2)
    )

    t = Table([[left, right]], colWidths=[85 * mm, 85 * mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), DARK),
        ('TOPPADDING', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (-1, 0), (-1, -1), 12),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return t


def _bottom_footer() -> Table:
    """Linha final com nome/OAB à esquerda e contato à direita."""
    t = Table(
        [[_p(_FOOTER_NAME, _s('fn1', fontSize=7, fontName='Helvetica-Bold', textColor=DARK)),
          _p(_FOOTER_CONTACT, _s('fn2', fontSize=7, fontName='Helvetica',
                                  textColor=GRAY_MID, alignment=2))]],
        colWidths=[85 * mm, 85 * mm],
    )
    t.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (-1, 0), (-1, -1), 0),
        ('ALIGN', (-1, 0), (-1, -1), 'RIGHT'),
    ]))
    return t


# ── Service ──────────────────────────────────────────────────────────────────

class CarteiraRelatoriosService:

    @staticmethod
    def gerar_pdf_cliente(db: Session, cliente_id: int) -> Tuple[bytes, str]:
        cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
        if not cliente:
            raise ValueError("Cliente nao encontrado")

        nome_cliente = cliente.nome or f"Cliente {cliente_id}"
        data_str = datetime.now().strftime('%d de %B de %Y').replace(
            'January', 'Janeiro').replace('February', 'Fevereiro').replace(
            'March', 'Marco').replace('April', 'Abril').replace(
            'May', 'Maio').replace('June', 'Junho').replace(
            'July', 'Julho').replace('August', 'Agosto').replace(
            'September', 'Setembro').replace('October', 'Outubro').replace(
            'November', 'Novembro').replace('December', 'Dezembro')

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

        # ── Totais ────────────────────────────────────────────────────────────
        total_deb   = sum(d.valor_aplicado or 0 for d in debentures)
        total_imob  = sum(i.valor_total_compromissado or 0 for i in imobiliario)
        total_fundo = sum(f.valor_aplicado or 0 for f in fundos)
        total_fin   = total_deb + total_fundo
        total_geral = total_imob + total_fin
        n_ativos    = len(debentures) + len(imobiliario) + len(fundos)

        # Êxito esperado
        pct_fin  = cliente.percentual_sucesso_fin or cliente.percentual_sucesso_geral or 0
        pct_imob = cliente.percentual_sucesso_imob or cliente.percentual_sucesso_geral or 0
        exito = total_fin * (pct_fin / 100) + total_imob * (pct_imob / 100)

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=18 * mm, rightMargin=18 * mm,
            topMargin=16 * mm, bottomMargin=18 * mm,
        )
        story = []

        # ── 1. Cabeçalho ──────────────────────────────────────────────────────
        story.append(_header_block(nome_cliente, data_str))
        story.append(Spacer(1, 2 * mm))
        story.append(HRFlowable(width='100%', thickness=0.5,
                                color=colors.HexColor('#e5e7eb'), spaceAfter=4))

        # ── 2. Título + pill do cliente ───────────────────────────────────────
        story.append(_title_row(nome_cliente))
        story.append(Spacer(1, 5 * mm))

        # ── 3. KPI row ────────────────────────────────────────────────────────
        kpi_row = [[
            _kpi_card("TOTAL GERAL", _brl(total_geral), dark=True),
            _kpi_card("IMOBILIARIO", _brl(total_imob)),
            _kpi_card("FINANCEIRO", _brl(total_fin)),
            _kpi_card("ATIVOS", str(n_ativos)),
        ]]
        kpi_table = Table(kpi_row, colWidths=[42.5 * mm] * 4)
        kpi_table.setStyle(TableStyle([
            ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 6 * mm))

        # ── 4. Debêntures ─────────────────────────────────────────────────────
        if debentures:
            for el in _section_hdr(f"DEBENTURES — {len(debentures)} POSICOES  |  {_brl(total_deb)}"):
                story.append(el)

            rows = []
            for d in debentures:
                em = emissao_map.get(d.emissao_id)
                rows.append([
                    d.numero_cautela or '-',
                    em.nome_serie if em else f"#{d.emissao_id}",
                    em.emissor if em else '-',
                    d.data_aquisicao.strftime('%d/%m/%Y') if d.data_aquisicao else '-',
                    _brl(d.valor_aplicado),
                    _brl(d.valor_atual_estimado) if d.valor_atual_estimado else '-',
                    d.status_resgate or 'Ativo',
                ])
            rows.append([
                'TOTAL', '', '', '',
                _brl(total_deb),
                _brl(sum(d.valor_atual_estimado or d.valor_aplicado or 0 for d in debentures)),
                '',
            ])
            story.append(_asset_table(
                ['CAUTELA', 'EMISSAO', 'EMISSOR', 'AQUISICAO', 'APLICADO', 'ATUAL ESTIM.', 'STATUS'],
                rows,
                [22*mm, 38*mm, 30*mm, 20*mm, 24*mm, 24*mm, 16*mm],
                teal_cols=[4, 5],
            ))
            story.append(Spacer(1, 5 * mm))

        # ── 5. Imobiliário ────────────────────────────────────────────────────
        if imobiliario:
            for el in _section_hdr(f"IMOBILIARIO — {len(imobiliario)} POSICOES  |  {_brl(total_imob)}"):
                story.append(el)

            rows = []
            for i in imobiliario:
                emp = emp_map.get(i.empreendimento_id)
                rows.append([
                    emp.nome_venda if emp else f"#{i.empreendimento_id}",
                    emp.cidade if emp and emp.cidade else '-',
                    _brl(i.valor_total_compromissado),
                    _brl(i.valor_efetivamente_investido) if i.valor_efetivamente_investido else '-',
                    _pct(i.percentual_participacao),
                ])
            rows.append([
                'TOTAL', '',
                _brl(total_imob),
                _brl(sum(i.valor_efetivamente_investido or 0 for i in imobiliario)),
                '',
            ])
            story.append(_asset_table(
                ['EMPREENDIMENTO', 'CIDADE', 'COMPROMETIDO', 'INVESTIDO', '% PART.'],
                rows,
                [55*mm, 30*mm, 30*mm, 30*mm, 25*mm],
                teal_cols=[2, 3],
            ))
            story.append(Spacer(1, 5 * mm))

        # ── 6. Fundos ─────────────────────────────────────────────────────────
        if fundos:
            for el in _section_hdr(f"FUNDOS — {len(fundos)} POSICOES  |  {_brl(total_fundo)}"):
                story.append(el)

            rows = []
            for f in fundos:
                ref = fundo_map.get(f.fundo_id)
                nome_fundo = ref.nome_fundo if ref else f"#{f.fundo_id}"
                queda = ref.percentual_credito_recuperavel if ref else None
                recup_str = f"{100 - queda:.0f}% recup." if queda is not None else '-'
                rows.append([
                    nome_fundo,
                    ref.gestora if ref else '-',
                    _brl(f.valor_aplicado),
                    _brl(f.valor_atual_estimado) if f.valor_atual_estimado else '-',
                    recup_str,
                    f.data_aplicacao.strftime('%d/%m/%Y') if f.data_aplicacao else '-',
                ])
            rows.append([
                'TOTAL', '',
                _brl(total_fundo),
                _brl(sum(f.valor_atual_estimado or f.valor_aplicado or 0 for f in fundos)),
                '', '',
            ])
            story.append(_asset_table(
                ['FUNDO', 'GESTORA', 'APLICADO', 'ATUAL ESTIM.', '% RECUP.', 'DATA APLIC.'],
                rows,
                [48*mm, 28*mm, 26*mm, 26*mm, 22*mm, 20*mm],
                teal_cols=[2, 3],
            ))
            story.append(Spacer(1, 5 * mm))

        # ── 7. Honorários (se houver) ─────────────────────────────────────────
        if exito > 0 and (pct_fin > 0 or pct_imob > 0):
            for el in _section_hdr("HONORARIOS DE EXITO"):
                story.append(el)

            hon_rows = []
            if total_fin > 0 and pct_fin > 0:
                hon_rows.append(['Ativos Financeiros (Deb. + Fundos)',
                                  _brl(total_fin), _pct(pct_fin), _brl(total_fin * pct_fin / 100)])
            if total_imob > 0 and pct_imob > 0:
                hon_rows.append(['Imobiliario',
                                  _brl(total_imob), _pct(pct_imob), _brl(total_imob * pct_imob / 100)])
            if len(hon_rows) > 1:
                hon_rows.append(['TOTAL', '', '', _brl(exito)])

            story.append(_asset_table(
                ['BASE DE CALCULO', 'VALOR', '% EXITO', 'HONORARIOS ESP.'],
                hon_rows,
                [70*mm, 35*mm, 25*mm, 40*mm],
                teal_cols=[3],
            ))
            story.append(Spacer(1, 5 * mm))

        # ── 8. Barra dark com total ───────────────────────────────────────────
        story.append(Spacer(1, 4 * mm))
        story.append(_dark_footer_bar(total_geral, exito))
        story.append(Spacer(1, 3 * mm))

        # ── 9. Rodapé final ───────────────────────────────────────────────────
        story.append(_bottom_footer())

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
        thin_border = Border(bottom=Side(style='thin', color='E5E7EB'))

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

            n_deb  = db.query(CarteiraDebenturePosicao).filter(
                CarteiraDebenturePosicao.cliente_id == cliente_id).count()
            n_imob = db.query(CarteiraImobiliarioPosicao).filter(
                CarteiraImobiliarioPosicao.cliente_id == cliente_id).count()
            n_fund = db.query(CarteiraFundoPosicao).filter(
                CarteiraFundoPosicao.cliente_id == cliente_id).count()

            from sqlalchemy import func as sqlfunc
            total_apl = (
                (db.query(sqlfunc.sum(CarteiraDebenturePosicao.valor_aplicado))
                    .filter(CarteiraDebenturePosicao.cliente_id == cliente_id).scalar() or 0) +
                (db.query(sqlfunc.sum(CarteiraImobiliarioPosicao.valor_total_compromissado))
                    .filter(CarteiraImobiliarioPosicao.cliente_id == cliente_id).scalar() or 0) +
                (db.query(sqlfunc.sum(CarteiraFundoPosicao.valor_aplicado))
                    .filter(CarteiraFundoPosicao.cliente_id == cliente_id).scalar() or 0)
            )

            ws.append([
                cliente.nome or f"Cliente {cliente_id}",
                cliente.tipo_pessoa or 'PF',
                cliente.cpf or '',
                n_deb, n_imob, n_fund, total_apl,
            ])

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

        for row in ws.iter_rows(min_row=2, min_col=7, max_col=7):
            for cell in row:
                cell.number_format = 'R$ #,##0.00'

        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()
