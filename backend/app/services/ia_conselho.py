"""Melhoria de texto via IA para o módulo Conselho (diretrizes, mensagens de eventos etc)."""
from app.config import settings


def melhorar_texto(campo: str, texto: str) -> str:
    if not settings.anthropic_api_key:
        return texto
    if not texto or not texto.strip():
        return texto
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        system = (
            "Você ajuda o escritório Pimenta Judice Advogados a redigir textos curtos e objetivos "
            f"para o campo '{campo}' de um painel de gestão interno (conselho consultivo, eventos de captação). "
            "Melhore clareza, tom profissional e concisão, mantendo o sentido original e o idioma português do Brasil. "
            "Responda APENAS com o texto melhorado, sem comentários, aspas ou explicações."
        )
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": texto}],
        )
        partes = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        resultado = "".join(partes).strip()
        return resultado or texto
    except Exception:
        return texto
