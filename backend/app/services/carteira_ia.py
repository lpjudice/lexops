import base64
import json
import os
import re
import httpx
from typing import Dict, Any


def _parse_json_maybe_fenced(raw: str) -> dict:
    """Tolera a IA devolver ```json ... ``` apesar do pedido de JSON puro."""
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if m:
        raw = m.group(1).strip()
    return json.loads(raw)


class CarteiraIAService:
    """Service para processar documentos com Claude Vision"""

    @staticmethod
    async def processar_documento(
        conteudo_bytes: bytes,
        mime_type: str,
        tipo_documento: str = "geral",
    ) -> Dict[str, Any]:
        """
        Processa documento com Claude Vision.

        Extrai campos para auto-fill:
        - Debêntures: série, taxa, vencimento, valor nominal, emissor
        - Imobiliário: nome, localização, valor, fases
        - Fundos: gestora, CNPJ, taxa, data aplicação
        """

        dados_base64 = base64.standard_b64encode(conteudo_bytes).decode("utf-8")

        prompts = {
            "debenture": """Analise este documento de securitização/debenture e extraia:
- serie (ex: BRMAPEX110)
- numero_emissao
- data_emissao (YYYY-MM-DD)
- data_vencimento (YYYY-MM-DD)
- taxa_juros (%)
- valor_nominal (R$)
- emissor
- status_resgate (Ativo/Solicitado/Negado/etc)
- observacoes

Retorne APENAS JSON válido.""",

            "imobiliario": """Analise este documento imobiliário e extraia:
- nome_empreendimento
- localização
- valor_total_compromissado (R$)
- valor_efetivamente_investido (R$)
- percentual_participacao (%)
- fases (lista)
- construtor
- observacoes

Retorne APENAS JSON válido.""",

            "fundo": """Analise este documento de fundo e extraia:
- nome_fundo
- gestora
- administradora
- cnpj_fundo
- data_aplicacao (YYYY-MM-DD)
- valor_aplicado (R$)
- quantidade_cotas
- taxa_administracao (%)
- observacoes

Retorne APENAS JSON válido.""",

            "emissao": """Analise esta escritura de emissão de debêntures ou termo de securitização. \
O documento pode cobrir UMA ou VÁRIAS séries da mesma emissão (ex: Série I, Série II...) — \
cada série pode ter indexador e/ou taxa diferentes, mas o resto (emissor, cláusulas de \
resgate, carência, garantias) normalmente é igual para todas as séries do mesmo documento.

Extraia os dados COMUNS a todas as séries uma única vez em "comum", e UM item em "series" \
para CADA série encontrada (mesmo que seja só uma).

Responda SOMENTE com JSON válido (sem markdown), neste formato exato:
{
  "comum": {
    "emissor": "nome da empresa emissora",
    "cnpj_emissor": "CNPJ do emissor, se constar",
    "data_inicio_emissao": "data de início/emissão em AAAA-MM-DD, ou null",
    "resgate_antecipado_emissao": <true|false — o documento PREVÊ resgate antecipado?>,
    "resgate_antecipado_tipo": "desvinculado_lastro (resgate independe do recebimento do lastro/portfólio) ou vinculado_lastro (condicionado ao recebimento do lastro) — null se resgate_antecipado_emissao=false",
    "clausulas_resgate": "transcreva as cláusulas relevantes sobre resgate antecipado, máx. 500 caracteres",
    "prazo_carencia_dias": <número de DIAS de carência antes de poder solicitar resgate (não meses — se o documento disser em meses, converta para dias), 0 se não houver>,
    "prazo_pgto_pos_resgate": "prazo para pagamento após pedido de resgate, ex: '30 dias', 'D+30'",
    "tipos_garantia": "descreva as garantias: alienação fiduciária, cessão de recebíveis, aval, etc."
  },
  "series": [
    {
      "nome_serie": "identificação da série (ex: APEX I, BRMAPEX110, Série 1ª)",
      "numero_emissao": <número inteiro da emissão>,
      "indexador": "CDI, IPCA, IGPM... desta série",
      "taxa_adicional": "taxa desta série, ex: '+ 2% a.a.'",
      "data_vencimento_previsto": "data de vencimento desta série em AAAA-MM-DD, ou null"
    }
  ]
}

Regras:
- Se o documento tiver só uma série, "series" tem um único item mesmo assim.
- "prazo_carencia_dias" é SEMPRE em dias — nunca em meses.
- Para campos não encontrados no documento, use null (ou "" para texto, 0 para prazo_carencia_dias).""",

            "geral": """Analise este documento financeiro/investimento e extraia:
- titulo_principal
- data_emissao (YYYY-MM-DD)
- valor_total (R$)
- taxa_juros (%) [se aplicável]
- entidade_responsavel
- tipo_ativo (Debênture/Fundo/Imóvel/Outro)
- observacoes

Retorne APENAS JSON válido.""",
        }

        prompt = prompts.get(tipo_documento, prompts["geral"])

        # PDF precisa ir como bloco "document" — mandar PDF dentro de um bloco
        # "image" é rejeitado pela API (ou, dependendo da versão, ignorado),
        # fazendo a IA "não ler nada" silenciosamente.
        is_pdf = mime_type == "application/pdf"
        content_block = {
            "type": "document" if is_pdf else "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": dados_base64,
            },
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-sonnet-5",
                    "max_tokens": 2048,
                    "messages": [
                        {
                            "role": "user",
                            "content": [content_block, {"type": "text", "text": prompt}],
                        }
                    ],
                },
            )

        resultado = response.json()

        if response.status_code != 200:
            erro_msg = resultado.get("error", {}).get("message", response.text[:300])
            return {
                "dados": {},
                "tipo": tipo_documento,
                "modelo": "claude-sonnet-5",
                "erro": f"Erro da IA ({response.status_code}): {erro_msg}",
            }

        conteudo = resultado.get("content") or []
        conteudo_resposta = conteudo[0].get("text", "{}") if conteudo else "{}"

        try:
            dados_extraidos = _parse_json_maybe_fenced(conteudo_resposta)
        except json.JSONDecodeError:
            dados_extraidos = {"raw": conteudo_resposta, "erro": "Parse JSON falhou"}

        return {
            "dados": dados_extraidos,
            "tipo": tipo_documento,
            "modelo": "claude-sonnet-5",
            "tokens_usados": resultado.get("usage", {}).get("output_tokens", 0),
        }

    @staticmethod
    def comparar_termo_vs_emissao(dados_termo: Dict, dados_emissao: Dict) -> Dict[str, Any]:
        """
        Compara Termo de Securitização vs Emissão.
        Identifica contradições na taxa, vencimento, etc.
        """
        contradicoes = []

        if dados_termo.get("taxa_juros") and dados_emissao.get("taxa_juros"):
            if dados_termo["taxa_juros"] != dados_emissao["taxa_juros"]:
                contradicoes.append({
                    "campo": "taxa_juros",
                    "termo": dados_termo["taxa_juros"],
                    "emissao": dados_emissao["taxa_juros"],
                    "severa": True,
                })

        if dados_termo.get("data_vencimento") and dados_emissao.get("data_vencimento"):
            if dados_termo["data_vencimento"] != dados_emissao["data_vencimento"]:
                contradicoes.append({
                    "campo": "data_vencimento",
                    "termo": dados_termo["data_vencimento"],
                    "emissao": dados_emissao["data_vencimento"],
                    "severa": True,
                })

        return {
            "comparado": True,
            "total_contradicoes": len(contradicoes),
            "contradicoes": contradicoes,
            "recomendacao": "Revisar manualmente" if contradicoes else "OK - Documentos consistentes",
        }
