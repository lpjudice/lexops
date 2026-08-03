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
from datetime import date, datetime, timedelta, timezone

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
- Paleta: teal #1C5A4E, verde-escuro #123D34 (headline), off-white #F4F3EE, cream #F5F0E8.
- Estilo EDITORIAL e MINIMALISTA: headline forte + no máximo UMA frase de apoio por slide.
  NUNCA use bullet points / listas nos slides. Texto curto (é imagem, não artigo).
- Tom: jurídico acessível, sem "juridiquês", credível. Sem promessas de resultado,
  sem prometer ganho de causa, sem consultoria específica. Conteúdo educativo.
- Sem emojis nos slides (podem aparecer só na legenda).
"""

# Contrato de saída — JSON estrito. Um slide = um objeto com um "layout".
JSON_CONTRATO = """
Responda APENAS com um objeto JSON (sem markdown) no formato:
{
  "posts": [
    {
      "titulo": "string curta (aparece na lista interna)",
      "tema": "assunto do post em poucas palavras",
      "formato": "carrossel" | "estatico",
      "legenda": "legenda do Instagram (2-4 frases + 1 pergunta/CTA; pode ter emojis)",
      "hashtags": "#ate #oito #hashtags #relevantes",
      "motivo": "1 frase: por que sugeri este tema (qual sinal da semana ou pilar)",
      "slides": [ ...ver regras abaixo... ]
    }
  ]
}

CADA SLIDE é um objeto com "tipo", "layout" e os campos daquele layout:

CAPA (1ª slide, tipo "capa") — escolha 1 dos 5 layouts e VARIE entre os posts:
- "capa_teal":     { "kicker","titulo" }                (impacto/urgência)
- "capa_offwhite": { "kicker","titulo" }                (educativo/limpo)
- "capa_split":    { "kicker","titulo" }                (tensão/comparativo)
- "capa_cream":    { "kicker","titulo" }                (premium/alta renda)
- "capa_keyword":  { "titulo","destaque" }              (destaque = 1 palavra que APARECE dentro do título)
  REGRAS DA CAPA (CRÍTICO p/ legibilidade no feed):
  * titulo = HOOK CURTO, no MÁXIMO 42 caracteres (~5-7 palavras). É um gancho, NÃO a explicação.
    Ex. BOM: "Seu quinhão pode ser penhorado?"  Ex. RUIM: uma frase inteira explicando o tema.
  * Escreva em caixa NORMAL (não CAIXA ALTA). NUNCA use markdown, asteriscos (*), # ou aspas no titulo.
  * kicker = curto, 1-3 palavras, ex.: "Holding · Sucessão".
  * destaque (capa_keyword) = UMA palavra exatamente como aparece no titulo, sem asteriscos.

MIOLO (tipo "conteudo") — ALTERNE os layouts, sem repetir sempre o mesmo, SEM bullets:
- "editorial": { "kicker","titulo","frase" }            (headline + 1 frase com barra lateral)
- "numero":    { "numero","titulo","frase" }            (numero = dado de impacto ex.: "50/50")
- "icones":    { "kicker","titulo","icones":[{"icone","label"}, ...2-3] }
- "citacao":   { "kicker","titulo","citacao" }          (citacao = definição/frase-chave em card)
- "imagem":    { "kicker","titulo","frase","icone_destaque" }
      (painel visual com UM ícone grande de marca — NÃO descreva imagens, escolha um icone_destaque)
  icone / icone_destaque ∈ [usuario,balanca,check,escudo,casa,familia,documento,acordo,grafico,engrenagem,cofre,arvore]

FECHAMENTO (última slide, tipo "fechamento", layout "fechamento"):
- { "titulo","frase","cta" }
  * VARIE o cta a cada post — NÃO use sempre "Fale com um especialista". Prefira ação de
    engajamento: "Salve este post", "Compartilhe com quem precisa", "Envie para seu contador",
    "Marque um herdeiro", "Comente PLANEJAR". Escolha o que combina com o tema.
  * titulo do fechamento = frase de reforço curta; frase = 1 linha de apoio.

