"""Agente master de Instagram — @dr.lucasjudice (Pimenta Judice).

Varre os sinais da semana no sistema (publicações, andamentos, peças, teses,
insights do site) + um banco de temas evergreen e propõe posts de carrossel /
estático já estruturados no padrão visual do escritório. A saída é um JSON
estrito (lista de slides) que o front renderiza com fidelidade.

Motor: Gemini 2.5 Flash (mesmo já usado em Teses/Jurisprudência), com
responseMimeType=application/json para garantir JSON parseável.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.andamento import AndamentoProcesso
from app.models.instagram import InstagramSugestao
from app.models.publicacao import Publicacao
from app.models.tese import Tese

logger = logging.getLogger(__name__)

# Blog "Pílulas Jurídicas" do site — servido por esta API (o site injeta via JS).
# Cada item: {id, data, area, assunto, subtitulo, script, audioUrl, fonteUrl, fonteTitulo, fonteNome, tipo}
INSIGHTS_API = "https://1minaudio.fly.dev/api/blog"

# ── Banco de temas evergreen (dias sem novidade / preencher calendário) ───────
# São os pilares do @dr.lucasjudice: patrimonial, sucessório e societário.
EVERGREEN_TEMAS = [
    "O que é planejamento patrimonial e por que você precisa",
    "Holding familiar: para quem realmente faz sentido",
    "Doação de cotas com reserva de usufruto",
    "ITCMD progressivo: o custo de não planejar a sucessão",
    "Inventário judicial x extrajudicial: tempo e custo real",
    "Testamento x holding: o que protege mais o patrimônio",
    "Pacto antenupcial: o que ele protege e o que não",
    "Blindagem patrimonial: mitos e o que é juridicamente válido",
    "Protocolo familiar: governança da família empresária",
    "Acordo de sócios: as cláusulas que evitam brigas",
    "Deadlock em sociedade 50/50: como prevenir a paralisia",
    "Apuração de haveres na saída de um sócio",
    "Cláusula de incomunicabilidade e impenhorabilidade na doação",
    "Sucessão do sócio: o herdeiro entra na empresa?",
    "Reforma tributária e o impacto no planejamento sucessório",
]

# ── Design system (resumo para o prompt) ──────────────────────────────────────
DESIGN_SYSTEM = """
IDENTIDADE VISUAL @dr.lucasjudice — Pimenta Judice (advocacia patrimonialista):
- Paleta: teal #008080 (primária), cream #F5F0E8, mint #E8F5F5, branco, texto #1A1A1A.
- Cada slide tem uma "variante" de fundo: "dark" (fundo teal), "light" (fundo mint),
  "white" (fundo branco) ou "cream" (fundo creme). Alterne para não cansar o feed.
- Tema de capa (campo tema_capa) define o tom do post:
  "A" = Dark Teal (impacto/urgência), "B" = White Bold (educativo),
  "C" = Cream (premium/alta renda), "D" = Split (comparativos X vs Y).
- Tom: jurídico acessível, sem "juridiquês", credível, sem promessas de resultado.
- Nunca prometer ganho de causa nem dar consultoria específica. Conteúdo educativo.
"""

# Contrato de saída — JSON estrito. Um slide = um objeto.
JSON_CONTRATO = """
Responda APENAS com um objeto JSON (sem markdown) no formato:
{
  "posts": [
    {
      "titulo": "string curto (aparece na lista interna)",
      "tema": "assunto do post em poucas palavras",
      "formato": "carrossel" | "estatico",
      "tema_capa": "A" | "B" | "C" | "D",
      "legenda": "legenda para o Instagram (2-4 frases + 1 pergunta/CTA)",
      "hashtags": "#ate #oito #hashtags #relevantes",
      "slides": [
        {
          "variante": "dark" | "light" | "white" | "cream",
          "tipo": "capa" | "conteudo" | "cta",
          "tag": "rótulo curto em caixa alta (opcional)",
          "titulo": "headline do slide",
          "subtitulo": "apoio (opcional)",
          "corpo": "parágrafo curto (opcional)",
          "bullets": ["item 1", "item 2"],
          "cards": [ { "destaque": "Palavra:", "texto": "explicação curta" } ],
          "cta": "chamada final (só no último slide de CTA)"
        }
      ]
    }
  ]
}
REGRAS DOS SLIDES:
- carrossel = exatamente 5 slides: 1 CAPA (tipo "capa", variante da cor do tema_capa),
  3 de CONTEÚDO (tipo "conteudo", alternando light/white/cream), 1 CTA (tipo "cta").
