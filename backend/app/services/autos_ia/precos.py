"""Preços por token dos modelos usados no módulo Autos IA, usados tanto para a
estimativa prévia (estimativa.py) quanto para o custo real calculado a partir
do `usage` retornado em cada chamada. Ajustar aqui se o modelo mudar — é a
única fonte dessas constantes no módulo.
"""
# claude-opus-4-5 — segmentacao.py e resumo.py (resumo/classificação/keywords).
PRECO_INPUT_POR_MTOK_USD = 5.0
PRECO_OUTPUT_POR_MTOK_USD = 25.0

# claude-haiku-4-5 — OCR de página escaneada (extracao.py, pdf_extract.py). Cai
# num modelo bem mais barato, mas SEM rastrear teria custo invisível: um PDF
# de origem digitalizada (comum em autos antigos ou documentos juntados como
# imagem) pode gerar várias chamadas de OCR por documento.
PRECO_HAIKU_INPUT_POR_MTOK_USD = 1.0
PRECO_HAIKU_OUTPUT_POR_MTOK_USD = 5.0


def calcular_custo_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * PRECO_INPUT_POR_MTOK_USD
        + output_tokens / 1_000_000 * PRECO_OUTPUT_POR_MTOK_USD
    )


def calcular_custo_ocr_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens / 1_000_000 * PRECO_HAIKU_INPUT_POR_MTOK_USD
        + output_tokens / 1_000_000 * PRECO_HAIKU_OUTPUT_POR_MTOK_USD
    )
