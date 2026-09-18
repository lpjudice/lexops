"""
Gerador de Instrumento de Procuração (PDF + versão HTML editável no Google Docs).
Mesmo padrão visual do Contrato de Honorários (contrato_pdf.py).

Partes customizáveis:
  - Outorgante(s) — lista dinâmica, cada um PF (nome, nacionalidade/estado civil/
    profissão, CPF, endereço, email) ou PJ (nome, CNPJ, sede, email, representante
    legal opcional)
  - Outorgado(s) — lista dinâmica de advogado(s): nome, OAB/UF, CPF. Com mais de
    um, vira um único parágrafo compacto ("OUTORGADO 1: ...; OUTORGADO 2: ...;
    todos com endereço profissional à X") em vez de um parágrafo por pessoa.
  - Endereço profissional (do escritório) dos outorgados — pré-preenchido, editável
  - Poderes: cláusula geral "ad judicia et extra" (pode ser desligada por completo),
    com os poderes especiais escolhidos individualmente + texto adicional livre
  - Finalidade específica (texto livre, opcional)
  - Validade (opcional — se vazia, procuração não tem prazo)
  - Data da procuração

O PDF tenta caber em 1 página: a fonte do corpo começa em 11pt e vai reduzindo
(10.5, depois 10) até caber; 10pt é o piso — abaixo disso aceita 2 páginas, a
menos que `forcar_uma_pagina=True`, que aí reduz também o respiro antes da
assinatura e vai até 9pt antes de desistir.
"""

import io
import re
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
# último (piso) é aceito mesmo que ainda resulte em 2 páginas. Antes de desistir,
# SEMPRE tenta de novo no piso com o respiro antes da assinatura mais apertado —
# resolve de graça (sem mudar fonte) o caso comum de só a assinatura vazar pra
# uma 2ª página. Só continua reduzindo a fonte além disso (9.5/9pt) se
# `forcar_uma_pagina` estiver ligado.
TAMANHOS_FONTE_CORPO = (11.0, 10.5, 10.0)
TAMANHOS_FONTE_FORCADO = (9.5, 9.0)  # só entram com forcar_uma_pagina=True

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
    # estado civil/profissão sempre em minúscula no documento, mesmo que o usuário
    # (ou o cadastro do cliente) tenha digitado em CAIXA ALTA.
    partes = [
        nacionalidade.strip(),
        estado_civil.strip().lower(),
        profissao.strip().lower(),
    ]
    return ", ".join(p for p in partes if p)


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


def _texto_poderes(
    poderes_modo: str, poderes_especiais: list[str] | None, poderes_adicionais: str,
    poderes_template_texto: str,
) -> str | None:
    """Texto que vai no lugar da cláusula ad judicia dentro de DOS PODERES —
    None quando `poderes_modo == "nenhum"` (aí só entra o que estiver em
    `finalidade`, ver chamadores)."""
    if poderes_modo == "template":
        texto = (poderes_template_texto or "").strip()
        return texto or None
    if poderes_modo == "nenhum":
        return None
    return _compor_clausula_poderes(poderes_especiais or [], poderes_adicionais)


