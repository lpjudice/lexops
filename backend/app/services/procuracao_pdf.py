"""
Gerador de Instrumento de Procuração (PDF + versão HTML editável no Google Docs).
Mesmo padrão visual do Contrato de Honorários (contrato_pdf.py).

Partes customizáveis:
  - Outorgante (nome, nacionalidade/estado civil/profissão, CPF/CNPJ, endereço, email)
  - Outorgado(s) — lista dinâmica de advogado(s): nome, OAB, CPF
  - Endereço profissional (do escritório) dos outorgados — pré-preenchido, editável
  - Poderes: cláusula geral "ad judicia et extra" (pode ser desligada por completo),
    com os poderes especiais escolhidos individualmente + texto adicional livre
  - Finalidade específica (texto livre, opcional)
  - Validade (opcional — se vazia, procuração não tem prazo)
  - Data da procuração

O PDF tenta caber em 1 página: a fonte do corpo começa em 11pt e vai reduzindo
(10.5, depois 10) até caber; 10pt é o piso — abaixo disso aceita 2 páginas.
"""

import io
from datetime import date
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
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

# Tamanhos de fonte do corpo tentados em ordem até o PDF caber em 1 página; o
# último (piso) é aceito mesmo que ainda resulte em 2 páginas.
TAMANHOS_FONTE_CORPO = (11.0, 10.5, 10.0)

# Base da cláusula "ad judicia et extra" — formulação genérica amplamente usada em
# procurações no Brasil (poderes gerais para o foro em geral). Os "poderes especiais"
# são compostos à parte, conforme a seleção do usuário (ver PODERES_ESPECIAIS_OPCOES).
PODERES_GERAIS_BASE = (
    "Pelo presente instrumento particular de mandato, o(a) OUTORGANTE nomeia e constitui "
    "seu(s) bastante procurador(es) o(s) OUTORGADO(S) acima qualificado(s), a quem confere "
    "amplos, gerais e ilimitados poderes para o foro em geral, com a cláusula \"ad judicia "
    "et extra\", em qualquer Juízo, Instância ou Tribunal, podendo propor contra quem de "
    "direito as ações competentes e defendê-lo(a) nas contrárias, seguindo umas e outras, "
    "até final decisão, usando os recursos legais e acompanhando-os"
)

# Chave → texto do poder especial (chaves espelham PoderEspecial em schemas/contrato.py).
PODERES_ESPECIAIS_OPCOES: dict[str, str] = {
    "confessar": "confessar",
    "desistir": "desistir",
    "transigir": "transigir",
    "firmar_acordos": "firmar compromissos ou acordos",
    "receber_quitacao": "receber e dar quitação",
    "substabelecer": "substabelecer esta a outrem, com ou sem reserva de iguais poderes",
}

CLAUSULA_ASSINATURA = (
    "E por estar assim justo, firma o(a) OUTORGANTE a presente PROCURAÇÃO, "
    "redigida em {data_procuracao}."
)


_MESES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _data_por_extenso(d: date) -> str:
    """'%d de %B de %Y' depende do locale do processo (pode sair em inglês no
    servidor) — usa nomes de mês fixos em português para não depender disso."""
    return f"{d.day:02d} de {_MESES_PT[d.month - 1]} de {d.year}"


def _compor_qualificacao(nacionalidade: str, estado_civil: str, profissao: str) -> str:
    partes = [p.strip() for p in (nacionalidade, estado_civil, profissao) if p and p.strip()]
    return ", ".join(partes)


def _compor_clausula_poderes(poderes_especiais: list[str], poderes_adicionais: str) -> str:
    """Monta a frase completa da cláusula ad judicia, incluindo só os poderes
    especiais selecionados + texto adicional livre (na sequência da mesma frase)."""
    extras = [PODERES_ESPECIAIS_OPCOES[k] for k in poderes_especiais if k in PODERES_ESPECIAIS_OPCOES]
    if poderes_adicionais.strip():
        extras.append(poderes_adicionais.strip())
    frase = PODERES_GERAIS_BASE
    if extras:
        frase += ", conferindo-lhe, ainda, poderes especiais para " + ", ".join(extras)
    frase += ", agindo em conjunto ou separadamente, dando tudo por bom, firme e valioso."
    return frase