REGRAS:
- carrossel = 1 capa + N slides de miolo + 1 fechamento. ESCOLHA o N conforme o
  tema exige (de 3 a 8 miolos): temas simples pedem menos, temas densos pedem mais.
  Não force 3; use quantos slides o conteúdo realmente precisar, sem encher linguiça.
- Alterne os layouts de miolo (não repita o mesmo layout em sequência).
- estatico = 1 slide (uma capa OU um "numero"/"citacao" de impacto).
- Português brasileiro. Frases curtas. Nada de listas/bullets em nenhum slide.
"""


def _janela(dias: int) -> date:
    return date.today() - timedelta(days=dias)


FONTES_VALIDAS = {"insights", "publicacoes", "andamentos", "pecas", "teses", "evergreen"}


def coletar_contexto_semana(db: Session, fontes: set[str] | None = None) -> dict:
    """Reúne os sinais da semana que alimentam o Agente master.

    `fontes` = conjunto de fontes habilitadas (None = todas). Permite, por exemplo,
    desselecionar 'insights' para forçar o Agente a buscar em outras fontes."""
    on = fontes if fontes else FONTES_VALIDAS
    ctx: dict = {"publicacoes": [], "andamentos": [], "pecas": [], "teses": [], "insights": [],
                 "evergreen": EVERGREEN_TEMAS if "evergreen" in on else []}

    # Publicações (Diário/DJEN/Recorte) dos últimos 7 dias
    if "publicacoes" in on:
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
                if p.peca_gerada and "pecas" in on:
                    ctx["pecas"].append({"tema": p.tipo_ato or "peça", "trecho": (p.peca_gerada or "")[:400]})
        except Exception as exc:  # pragma: no cover — resiliente a schema/ausência de dados
            logger.warning("[ig] falha ao coletar publicações: %s", exc)

    # Andamentos dos últimos 7 dias
    if "andamentos" in on:
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
    if "teses" in on:
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
    if "insights" in on:
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


def _build_prompt(ctx: dict, quantidade: int, formato: str | None, evitar: list[str] | None = None) -> str:
    ctx_txt = _resumir_contexto(ctx)
    fmt_instr = (
        f"Todos os {quantidade} posts devem ser do formato '{formato}'."
        if formato else
        f"Varie o formato: a maioria carrossel, 1 estático se fizer sentido. Gere {quantidade} posts."
    )
    evitar_txt = ""
    if evitar:
        lista = "\n".join(f"- {t}" for t in evitar[:40])
        evitar_txt = (
            "\n\nTEMAS JÁ ABORDADOS RECENTEMENTE (NÃO repita nem traga o mesmo ângulo — "
            "escolha assuntos ou recortes DIFERENTES):\n" + lista
        )
    return f"""Você é o social media jurídico do @dr.lucasjudice (Pimenta Judice Advogados),
especialista em Planejamento Patrimonial, Sucessório e Direito Societário.

Sua tarefa: propor {quantidade} sugestões de post para o Instagram, ancoradas
NOS ACONTECIMENTOS DA SEMANA. Priorize, nesta ordem, as "Pílulas Jurídicas /
Insights do site" e as "Publicações/intimações" — são os ganchos mais quentes e
atuais. Use andamentos, peças e teses como reforço, e os temas evergreen só
quando não houver gancho forte. VARIE bastante os temas entre si nesta rodada.
Para cada post, escreva um campo "motivo" curto (qual sinal da semana ou pilar).

{DESIGN_SYSTEM}

DADOS DA SEMANA:
{ctx_txt}{evitar_txt}

{fmt_instr}

{JSON_CONTRATO}