def _linha_outorgante(og: dict, numero: int | None = None) -> str:
    """`og`: {"tipo": "PF"|"PJ", "nome", "nacionalidade", "estado_civil", "profissao",
    "cpf_cnpj", "endereco", "email", "representante_nome", "representante_cpf",
    "representante_cargo"}. `numero`: se houver mais de 1 outorgante, prefixa
    "OUTORGANTE N: " no início do parágrafo."""
    tipo = og.get("tipo") or "PF"
    nome = (og.get("nome") or "").strip()
    prefixo = f"<b>OUTORGANTE {numero}:</b> " if numero else ""
    nome_fmt = f"<b>{nome.upper()}</b>"

    if tipo == "PJ":
        cpf_cnpj = (og.get("cpf_cnpj") or "").strip()
        endereco = (og.get("endereco") or "").strip()
        email = (og.get("email") or "").strip()
        rep_nome = (og.get("representante_nome") or "").strip()
        rep_cpf = (og.get("representante_cpf") or "").strip()
        rep_cargo = (og.get("representante_cargo") or "").strip()

        partes = [nome_fmt, "pessoa jurídica de direito privado"]
        if cpf_cnpj:
            partes.append(f"registrada sob o n. {cpf_cnpj}")
        linha = ", ".join(partes)
        if endereco:
            linha += f", com sede em {endereco}"
        if email:
            linha += f", e-mail {email}"
        if rep_nome:
            rep_partes = [f"<b>{rep_nome.upper()}</b>"]
            if rep_cargo:
                rep_partes.append(rep_cargo)
            linha += ", neste ato representada por " + ", ".join(rep_partes)
            if rep_cpf:
                linha += f", portador(a) do CPF n. {rep_cpf}"
        linha += ", doravante denominada OUTORGANTE;"
        return prefixo + linha

    # PF (padrão)
    qualificacao = _compor_qualificacao(
        og.get("nacionalidade") or "", og.get("estado_civil") or "", og.get("profissao") or "",
    )
    cpf_cnpj = (og.get("cpf_cnpj") or "").strip()
    endereco = (og.get("endereco") or "").strip()
    email = (og.get("email") or "").strip()
    partes = [nome_fmt]
    if qualificacao:
        partes.append(qualificacao)
    linha = ", ".join(partes)
    if cpf_cnpj:
        linha += f", cadastrado(a) no CPF/MF de n. {cpf_cnpj}"
    if endereco:
        linha += f", residente/domiciliado em {endereco}"
    if email:
        linha += f", e-mail {email}"
    linha += ", doravante denominado(a) OUTORGANTE;"
    return prefixo + linha


def _nome_assinatura(og: dict) -> str:
    """Quem 'assina' visualmente no rodapé: o representante legal (se PJ e
    informado) ou o próprio outorgante."""
    rep_nome = (og.get("representante_nome") or "").strip()
    if (og.get("tipo") or "PF") == "PJ" and rep_nome:
        return rep_nome.upper()
    return (og.get("nome") or "").strip().upper()