def _linha_outorgante(
    outorgante_nome: str, outorgante_nacionalidade: str, outorgante_estado_civil: str,
    outorgante_profissao: str, outorgante_cpf_cnpj: str, outorgante_endereco: str,
    outorgante_email: str,
) -> str:
    qualificacao = _compor_qualificacao(outorgante_nacionalidade, outorgante_estado_civil, outorgante_profissao)
    partes = [outorgante_nome.strip().upper()]
    if qualificacao:
        partes.append(qualificacao)
    linha = ", ".join(partes)
    if outorgante_cpf_cnpj:
        linha += f", com {outorgante_cpf_cnpj}"
    if outorgante_endereco:
        linha += f", residente/domiciliado em {outorgante_endereco}"
    if outorgante_email:
        linha += f", e-mail {outorgante_email}"
    linha += ", doravante denominado(a) OUTORGANTE;"
    return linha


def _linha_outorgado(adv: dict, endereco_escritorio: str) -> str | None:
    nome = (adv.get("nome") or "").strip()
    if not nome:
        return None
    oab = (adv.get("oab") or "").strip()
    cpf = (adv.get("cpf") or "").strip()
    partes = [f"{nome.upper()}, advogado(a)"]
    if oab:
        partes.append(f"inscrito(a) na OAB sob o n.º {oab}")
    if cpf:
        partes.append(f"portador(a) do CPF n.º {cpf}")
    partes.append(f"com endereço profissional em {endereco_escritorio}")
    return ", ".join(partes) + ";"


def _capitalizar_primeira(s: str) -> str:
    s = s.strip()
    return s[0].upper() + s[1:] if s else s


def _finalidade_paragrafos(finalidade: str, data_validade: date | None) -> list[str]:
    """Parágrafos da finalidade (1ª letra maiúscula). Se houver validade, ela entra
    em negrito ao final do último parágrafo, na mesma linha — só quando há
    finalidade; sem finalidade, a validade vira parágrafo à parte (ver chamadores)."""
    texto = _capitalizar_primeira(finalidade)
    paragrafos = [p.strip().replace("\n", " ") for p in texto.split("\n\n") if p.strip()]
    if paragrafos and data_validade:
        ultimo = paragrafos[-1].rstrip(".")
        paragrafos[-1] = f"{ultimo}. Válida até <b>{_data_por_extenso(data_validade)}</b>."
    return paragrafos