Inclua em cada post um campo "motivo": "1 frase explicando a origem do tema".
"""


# Preços aproximados por milhão de tokens (USD)
_GEMINI_IN_PER_MTOK = 0.30
_GEMINI_OUT_PER_MTOK = 2.50
_CLAUDE_IN_PER_MTOK = 5.00   # Opus 4.x / 5
_CLAUDE_OUT_PER_MTOK = 25.00

SYSTEM_JSON = (
    "Você é o social media jurídico do @dr.lucasjudice (Pimenta Judice). "
    "Responda SEMPRE E SOMENTE com JSON válido — sem markdown, sem crases, sem comentários."
)


def _strip_fences(txt: str) -> str:
    """Remove cercas ```json ... ``` que o modelo às vezes adiciona."""
    t = txt.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
    return t.strip()


def _call_gemini_json(prompt: str) -> tuple[dict, float]:
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
    body = resp.json()
    txt = body["candidates"][0]["content"]["parts"][0]["text"]
    usage = body.get("usageMetadata", {}) or {}
    tin = usage.get("promptTokenCount", 0) or 0
    tout = usage.get("candidatesTokenCount", 0) or 0
    custo = round((tin * _GEMINI_IN_PER_MTOK + tout * _GEMINI_OUT_PER_MTOK) / 1_000_000, 5)
    return json.loads(_strip_fences(txt)), custo


def _call_claude_json(prompt: str) -> tuple[dict, float]:
    """Gera via Claude (Anthropic). Modelo configurável (settings.instagram_claude_model)."""
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY não configurada.")
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.instagram_claude_model or "claude-opus-4-5",
        max_tokens=8000,
        system=SYSTEM_JSON,
        messages=[{"role": "user", "content": prompt}],
    )
    txt = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
    usage = getattr(msg, "usage", None)
    tin = getattr(usage, "input_tokens", 0) or 0
    tout = getattr(usage, "output_tokens", 0) or 0
    custo = round((tin * _CLAUDE_IN_PER_MTOK + tout * _CLAUDE_OUT_PER_MTOK) / 1_000_000, 5)
    return json.loads(_strip_fences(txt)), custo


def _call_llm_json(prompt: str) -> tuple[dict, float]:
    """Dispatcher: Claude por padrão, Gemini como alternativa/fallback."""
    engine = (settings.instagram_ia_engine or "claude").lower()
    if engine == "claude" and settings.anthropic_api_key:
        return _call_claude_json(prompt)
    return _call_gemini_json(prompt)


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


def _temas_recentes(db: Session, limite: int = 40) -> list[str]:
    """Títulos/temas já gerados recentemente — para o Agente não repetir assuntos."""
    try:
        rows = db.execute(
            select(InstagramSugestao.titulo, InstagramSugestao.tema)
            .order_by(InstagramSugestao.data_geracao.desc())
            .limit(limite)
        ).all()
        vistos: list[str] = []
        for titulo, tema in rows:
            t = (tema or titulo or "").strip()
            if t and t not in vistos:
                vistos.append(t)
        return vistos
    except Exception:  # pragma: no cover
        return []


_CAPA_COD = {
    "capa_teal": "1", "capa_offwhite": "2", "capa_split": "3",
    "capa_cream": "4", "capa_keyword": "5",
}


def _capa_codigo(slides: list) -> str:
    """Código 1-5 da capa (para o chip da lista), lido do 1º slide."""
    if slides and isinstance(slides[0], dict):
        return _CAPA_COD.get(slides[0].get("layout", ""), "1")
    return "1"


def ajustar_sugestao(db: Session, sug: InstagramSugestao, instrucao: str, slide_index: int | None) -> InstagramSugestao:
    """Aplica um ajuste PONTUAL via IA: muda só o que foi pedido, mantém o resto.

    Manda o post atual (JSON) + a instrução e exige de volta o MESMO post com a
    alteração mínima. Preserva layouts e a estrutura dos demais slides."""
    post_atual = {
        "titulo": sug.titulo,
        "tema": sug.tema,
        "formato": sug.formato,
        "legenda": sug.legenda,
        "hashtags": sug.hashtags,
        "slides": sug.slides,
    }
    foco = (
        f"\nO ajuste foca no slide de índice {slide_index} (base 0). Altere só esse slide."
        if slide_index is not None else ""
    )
    prompt = f"""Você edita um post de Instagram já pronto (padrão @dr.lucasjudice).
