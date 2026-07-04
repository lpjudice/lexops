"""
Chat IA multi-modelo para contexto de cliente.
Inclui PDFs do cliente como contexto em cada chamada.
"""
import base64
from pathlib import Path

import httpx

from app.config import settings

UPLOADS_DIR = Path("/app/uploads/clientes")


def _carregar_pdfs(cliente_id: str) -> list[Path]:
    pasta = UPLOADS_DIR / cliente_id
    if not pasta.exists():
        return []
    return sorted([f for f in pasta.iterdir() if f.suffix.lower() == ".pdf"])


def chat_claude(
    pergunta: str, historico: list[dict], cliente_id: str, contexto: str,
    nome_cliente: str = "", pdf_paths: list[Path] | None = None,
) -> str:
    if not settings.anthropic_api_key:
        return "❌ ANTHROPIC_API_KEY não configurada."
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        pdfs = pdf_paths if pdf_paths is not None else _carregar_pdfs(cliente_id)

        system = (
            "Você é um assistente jurídico do escritório Pimenta Judice Advogados Associados.\n"
            f"Contexto do cliente: {contexto}\n"
            "Responda com precisão, citando documentos quando relevante. Use linguagem jurídica adequada."
        )

        messages = []
        for h in historico:
            role = "assistant" if h["role"] == "model" else h["role"]
            messages.append({"role": role, "content": h["content"]})

        content: list = []
        for pdf in pdfs:
            pdf_data = base64.b64encode(pdf.read_bytes()).decode()
            content.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_data},
            })
        content.append({"type": "text", "text": pergunta})
        messages.append({"role": "user", "content": content})

        msg = client.messages.create(
            model="claude-opus-4-5",
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
) -> str:
    if not settings.openai_api_key:
        return "❌ OPENAI_API_KEY não configurada."
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        pdfs = pdf_paths if pdf_paths is not None else _carregar_pdfs(cliente_id)
        pdf_note = f" [{len(pdfs)} PDF(s) do cliente disponíveis no contexto]" if pdfs else ""

        system = (
            "Você é um assistente jurídico do escritório Pimenta Judice Advogados Associados.\n"
            f"Contexto do cliente: {contexto}{pdf_note}\n"
            "Responda com precisão e use linguagem jurídica adequada."
        )

        messages: list[dict] = [{"role": "system", "content": system}]
        for h in historico:
            role = "assistant" if h["role"] == "model" else h["role"]
            messages.append({"role": role, "content": h["content"]})
        messages.append({"role": "user", "content": pergunta})

        resp = client.chat.completions.create(model="gpt-4o", max_tokens=2048, messages=messages)
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"❌ Erro GPT-4o: {e}"


def chat_gemini(
    pergunta: str, historico: list[dict], cliente_id: str, contexto: str,
    nome_cliente: str = "", pdf_paths: list[Path] | None = None,
) -> str:
    if not settings.google_ai_api_key:
        return "❌ GOOGLE_AI_API_KEY não configurada."
    try:
        from app.services.pasta_cliente import carregar_contexto_gemini

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={settings.google_ai_api_key}"
        )

        system_text = (
            "Você é um assistente jurídico do escritório Pimenta Judice Advogados Associados.\n"
            f"Contexto do cliente: {contexto}\n"
            "Responda com precisão, citando documentos quando relevante. Use linguagem jurídica adequada."
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
