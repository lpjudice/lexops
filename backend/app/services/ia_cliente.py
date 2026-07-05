"""
Chat IA multi-modelo para contexto de cliente.
Inclui PDFs do cliente como contexto em cada chamada.
"""
import base64
from pathlib import Path

import httpx

from app.config import settings

UPLOADS_DIR = Path("/app/uploads/clientes")

_INSTRUCAO_ANTI_DISCLAIMER = (
    "\nVocê TEM acesso ao histórico e ao contexto do processo/cliente fornecido acima — "
    "isso já foi extraído do sistema interno do escritório (andamentos, prazos, documentos, "
    "memória estratégica). NUNCA diga que não tem acesso ao processo ou que precisaria consultar "
    "o sistema/tribunal online — use o que foi fornecido. Se um dado específico não estiver no "
    "contexto, diga isso pontualmente, mas não trate a ausência de UM dado como falta de acesso a tudo."
)


def _carregar_pdfs(cliente_id: str) -> list[Path]:
    pasta = UPLOADS_DIR / cliente_id
    if not pasta.exists():
        return []
    return sorted([f for f in pasta.iterdir() if f.suffix.lower() == ".pdf"])


def _texto_dos_pdfs(pdfs: list[Path]) -> str:
    """Extrai texto real dos PDFs (cascata pypdf → pdfminer → Claude OCR) pra
    injetar como texto simples — mais robusto que mandar o PDF bruto pro
    modelo (evita limites/formatos específicos de cada provedor)."""
    if not pdfs:
        return ""
    from app.services.pdf_extract import extrair_texto_pdf

    blocos = []
    for pdf in pdfs:
        try:
            texto = extrair_texto_pdf(pdf.read_bytes())
        except Exception:
            texto = ""
        if texto:
            blocos.append(f"--- Documento: {pdf.name} ---\n{texto[:6000]}")
    return "\n\n".join(blocos)


def chat_claude(
    pergunta: str, historico: list[dict], cliente_id: str, contexto: str,
    nome_cliente: str = "", pdf_paths: list[Path] | None = None,
    model: str = "claude-opus-4-5", instrucao_extra: str = "",
) -> str:
    if not settings.anthropic_api_key:
        return "❌ ANTHROPIC_API_KEY não configurada."
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        pdfs = pdf_paths if pdf_paths is not None else _carregar_pdfs(cliente_id)
        texto_docs = _texto_dos_pdfs(pdfs)

        system = (
            "Você é um assistente jurídico do escritório Pimenta Judice Advogados Associados.\n"
            + instrucao_extra
            + f"\nContexto do cliente: {contexto}\n"
            + (f"\n{texto_docs}\n" if texto_docs else "")
            + _INSTRUCAO_ANTI_DISCLAIMER
            + "\nResponda com precisão, citando documentos quando relevante. Use linguagem jurídica adequada."
        )

        messages = []
        for h in historico:
            role = "assistant" if h["role"] == "model" else h["role"]
            messages.append({"role": role, "content": h["content"]})
        messages.append({"role": "user", "content": pergunta})

        msg = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system,
            messages=messages,
        )
        return msg.content[0].text
    except Exception as e:
        return f"❌ Erro Claude: {e}"


def chat_gpt(
    pergunta: str, historico: list[dict], cliente_id: str, contexto: str,
    nome_cliente: str = "", pdf_paths: list[Path] | None = None,
    model: str = "gpt-4o", instrucao_extra: str = "",
) -> str:
    if not settings.openai_api_key:
        return "❌ OPENAI_API_KEY não configurada."
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        pdfs = pdf_paths if pdf_paths is not None else _carregar_pdfs(cliente_id)
        texto_docs = _texto_dos_pdfs(pdfs)

        system = (
            "Você é um assistente jurídico do escritório Pimenta Judice Advogados Associados.\n"
            + instrucao_extra
            + f"\nContexto do cliente: {contexto}\n"
            + (f"\n{texto_docs}\n" if texto_docs else "")
            + _INSTRUCAO_ANTI_DISCLAIMER
            + "\nResponda com precisão e use linguagem jurídica adequada."
        )

        messages: list[dict] = [{"role": "system", "content": system}]
        for h in historico:
            role = "assistant" if h["role"] == "model" else h["role"]
            messages.append({"role": role, "content": h["content"]})
        messages.append({"role": "user", "content": pergunta})

        resp = client.chat.completions.create(model=model, max_tokens=2048, messages=messages)
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"❌ Erro GPT-4o: {e}"


def chat_gemini(
    pergunta: str, historico: list[dict], cliente_id: str, contexto: str,
    nome_cliente: str = "", pdf_paths: list[Path] | None = None,
    model: str = "gemini-2.5-flash", instrucao_extra: str = "",
) -> str:
    if not settings.google_ai_api_key:
        return "❌ GOOGLE_AI_API_KEY não configurada."
    try:
        from app.services.pasta_cliente import carregar_contexto_gemini

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={settings.google_ai_api_key}"
        )

        system_text = (
            "Você é um assistente jurídico do escritório Pimenta Judice Advogados Associados.\n"
            + instrucao_extra
            + f"\nContexto do cliente: {contexto}\n"
            + _INSTRUCAO_ANTI_DISCLAIMER
            + "\nResponda com precisão, citando documentos quando relevante. Use linguagem jurídica adequada."
        )

        if pdf_paths is not None:
            arquivos_dropbox = [
                {"tipo": "pdf", "nome": p.name, "conteudo": p.read_bytes()}
                for p in pdf_paths
            ]
        else:
            # Load from Dropbox folder first
            arquivos_dropbox = carregar_contexto_gemini(nome_cliente) if nome_cliente else []

            # Fallback to /app/uploads if Dropbox is empty
            if not arquivos_dropbox:
                pdfs_fallback = _carregar_pdfs(cliente_id)
                arquivos_dropbox = [
                    {"tipo": "pdf", "nome": p.name, "conteudo": p.read_bytes()}
                    for p in pdfs_fallback
                ]

        contents: list[dict] = []
        if arquivos_dropbox:
            doc_parts: list = []
            for arq in arquivos_dropbox:
                if arq["tipo"] == "pdf":
                    pdf_data = base64.b64encode(arq["conteudo"]).decode()
                    doc_parts.append({"inline_data": {"mime_type": "application/pdf", "data": pdf_data}})
                elif arq["tipo"] == "texto":
                    doc_parts.append({"text": f"--- {arq['nome']} ---\n{arq['texto']}"})
            doc_parts.append({"text": f"Acima estão {len(arquivos_dropbox)} documento(s) do cliente."})
            contents.append({"role": "user", "parts": doc_parts})
            contents.append({"role": "model", "parts": [{"text": "Entendido. Li os documentos e estou pronto."}]})

        for h in historico:
            contents.append({"role": h["role"], "parts": [{"text": h["content"]}]})
        contents.append({"role": "user", "parts": [{"text": pergunta}]})

        payload = {
            "system_instruction": {"parts": [{"text": system_text}]},
            "contents": contents,
        }
        resp = httpx.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"❌ Erro Gemini: {e}"


CHAT_FNS = {"claude": chat_claude, "gpt": chat_gpt, "gemini": chat_gemini}


def chat(
    modelo: str, pergunta: str, historico: list[dict], cliente_id: str, contexto: str,
    nome_cliente: str = "", pdf_paths: list[Path] | None = None,
) -> str:
    fn = CHAT_FNS.get(modelo)
    if not fn:
        return f"❌ Modelo desconhecido: {modelo}"
    return fn(pergunta, historico, cliente_id, contexto, nome_cliente, pdf_paths=pdf_paths)
