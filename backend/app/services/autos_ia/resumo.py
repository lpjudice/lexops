"""Resumo, palavras-chave e extração de IDs mencionados para uma peça já segmentada."""
import logging
from dataclasses import dataclass

from app.services.autos_ia.precos import calcular_custo_usd

logger = logging.getLogger(__name__)

LIMITE_CHARS_TEXTO = 300_000

TOOL_SCHEMA = {
    "name": "registrar_resumo",
    "description": "Registra o resumo, palavras-chave e IDs mencionados de uma peça processual.",
    "input_schema": {
        "type": "object",
        "properties": {
            "resumo": {
                "type": "string",
                "description": "Resumo objetivo em até 5 frases, cobrindo o que a peça pede/decide, os "
                               "fundamentos principais e qualquer prazo ou determinação relevante.",
            },
            "palavras_chave": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3 a 8 termos/temas jurídicos que caracterizam a peça (institutos, teses, "
                               "matérias), em minúsculas, sem acentuação forçada nem repetição do título.",
            },
            "ids_mencionados": {
                "type": "array",
                "items": {"type": "string"},
                "description": "IDs, números de evento ou de documento de OUTRAS peças do processo "
                               "citados no texto (ex.: 'Evento 45', 'ID 0012345678', 'fls. 230'). "
                               "Não inclua o próprio ID desta peça. Lista vazia se não houver nenhuma.",
            },
        },
        "required": ["resumo", "palavras_chave", "ids_mencionados"],
    },
}

SYSTEM_PROMPT = (
    "Você é um assistente jurídico especializado em processo civil brasileiro, encarregado de indexar "
    "peças de um processo grande para permitir busca e navegação posteriores. Seja fiel ao conteúdo, "
    "não invente fatos, valores ou datas que não estejam no texto."
)


@dataclass
class ResumoPeca:
    resumo: str
    keywords: list[str]
    ids_mencionados: list[str]
    custo_usd: float


def resumir_peca(texto_md: str, titulo: str, tipo: str) -> ResumoPeca:
    import anthropic
    client = anthropic.Anthropic()

    texto = texto_md[:LIMITE_CHARS_TEXTO]
    prompt = (
        f"Peça processual — tipo: {tipo}; título: {titulo}.\n\n"
        f"Texto da peça:\n\n{texto}"
    )

    resp = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        tools=[TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "registrar_resumo"},
        messages=[{"role": "user", "content": prompt}],
    )
    custo_usd = calcular_custo_usd(resp.usage.input_tokens, resp.usage.output_tokens)
    for bloco in resp.content:
        if bloco.type == "tool_use" and bloco.name == "registrar_resumo":
            dados = bloco.input
            return ResumoPeca(
                resumo=(dados.get("resumo") or "").strip(),
                keywords=[k.strip().lower() for k in (dados.get("palavras_chave") or []) if k.strip()][:8],
                ids_mencionados=[i.strip() for i in (dados.get("ids_mencionados") or []) if i.strip()],
                custo_usd=custo_usd,
            )
    raise RuntimeError("Claude não devolveu resumo via tool_use")