Aplique EXATAMENTE E SOMENTE o ajuste pedido, mudando o mínimo possível. Não
reescreva o post inteiro: preserve todos os outros slides, layouts, textos,
legenda e hashtags que não foram mencionados. Mantenha o mesmo schema de slides.

{DESIGN_SYSTEM}

PEDIDO DE AJUSTE: "{instrucao}"{foco}

POST ATUAL (JSON):
{json.dumps(post_atual, ensure_ascii=False)}

Responda APENAS com o JSON do post completo já ajustado, no mesmo formato
(chaves: titulo, tema, formato, legenda, hashtags, slides[]). Sem markdown."""
    data, custo = _call_llm_json(prompt)
    if not isinstance(data, dict) or not data.get("slides"):
        raise ValueError("A IA não retornou um post válido no ajuste.")
    sug.titulo = (data.get("titulo") or sug.titulo)[:255]
    sug.tema = (data.get("tema") or sug.tema)[:255]
    sug.legenda = data.get("legenda") if data.get("legenda") is not None else sug.legenda
    sug.hashtags = data.get("hashtags") if data.get("hashtags") is not None else sug.hashtags
    sug.slides = data["slides"]
    sug.tema_capa = _capa_codigo(data["slides"])
    sug.custo_usd = round((sug.custo_usd or 0.0) + custo, 5)
    # Histórico do pedido de ajuste
    hist = list(sug.ajustes or [])
    hist.append({"instrucao": instrucao, "quando": datetime.now(timezone.utc).isoformat()})
    sug.ajustes = hist
    sug.ajustes_count = (sug.ajustes_count or 0) + 1
    db.commit()
    db.refresh(sug)
    return sug


def gerar_post_de_video(tema: str, resumo: str, pontos: list[str]) -> tuple[dict, float]:
    """Claude monta UM post de carrossel a partir do conteúdo extraído de um vídeo."""
    pts = "\n".join(f"- {p}" for p in (pontos or []))
    prompt = f"""Você é o social media jurídico do @dr.lucasjudice (Pimenta Judice).
Crie UM post de carrossel a partir do CONTEÚDO DE UM VÍDEO abaixo, no padrão visual
do escritório. Fidelize-se ao que o vídeo diz — não invente fatos novos.

{DESIGN_SYSTEM}

CONTEÚDO DO VÍDEO:
Tema: {tema}
Resumo: {resumo}
Pontos-chave:
{pts}

{JSON_CONTRATO}

Gere EXATAMENTE 1 post (lista "posts" com 1 item). O carrossel deve refletir os
pontos-chave do vídeo (1 capa + miolos cobrindo os pontos + 1 fechamento).
Inclua o campo "motivo": "Gerado a partir de um vídeo enviado".
"""
    data, custo = _call_llm_json(prompt)
    posts = data.get("posts") if isinstance(data, dict) else data
    if not isinstance(posts, list) or not posts or not isinstance(posts[0], dict) or not posts[0].get("slides"):
        raise ValueError("A IA não retornou um post válido do vídeo.")
    return posts[0], custo


def gerar_sugestoes(
    db: Session, quantidade: int = 3, formato: str | None = None, fontes: set[str] | None = None,
) -> list[InstagramSugestao]:
    """Gera sugestões, persiste no banco e retorna as instâncias criadas."""
    ctx = coletar_contexto_semana(db, fontes)
    evitar = _temas_recentes(db)
    prompt = _build_prompt(ctx, quantidade, formato, evitar=evitar)
    data, custo = _call_llm_json(prompt)

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
            tema_capa=_capa_codigo(slides),
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

    # Rateia o custo da chamada entre os posts criados
    if criadas:
        por_post = round(custo / len(criadas), 5)
        for sug in criadas:
            sug.custo_usd = por_post

    db.commit()
    for s in criadas:
        db.refresh(s)
    return criadas