def _estilos(corpo_size: float = 10.5):
    return {
        "titulo": ParagraphStyle(
            "titulo", fontName="Helvetica-Bold", fontSize=13, textColor=DARK,
            alignment=TA_CENTER, spaceAfter=4
        ),
        "secao_titulo": ParagraphStyle(
            "secao_titulo", fontName="Helvetica-Bold", fontSize=corpo_size + 0.5, textColor=DARK,
            spaceBefore=14, spaceAfter=5, alignment=TA_CENTER
        ),
        "corpo": ParagraphStyle(
            "corpo", fontName="Helvetica", fontSize=corpo_size, textColor=DARK,
            leading=corpo_size * 1.45, spaceAfter=5, alignment=TA_JUSTIFY
        ),
        "parte_label": ParagraphStyle(
            "parte_label", fontName="Helvetica-Bold", fontSize=corpo_size, textColor=DARK,
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


def _num_paginas(pdf_bytes: bytes) -> int:
    try:
        return len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    except Exception:
        return 1


def _montar_pdf(
    corpo_size: float,
    outorgante_nome: str,
    outorgante_nacionalidade: str,
    outorgante_estado_civil: str,
    outorgante_profissao: str,
    outorgante_cpf_cnpj: str,
    outorgante_endereco: str,
    outorgante_email: str,
    outorgados: list[dict],
    endereco_escritorio: str,
    incluir_poderes_gerais: bool,
    poderes_especiais: list[str] | None,
    poderes_adicionais: str,
    finalidade: str,
    data_validade: date | None,
    data_procuracao: date | None,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=3 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title=f"Procuração — {outorgante_nome}",
    )

    st = _estilos(corpo_size)
    story = []
    data_str = _data_por_extenso(data_procuracao or date.today())

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
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("PROCURAÇÃO", st["titulo"]))
    story.append(HRFlowable(width="50%", thickness=0.5, color=colors.HexColor("#e5e7eb"),
                             spaceAfter=14, hAlign="CENTER"))

    # ── OUTORGANTE ────────────────────────────────────────────────────────────
    story.append(Paragraph("<b>OUTORGANTE:</b>", st["parte_label"]))
    story.append(Paragraph(
        _linha_outorgante(
            outorgante_nome, outorgante_nacionalidade, outorgante_estado_civil,
            outorgante_profissao, outorgante_cpf_cnpj, outorgante_endereco, outorgante_email,
        ),
        st["corpo"]
    ))
    story.append(Spacer(1, 0.2 * cm))

    # ── OUTORGADO(S) — dinâmico, um ou mais advogados ───────────────────────────
    story.append(Paragraph("<b>OUTORGADO(S):</b>", st["parte_label"]))
    for adv in outorgados:
        linha = _linha_outorgado(adv, endereco_escritorio)
        if linha:
            story.append(Paragraph(linha, st["corpo"]))

    story.append(Spacer(1, 0.3 * cm))

    # ── PODERES ───────────────────────────────────────────────────────────────
    story.append(Paragraph("DOS PODERES", st["secao_titulo"]))
    tem_finalidade = bool(finalidade.strip())
    if incluir_poderes_gerais:
        story.append(Paragraph(_compor_clausula_poderes(poderes_especiais or [], poderes_adicionais), st["corpo"]))
        if tem_finalidade:
            story.append(Spacer(1, 0.2 * cm))
            story.append(Paragraph("DA FINALIDADE ESPECÍFICA", st["secao_titulo"]))
            for paragrafo in _finalidade_paragrafos(finalidade, data_validade):
                story.append(Paragraph(paragrafo, st["corpo"]))
        elif data_validade:
            story.append(Paragraph(
                f"A presente procuração terá validade até <b>{_data_por_extenso(data_validade)}</b>.",
                st["corpo"]
            ))
    else:
        # Sem cláusula geral — os poderes são só o que estiver em `finalidade`.
        if tem_finalidade:
            for paragrafo in _finalidade_paragrafos(finalidade, data_validade):
                story.append(Paragraph(paragrafo, st["corpo"]))
        else:
            story.append(Paragraph("—", st["corpo"]))
            if data_validade:
                story.append(Paragraph(
                    f"A presente procuração terá validade até <b>{_data_por_extenso(data_validade)}</b>.",
                    st["corpo"]
                ))

    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        CLAUSULA_ASSINATURA.format(data_procuracao=data_str),
        st["corpo"]
    ))

    # ── ASSINATURA (só o outorgante — mandato unilateral) ───────────────────────
    story.append(Spacer(1, 1.5 * cm))
    story.append(HRFlowable(width="100%", thickness=0.3, color=colors.HexColor("#e5e7eb"),
                             spaceAfter=12))

    assinatura_data = [[_bloco_assinatura(st, outorgante_nome.upper(), "OUTORGANTE")]]
    tabela_ass = Table(assinatura_data, colWidths=[16 * cm])
    tabela_ass.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(KeepTogether([tabela_ass]))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def gerar_procuracao(
    outorgante_nome: str,
    outorgante_nacionalidade: str,
    outorgante_estado_civil: str,
    outorgante_profissao: str,
    outorgante_cpf_cnpj: str,
    outorgante_endereco: str,
    outorgante_email: str,
    outorgados: list[dict],
    endereco_escritorio: str,
    incluir_poderes_gerais: bool = True,
    poderes_especiais: list[str] | None = None,
    poderes_adicionais: str = "",
    finalidade: str = "",
    data_validade: date | None = None,
    data_procuracao: date | None = None,
) -> bytes:
    """
    Gera o PDF do instrumento de procuração. Retorna bytes.
    `outorgados`: lista de {"nome": str, "oab": str, "cpf": str}.
    Tenta caber em 1 página, reduzindo a fonte do corpo até o piso (10pt); se
    mesmo assim não couber, aceita 2 páginas nessa fonte mínima.
    """
    kwargs = dict(
        outorgante_nome=outorgante_nome, outorgante_nacionalidade=outorgante_nacionalidade,
        outorgante_estado_civil=outorgante_estado_civil, outorgante_profissao=outorgante_profissao,
        outorgante_cpf_cnpj=outorgante_cpf_cnpj, outorgante_endereco=outorgante_endereco,
        outorgante_email=outorgante_email, outorgados=outorgados, endereco_escritorio=endereco_escritorio,
        incluir_poderes_gerais=incluir_poderes_gerais, poderes_especiais=poderes_especiais,
        poderes_adicionais=poderes_adicionais, finalidade=finalidade, data_validade=data_validade,
        data_procuracao=data_procuracao,
    )
    pdf_bytes = _montar_pdf(TAMANHOS_FONTE_CORPO[0], **kwargs)
    for tamanho in TAMANHOS_FONTE_CORPO[1:]:
        if _num_paginas(pdf_bytes) <= 1:
            break
        pdf_bytes = _montar_pdf(tamanho, **kwargs)
    return pdf_bytes


