"""Estimativa aproximada de custo (chamadas à IA) e tempo de processamento a
partir só do número de páginas/itens. Não é uma cotação exata — é uma ordem
de grandeza para o usuário decidir se quer prosseguir. Constantes de preço em
services/autos_ia/precos.py; ajustar lá se o modelo mudar.
"""
import math

from app.services.autos_ia.ingestao import RESUMO_MAX_WORKERS
from app.services.autos_ia.precos import PRECO_INPUT_POR_MTOK_USD, PRECO_OUTPUT_POR_MTOK_USD
from app.services.autos_ia.segmentacao import SUBLOTE_PAGINAS

TOKENS_POR_PAGINA_ESTIMADO = 700
PAGINAS_POR_PECA_ESTIMADO = 4
SEGUNDOS_POR_CHAMADA_LLM = 8

TOKENS_SAIDA_SEGMENTACAO = 2000
TOKENS_SAIDA_RESUMO = 400


def estimar_processamento(total_paginas: int) -> dict:
    """Upload manual de bloco de PDF: passa por segmentação (IA decide os limites
    entre peças) e depois resumo — duas chamadas de IA por peça, em média."""
    total_paginas = max(1, total_paginas)
    chamadas_segmentacao = math.ceil(total_paginas / SUBLOTE_PAGINAS)
    pecas_estimadas = max(1, round(total_paginas / PAGINAS_POR_PECA_ESTIMADO))

    tokens_in_seg = SUBLOTE_PAGINAS * TOKENS_POR_PAGINA_ESTIMADO
    custo_segmentacao = chamadas_segmentacao * (
        tokens_in_seg / 1_000_000 * PRECO_INPUT_POR_MTOK_USD
        + TOKENS_SAIDA_SEGMENTACAO / 1_000_000 * PRECO_OUTPUT_POR_MTOK_USD
    )

    tokens_in_resumo = PAGINAS_POR_PECA_ESTIMADO * TOKENS_POR_PAGINA_ESTIMADO
    custo_resumo = pecas_estimadas * (
        tokens_in_resumo / 1_000_000 * PRECO_INPUT_POR_MTOK_USD
        + TOKENS_SAIDA_RESUMO / 1_000_000 * PRECO_OUTPUT_POR_MTOK_USD
    )

    tempo_segmentacao_s = chamadas_segmentacao * SEGUNDOS_POR_CHAMADA_LLM  # sequencial
    tempo_resumo_s = math.ceil(pecas_estimadas / RESUMO_MAX_WORKERS) * SEGUNDOS_POR_CHAMADA_LLM  # paralelo

    return {
        "pecas_estimadas": pecas_estimadas,
        "custo_estimado_usd": round(custo_segmentacao + custo_resumo, 2),
        "tempo_estimado_minutos": round((tempo_segmentacao_s + tempo_resumo_s) / 60, 1),
    }


def estimar_importacao_existentes(total_itens: int) -> dict:
    """Importação a partir de andamentos já baixados (jus.br/Drive): cada
    andamento já É um documento discreto, então não há chamada de segmentação —
    só uma chamada de resumo por item (assumindo ~PAGINAS_POR_PECA_ESTIMADO
    páginas por documento, na falta do tamanho real antes de baixar/ler)."""
    total_itens = max(0, total_itens)
    tokens_in = PAGINAS_POR_PECA_ESTIMADO * TOKENS_POR_PAGINA_ESTIMADO
    custo = total_itens * (
        tokens_in / 1_000_000 * PRECO_INPUT_POR_MTOK_USD
        + TOKENS_SAIDA_RESUMO / 1_000_000 * PRECO_OUTPUT_POR_MTOK_USD
    )
    tempo_s = math.ceil(total_itens / RESUMO_MAX_WORKERS) * SEGUNDOS_POR_CHAMADA_LLM if total_itens else 0

    return {
        "itens_pendentes": total_itens,
        "custo_estimado_usd": round(custo, 2),
        "tempo_estimado_minutos": round(tempo_s / 60, 1),
    }