- estatico = exatamente 1 slide (tipo "capa") com um dado/frase de impacto.
- Slide de CAPA: use tag + titulo forte (pode quebrar em linhas curtas) + subtitulo "Arraste →".
- Slides de conteúdo: prefira bullets OU cards (3 no máximo), texto curto e escaneável.
- Slide de CTA: convite para salvar/comentar/chamar no direct. Sem telefone/preço.
- Textos curtos (é imagem, não artigo). Português brasileiro. Sem emojis nos slides.
"""


def _janela(dias: int) -> date:
    return date.today() - timedelta(days=dias)


def coletar_contexto_semana(db: Session) -> dict:
    """Reúne os sinais da semana que alimentam o Agente master."""
    ctx: dict = {"publicacoes": [], "andamentos": [], "pecas": [], "teses": [], "insights": [], "evergreen": EVERGREEN_TEMAS}

    # Publicações (Diário/DJEN/Recorte) dos últimos 7 dias
    try:
        pubs = db.execute(
            select(Publicacao)
            .where(Publicacao.data_publicacao >= _janela(7))
            .where(Publicacao.rejeitada.is_(False))
            .order_by(Publicacao.data_publicacao.desc())
            .limit(30)
        ).scalars().all()
        for p in pubs:
            resumo = (p.texto_resumo or p.texto_completo or "")[:400]
            if not resumo:
                continue
            ctx["publicacoes"].append({
                "data": p.data_publicacao.isoformat() if p.data_publicacao else None,
                "tipo_ato": p.tipo_ato,
                "tribunal": p.tribunal,
                "resumo": resumo,
            })
            # Peças geradas a partir da publicação viram sinal de "peça da semana"
            if p.peca_gerada:
                ctx["pecas"].append({"tema": p.tipo_ato or "peça", "trecho": (p.peca_gerada or "")[:400]})
    except Exception as exc:  # pragma: no cover — resiliente a schema/ausência de dados
        logger.warning("[ig] falha ao coletar publicações: %s", exc)

    # Andamentos dos últimos 7 dias
    try:
        ands = db.execute(
            select(AndamentoProcesso)
            .where(AndamentoProcesso.data_andamento >= _janela(7))
            .order_by(AndamentoProcesso.data_andamento.desc())
            .limit(30)
        ).scalars().all()
        for a in ands:
            ctx["andamentos"].append({
                "data": a.data_andamento.isoformat() if a.data_andamento else None,
                "tipo": a.tipo,
                "descricao": (a.descricao or "")[:300],
            })
    except Exception as exc:  # pragma: no cover
        logger.warning("[ig] falha ao coletar andamentos: %s", exc)

    # Teses dos últimos 14 dias
    try:
        teses = db.execute(
            select(Tese).where(Tese.created_at >= datetime.combine(_janela(14), datetime.min.time()))
            .order_by(Tese.created_at.desc()).limit(15)
        ).scalars().all()
        for t in teses:
            ctx["teses"].append({"titulo": t.titulo, "trecho": (t.texto_input or "")[:400]})
    except Exception as exc:  # pragma: no cover
        logger.warning("[ig] falha ao coletar teses: %s", exc)

    # Insights do site (Pílulas Jurídicas) — hoje pode vir vazio; resiliente
    try:
        ctx["insights"] = coletar_insights_web()
    except Exception as exc:  # pragma: no cover
        logger.warning("[ig] falha ao coletar insights do site: %s", exc)

    return ctx


def coletar_insights_web(limite: int = 15) -> list[dict]:
    """Puxa as Pílulas Jurídicas recentes da API do blog (1minaudio).

    É a fonte editorial mais rica: temas jurídicos atuais já escritos pelo Lucas,
    datados e com a fonte primária. Best-effort: se a API falhar, retorna []."""
    import httpx

    resp = httpx.get(INSIGHTS_API, params={"limit": limite, "page": 1}, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    itens = data.get("posts") or data.get("data") or data.get("items") or (data if isinstance(data, list) else [])
    out: list[dict] = []
    for it in itens[:limite]:
        script = (it.get("script") or "").strip().replace("\n", " ")
        out.append({
            "data": it.get("data"),
            "area": it.get("area"),
            "assunto": it.get("assunto") or it.get("titulo"),
            "subtitulo": it.get("subtitulo"),
            "resumo": script[:500],
            "fonte": it.get("fonteUrl") or it.get("fonteTitulo"),
        })
    return out


def _resumir_contexto(ctx: dict) -> str:
    """Transforma o contexto coletado em texto para o prompt."""
    partes: list[str] = []

    def bloco(nome: str, itens: list, fmt) -> None:
        if not itens:
            return
        partes.append(f"\n### {nome} (semana):")
        for it in itens[:12]:
            partes.append("- " + fmt(it))

    bloco("Publicações / intimações", ctx.get("publicacoes", []),
          lambda p: f"[{p.get('tipo_ato') or 'ato'}] {p.get('resumo', '')}")
    bloco("Andamentos de processos", ctx.get("andamentos", []),
          lambda a: f"[{a.get('tipo') or 'andamento'}] {a.get('descricao', '')}")
    bloco("Peças produzidas", ctx.get("pecas", []),
          lambda p: f"[{p.get('tema')}] {p.get('trecho', '')}")
    bloco("Teses IA", ctx.get("teses", []),
          lambda t: f"{t.get('titulo')}: {t.get('trecho', '')}")
    bloco("Pílulas Jurídicas / Insights do site (fonte editorial rica)", ctx.get("insights", []),
          lambda i: f"[{i.get('area') or '—'}] {i.get('assunto') or ''}: {i.get('resumo', '')}")

    partes.append("\n### Temas evergreen (use quando não houver novidade forte):")
    for tema in ctx.get("evergreen", [])[:15]:
        partes.append("- " + tema)

    return "\n".join(partes) if partes else "(sem sinais da semana — use os temas evergreen)"


def _build_prompt(ctx: dict, quantidade: int, formato: str | None) -> str:
    ctx_txt = _resumir_contexto(ctx)
    fmt_instr = (
        f"Todos os {quantidade} posts devem ser do formato '{formato}'."
        if formato else
        f"Varie o formato: a maioria carrossel, 1 estático se fizer sentido. Gere {quantidade} posts."
    )
    return f"""Você é o social media jurídico do @dr.lucasjudice (Pimenta Judice Advogados),
