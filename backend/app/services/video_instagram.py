"""Vídeo → copy: o Gemini assiste ao vídeo e gera a legenda pronta p/ postar.

Usa a File API do Gemini (upload → aguarda ACTIVE → generateContent). O vídeo é
interpretado pelo modelo (áudio + imagem). Claude não é usado aqui (não faz vídeo).
"""
from __future__ import annotations

import json
import time

from app.config import settings

_BASE = "https://generativelanguage.googleapis.com"
_GEMINI_IN = 0.30
_GEMINI_OUT = 2.50


def _strip_fences(txt: str) -> str:
    t = (txt or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
    return t.strip()


def _upload_gemini_file(video: bytes, mime: str, key: str) -> str:
    """Upload resumável para a File API; retorna file_uri quando ACTIVE."""
    import httpx

    start = httpx.post(
        f"{_BASE}/upload/v1beta/files?key={key}",
        headers={
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(len(video)),
            "X-Goog-Upload-Header-Content-Type": mime,
            "Content-Type": "application/json",
        },
        json={"file": {"display_name": "reels"}},
        timeout=60,
    )
    start.raise_for_status()
    upload_url = start.headers.get("X-Goog-Upload-URL")
    if not upload_url:
        raise RuntimeError("File API não retornou URL de upload.")

    up = httpx.post(
        upload_url,
        headers={
            "X-Goog-Upload-Command": "upload, finalize",
            "X-Goog-Upload-Offset": "0",
            "Content-Length": str(len(video)),
        },
        content=video,
        timeout=300,
    )
    up.raise_for_status()
    info = up.json()["file"]
    name, uri, state = info["name"], info["uri"], info.get("state")

    for _ in range(40):  # vídeo precisa processar antes de ficar ACTIVE
        if state == "ACTIVE":
            return uri
        if state == "FAILED":
            raise RuntimeError("Gemini falhou ao processar o vídeo.")
        time.sleep(3)
        r = httpx.get(f"{_BASE}/v1beta/{name}?key={key}", timeout=30)
        r.raise_for_status()
        state = r.json().get("state")
    raise RuntimeError("Vídeo não ficou pronto a tempo (timeout de processamento).")


def gerar_copy_de_video(video: bytes, mime: str, tema: str) -> tuple[dict, float]:
    """Retorna ({legenda, hashtags, roteiro}, custo_usd)."""
    import httpx

    key = settings.google_ai_api_key
    if not key:
        raise RuntimeError("GOOGLE_AI_API_KEY não configurada (necessária para vídeo).")

    uri = _upload_gemini_file(video, mime, key)
    prompt = f"""Você é o social media jurídico do @dr.lucasjudice (Pimenta Judice),
advocacia patrimonialista (holding, sucessão, societário, reforma tributária).
Assista ao vídeo (imagem + áudio) e gere a COPY pronta para postar no Instagram.
Contexto/tema do post: {tema or 'planejamento patrimonial'}.

Tom jurídico acessível, sem prometer resultado, sem consultoria específica.
Responda APENAS com JSON válido (sem markdown):
{{
  "legenda": "2 a 4 frases + 1 pergunta/CTA (pode ter emojis)",
  "hashtags": "#ate #oito #hashtags #relevantes",
  "roteiro": ["3 a 5 marcações do que aparece/é dito no vídeo (opcional)"]
}}"""
    payload = {
        "contents": [{"role": "user", "parts": [
            {"file_data": {"mime_type": mime, "file_uri": uri}},
            {"text": prompt},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8},
    }
    return _gemini_video(uri, mime, prompt, key)


def _gemini_video(uri: str, mime: str, prompt: str, key: str) -> tuple[dict, float]:
    import httpx

    payload = {
        "contents": [{"role": "user", "parts": [
            {"file_data": {"mime_type": mime, "file_uri": uri}},
            {"text": prompt},
        ]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8},
    }
    resp = httpx.post(
        f"{_BASE}/v1beta/models/gemini-2.5-flash:generateContent?key={key}",
        json=payload, timeout=180,
    )
    resp.raise_for_status()
    body = resp.json()
    txt = body["candidates"][0]["content"]["parts"][0]["text"]
    usage = body.get("usageMetadata", {}) or {}
    tin = usage.get("promptTokenCount", 0) or 0
    tout = usage.get("candidatesTokenCount", 0) or 0
    custo = round((tin * _GEMINI_IN + tout * _GEMINI_OUT) / 1_000_000, 5)
    return json.loads(_strip_fences(txt)), custo


def analisar_video_para_post(video: bytes, mime: str) -> tuple[dict, float]:
    """Analisa o vídeo e retorna o conteúdo para GERAR UM POST de carrossel.

    Retorna ({tema, resumo, pontos[], legenda, hashtags}, custo_usd)."""
    key = settings.google_ai_api_key
    if not key:
        raise RuntimeError("GOOGLE_AI_API_KEY não configurada (necessária para vídeo).")
    uri = _upload_gemini_file(video, mime, key)
    prompt = """Você é o social media jurídico do @dr.lucasjudice (Pimenta Judice),
advocacia patrimonialista. Assista ao vídeo (imagem + áudio) e EXTRAIA o conteúdo
para virar um post de carrossel no Instagram.

Responda APENAS com JSON válido (sem markdown):
{
  "tema": "assunto do vídeo em poucas palavras",
  "resumo": "3 a 5 frases resumindo o que é dito/mostrado (será a base dos slides)",
  "pontos": ["4 a 7 pontos/ideias-chave do vídeo, em ordem"],
  "legenda": "legenda pronta p/ Instagram (2-4 frases + CTA; pode ter emojis)",
  "hashtags": "#ate #oito #hashtags"
}"""
    return _gemini_video(uri, mime, prompt, key)