def _paragrafo_outorgados(outorgados: list[dict], endereco_escritorio: str) -> str | None:
    """1 outorgado: parágrafo simples de sempre. 2+: parágrafo único compacto —
    "OUTORGADO 1: NOME, advogado(a), inscrito(a) na OAB/UF sob o n.º X, portador(a)
    do CPF n.º Y; OUTORGADO 2: ...; todos com endereço profissional à Z." — evita
    repetir o mesmo endereço em cada um."""
    validos = [o for o in outorgados if (o.get("nome") or "").strip()]
    if not validos:
        return None

    def _pessoa(adv: dict, numero: int | None) -> str:
        nome = adv["nome"].strip()
        oab = (adv.get("oab") or "").strip()
        oab_uf = (adv.get("oab_uf") or "").strip()
        cpf = (adv.get("cpf") or "").strip()
        prefixo = f"<b>OUTORGADO {numero}:</b> " if numero else ""
        texto = f"{prefixo}<b>{nome.upper()}</b>, advogado(a)"
        if oab:
            texto += f", inscrito(a) na OAB/{oab_uf} sob o n.º {oab}" if oab_uf else f", inscrito(a) na OAB sob o n.º {oab}"
        if cpf:
            texto += f", portador(a) do CPF n.º {cpf}"
        return texto

    if len(validos) == 1:
        return _pessoa(validos[0], None) + f", com endereço profissional em {endereco_escritorio};"

    pessoas = [_pessoa(adv, i) for i, adv in enumerate(validos, start=1)]
    return "; ".join(pessoas) + f"; todos com endereço profissional à {endereco_escritorio}."


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
    outorgantes: list[dict],
    outorgados: list[dict],
    endereco_escritorio: str,
    poderes_modo: str,
    poderes_especiais: list[str] | None,
    poderes_adicionais: str,
    poderes_template_texto: str,
    finalidade: str,
    data_validade: date | None,
    data_procuracao: date | None,
    spacer_assinatura_cm: float = 1.5,
) -> bytes:
    buf = io.BytesIO()
    outorgantes_validos = [o for o in outorgantes if (o.get("nome") or "").strip()]
    titulo_doc = outorgantes_validos[0]["nome"] if outorgantes_validos else "Procuração"
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=3 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title=f"Procuração — {titulo_doc}",
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

    # ── OUTORGANTE(S) ─────────────────────────────────────────────────────────
    rotulo_outorgante = "OUTORGANTE(S):" if len(outorgantes_validos) > 1 else "OUTORGANTE:"
    story.append(Paragraph(f"<b>{rotulo_outorgante}</b>", st["parte_label"]))
    numerar = len(outorgantes_validos) > 1
    for i, og in enumerate(outorgantes_validos, start=1):
        story.append(Paragraph(_linha_outorgante(og, i if numerar else None), st["corpo"]))
    story.append(Spacer(1, 0.2 * cm))

    # ── OUTORGADO(S) — dinâmico, um ou mais advogados ───────────────────────────
    story.append(Paragraph("<b>OUTORGADO(S):</b>", st["parte_label"]))
    paragrafo_outorgados = _paragrafo_outorgados(outorgados, endereco_escritorio)
    if paragrafo_outorgados:
        story.append(Paragraph(paragrafo_outorgados, st["corpo"]))

    story.append(Spacer(1, 0.3 * cm))

    # ── PODERES ───────────────────────────────────────────────────────────────
    story.append(Paragraph("DOS PODERES", st["secao_titulo"]))
    tem_finalidade = bool(finalidade.strip())
    texto_poderes = _texto_poderes(poderes_modo, poderes_especiais, poderes_adicionais, poderes_template_texto)
    if texto_poderes:
        story.append(Paragraph(texto_poderes, st["corpo"]))
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

    # ── ASSINATURA(S) — 1 outorgante: bloco centralizado; 2+: tabela, 2 por linha ──
    story.append(Spacer(1, spacer_assinatura_cm * cm))
    story.append(HRFlowable(width="100%", thickness=0.3, color=colors.HexColor("#e5e7eb"),
                             spaceAfter=12))

    assinantes = [(_nome_assinatura(og), "OUTORGANTE") for og in outorgantes_validos] or [("", "OUTORGANTE")]
    story.append(_tabela_assinaturas(st, assinantes))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def gerar_procuracao(
    outorgantes: list[dict],
    outorgados: list[dict],
    endereco_escritorio: str,
    poderes_modo: str = "ad_judicia",
    poderes_especiais: list[str] | None = None,
    poderes_adicionais: str = "",
    poderes_template_texto: str = "",
    finalidade: str = "",
    data_validade: date | None = None,
    data_procuracao: date | None = None,
    forcar_uma_pagina: bool = False,
) -> bytes:
    """
    Gera o PDF do instrumento de procuração. Retorna bytes.
    `outorgantes`: lista de dicts (ver `_linha_outorgante`). `outorgados`: lista
    de {"nome", "oab", "oab_uf", "cpf"}. `poderes_modo`: "ad_judicia" (padrão,
    usa `poderes_especiais`/`poderes_adicionais`), "template" (usa o texto
    livre em `poderes_template_texto` no lugar da cláusula padrão) ou "nenhum"
    (só o que estiver em `finalidade`).
    Tenta caber em 1 página, reduzindo a fonte do corpo até o piso (10pt); antes
    de desistir, tenta de novo no piso com o respiro antes da assinatura mais
    apertado (resolve de graça o caso comum de só a assinatura vazar pra uma
    2ª página). Se `forcar_uma_pagina` estiver ligado e ainda não couber, reduz
    a fonte mais um pouco (9.5, depois 9pt) antes de aceitar 2 páginas.
    """
    kwargs = dict(
        outorgantes=outorgantes, outorgados=outorgados, endereco_escritorio=endereco_escritorio,
        poderes_modo=poderes_modo, poderes_especiais=poderes_especiais,
        poderes_template_texto=poderes_template_texto,
        poderes_adicionais=poderes_adicionais, finalidade=finalidade, data_validade=data_validade,
        data_procuracao=data_procuracao,
    )
    pdf_bytes = _montar_pdf(TAMANHOS_FONTE_CORPO[0], spacer_assinatura_cm=1.5, **kwargs)
    for tamanho in TAMANHOS_FONTE_CORPO[1:]:
        if _num_paginas(pdf_bytes) <= 1:
            return pdf_bytes
        pdf_bytes = _montar_pdf(tamanho, spacer_assinatura_cm=1.5, **kwargs)

    if _num_paginas(pdf_bytes) > 1:
        pdf_bytes = _montar_pdf(TAMANHOS_FONTE_CORPO[-1], spacer_assinatura_cm=0.6, **kwargs)

    if forcar_uma_pagina and _num_paginas(pdf_bytes) > 1:
        for tamanho in TAMANHOS_FONTE_FORCADO:
            candidato = _montar_pdf(tamanho, spacer_assinatura_cm=0.6, **kwargs)
            pdf_bytes = candidato
            if _num_paginas(candidato) <= 1:
                break

    return pdf_bytes