especialista em Planejamento Patrimonial, Sucessório e Direito Societário.

Sua tarefa: propor {quantidade} sugestões de post para o Instagram, ancoradas
NOS ACONTECIMENTOS DA SEMANA. Priorize, nesta ordem, as "Pílulas Jurídicas /
Insights do site" e as "Publicações/intimações" — são os ganchos mais quentes e
atuais. Use andamentos, peças e teses como reforço, e os temas evergreen só
quando não houver gancho forte. Para cada post, escreva um campo "motivo" curto
explicando por que sugeriu (qual sinal da semana ou pilar).

{DESIGN_SYSTEM}

DADOS DA SEMANA:
{ctx_txt}

{fmt_instr}

{JSON_CONTRATO}

Inclua em cada post um campo "motivo": "1 frase explicando a origem do tema".
"""


def _call_gemini_json(prompt: str) -> dict:
    if not settings.google_ai_api_key:
        raise RuntimeError("GOOGLE_AI_API_KEY não configurada.")
    import httpx

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={settings.google_ai_api_key}"
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9},
    }
    resp = httpx.post(url, json=payload, timeout=120)
    resp.raise_for_status()
    txt = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(txt)


def _classificar_fonte(ctx: dict) -> str:
    """Fonte 'dominante' da rodada (para rotular a sugestão)."""
    if ctx.get("insights"):
        return "insight"
    if ctx.get("publicacoes"):
        return "publicacao"
    if ctx.get("andamentos"):
        return "andamento"
    if ctx.get("pecas"):
        return "peca"
    if ctx.get("teses"):
        return "tese"
    return "evergreen"


def gerar_sugestoes(db: Session, quantidade: int = 3, formato: str | None = None) -> list[InstagramSugestao]:
    """Gera sugestões, persiste no banco e retorna as instâncias criadas."""
    ctx = coletar_contexto_semana(db)
    prompt = _build_prompt(ctx, quantidade, formato)
    data = _call_gemini_json(prompt)

    posts = data.get("posts") if isinstance(data, dict) else data
    if not isinstance(posts, list):
        raise ValueError("Resposta da IA sem lista 'posts'.")

    fonte_default = _classificar_fonte(ctx)
    criadas: list[InstagramSugestao] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        slides = post.get("slides") or []
        if not slides:
            continue
        sug = InstagramSugestao(
            titulo=(post.get("titulo") or post.get("tema") or "Post sugerido")[:255],
            tema=(post.get("tema") or "")[:255],
            formato="estatico" if post.get("formato") == "estatico" else "carrossel",
            tema_capa=(post.get("tema_capa") or "A")[:1].upper(),
            slides=slides,
            legenda=post.get("legenda") or "",
            hashtags=post.get("hashtags") or "",
            fonte_tipo=fonte_default,
            fonte_ref=None,
            motivo_ia=post.get("motivo") or "",
            status="sugerido",
        )
        db.add(sug)
        criadas.append(sug)

    db.commit()
    for s in criadas:
        db.refresh(s)
    return criadas
