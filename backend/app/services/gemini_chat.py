"""
Chat com documentos de processo usando Gemini 1.5 Pro.
Funciona como NotebookLM: carrega PDFs do processo e responde perguntas em tempo real.
"""
import base64
from pathlib import Path

from app.config import settings

SYSTEM_PROMPT = (
    "Você é um assistente jurídico do escritório Pimenta Judice Advogados Associados, "
    "com acesso completo aos documentos de um processo judicial específico. "
    "Responda perguntas sobre o processo com precisão, citando trechos relevantes quando útil. "
    "Use linguagem jurídica adequada e seja objetivo. "
    "Se a informação não estiver nos documentos fornecidos, diga claramente."
)


def chat_processo(
    pergunta: str,
    historico: list[dict],   # [{"role": "user"|"model", "content": str}, ...]
    pdf_paths: list[str],
) -> str:
    if not settings.google_ai_api_key:
        return "❌ GOOGLE_AI_API_KEY não configurada."
    try:
        import httpx

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={settings.google_ai_api_key}"
        )

        contents: list[dict] = []

        # PDFs inline como contexto inicial
        pdf_parts: list = []
        for pdf_path in pdf_paths:
            p = Path(pdf_path)
            if p.exists() and p.suffix.lower() == ".pdf":
                pdf_data = base64.b64encode(p.read_bytes()).decode()
                pdf_parts.append({"inline_data": {"mime_type": "application/pdf", "data": pdf_data}})

        if pdf_parts:
            pdf_parts.append({"text": f"Acima estão {len(pdf_parts)} documento(s) do processo. Use-os para responder."})
            contents.append({"role": "user", "parts": pdf_parts})
            contents.append({"role": "model", "parts": [{"text": "Entendido. Li os documentos e estou pronto para responder."}]})

        # Histórico
        for h in historico:
            contents.append({"role": h["role"], "parts": [{"text": h["content"]}]})

        # Pergunta atual
        contents.append({"role": "user", "parts": [{"text": pergunta}]})

        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": contents,
        }

        resp = httpx.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    except Exception as e:
        return f"❌ Erro Gemini: {e}"
