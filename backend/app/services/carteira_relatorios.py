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
# Preto puro é usado só em 2 lugares do documento (pill do cliente + barra de
# total) — todo o resto usa tons claros com acento colorido, para um visual
# mais suave (sem blocos escuros empilhados).
DARK        = colors.HexColor('#1F2937')   # charcoal suave — pill + barra final
TEXT        = colors.HexColor('#111827')   # texto principal (quase-preto, não puro)
TEAL        = colors.HexColor('#0d9488')
TEAL_TINT   = colors.HexColor('#F0FDFA')   # header de tabela (financeiro)
AMBER       = colors.HexColor('#d97706')
AMBER_TINT  = colors.HexColor('#FFFBEB')   # header de tabela (imobiliário)
GRAY_MID    = colors.HexColor('#6B7280')
GRAY_BORDER = colors.HexColor('#E5E7EB')
GRAY_ROW    = colors.HexColor('#FAFAFA')
GRAY_TOTAL  = colors.HexColor('#F3F4F6')
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
        probe = Image(_LOGO_PATH)
        target_w = 40 * mm
        target_h = target_w * probe.imageHeight / probe.imageWidth
        # width/height precisam ir no construtor (kind='direct') — setar
        # drawWidth/drawHeight depois de criado não é respeitado dentro de Table.
        logo = Image(_LOGO_PATH, width=target_w, height=target_h, kind='direct')
        logo.hAlign = 'LEFT'
        logo_cell = logo
    except Exception:
        logo_cell = _p("PIMENTA JUDICE<br/><font size='6'>ADVOGADOS ASSOCIADOS</font>",
                       _s('lgfb', fontSize=12, fontName='Helvetica-Bold', textColor=TEXT))

    info = Table(
        [[_p("Relatorio de Carteira",
             _s('rh1', fontSize=9, fontName='Helvetica-Bold', textColor=TEXT, spaceAfter=1))],
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
    """Título grande à esquerda + pill (único bloco escuro do topo) com o nome do cliente."""
    title_cell = Table(
        [[_p("CARTEIRA DE INVESTIMENTOS",
             _s('tt1', fontSize=15, leading=18, fontName='Helvetica-Bold', textColor=TEXT))],
         [_p("Posicoes ativas · Relatorio consolidado",
             _s('tt2', fontSize=9, leading=11, fontName='Helvetica', textColor=GRAY_MID))]],
        colWidths=[110 * mm],
    )
    title_cell.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (0, 0), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    nome_upper = nome_cliente.upper()
    pill = Table(
        [[_p(nome_upper, _s('pill', fontSize=9, fontName='Helvetica-Bold', textColor=WHITE))]],
        colWidths=[58 * mm], cornerRadii=[10, 10, 10, 10],
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


def _section_hdr(label: str, accent=TEAL) -> list:
    """ALL CAPS + linha fina colorida (teal/âmbar conforme a seção) — sem fundo escuro."""
    return [
        Spacer(1, 3 * mm),
        _p(label, _s('sh', fontSize=8, fontName='Helvetica-Bold', textColor=TEXT,
                     spaceBefore=0, spaceAfter=2, tracking=0.5)),
        HRFlowable(width='100%', thickness=1, color=accent, spaceAfter=3),
    ]


def _kpi_card(label: str, value: str, accent=TEAL) -> Table:
    """Card claro com borda fina e acento colorido no topo — sem fundo escuro."""
    rows = [[_p(label, _s('kl', fontSize=7, leading=9, fontName='Helvetica-Bold',
                           textColor=GRAY_MID))],
            [_p(value, _s('kv', fontSize=13, leading=16, fontName='Helvetica-Bold',
                           textColor=TEXT))]]

    inner = Table(rows, colWidths=[40 * mm], cornerRadii=[5, 5, 5, 5])
    inner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), GRAY_ROW),
        ('BOX', (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ('LINEABOVE', (0, 0), (-1, 0), 2.5, accent),
        ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    outer = Table([[inner]], colWidths=[42.5 * mm])
    outer.setStyle(TableStyle([
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING', (0, 0), (-1, -1), 1), ('RIGHTPADDING', (0, 0), (-1, -1), 1),
    ]))
    return outer


def _asset_table(headers: list, rows: list, col_widths: list,
                 accent_cols: list = None, accent=TEAL, tint=TEAL_TINT) -> Table:
    """Tabela clara e arredondada: header com leve tingimento colorido, linhas
    alternadas suaves, total em cinza claro — sem blocos pretos."""
    data = [headers] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1, cornerRadii=[6, 6, 6, 6])

    style = [
        ('BACKGROUND', (0, 0), (-1, 0), tint),
        ('TEXTCOLOR', (0, 0), (-1, 0), TEXT),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('LINEBELOW', (0, 0), (-1, 0), 1, accent),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 7),
        ('RIGHTPADDING', (0, 0), (-1, -1), 7),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [WHITE, GRAY_ROW]),
        ('LINEBELOW', (0, 1), (-1, -2), 0.3, GRAY_BORDER),
        ('BOX', (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]

    if accent_cols:
        for col in accent_cols:
            for r in range(1, len(data)):
                style.append(('TEXTCOLOR', (col, r), (col, r), accent))
                style.append(('FONTNAME', (col, r), (col, r), 'Helvetica-Bold'))

    # Linha de total: cinza claro, sem preto
    if rows and str(rows[-1][0]).startswith('TOTAL'):
        i = len(data) - 1
        style += [
            ('BACKGROUND', (0, i), (-1, i), GRAY_TOTAL),
            ('TEXTCOLOR', (0, i), (-1, i), TEXT),
            ('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
            ('LINEABOVE', (0, i), (-1, i), 0.75, GRAY_BORDER),
        ]
        if accent_cols:
            for col in accent_cols:
                style.append(('TEXTCOLOR', (col, i), (col, i), accent))

    t.setStyle(TableStyle(style))
    return t


def _dark_footer_bar(total_geral: float, exito: float = 0) -> Table:
    """Barra de rodapé (2º e último bloco escuro do documento) com o total em destaque."""
    left_rows = [[_p("TOTAL APLICADO",
                      _s('fl', fontSize=7, leading=9, fontName='Helvetica-Bold',
                         textColor=colors.HexColor('#9CA3AF')))],
                 [_p(_brl(total_geral),
                      _s('fv', fontSize=20, leading=23, fontName='Helvetica-Bold',
                         textColor=WHITE))]]
    if exito > 0:
        left_rows.append([_p(f"Expectativa de exito: {_brl(exito)}",
                              _s('fe', fontSize=8, leading=10, fontName='Helvetica',
                                 textColor=colors.HexColor('#9CA3AF')))])

    left = Table(left_rows, colWidths=[85 * mm])
    left_style = [
        ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (0, 0), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]
    if exito > 0:
        left_style.append(('TOPPADDING', (0, 2), (0, 2), 2))
    left.setStyle(TableStyle(left_style))

    right = _p(
        "Honorarios calculados sobre valores efetivamente recuperados.<br/>"
        "Valores estimados nao constituem garantia de resultado.",
        _s('fn', fontSize=7, fontName='Helvetica',
           textColor=colors.HexColor('#9CA3AF'), alignment=2)
    )

    t = Table([[left, right]], colWidths=[85 * mm, 85 * mm], cornerRadii=[8, 8, 8, 8])
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
        [[_p(_FOOTER_NAME, _s('fn1', fontSize=7, fontName='Helvetica-Bold', textColor=TEXT)),
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
            _kpi_card("TOTAL GERAL", _brl(total_geral), accent=TEAL),
            _kpi_card("IMOBILIARIO", _brl(total_imob), accent=AMBER),
            _kpi_card("FINANCEIRO", _brl(total_fin), accent=TEAL),
            _kpi_card("ATIVOS", str(n_ativos), accent=GRAY_MID),
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
            for el in _section_hdr(f"DEBENTURES — {len(debentures)} POSICOES  |  {_brl(total_deb)}", accent=TEAL):
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
                accent_cols=[4, 5], accent=TEAL, tint=TEAL_TINT,
            ))
            story.append(Spacer(1, 5 * mm))

        # ── 5. Imobiliário ────────────────────────────────────────────────────
        if imobiliario:
            for el in _section_hdr(f"IMOBILIARIO — {len(imobiliario)} POSICOES  |  {_brl(total_imob)}", accent=AMBER):
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
                accent_cols=[2, 3], accent=AMBER, tint=AMBER_TINT,
            ))
            story.append(Spacer(1, 5 * mm))

        # ── 6. Fundos ─────────────────────────────────────────────────────────
        if fundos:
            for el in _section_hdr(f"FUNDOS — {len(fundos)} POSICOES  |  {_brl(total_fundo)}", accent=TEAL):
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
                accent_cols=[2, 3],
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
                accent_cols=[3],
            ))
            story.append(Spacer(1, 5 * mm))

        # ── 8-9. Barra dark com total + rodapé final (nunca separados por quebra de página)
        story.append(KeepTogether([
            Spacer(1, 4 * mm),
            _dark_footer_bar(total_geral, exito),
            Spacer(1, 3 * mm),
            _bottom_footer(),
        ]))

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