def _bloco_assinatura(st: dict, nome: str, papel: str):
    return [
        Paragraph("_" * 38, ParagraphStyle(
            "linha", fontName="Helvetica", fontSize=10, textColor=DARK, alignment=TA_CENTER, spaceAfter=4
        )),
        Paragraph(nome, st["assinatura_label"]),
        Paragraph(papel, st["assinatura_sub"]),
    ]


def _tabela_assinaturas(st: dict, assinantes: list[tuple[str, str]]) -> Table:
    """1 assinante: 1 célula ocupando a largura toda. 2+: 2 por linha, igual à
    versão Docs (mesma lógica, agora em reportlab)."""
    if len(assinantes) <= 1:
        nome, papel = assinantes[0]
        linhas = [[_bloco_assinatura(st, nome, papel)]]
        larguras = [16 * cm]
    else:
        linhas = []
        linha_atual = []
        for nome, papel in assinantes:
            linha_atual.append(_bloco_assinatura(st, nome, papel))
            if len(linha_atual) == 2:
                linhas.append(linha_atual)
                linha_atual = []
        if linha_atual:
            linha_atual.append("")  # completa a linha ímpar com célula vazia
            linhas.append(linha_atual)
        larguras = [8 * cm, 8 * cm]

    tabela = Table(linhas, colWidths=larguras)
    tabela.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
    ]))
    return tabela


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


_RE_BOLD = re.compile(r"(<b>.*?</b>)")


def _esc_bold(s: str) -> str:
    """Escapa `s` pra HTML preservando tags <b>...</b> já embutidas (nomes,
    "OUTORGANTE N:"/"OUTORGADO N:" e a validade em negrito vêm assim de
    `_linha_outorgante`/`_paragrafo_outorgados`/`_finalidade_paragrafos`) — sem
    isso as tags apareceriam como texto literal."""
    partes = _RE_BOLD.split(s)
    out = []
    for p in partes:
        if p.startswith("<b>") and p.endswith("</b>"):
            out.append("<b>" + _esc(p[3:-4]) + "</b>")
        else:
            out.append(_esc(p))
    return "".join(out)


