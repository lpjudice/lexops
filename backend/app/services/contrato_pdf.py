"""
Gerador de Contrato de Honorários Advocatícios em PDF.
Baseado no modelo padrão de Pimenta Júdice Advogados.

Partes customizáveis:
  - Contratante (nome, qualificação, CPF/CNPJ, endereço, email)
  - Objeto (tipo predefinido ou texto livre)
  - Honorários (valor, data vencimento, condição, % êxito)
  - Data do contrato
"""

import io
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)

_LOGO_PATH = Path(__file__).parent.parent.parent / "logo.png"

DARK = colors.HexColor("#1d1e20")
TEAL = colors.HexColor("#00b090")
MID_GRAY = colors.HexColor("#6b7280")

# ── OBJETO PRE-DEFINIDO: PPS ──────────────────────────────────────────────────

OBJETO_PPS = (
    "Trata-se de contratação para planejar, desenhar e estruturar o conjunto de atos necessários "
    "à organização patrimonial e sucessória da família imediata da CONTRATANTE, compreendendo a "
    "constituição das holdings e reorganizações indispensáveis à efetivação da doação da matriarca "
    "aos filhos, com vistas à proteção patrimonial e à eficiência tributária, sempre nos limites da "
    "legislação aplicável.\n\n"
    "A presente contratação não abrange — ainda que eventualmente sejam criadas holdings "
    "individualizadas para cada filho como veículos de recebimento das doações — o planejamento "
    "patrimonial, societário, sucessório ou tributário próprio de cada donatário ou de seus "
    "respectivos núcleos familiares, tampouco a finalização das estruturas internas dessas "
    "sociedades, que depende de escopo exclusivo para tal fim.\n\n"
    "Este contrato inclui:\n\n"
    "(i) a análise dos documentos relativos ao patrimônio da família, abrangendo bens móveis, "
    "imóveis urbanos e rurais, participações societárias e demais ativos relevantes, incluindo "
    "também a revisão e higienização documental de imóveis (matrículas, averbações, "
    "confrontações, georreferenciamento);\n\n"
    "(ii) a elaboração de estratégia de planejamento sucessório que pode (ou não) conter: "
    "testamento; análise tributária; economia fiscal; sugestão de ajustes contábeis operacionais; "
    "instituição ou reserva de usufruto; estudo comparativo de custos tributários entre doação, "
    "integralização, compra e venda, arrendamento, usufruto ou outros modelos; elaboração de "
    "minutas societárias, civis e familiares; protocolos familiares; conselhos de família; "
    "governança corporativa; formação de conselhos consultivos ou de administração; acordo de "
    "sócios; reorganizações societárias; instituições de diferentes classes de quotas ou ações; "
    "fusões e/ou cisões; estruturas tipo \"drop-down\"; criação de sociedades-veículo (para "
    "projetos específicos de segregação de risco); desenho de plano de sucessão em empresas "
    "operacionais; instrumentos de fidúcia; apoio estratégico (e não executivo) em cartórios de "
    "notas e de registro de imóveis; acompanhamento da implementação da estratégia; avaliações "
    "sobre a conveniência de seguros de vida com finalidade sucessória ou equalizatória; e "
    "consultoria tributária diretamente relacionada ao projeto e enquanto durar o planejamento. "
    "Essa cláusula não é exaustiva, mas não significa que todas as estratégias são aplicáveis ao "
    "caso;\n\n"
    "(iii) a prática de todos os atos inerentes ao exercício da advocacia para consecução do "
    "objeto, caracterizando-se as obrigações do CONTRATADO como de meio, nos termos do Estatuto "
    "da OAB.\n\n"
    "O CONTRATADO compromete-se, ainda, a ajuizar as eventuais ações judiciais necessárias ao "
    "redor da formação da holding familiar, especialmente aquelas voltadas à declaração de não "
    "incidência, inexigibilidade ou redução de ITCMD e/ou ITBI, quando aplicável e quando "
    "escolhida pelo CONTRATANTE. Ressalva-se, contudo, que a obrigação de atuação judicial se "
    "limita ao ajuizamento de demandas em que o CONTRATANTE figure como polo ativo, não estando "
    "abrangidas ações administrativas ou judiciais supervenientes eventualmente decorrentes do "
    "tema ora contratado."
)

OBJETOS: dict[str, str] = {
    "PPS": OBJETO_PPS,
}

# ── CLÁUSULAS FIXAS ───────────────────────────────────────────────────────────

