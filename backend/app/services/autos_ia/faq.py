"""Respostas pré-mapeadas: cada pergunta é respondida com base no TEXTO INTEGRAL das
peças mais relevantes (busca por tema, full-text sobre título/resumo/texto/palavras-chave —
ver busca.py), citando expressamente as peças usadas como fonte.

Antes disso, o contexto mandado pra IA responder era só o RESUMO de cada peça — a busca
(que olha o texto inteiro) até achava a peça certa, mas qualquer detalhe que o resumo (uma
compressão) tivesse deixado de fora — um nome de parte específico, por exemplo — ficava
invisível pra IA de resposta, mesmo estando bem ali no documento original. Reproduzido de
verdade no Apex: pergunta pelo pedido de um peticionário específico achou a peça certa (via
busca) mas respondeu "não encontrado" porque o nome não estava no resumo dela. Texto
integral custa mais tokens/tempo por pergunta — LIMITE_PECAS_CONTEXTO foi reduzido de 15
pra 8 pra compensar, e cada peça é truncada a um teto generoso (ver _TETO_CHARS_POR_PECA)
contra o caso patológico de uma peça de centenas de páginas."""
import logging

from sqlalchemy.orm import Session

from app.models.autos_ia import AutosIAPerguntaFaq, AutosIAPeca
from app.services.autos_ia.busca import buscar_pecas

logger = logging.getLogger(__name__)

LIMITE_PECAS_CONTEXTO = 8
_TETO_CHARS_POR_PECA = 40_000

SYSTEM_PROMPT = (
    "Você é um assistente jurídico que responde perguntas sobre um processo judicial com base "
    "EXCLUSIVAMENTE no texto integral das peças fornecidas como contexto. Se o contexto não for "
    "suficiente para responder com segurança, diga isso claramente em vez de especular. Sempre que "
    "citar um fato, mencione a peça de origem (título e páginas)."
)


def _montar_contexto(pecas: list[AutosIAPeca]) -> str:
    blocos = []
    for p in pecas:
        cabecalho = f"### {p.titulo} — págs. {p.pagina_inicio}-{p.pagina_fim}"
        if p.data_peca:
            cabecalho += f" — {p.data_peca.isoformat()}"
        if p.id_processual:
            cabecalho += f" — ID {p.id_processual}"
        texto = (p.texto_md or p.resumo or "(sem texto disponível)")[:_TETO_CHARS_POR_PECA]
        blocos.append(f"{cabecalho}\n{texto}")
    return "\n\n".join(blocos)


def _chamar_llm(pergunta: str, contexto: str) -> str:
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1536,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Pergunta: {pergunta}\n\nResumos de peças do processo:\n\n{contexto}",
        }],
    )
    return resp.content[0].text.strip() if resp.content else ""


def responder_pergunta(db: Session, pergunta_obj: AutosIAPerguntaFaq) -> None:
    try:
        pecas = buscar_pecas(
            db, pergunta_obj.caso_id, query=pergunta_obj.pergunta,
            incluir_anexos=True, limite=LIMITE_PECAS_CONTEXTO,
        )
        pecas = [p for p in pecas if p.texto_md and p.texto_md.strip()]
        if not pecas:
            pergunta_obj.resposta = (
                "Ainda não há peças lidas relacionadas a essa pergunta neste caso."
            )
            pergunta_obj.pecas_relacionadas = []
        else:
            contexto = _montar_contexto(pecas)
            pergunta_obj.resposta = _chamar_llm(pergunta_obj.pergunta, contexto)
            pergunta_obj.pecas_relacionadas = [str(p.id) for p in pecas]
        pergunta_obj.status = "respondida"
        pergunta_obj.erro_mensagem = None
    except Exception as exc:
        logger.error("Falha ao responder FAQ %s: %s", pergunta_obj.id, exc)
        pergunta_obj.status = "erro"
        pergunta_obj.erro_mensagem = str(exc)
    db.commit()