def gerar_procuracao_html(
    outorgantes: list[dict],
    outorgados: list[dict],
    endereco_escritorio: str,
    poderes_modo: str = "ad_judicia",
    poderes_especiais: list[str] | None = None,
    poderes_adicionais: str = "",
    poderes_template_texto: str = "",
    finalidade: str = "",
    data_validade: date | None = None,
    data_procuracao: date | None = None,
    forcar_uma_pagina: bool = False,  # sem efeito no Docs (não paginado); mantido por simetria de assinatura
) -> bytes:
    """
    Mesmo conteúdo de `gerar_procuracao`, como HTML autocontido (logo embutida em
    base64, fonte Archivo, texto justificado) — usado para subir ao Drive com
    conversão automática para Google Docs (versão editável pelo usuário).

    O importador de HTML do Google Docs ignora bastante CSS "solto" (margin:auto
    em <img>, <div> com background-color) — por isso a logo vai num <p centered>
    e a linha verde usa uma tabela 1x1 com fundo colorido, que ele preserva.

    Convenção: essa página é um ponto de partida editável, não fica sincronizada
    de volta com o PDF gerado pelo sistema — mudanças aqui não alteram o PDF já
    anexado ao contrato/procuração. Para usar uma versão editada, baixe como PDF
    no próprio Google Docs e faça upload dela no sistema (substituindo o anexo).
    """
    import base64

    data_str = _data_por_extenso(data_procuracao or date.today())
    outorgantes_validos = [o for o in outorgantes if (o.get("nome") or "").strip()]
    numerar = len(outorgantes_validos) > 1
    assinantes = [(_nome_assinatura(og), "OUTORGANTE") for og in outorgantes_validos] or [("", "OUTORGANTE")]

    logo_html = ""
    if _LOGO_PATH.exists():
        logo_b64 = base64.b64encode(_LOGO_PATH.read_bytes()).decode()
        logo_html = (
            '<p style="text-align:center; margin:0 0 4px 0;">'
            f'<img src="data:image/png;base64,{logo_b64}" alt="Pimenta Júdice" height="112">'
            '</p>'
        )

    linha_verde = (
        '<table style="width:100%; border-collapse:collapse; margin:8px 0 18px 0;"><tr>'
        '<td style="background-color:#00b090; height:4px; font-size:1px; line-height:1px;">&nbsp;</td>'
        '</tr></table>'
    )

    corpo_style = "font-family:'Archivo', sans-serif; font-weight:200; font-size:11pt; color:#1d1e20;"
    justificado = "text-align:justify; margin:0 0 10px 0;"

    rotulo_outorgante = "OUTORGANTE(S):" if len(outorgantes_validos) > 1 else "OUTORGANTE:"
    partes: list[str] = [
        f'<html><body style="{corpo_style} max-width:720px; margin:0 auto;">',
        logo_html,
        linha_verde,
        '<h1 style="text-align:center; font-weight:700; font-size:15pt; letter-spacing:1px;">PROCURAÇÃO</h1>',
        '<div style="height:1px; background:#e5e7eb; width:50%; margin:0 auto 18px auto;"></div>',
        f'<p style="{justificado}"><b>{rotulo_outorgante}</b><br>',
    ]
    for i, og in enumerate(outorgantes_validos, start=1):
        partes.append(_esc_bold(_linha_outorgante(og, i if numerar else None)) + "<br>")
    partes.append("</p>")

    partes.append(f'<p style="{justificado}"><b>OUTORGADO(S):</b><br>')
    paragrafo_outorgados = _paragrafo_outorgados(outorgados, endereco_escritorio)
    if paragrafo_outorgados:
        partes.append(_esc_bold(paragrafo_outorgados))
    partes.append("</p>")

    partes.append('<h3 style="text-align:center; font-weight:700;">DOS PODERES</h3>')
    tem_finalidade = bool(finalidade.strip())
    texto_poderes = _texto_poderes(poderes_modo, poderes_especiais, poderes_adicionais, poderes_template_texto)
    if texto_poderes:
        partes.append(f'<p style="{justificado}">' + _esc(texto_poderes) + "</p>")
        if tem_finalidade:
            partes.append('<h3 style="text-align:center; font-weight:700;">DA FINALIDADE ESPECÍFICA</h3>')
            for paragrafo in _finalidade_paragrafos(finalidade, data_validade):
                partes.append(f'<p style="{justificado}">' + _esc_bold(paragrafo) + "</p>")
        elif data_validade:
            partes.append(f'<p style="{justificado}">A presente procuração terá validade até '
                           f'<b>{_data_por_extenso(data_validade)}</b>.</p>')
    else:
        if tem_finalidade:
            for paragrafo in _finalidade_paragrafos(finalidade, data_validade):
                partes.append(f'<p style="{justificado}">' + _esc_bold(paragrafo) + "</p>")
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