CLAUSULA_RESCISAO = (
    "O presente contrato vigorará por prazo indeterminado até a finalização do planejamento, "
    "com início na data de sua assinatura, podendo ser rescindido por qualquer das partes somente "
    "por motivo justificado, nos termos desta cláusula e de seus subitens. A rescisão contratual "
    "poderá ocorrer de pleno direito, mediante notificação extrajudicial ou judicial, nas seguintes "
    "hipóteses:\n\n"
    "I – <b>Rescisão Justificada</b>: por iniciativa do CONTRATADO ou do CONTRATANTE, em razão do "
    "inadimplemento de qualquer obrigação contratual, hipótese em que o CONTRATADO fará jus aos "
    "honorários proporcionais aos serviços já executados, incluindo, quando cabível, os honorários "
    "de êxito.\n\n"
    "<b>Parágrafo Único</b> – Para o exercício válido da rescisão justificada, a parte que a invocar "
    "deverá estar regularmente adimplente com todas as suas obrigações contratuais. Ressalta-se que "
    "a revogação ou rescisão imotivada por parte do CONTRATANTE, uma vez iniciado o trabalho "
    "profissional, não suspenderá nem afastará o dever de pagamento integral dos honorários "
    "contratados, inclusive os de êxito, bem como o pró-labore, ainda que o encerramento da "
    "prestação de serviços ocorra antes da conclusão definitiva da demanda, projeto ou planejamento."
)

CLAUSULA_MULTA = (
    "As partes estabelecem que havendo atraso no pagamento dos honorários, ensejará multa no valor "
    "de 10% (dez por cento) do montante devido e serão cobrados juros de mora na proporção de 1% "
    "(um por cento) ao mês, devidamente atualizados."
)

CLAUSULA_RESPONSABILIDADE = (
    "É obrigação da CONTRATANTE, sempre que solicitada, entregar, fornecer ou disponibilizar ao "
    "CONTRATADO todos os documentos necessários, provas, informações e subsídios, em tempo hábil, "
    "para que este possa cumprir o objeto do presente contrato. Qualquer omissão ou negligência "
    "por parte da CONTRATANTE será de sua inteira responsabilidade.\n\n"
    "Todas as custas, taxas judiciárias, certidões e emolumentos necessários serão de "
    "responsabilidade do CONTRATANTE, assim como também o serão os custos com fotocópias, "
    "reconhecimento de firmas, autenticação de documentos, certidões, porte de correio, custos "
    "epistolares e/ou cartoriais, que, caso adiantados pelo CONTRATADO, serão reembolsados "
    "mediante a apresentação de Relatório de Reembolso acompanhado de recibos comprobatórios.\n\n"
    "O CONTRATADO não será responsabilizado caso resultem danos por não tomar conhecimento de "
    "informações e documentos substanciais para a sua atividade ou em decorrência da "
    "impossibilidade de contato com a CONTRATANTE, que deverá manter atualizadas quaisquer "
    "informações relevantes para a demanda, bem como as informações cadastrais fornecidas.\n\n"
    "O CONTRATADO, ainda, não será responsabilizado por quaisquer danos que sobrevierem das "
    "demandas e/ou trabalhos que patrocinar, cabendo-lhe tão somente o emprego diligente de seus "
    "conhecimentos, meios e técnicas para a defesa dos interesses da CONTRATANTE, inexistindo "
    "qualquer garantia de resultado."
)

CLAUSULA_FORO = (
    "Para dirimir quaisquer controvérsias oriundas deste contrato, as partes elegem o foro da "
    "comarca de Vitória/ES. Por estarem assim justos e contratados, assinam, via assinatura "
    "eletrônica, nos moldes do art. 10 da MP 2.200/01 em vigor no Brasil, o \"De Acordo\" com o "
    "presente CONTRATO, o que também vale para as testemunhas indicadas, sendo todos os documentos "
    "de igual teor e redigidos em {data_contrato}."
)


def _estilos():
    return {
        "titulo": ParagraphStyle(
            "titulo", fontName="Helvetica-Bold", fontSize=13, textColor=DARK,
            alignment=TA_CENTER, spaceAfter=4
        ),
        "clausula_titulo": ParagraphStyle(
            "clausula_titulo", fontName="Helvetica-Bold", fontSize=10.5, textColor=DARK,
            spaceBefore=16, spaceAfter=6, alignment=TA_CENTER
        ),
        "corpo": ParagraphStyle(
            "corpo", fontName="Helvetica", fontSize=10, textColor=DARK,
            leading=15, spaceAfter=6, alignment=TA_JUSTIFY
        ),
        "parte_label": ParagraphStyle(
            "parte_label", fontName="Helvetica-Bold", fontSize=10, textColor=DARK,
            spaceAfter=2, alignment=TA_LEFT
        ),
        "assinatura_label": ParagraphStyle(
            "assinatura_label", fontName="Helvetica-Bold", fontSize=9.5, textColor=DARK,
            alignment=TA_CENTER, spaceAfter=2
        ),
        "assinatura_sub": ParagraphStyle(
            "assinatura_sub", fontName="Helvetica", fontSize=9, textColor=MID_GRAY,
            alignment=TA_CENTER
        ),
    }


