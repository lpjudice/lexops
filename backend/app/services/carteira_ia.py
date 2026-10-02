import base64
import json
import os
import httpx
from typing import Dict, Any


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

            "emissao": """Analise esta escritura de emissão de debêntures ou termo de securitização e extraia:
- nome_serie (ex: APEX I, BRMAPEX110)
- numero_emissao (número inteiro)
- emissor (nome da empresa emissora)
- cnpj_emissor
- indexador (CDI, IPCA, IGPM...)
- taxa_adicional (ex: + 2% a.a.)
- data_inicio_emissao (YYYY-MM-DD)
- data_vencimento_previsto (YYYY-MM-DD)
- resgate_antecipado_emissao (true/false — o documento PREVÊ resgate antecipado?)
- resgate_antecipado_tipo (APENAS se resgate_antecipado_emissao=true: "desvinculado_lastro" se o resgate independe do recebimento do lastro/portfólio, ou "vinculado_lastro" se condicionado ao recebimento do lastro)
- clausulas_resgate (transcreva as cláusulas relevantes sobre resgate antecipado, máx. 500 caracteres)
- prazo_carencia_meses (número de meses de carência antes de poder solicitar resgate, 0 se não houver)
- prazo_pgto_pos_resgate (prazo para pagamento após pedido de resgate, ex: "30 dias", "D+30")
- tipos_garantia (descreva as garantias: alienação fiduciária, cessão de recebíveis, aval, etc.)

Retorne APENAS JSON válido. Para campos não encontrados retorne null.""",

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

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 1024,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime_type,
                                        "data": dados_base64,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": prompt,
                                }
                            ],
                        }
                    ],
                },
            )

        resultado = response.json()
        conteudo_resposta = resultado.get("content", [{}])[0].get("text", "{}")

        try:
            dados_extraidos = json.loads(conteudo_resposta)
        except json.JSONDecodeError:
            dados_extraidos = {"raw": conteudo_resposta, "erro": "Parse JSON falhou"}

        return {
            "dados": dados_extraidos,
            "tipo": tipo_documento,
            "modelo": "claude-3-5-sonnet",
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
