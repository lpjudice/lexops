"""Resumo, classificação, peticionante e IDs mencionados/próprios de uma peça
já segmentada (ou importada do jus.br/Drive) — tudo na mesma chamada de IA,
pra não pagar duas vezes pelo mesmo texto: a classificação por palavra-chave
usada antes de chamar a IA (jus.br) ou decidida na segmentação (upload) é só
um palpite inicial; aqui a IA já está lendo o texto inteiro mesmo assim, então
aproveita pra confirmar/corrigir tipo e extrair peticionante e o ID que a
própria peça usa pra se referenciar (essencial pro grafo: o ID interno do
jus.br quase nunca é o que outras peças citam no texto — ver jusbr_import.py)."""
import logging
from dataclasses import dataclass

from app.services.autos_ia.precos import calcular_custo_usd
from app.services.autos_ia.segmentacao import TIPOS_VALIDOS

logger = logging.getLogger(__name__)

LIMITE_CHARS_TEXTO = 300_000

TOOL_SCHEMA = {
    "name": "registrar_resumo",
    "description": "Registra o resumo, classificação, peticionante e IDs de uma peça processual.",
    "input_schema": {
        "type": "object",
        "properties": {
            "tipo": {
                "type": "string",
                "enum": sorted(TIPOS_VALIDOS),
                "description": "Classificação da peça pelo CONTEÚDO real do texto, não pelo rótulo que "
                               "o sistema de origem deu a ela (esse rótulo costuma ser genérico, ex.: "
                               "'Documento Diverso' ou 'Juntada'). 'documento' é pra anexos/comprovantes "
                               "de apoio (procuração, RG, guia, extrato, contrato social...); use os "
                               "demais tipos só para atos processuais em si.",
            },
            "peticionante": {
                "type": ["string", "null"],
                "description": "Quem apresentou/assina esta peça: nome da parte (ex.: 'Autor', 'Réu', "
                               "ou o nome próprio se identificável), 'Ministério Público', ou o nome do "
                               "juízo/relator se for um ato do próprio juízo (decisão, despacho, "
                               "sentença). Null se não for identificável no texto.",
            },
            "id_proprio": {
                "type": ["string", "null"],
                "description": "O número/ID pelo qual esta MESMA peça se identifica no próprio texto "
                               "(ex.: 'Evento 45', 'ID 0012345678', um número de protocolo no cabeçalho "
                               "ou rodapé) — é o que outras peças citariam pra se referir a ela. Null se "
                               "não houver nenhum identificador desse tipo visível no texto.",
            },
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
                               "Não inclua o próprio ID desta peça (esse vai em id_proprio). Lista vazia "
                               "se não houver nenhuma menção.",
            },
        },
        "required": ["tipo", "peticionante", "id_proprio", "resumo", "palavras_chave", "ids_mencionados"],
    },
}

SYSTEM_PROMPT = (
    "Você é um assistente jurídico especializado em processo civil brasileiro, encarregado de indexar "
    "peças de um processo grande para permitir busca e navegação posteriores, como um advogado revisando "
    "os autos identificaria cada peça. Seja fiel ao conteúdo, não invente fatos, valores, nomes ou datas "
    "que não estejam no texto — quando não for identificável, use null."
)


@dataclass
class ResumoPeca:
    tipo: str
    peticionante: str | None
    id_proprio: str | None
    resumo: str
    keywords: list[str]
    ids_mencionados: list[str]
    custo_usd: float


TOOL_SCHEMA_RECLASSIFICACAO = {
    "name": "registrar_reclassificacao",
    "description": "Registra só a classificação, peticionante e ID próprio de uma peça já resumida.",
    "input_schema": {
        "type": "object",
        "properties": {
            "tipo": TOOL_SCHEMA["input_schema"]["properties"]["tipo"],
            "peticionante": TOOL_SCHEMA["input_schema"]["properties"]["peticionante"],
            "id_proprio": TOOL_SCHEMA["input_schema"]["properties"]["id_proprio"],
        },
        "required": ["tipo", "peticionante", "id_proprio"],
    },
}

