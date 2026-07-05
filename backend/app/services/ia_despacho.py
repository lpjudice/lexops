"""Sugestão de ação do "gestor jurídico" após uma publicação do Diário ser
confirmada como vinculada a um processo/cliente. Cruza o texto da publicação
com o contexto completo do processo (estratégia, andamentos, prazos, docs)
para sugerir o que fazer — nunca executa nada sozinho.
"""
import json
import re

from app.config import settings

MODEL = "claude-opus-4-5"

_SYSTEM = """Você é o gestor jurídico de um escritório de advocacia. Recebeu uma nova \
publicação do Diário Oficial já confirmada como sendo deste processo específico, e tem \
acesso ao contexto completo do processo (estratégia, andamentos, prazos, documentos).

Analise a publicação à luz desse contexto e retorne SOMENTE um JSON com este esquema:
{
  "resumo_raciocinio": "2-3 frases explicando o que a publicação significa NESTE processo específico, cruzando com o estágio atual",
  "requer_prazo": true ou false,
  "opcoes_prazo": [
    {
      "label": "nome curto do caminho (ex: 'Embargos de Declaração' ou 'Agravo de Instrumento')",
      "peca_necessaria": "contestacao" | "recurso" | "contrarrazoes" | "manifestacao" | "audiencia" | "pericia" | "outro",
      "dias_prazo": número inteiro,
      "tipo_contagem": "uteis" | "corridos"
    }
  ],
  "tarefas_sugeridas": [
    {"titulo": "título curto e acionável", "responsavel": "nome se identificável no contexto, senão null"}
  ],
  "rascunho_sugerido": "um parágrafo inicial de rascunho da peça, se fizer sentido gerar algo" ou null
}

Regras importantes:
- REGRA MAIS IMPORTANTE, NUNCA VIOLE: se o TEXTO DA PUBLICAÇÃO menciona um prazo explícito \
(ex: "no prazo de 10 dias", "em 5 dias", "prazo de 15 dias úteis"), você é OBRIGADO a colocar \
requer_prazo=true e preencher "opcoes_prazo" com pelo menos uma opção usando esse número de dias \
— MESMO QUE já exista uma tarefa parecida no contexto do processo (tarefas e prazos são coisas \
diferentes: uma tarefa é um lembrete informal e não substitui a contagem formal de um prazo \
processual). "Já ter uma tarefa aberta sobre o assunto" NUNCA é motivo pra deixar requer_prazo=false \
quando a publicação em si estabelece um prazo. Isso é a regra mais básica do seu trabalho — errar \
aqui significa o escritório perder um prazo de verdade.
- "opcoes_prazo" normalmente tem 1 item. Só coloque MAIS de um item quando a decisão sobre o \
ato publicado abrir mais de um caminho processual real (ex: cabe tanto embargos de declaração \
quanto agravo, com prazos diferentes) — nesse caso liste cada caminho como uma opção separada, \
pra um humano escolher qual seguir.
- "tarefas_sugeridas" pode ter 0, 1 ou várias tarefas (ex: uma pra elaborar a peça, outra pra \
juntar documento, outra pra comunicar o cliente). Não invente tarefas desnecessárias.
- requer_prazo=false e opcoes_prazo=[] só se aplicam quando a publicação é genuinamente \
informativa e NÃO menciona nenhum prazo em dias (ex: mera juntada de documento, publicação \
confirmando algo que já foi cumprido). Releia o texto da publicação antes de decidir isso.
- Sem markdown, sem explicações fora do JSON."""


