from io import BytesIO
from datetime import datetime
from typing import List
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from sqlalchemy.orm import Session

from app.models.carteira import (
    CarteiraCliente,
    CarteiraDebenturePosicao,
    CarteiraImobiliarioPosicao,
    CarteiraFundoPosicao,
)


class CarteiraRelatoriosService:
    """Service para gerar PDF e XLSX da carteira"""

    @staticmethod
    def gerar_pdf_cliente(db: Session, cliente_id: int) -> bytes:
        """Gera PDF consolidado do cliente com todos os ativos"""

        cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
        if not cliente:
            raise ValueError("Cliente não encontrado")

        debentures = db.query(CarteiraDebenturePosicao).filter(
            CarteiraDebenturePosicao.cliente_id == cliente_id
        ).all()

        imobiliario = db.query(CarteiraImobiliarioPosicao).filter(
            CarteiraImobiliarioPosicao.cliente_id == cliente_id
        ).all()

        fundos = db.query(CarteiraFundoPosicao).filter(
            CarteiraFundoPosicao.cliente_id == cliente_id
        ).all()

        # Criar PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        story = []

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1F2937'),
            spaceAfter=12,
            fontName='Helvetica-Bold'
        )

        # Título
        story.append(Paragraph("📊 CARTEIRA DE ATIVOS", title_style))
        story.append(Paragraph(f"Cliente: <b>{cliente.nome or f'Cliente {cliente.id}'}</b>", styles['Normal']))
        story.append(Paragraph(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M')}", styles['Normal']))
        story.append(Spacer(1, 0.3*inch))

        # KPIs resumidos
        carteira_total = (
            sum(d.valor_aplicado for d in debentures) +
            sum(i.valor_efetivamente_investido for i in imobiliario) +
            sum(f.valor_aplicado for f in fundos)
        )

        valor_atual = (
            sum(d.valor_atual_estimado or 0 for d in debentures) +
            sum(i.valor_esperado_retorno or 0 for i in imobiliario) +
            sum(f.valor_atual_estimado or 0 for f in fundos)
        )

        kpi_data = [
            ['MÉTRICA', 'VALOR'],
            ['Total Investido', f'R$ {carteira_total:,.2f}'],
            ['Valor Atual (Proj.)', f'R$ {valor_atual:,.2f}'],
            ['Variação', f'{((valor_atual - carteira_total) / carteira_total * 100) if carteira_total > 0 else 0:.2f}%'],
            ['Qtd Ativos', f'{len(debentures) + len(imobiliario) + len(fundos)}'],
        ]

        kpi_table = Table(kpi_data, colWidths=[3*inch, 2*inch])
        kpi_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 0.3*inch))

        # Debêntures
        if debentures:
            story.append(Paragraph("💰 DEBÊNTURES", title_style))
            deb_data = [['Cautela', 'Valor Aplicado', 'Valor Atual', 'Variação']]
            for d in debentures:
                var = ((d.valor_atual_estimado - d.valor_aplicado) / d.valor_aplicado * 100) if d.valor_aplicado > 0 else 0
                deb_data.append([
                    d.numero_cautela or '-',
                    f'R$ {d.valor_aplicado:,.0f}',
                    f'R$ {d.valor_atual_estimado:,.0f}',
                    f'{var:.2f}%'
                ])

            deb_table = Table(deb_data, colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch])
            deb_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10B981')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ]))
            story.append(deb_table)
            story.append(Spacer(1, 0.2*inch))

        # Imobiliário
        if imobiliario:
            story.append(Paragraph("🏢 IMOBILIÁRIO", title_style))
            imob_data = [['Empreendimento', 'Investido', 'Retorno Esperado', '%']]
            for i in imobiliario:
                imob_data.append([
                    f'Empreendimento {i.id}',
                    f'R$ {i.valor_efetivamente_investido:,.0f}',
                    f'R$ {i.valor_esperado_retorno:,.0f}',
                    f'{i.percentual_participacao:.1f}%'
                ])

            imob_table = Table(imob_data, colWidths=[2*inch, 1.5*inch, 1.5*inch, 1*inch])
            imob_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F59E0B')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ]))
            story.append(imob_table)
            story.append(Spacer(1, 0.2*inch))

        # Fundos
        if fundos:
            story.append(Paragraph("📈 FUNDOS", title_style))
            fund_data = [['Fundo', 'Investido', 'Valor Atual', 'Cotas']]
            for f in fundos:
                fund_data.append([
                    f'Fundo {f.id}',
                    f'R$ {f.valor_aplicado:,.0f}',
                    f'R$ {f.valor_atual_estimado or 0:,.0f}',
                    f'{f.quantidade_cotas:.0f}'
                ])

            fund_table = Table(fund_data, colWidths=[2*inch, 1.5*inch, 1.5*inch, 1.5*inch])
            fund_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3B82F6')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ]))
            story.append(fund_table)

        doc.build(story)
        return buffer.getvalue()

    @staticmethod
    def exportar_xlsx_qualificacao(db: Session, cliente_ids: List[int]) -> bytes:
        """Exporta qualificação de clientes em XLSX"""

        wb = Workbook()
        ws = wb.active
        ws.title = "Qualificação"

        # Headers
        headers = ['Cliente', 'Debêntures', 'Imobiliário', 'Fundos', 'Total Investido', 'Valor Atual']
        ws.append(headers)

        header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF")

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Dados
        for cliente_id in cliente_ids:
            cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
            if not cliente:
                continue

            debentures = db.query(CarteiraDebenturePosicao).filter(
                CarteiraDebenturePosicao.cliente_id == cliente_id
            ).count()

            imobiliario = db.query(CarteiraImobiliarioPosicao).filter(
                CarteiraImobiliarioPosicao.cliente_id == cliente_id
            ).count()

            fundos = db.query(CarteiraFundoPosicao).filter(
                CarteiraFundoPosicao.cliente_id == cliente_id
            ).count()

            total_investido = (
                db.query(CarteiraDebenturePosicao).filter(
                    CarteiraDebenturePosicao.cliente_id == cliente_id
                ).with_entities(
                    db.func.sum(CarteiraDebenturePosicao.valor_aplicado)
                ).scalar() or 0
            ) + (
                db.query(CarteiraImobiliarioPosicao).filter(
                    CarteiraImobiliarioPosicao.cliente_id == cliente_id
                ).with_entities(
                    db.func.sum(CarteiraImobiliarioPosicao.valor_efetivamente_investido)
                ).scalar() or 0
            ) + (
                db.query(CarteiraFundoPosicao).filter(
                    CarteiraFundoPosicao.cliente_id == cliente_id
                ).with_entities(
                    db.func.sum(CarteiraFundoPosicao.valor_aplicado)
                ).scalar() or 0
            )

            valor_atual = (
                db.query(CarteiraDebenturePosicao).filter(
                    CarteiraDebenturePosicao.cliente_id == cliente_id
                ).with_entities(
                    db.func.sum(CarteiraDebenturePosicao.valor_atual_estimado)
                ).scalar() or 0
            )

            ws.append([
                cliente.nome or f"Cliente {cliente_id}",
                debentures,
                imobiliario,
                fundos,
                total_investido,
                valor_atual,
            ])

        # Formatar colunas
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 12
        ws.column_dimensions['C'].width = 12
        ws.column_dimensions['D'].width = 12
        ws.column_dimensions['E'].width = 15
        ws.column_dimensions['F'].width = 15

        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()
