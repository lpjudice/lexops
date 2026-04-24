"""
Serviço de IA para geração de teses jurídicas.
Suporta Claude (Anthropic), GPT-4o (OpenAI) e Gemini (Google).
"""
from app.config import settings

SYSTEM_PROMPT = (
    "Você é um assistente jurídico especializado em Direito brasileiro. "
    "Analise o texto fornecido e produza uma tese jurídica bem fundamentada, "
    "citando doutrina, jurisprudência e legislação aplicável quando possível. "
    "Seja objetivo, preciso e use linguagem jurídica adequada."
)


def gerar_claude(texto_input: str) -> str:
    if not settings.anthropic_api_key:
        return "❌ ANTHROPIC_API_KEY não configurada."
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": texto_input}],
        )
        return msg.content[0].text
    except Exception as e:
        return f"❌ Erro Claude: {e}"


def gerar_gpt(texto_input: str) -> str:
    if not settings.openai_api_key:
        return "❌ OPENAI_API_KEY não configurada."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=2048,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": texto_input},
            ],
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"❌ Erro GPT-4o: {e}"


def gerar_gemini(texto_input: str) -> str:
    if not settings.google_ai_api_key:
        return "❌ GOOGLE_AI_API_KEY não configurada."
    try:
        import httpx
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.5-flash:generateContent?key={settings.google_ai_api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": texto_input}]}],
        }
        resp = httpx.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"❌ Erro Gemini: {e}"


GERADORES = {
    "claude": gerar_claude,
    "gpt": gerar_gpt,
    "gemini": gerar_gemini,
}


def gerar(modelo: str, texto_input: str) -> str:
    fn = GERADORES.get(modelo)
    if not fn:
        return f"❌ Modelo desconhecido: {modelo}"
    return fn(texto_input)