_SYSTEM_PECA = """Você é o advogado redator do escritório Pimenta Judice Advogados Associados, \
OAB/ES 14.477 (advogado responsável: Lucas Pimenta Judice). Vai redigir o corpo de uma peça \
processual com base EXCLUSIVAMENTE no contexto do processo e na publicação fornecidos.

REGRAS ABSOLUTAS:
1. NUNCA invente fatos, datas, números de documentos, valores ou teses jurídicas que não estejam \
no contexto fornecido. Se precisar de uma informação que não está disponível (ex: data exata de \
um fato, número de um documento, nome de uma testemunha), escreva literalmente "XXX [o que falta, \
ex: XXX-DATA DO FATO XXX]" no lugar — isso será destacado em vermelho depois, então use esse \
marcador sempre que faltar algo, nunca tente adivinhar ou preencher com algo plausível.
2. A numeração de parágrafos só começa DEPOIS da qualificação inicial das partes (a qualificação \
em si não é numerada).
3. Se houver Memória Estratégica ou documentos do processo com fatos resumidos, você PODE abrir a \
peça com uma breve menção aos fatos relevantes do processo (2-3 frases), mas só com fatos que \
estejam de fato no contexto fornecido.
4. Use **texto** para negrito (será convertido depois). Não use outra formatação markdown.
5. Retorne SOMENTE um JSON com este esquema:
{
  "titulo_peca": "ex: CONTESTAÇÃO" ou o nome adequado da peça em maiúsculas,
  "enderecamento": "ex: EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DA [vara] DA COMARCA DE [comarca]",
  "qualificacao": "qualificação das partes (nome do cliente, tipo — autor/réu — e outra parte, com base no contexto)",
  "paragrafos": ["parágrafo 1 do corpo da peça", "parágrafo 2", "..."],
  "fechamento": "termos em que pede deferimento, local e data por extenso",
  "itens_faltantes": ["lista curta do que ficou marcado como XXX, pra revisão humana"]
}
Sem markdown fora dos campos, sem explicações extras."""


def _parse_json(raw: str) -> dict:
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if match:
        raw = match.group(1).strip()
    return json.loads(raw)


def sugerir_acao(contexto_processo: str, texto_publicacao: str) -> dict:
    if not settings.anthropic_api_key:
        return {"erro": "ANTHROPIC_API_KEY não configurada"}
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        mensagem = (
            f"CONTEXTO DO PROCESSO:\n{contexto_processo[:12000]}\n\n"
            f"PUBLICAÇÃO NOVA:\n{texto_publicacao[:4000]}"
        )
        msg = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=_SYSTEM,
            messages=[{"role": "user", "content": mensagem}],
        )
        return _parse_json(msg.content[0].text.strip())
    except Exception as e:
        return {"erro": str(e)}


def gerar_peca(
    contexto_processo: str,
    texto_publicacao: str,
    opcao_prazo: dict,
    prompt_extra: str = "",
) -> dict:
    """Gera o conteúdo da peça (texto estruturado) pra uma das opções de
    prazo/caminho já escolhida. Não inventa fatos — usa marcadores XXX pro
    que faltar. A escrita definitiva no Google Docs (timbrado) é uma etapa
    posterior que consome este mesmo conteúdo."""
    if not settings.anthropic_api_key:
        return {"erro": "ANTHROPIC_API_KEY não configurada"}
    try:
        import anthropic

        from datetime import date
        hoje_extenso = date.today().strftime("%d/%m/%Y")

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        mensagem = (
            f"DATA DE HOJE (use no fechamento, por extenso — isso NÃO é item faltante): {hoje_extenso}\n\n"
            f"CONTEXTO DO PROCESSO:\n{contexto_processo[:12000]}\n\n"
            f"PUBLICAÇÃO:\n{texto_publicacao[:4000]}\n\n"
            f"PEÇA A REDIGIR: {opcao_prazo.get('label') or opcao_prazo.get('peca_necessaria')}\n"
            + (f"\nINSTRUÇÃO ADICIONAL DO ADVOGADO:\n{prompt_extra[:2000]}" if prompt_extra else "")
        )
        msg = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=_SYSTEM_PECA,
            messages=[{"role": "user", "content": mensagem}],
        )
        return _parse_json(msg.content[0].text.strip())
    except Exception as e:
        return {"erro": str(e)}
