"""Estimativa aproximada de custo (chamadas à IA) e tempo de processamento de um
bloco, a partir só do número de páginas. Não é uma cotação exata — é uma ordem
de grandeza para o usuário decidir se quer subir o bloco inteiro de uma vez ou
em pedaços menores. Constantes calibradas para o modelo Opus usado em
segmentacao.py/resumo.py; ajustar aqui se o modelo mudar.
"""
import math

from app.services.autos_ia.ingestao import RESUMO_MAX_WORKERS
from app.services.autos_ia.segmentacao import SUBLOTE_PAGINAS

TOKENS_POR_PAGINA_ESTIMADO = 700
PAGINAS_POR_PECA_ESTIMADO = 4
PRECO_INPUT_POR_MTOK_USD = 5.0
PRECO_OUTPUT_POR_MTOK_USD = 25.0
SEGUNDOS_POR_CHAMADA_LLM = 8

TOKENS_SAIDA_SEGMENTACAO = 2000
TOKENS_SAIDA_RESUMO = 400


def estimar_processamento(total_paginas: int) -> dict:
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