def gerar_contrato(
    contratante_nome: str,
    contratante_qualificacao: str,
    contratante_cpf_cnpj: str,
    contratante_endereco: str,
    contratante_email: str,
    objeto_tipo: str,
    objeto_texto_livre: str,
    valor_honorarios: str,
    data_vencimento: str,
    condicao_pagamento: str,
    percentual_exito: str,
    data_contrato: date | None = None,
) -> bytes:
    """Gera o PDF do contrato de honorários. Retorna bytes."""

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=3 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title=f"Contrato de Honorários — {contratante_nome}",
    )

    st = _estilos()
    story = []
    data_str = (data_contrato or date.today()).strftime("%d de %B de %Y")

    # ── Cabeçalho com logo ────────────────────────────────────────────────────
    if _LOGO_PATH.exists():
        img = Image(str(_LOGO_PATH))
        orig_w, orig_h = img.imageWidth, img.imageHeight
        max_h = 2.2 * cm
        ratio = max_h / orig_h
        img.drawWidth = orig_w * ratio
        img.drawHeight = max_h
        img.hAlign = "CENTER"
        story.append(img)
        story.append(Spacer(1, 0.3 * cm))
    else:
        story.append(Paragraph("PIMENTA JÚDICE ADVOGADOS", ParagraphStyle(
            "hdr", fontName="Helvetica-Bold", fontSize=10, textColor=TEAL,
            spaceAfter=4, alignment=TA_CENTER, letterSpacing=2
        )))

    story.append(HRFlowable(width="100%", thickness=0.5, color=TEAL, spaceAfter=14))

    story.append(Paragraph("CONTRATO DE HONORÁRIOS ADVOCATÍCIOS", st["titulo"]))
    story.append(HRFlowable(width="50%", thickness=0.5, color=colors.HexColor("#e5e7eb"),
                             spaceAfter=14, hAlign="CENTER"))

    # ── PARTES ────────────────────────────────────────────────────────────────
    story.append(Paragraph("<b>CONTRATANTE:</b>", st["parte_label"]))
    story.append(Paragraph(
        f"{contratante_nome}, {contratante_qualificacao}, "
        f"com {contratante_cpf_cnpj}, "
        f"residente/domiciliado em {contratante_endereco}"
        f"{', e-mail ' + contratante_email if contratante_email else ''}, "
        "doravante denominado(a) como <b>CONTRATANTE</b>;",
        st["corpo"]
    ))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("<b>CONTRATADO:</b>", st["parte_label"]))
    story.append(Paragraph(
        "PIMENTA JÚDICE ADVOGADOS ASSOCIADOS, inscrita no CNPJ sob o n.º 10.901.611/0001-64, "
        "representada por seu respectivo representante Dr. <b>LUCAS PIMENTA JÚDICE</b>, "
        "brasileiro, casado, advogado inscrito na OAB/ES sob o n.º 14.477, portador do CPF "
        "n.º 101.404.477-41, com endereço comercial na Rua João da Cruz, n.º 25, Conjunto 401, "
        "Praia do Canto, Vitória/ES, CEP 29.055-620, e e-mail institucional "
        "pj@pimentajudice.com.br, doravante denominado <b>CONTRATADO</b>;",
        st["corpo"]
    ))

    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "As partes acima identificadas têm, entre si, justo e acertado o presente Contrato de "
        "Honorários Advocatícios, que se regerá pelas cláusulas e pelas condições a seguir "
        "descritas.",
        st["corpo"]
    ))

    # ── CLÁUSULA PRIMEIRA — OBJETO ─────────────────────────────────────────────
    story.append(Paragraph("CLÁUSULA PRIMEIRA – DO OBJETO DO CONTRATO", st["clausula_titulo"]))
    objeto_texto = OBJETOS.get(objeto_tipo, objeto_texto_livre or "")
    for paragrafo in objeto_texto.split("\n\n"):
        paragrafo = paragrafo.strip()
        if paragrafo:
            story.append(Paragraph(paragrafo.replace("\n", " "), st["corpo"]))

    # ── CLÁUSULA SEGUNDA — HONORÁRIOS ─────────────────────────────────────────
    story.append(Paragraph("CLÁUSULA SEGUNDA – DOS HONORÁRIOS", st["clausula_titulo"]))

    exito_pct = percentual_exito.strip() if percentual_exito else "15%"

    corpo_honorarios = (
        f"A CONTRATANTE pagará ao CONTRATADO, a título de honorários de \"<i>pro-labore</i>\", "
        f"o valor de <b>R$ {valor_honorarios}</b>, "
        f"a ser pago {condicao_pagamento or 'conforme acordado entre as partes'}."
        f" Vencimento: {data_vencimento or 'a definir'}.\n\n"
        "O pagamento deverá ser realizado via PIX ou TED na conta abaixo identificada:\n\n"
        "Pimenta Judice Advogados Associados SC | CNPJ: 10.901.611/0001-64 (chave PIX)\n"
        "Banco Inter SA (077) | Agência: 0001 | Conta Corrente: 1812719-3\n\n"
        f"Adicionalmente, e na hipótese de êxito de demanda judicial eventualmente ajuizada "
        f"pelo CONTRATADO representando a CONTRATANTE, o CONTRATADO fará jus a honorários de "
        f"êxito correspondentes a {exito_pct} sobre o valor efetivamente recuperado e/ou "
        "economizado frente à expectativa inicial de pagamento."
    )
    for paragrafo in corpo_honorarios.split("\n\n"):
        paragrafo = paragrafo.strip()
        if paragrafo:
            story.append(Paragraph(paragrafo.replace("\n", " "), st["corpo"]))

    story.append(PageBreak())

    # ── CLÁUSULA TERCEIRA — VIGÊNCIA ──────────────────────────────────────────
    story.append(Paragraph("CLÁUSULA TERCEIRA – DA VIGÊNCIA E RESCISÃO", st["clausula_titulo"]))
    for paragrafo in CLAUSULA_RESCISAO.split("\n\n"):
        paragrafo = paragrafo.strip()
        if paragrafo:
            story.append(Paragraph(paragrafo.replace("\n", " "), st["corpo"]))

    # ── CLÁUSULA QUARTA — MULTA ───────────────────────────────────────────────
    story.append(Paragraph("CLÁUSULA QUARTA – DA EVENTUAL MULTA", st["clausula_titulo"]))
    story.append(Paragraph(CLAUSULA_MULTA, st["corpo"]))

    # ── CLÁUSULA QUINTA — RESPONSABILIDADE ───────────────────────────────────
    story.append(Paragraph("CLÁUSULA QUINTA – DA RESPONSABILIDADE", st["clausula_titulo"]))
    for paragrafo in CLAUSULA_RESPONSABILIDADE.split("\n\n"):
        paragrafo = paragrafo.strip()
        if paragrafo:
            story.append(Paragraph(paragrafo.replace("\n", " "), st["corpo"]))

    # ── CLÁUSULA SEXTA — FORO ────────────────────────────────────────────────
    story.append(Paragraph("CLÁUSULA SEXTA – DO FORO E ASSINATURA DIGITAL", st["clausula_titulo"]))
    story.append(Paragraph(
        CLAUSULA_FORO.format(data_contrato=data_str),
        st["corpo"]
    ))

    # ── ASSINATURAS ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 1.5 * cm))
    story.append(HRFlowable(width="100%", thickness=0.3, color=colors.HexColor("#e5e7eb"),
                             spaceAfter=12))

    assinatura_data = [
        [
            _bloco_assinatura(st, "LUCAS PIMENTA JÚDICE", "CONTRATADO — OAB/ES 14.477"),
            _bloco_assinatura(st, contratante_nome.upper(), "CONTRATANTE"),
        ]
    ]
    tabela_ass = Table(assinatura_data, colWidths=[8 * cm, 8 * cm])
    tabela_ass.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether([tabela_ass]))

    story.append(Spacer(1, 0.8 * cm))
    story.append(Paragraph("Testemunhas conforme assinaturas digitais", ParagraphStyle(
        "test", fontName="Helvetica", fontSize=9, textColor=MID_GRAY, alignment=TA_CENTER
    )))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def _bloco_assinatura(st: dict, nome: str, papel: str):
    # Return a list of Paragraphs — KeepTogether cannot be used inside Table cells
    return [
        Paragraph("_" * 38, ParagraphStyle(
            "linha", fontName="Helvetica", fontSize=10, textColor=DARK, alignment=TA_CENTER, spaceAfter=4
        )),
        Paragraph(nome, st["assinatura_label"]),
        Paragraph(papel, st["assinatura_sub"]),
    ]
