"""Segmentação das páginas extraídas em peças processuais individuais.

Importante para a fidelidade do acervo: o modelo de IA decide apenas ONDE
estão os limites entre peças e extrai metadados (tipo, título, autor, data,
ID processual) — o texto de cada peça (`texto_md`) é sempre montado por nós
a partir do texto originalmente extraído página a página, nunca reescrito
pela IA. Isso evita qualquer risco de alteração/alucinação do conteúdo legal.

Uma peça pode atravessar a fronteira de um lote de páginas (upload ou
sublote interno). Quando isso acontece, o último segmento do lote fica
marcado como incompleto e vira o "buffer" reaproveitado no próximo lote,
para não duplicar nem cortar a peça ao meio.
"""
import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.services.autos_ia.extracao import PaginaExtraida, montar_markdown_com_marcadores
from app.services.autos_ia.precos import calcular_custo_usd

logger = logging.getLogger(__name__)

# Tamanho de cada chamada à IA de segmentação, em páginas. Mantém o prompt
# dentro de um contexto confortável mesmo quando o usuário sobe blocos grandes.
SUBLOTE_PAGINAS = 40

TIPOS_VALIDOS = {
    "peticao", "decisao", "despacho", "certidao", "oficio", "recurso", "documento", "outro",
}


@dataclass
class PecaSegmentada:
    tipo: str
    titulo: str
    autor: str | None
    data_peca: str | None
    id_processual: str | None
    pagina_inicio: int
    pagina_fim: int
    texto_md: str


TOOL_SCHEMA = {
    "name": "registrar_segmentos",
    "description": "Registra os segmentos (peças processuais) identificados no lote de páginas.",
    "input_schema": {
        "type": "object",
        "properties": {
            "segmentos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "pagina_inicio": {"type": "integer"},
                        "pagina_fim": {"type": "integer"},
                        "tipo": {
                            "type": "string",
                            "enum": sorted(TIPOS_VALIDOS),
                        },
                        "titulo": {"type": "string"},
                        "autor": {"type": ["string", "null"]},
                        "data_peca": {
                            "type": ["string", "null"],
                            "description": "Formato AAAA-MM-DD, apenas se identificável no texto.",
                        },
                        "id_processual": {
                            "type": ["string", "null"],
                            "description": "Número/ID do evento ou documento no processo, se aparecer explicitamente.",
                        },
                        "completa": {
                            "type": "boolean",
                            "description": "false apenas no ÚLTIMO segmento, se ele for cortado pelo fim deste lote.",
                        },
                    },
                    "required": ["pagina_inicio", "pagina_fim", "tipo", "titulo", "completa"],
                },
            },
        },
        "required": ["segmentos"],
    },
}


def _montar_prompt(pagina_inicio_lote: int, pagina_fim_lote: int, buffer_pagina_inicio: int | None) -> str:
    aviso_buffer = ""
    if buffer_pagina_inicio is not None:
        aviso_buffer = (
            f"\n\nATENÇÃO: as páginas deste lote começam continuando uma peça que já vinha sendo lida "
            f"desde a página {buffer_pagina_inicio} (o texto anterior a este lote não está incluído "
            f"abaixo, apenas o restante dela). Se o início deste lote for de fato a continuação dessa "
            f"peça, o PRIMEIRO segmento deve ter pagina_inicio = {buffer_pagina_inicio}."
        )

    return (
        f"Abaixo está um trecho de autos de um processo judicial brasileiro, da página "
        f"{pagina_inicio_lote} à {pagina_fim_lote}, com marcadores `<!-- pagina N -->` indicando onde "
        f"cada página começa.{aviso_buffer}\n\n"
        "Identifique os limites entre peças processuais distintas (petições, decisões, despachos, "
        "certidões, ofícios, recursos, outros documentos juntados) e registre-os com a ferramenta "
        "`registrar_segmentos`. Regras:\n"
        "- Os segmentos devem ser contíguos e cobrir TODAS as páginas do lote, sem sobreposição e sem lacunas.\n"
        "- pagina_inicio/pagina_fim usam sempre a numeração indicada nos marcadores.\n"
        "- Extraia tipo, título (ex.: 'Petição de Embargos de Declaração', 'Decisão interlocutória'), "
        "autor/subscritor (parte ou juízo) e data quando estiverem claramente identificáveis no texto.\n"
        "- id_processual é o número do evento/documento dentro do processo (se citado explicitamente na "
        "própria peça, ex.: 'Evento 45' ou um ID de documento do PJe/jus.br). Deixe null se não houver.\n"
        "- Marque completa=false SOMENTE no último segmento da lista, e apenas se ele terminar sem sinais "
        "de encerramento (assinatura, 'nesses termos, pede deferimento', despacho seguido de nova peça) "
        "antes do fim do lote — ou seja, se a peça claramente continua além da última página deste lote.\n"
        "- Todos os demais segmentos são sempre completa=true.\n"
    )


