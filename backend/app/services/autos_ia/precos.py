"""Preços por token do modelo usado em segmentacao.py/resumo.py (Opus), usados
tanto para a estimativa prévia (estimativa.py) quanto para o custo real
calculado a partir do `usage` retornado em cada chamada. Ajustar aqui se o
modelo mudar — é a única fonte dessas constantes no módulo Autos IA.
"""
PRECO_INPUT_POR_MTOK_USD = 5.0
PRECO_OUTPUT_POR_MTOK_USD = 25.0


def calcular_custo_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * PRECO_INPUT_POR_MTOK_USD
        + output_tokens / 1_000_000 * PRECO_OUTPUT_POR_MTOK_USD
    )