def _bloco_assinatura(st: dict, nome: str, papel: str):
    return [
        Paragraph("_" * 38, ParagraphStyle(
            "linha", fontName="Helvetica", fontSize=10, textColor=DARK, alignment=TA_CENTER, spaceAfter=4
        )),
        Paragraph(nome, st["assinatura_label"]),
        Paragraph(papel, st["assinatura_sub"]),
    ]


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def gerar_procuracao_html(
    outorgante_nome: str,
    outorgante_nacionalidade: str,
    outorgante_estado_civil: str,
    outorgante_profissao: str,
    outorgante_cpf_cnpj: str,
    outorgante_endereco: str,
    outorgante_email: str,
    outorgados: list[dict],
    endereco_escritorio: str,
    incluir_poderes_gerais: bool = True,
    poderes_especiais: list[str] | None = None,
    poderes_adicionais: str = "",
    finalidade: str = "",
    data_validade: date | None = None,
    data_procuracao: date | None = None,
    assinantes: list[tuple[str, str]] | None = None,
) -> bytes:
    """
    Mesmo conteúdo de `gerar_procuracao`, como HTML autocontido (logo embutida em
    base64, fonte Archivo, texto justificado) — usado para subir ao Drive com
    conversão automática para Google Docs (versão editável pelo usuário).

    Convenção: essa página é um ponto de partida editável, não fica sincronizada
    de volta com o PDF gerado pelo sistema — mudanças aqui não alteram o PDF já
    anexado ao contrato/procuração. Para usar uma versão editada, baixe como PDF
    no próprio Google Docs e faça upload dela no sistema (substituindo o anexo).
    """
    import base64

    data_str = _data_por_extenso(data_procuracao or date.today())
    assinantes = assinantes or [(outorgante_nome.upper(), "OUTORGANTE")]

    logo_img = ""
    if _LOGO_PATH.exists():
        logo_b64 = base64.b64encode(_LOGO_PATH.read_bytes()).decode()
        logo_img = (
            f'<img src="data:image/png;base64,{logo_b64}" alt="Pimenta Júdice" '
            f'style="display:block; margin:0 auto; height:56px;">'
        )

    corpo_style = "font-family:'Archivo', sans-serif; font-weight:200; font-size:11pt; color:#1d1e20;"
    justificado = "text-align:justify; margin:0 0 10px 0;"

    partes: list[str] = [
        f'<html><body style="{corpo_style} max-width:720px; margin:0 auto;">',
        logo_img,
        '<div style="height:2px; background:#00b090; margin:12px 0 18px 0;"></div>',
        '<h1 style="text-align:center; font-weight:700; font-size:15pt; letter-spacing:1px;">PROCURAÇÃO</h1>',
        '<div style="height:1px; background:#e5e7eb; width:50%; margin:0 auto 18px auto;"></div>',
        f'<p style="{justificado}"><b>OUTORGANTE:</b><br>' + _esc(_linha_outorgante(
            outorgante_nome, outorgante_nacionalidade, outorgante_estado_civil,
            outorgante_profissao, outorgante_cpf_cnpj, outorgante_endereco, outorgante_email,
        )) + '</p>',
        f'<p style="{justificado}"><b>OUTORGADO(S):</b><br>',
    ]
    for adv in outorgados:
        linha = _linha_outorgado(adv, endereco_escritorio)
        if linha:
            partes.append(_esc(linha) + "<br>")
    partes.append("</p>")

    partes.append('<h3 style="text-align:center; font-weight:700;">DOS PODERES</h3>')
    tem_finalidade = bool(finalidade.strip())
    if incluir_poderes_gerais:
        partes.append(f'<p style="{justificado}">' + _esc(_compor_clausula_poderes(poderes_especiais or [], poderes_adicionais)) + "</p>")
        if tem_finalidade:
            partes.append('<h3 style="text-align:center; font-weight:700;">DA FINALIDADE ESPECÍFICA</h3>')
            for paragrafo in _finalidade_paragrafos(finalidade, data_validade):
                partes.append(f'<p style="{justificado}">' + _html_negrito(paragrafo) + "</p>")
        elif data_validade:
            partes.append(f'<p style="{justificado}">A presente procuração terá validade até '
                           f'<b>{_data_por_extenso(data_validade)}</b>.</p>')
    else:
        if tem_finalidade:
            for paragrafo in _finalidade_paragrafos(finalidade, data_validade):
                partes.append(f'<p style="{justificado}">' + _html_negrito(paragrafo) + "</p>")
        else:
            partes.append(f'<p style="{justificado}">—</p>')
            if data_validade:
                partes.append(f'<p style="{justificado}">A presente procuração terá validade até '
                               f'<b>{_data_por_extenso(data_validade)}</b>.</p>')

    partes.append(f'<p style="{justificado}">' + _esc(CLAUSULA_ASSINATURA.format(data_procuracao=data_str)) + "</p>")

    # ── Assinatura(s) — 1 só: bloco centralizado; 2+: tabela, 2 por linha ───────
    partes.append('<div style="margin-top:50px;">')
    if len(assinantes) <= 1:
        nome, papel = assinantes[0]
        partes.append(
            '<div style="text-align:center;">____________________________________<br>'
            f'<b>{_esc(nome)}</b><br>{_esc(papel)}</div>'
        )
    else:
        partes.append('<table style="width:100%; border-collapse:collapse;"><tr>')
        for i, (nome, papel) in enumerate(assinantes):
            if i > 0 and i % 2 == 0:
                partes.append('</tr><tr>')
            partes.append(
                '<td style="width:50%; text-align:center; border:1px solid #ffffff; padding:24px 8px 0 8px;">'
                f'____________________________________<br><b>{_esc(nome)}</b><br>{_esc(papel)}</td>'
            )
        partes.append('</tr></table>')
    partes.append('</div>')

    partes.append("</body></html>")
    return "".join(partes).encode("utf-8")


def _html_negrito(paragrafo_com_tag_b: str) -> str:
    """`_finalidade_paragrafos` já devolve texto com <b> ao redor da validade; o
    resto precisa ser escapado sem mexer nessa tag."""
    if "<b>" not in paragrafo_com_tag_b:
        return _esc(paragrafo_com_tag_b)
    antes, resto = paragrafo_com_tag_b.split("<b>", 1)
    negrito, depois = resto.split("</b>", 1)
    return _esc(antes) + "<b>" + _esc(negrito) + "</b>" + _esc(depois)