def _chamar_llm(
    markdown: str, pagina_inicio_lote: int, pagina_fim_lote: int, buffer_pagina_inicio: int | None
) -> tuple[list[dict], float]:
    import anthropic
    client = anthropic.Anthropic()
    prompt = _montar_prompt(pagina_inicio_lote, pagina_fim_lote, buffer_pagina_inicio)
    resp = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=8192,
        tools=[TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "registrar_segmentos"},
        messages=[{
            "role": "user",
            "content": f"{prompt}\n\n---\n\n{markdown}",
        }],
    )
    custo_usd = calcular_custo_usd(resp.usage.input_tokens, resp.usage.output_tokens)
    for bloco in resp.content:
        if bloco.type == "tool_use" and bloco.name == "registrar_segmentos":
            return bloco.input.get("segmentos", []), custo_usd
    raise RuntimeError("Claude não devolveu segmentos via tool_use")


def _fatiar_texto(paginas_por_numero: dict[int, str], pagina_inicio: int, pagina_fim: int) -> str:
    partes = [paginas_por_numero[n] for n in range(pagina_inicio, pagina_fim + 1) if n in paginas_por_numero]
    return "\n\n".join(p for p in partes if p.strip())


def segmentar_paginas(
    paginas: list[PaginaExtraida],
    buffer_incompleto: str | None,
    buffer_pagina_inicio: int | None,
    on_progresso: Callable[[int, int], None] | None = None,
    on_custo: Callable[[float], None] | None = None,
) -> tuple[list[PecaSegmentada], str | None, int | None]:
    """Segmenta as páginas em peças, processando em sublotes internos.

    `on_progresso(paginas_feitas, total_paginas)`, quando informado, é chamado após cada sublote.
    `on_custo(custo_usd)`, quando informado, é chamado com o custo real de cada chamada à IA.

    Retorna (peças completas, novo buffer de texto incompleto ou None, página de início do buffer ou None).
    """
    todas_pecas: list[PecaSegmentada] = []
    paginas_por_numero = {p.numero_global: p.texto for p in paginas}
    total_paginas = len(paginas)

    for inicio in range(0, len(paginas), SUBLOTE_PAGINAS):
        sublote = paginas[inicio: inicio + SUBLOTE_PAGINAS]
        markdown = montar_markdown_com_marcadores(sublote)
        pagina_inicio_lote = sublote[0].numero_global
        pagina_fim_lote = sublote[-1].numero_global

        try:
            segmentos, custo = _chamar_llm(markdown, pagina_inicio_lote, pagina_fim_lote, buffer_pagina_inicio)
            if on_custo:
                on_custo(custo)
        except Exception as exc:
            logger.error("Segmentação falhou no lote %d-%d: %s", pagina_inicio_lote, pagina_fim_lote, exc)
            # Fallback seguro: trata o lote inteiro como uma peça única "outro", sem perder texto.
            segmentos = [{
                "pagina_inicio": buffer_pagina_inicio if buffer_pagina_inicio is not None else pagina_inicio_lote,
                "pagina_fim": pagina_fim_lote,
                "tipo": "outro",
                "titulo": f"Trecho não segmentado (págs. {pagina_inicio_lote}-{pagina_fim_lote})",
                "autor": None,
                "data_peca": None,
                "id_processual": None,
                "completa": True,
            }]

        for indice, seg in enumerate(segmentos):
            eh_ultimo = indice == len(segmentos) - 1
            p_ini, p_fim = seg["pagina_inicio"], seg["pagina_fim"]

            if buffer_pagina_inicio is not None and indice == 0 and p_ini == buffer_pagina_inicio:
                texto = (buffer_incompleto or "") + "\n\n" + _fatiar_texto(paginas_por_numero, pagina_inicio_lote, p_fim)
                buffer_incompleto, buffer_pagina_inicio = None, None
            else:
                texto = _fatiar_texto(paginas_por_numero, p_ini, p_fim)

            if eh_ultimo and not seg.get("completa", True):
                buffer_incompleto = texto
                buffer_pagina_inicio = p_ini
                continue

            tipo = seg.get("tipo") or "outro"
            if tipo not in TIPOS_VALIDOS:
                tipo = "outro"

            todas_pecas.append(PecaSegmentada(
                tipo=tipo,
                titulo=(seg.get("titulo") or "Peça sem título").strip()[:500],
                autor=(seg.get("autor") or None),
                data_peca=(seg.get("data_peca") or None),
                id_processual=(seg.get("id_processual") or None),
                pagina_inicio=p_ini,
                pagina_fim=p_fim,
                texto_md=texto,
            ))

        if on_progresso:
            on_progresso(min(inicio + SUBLOTE_PAGINAS, total_paginas), total_paginas)

    return todas_pecas, buffer_incompleto, buffer_pagina_inicio