# Reclassificação de peças já resumidas (ver reclassificar_peca) — só precisa
# confirmar tipo/peticionante/ID, não o resumo inteiro de novo. Cabeçalho +
# fecho cobrem a esmagadora maioria dos casos (tipo do ato, parte que assina,
# número de evento/protocolo ficam no início ou na assinatura), e cortar o meio
# do texto é o que reduz o custo de entrada — a IA não precisa reler a peça
# inteira só pra confirmar esses três campos.
LIMITE_CHARS_RECLASSIFICACAO_INICIO = 6000
LIMITE_CHARS_RECLASSIFICACAO_FIM = 1500


@dataclass
class ReclassificacaoPeca:
    tipo: str
    peticionante: str | None
    id_proprio: str | None
    custo_usd: float


def reclassificar_peca(texto_md: str, titulo: str, tipo_atual: str) -> ReclassificacaoPeca:
    """Versão barata de resumir_peca: só tipo/peticionante/id_proprio, com saída
    curta e entrada truncada (início + fecho do texto). Usada para reclassificar
    peças que já foram resumidas antes desses três campos existirem, sem pagar
    de novo pelo resumo/keywords/ids_mencionados (que não mudam)."""
    import anthropic
    client = anthropic.Anthropic()

    texto = texto_md
    if len(texto) > LIMITE_CHARS_RECLASSIFICACAO_INICIO + LIMITE_CHARS_RECLASSIFICACAO_FIM:
        texto = (
            texto[:LIMITE_CHARS_RECLASSIFICACAO_INICIO]
            + "\n\n[...]\n\n"
            + texto[-LIMITE_CHARS_RECLASSIFICACAO_FIM:]
        )
    prompt = (
        f"Peça processual — classificação atual (a confirmar/corrigir): {tipo_atual}; título: {titulo}.\n\n"
        f"Início e fecho do texto da peça:\n\n{texto}"
    )

    resp = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=300,
        system=SYSTEM_PROMPT,
        tools=[TOOL_SCHEMA_RECLASSIFICACAO],
        tool_choice={"type": "tool", "name": "registrar_reclassificacao"},
        messages=[{"role": "user", "content": prompt}],
    )
    custo_usd = calcular_custo_usd(resp.usage.input_tokens, resp.usage.output_tokens)
    for bloco in resp.content:
        if bloco.type == "tool_use" and bloco.name == "registrar_reclassificacao":
            dados = bloco.input
            tipo_ia = (dados.get("tipo") or "").strip()
            return ReclassificacaoPeca(
                tipo=tipo_ia if tipo_ia in TIPOS_VALIDOS else tipo_atual,
                peticionante=(dados.get("peticionante") or "").strip() or None,
                id_proprio=(dados.get("id_proprio") or "").strip() or None,
                custo_usd=custo_usd,
            )
    raise RuntimeError("Claude não devolveu reclassificação via tool_use")


def resumir_peca(texto_md: str, titulo: str, tipo: str) -> ResumoPeca:
    import anthropic
    client = anthropic.Anthropic()

    texto = texto_md[:LIMITE_CHARS_TEXTO]
    prompt = (
        f"Peça processual — classificação inicial (a confirmar): {tipo}; título: {titulo}.\n\n"
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
            tipo_ia = (dados.get("tipo") or "").strip()
            return ResumoPeca(
                tipo=tipo_ia if tipo_ia in TIPOS_VALIDOS else tipo,
                peticionante=(dados.get("peticionante") or "").strip() or None,
                id_proprio=(dados.get("id_proprio") or "").strip() or None,
                resumo=(dados.get("resumo") or "").strip(),
                keywords=[k.strip().lower() for k in (dados.get("palavras_chave") or []) if k.strip()][:8],
                ids_mencionados=[i.strip() for i in (dados.get("ids_mencionados") or []) if i.strip()],
                custo_usd=custo_usd,
            )
    raise RuntimeError("Claude não devolveu resumo via tool_use")
