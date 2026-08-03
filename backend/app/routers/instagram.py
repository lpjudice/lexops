import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.instagram import DEFAULT_ASSESSORIA_EMAILS, InstagramConfig, InstagramSugestao
from app.schemas.instagram import (
    AjustarRequest,
    ConfigOut,
    ConfigUpdate,
    CustosMes,
    CustosOut,
    EnviarAssessoriaRequest,
    EnviarAssessoriaResponse,
    GerarRequest,
    GerarResponse,
    SugestaoOut,
    SugestaoUpdate,
)
from app.services import ia_instagram

router = APIRouter(
    prefix="/instagram",
    tags=["instagram"],
    dependencies=[Depends(get_current_user)],
)


def _get(db: Session, sugestao_id: uuid.UUID) -> InstagramSugestao:
    sug = db.get(InstagramSugestao, sugestao_id)
    if not sug:
        raise HTTPException(status_code=404, detail="Sugestão não encontrada")
    return sug


def _checar_ia_configurada() -> None:
    """Garante que a chave do motor de IA ativo está configurada."""
    engine = (settings.instagram_ia_engine or "claude").lower()
    if engine == "claude" and settings.anthropic_api_key:
        return
    if settings.google_ai_api_key:
        return
    raise HTTPException(
        status_code=400,
        detail="Nenhuma chave de IA configurada (ANTHROPIC_API_KEY ou GOOGLE_AI_API_KEY).",
    )


def _get_config(db: Session) -> InstagramConfig:
    cfg = db.get(InstagramConfig, 1)
    if not cfg:
        cfg = InstagramConfig(id=1, assessoria_emails=DEFAULT_ASSESSORIA_EMAILS)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("/config", response_model=ConfigOut)
def obter_config(db: Session = Depends(get_db)):
    return _get_config(db)


@router.put("/config", response_model=ConfigOut)
def salvar_config(payload: ConfigUpdate, db: Session = Depends(get_db)):
    cfg = _get_config(db)
    cfg.assessoria_emails = payload.assessoria_emails.strip()
    db.commit()
    db.refresh(cfg)
    return cfg


@router.get("/sugestoes", response_model=list[SugestaoOut])
def listar_sugestoes(
    status_filtro: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    stmt = select(InstagramSugestao).order_by(
        InstagramSugestao.data_sugerida.is_(None),  # com data primeiro na agenda
        InstagramSugestao.data_sugerida.asc(),
        InstagramSugestao.data_geracao.desc(),
    )
    if status_filtro:
        stmt = stmt.where(InstagramSugestao.status == status_filtro)
    return db.execute(stmt).scalars().all()


@router.get("/custos", response_model=CustosOut)
def custos(db: Session = Depends(get_db)):
    """Gasto de IA: total, mês atual e por mês (geração + ajustes)."""
    from sqlalchemy import func as sqlfunc

    mes = sqlfunc.to_char(InstagramSugestao.data_geracao, "MM/YYYY")
    rows = db.execute(
        select(mes.label("mes"),
               sqlfunc.coalesce(sqlfunc.sum(InstagramSugestao.custo_usd), 0.0),
               sqlfunc.count())
        .group_by(mes)
        .order_by(mes.desc())
    ).all()
    por_mes = [CustosMes(mes=m, total_usd=round(float(t or 0), 4), qtd=int(q)) for m, t, q in rows]
    total = round(sum(x.total_usd for x in por_mes), 4)
    mes_atual = datetime.now(timezone.utc).strftime("%m/%Y")
    mes_atual_usd = next((x.total_usd for x in por_mes if x.mes == mes_atual), 0.0)
    return CustosOut(total_usd=total, mes_atual_usd=mes_atual_usd, por_mes=por_mes)


@router.post("/gerar", response_model=GerarResponse)
def gerar(payload: GerarRequest, db: Session = Depends(get_db)):
    _checar_ia_configurada()
    quantidade = max(1, min(payload.quantidade or 3, 8))
    fontes = set(payload.fontes) if payload.fontes else None
    try:
        criadas = ia_instagram.gerar_sugestoes(db, quantidade=quantidade, formato=payload.formato, fontes=fontes)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao gerar sugestões: {exc}")
    aviso = None if criadas else "A IA não retornou posts válidos. Tente novamente."
    return GerarResponse(criadas=len(criadas), sugestoes=criadas, aviso=aviso)


@router.patch("/sugestoes/{sugestao_id}", response_model=SugestaoOut)
def atualizar(sugestao_id: uuid.UUID, payload: SugestaoUpdate, db: Session = Depends(get_db)):
    sug = _get(db, sugestao_id)
    dados = payload.model_dump(exclude_unset=True)
    if "slides" in dados and dados["slides"] is not None:
        dados["slides"] = [s.model_dump() if hasattr(s, "model_dump") else s for s in payload.slides]
    for campo, valor in dados.items():
        setattr(sug, campo, valor)
    # Marca o momento da aprovação (para o filtro por mês na Agenda)
    if dados.get("status") == "aprovado" and sug.aprovado_em is None:
        sug.aprovado_em = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sug)
    return sug


@router.post("/sugestoes/{sugestao_id}/ajustar", response_model=SugestaoOut)
def ajustar(sugestao_id: uuid.UUID, payload: AjustarRequest, db: Session = Depends(get_db)):
    """Ajuste pontual via IA: muda só o que foi pedido, mantém o resto do post."""
    _checar_ia_configurada()
    sug = _get(db, sugestao_id)
    if not (payload.instrucao or "").strip():
        raise HTTPException(status_code=400, detail="Descreva o ajuste desejado.")
    try:
        return ia_instagram.ajustar_sugestao(db, sug, payload.instrucao.strip(), payload.slide_index)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao ajustar: {exc}")


@router.delete("/sugestoes/{sugestao_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir(sugestao_id: uuid.UUID, db: Session = Depends(get_db)):
    sug = _get(db, sugestao_id)
    db.delete(sug)
    db.commit()


def _split_emails(raw: str) -> list[str]:
    return [e.strip() for e in (raw or "").replace(";", ",").split(",") if e.strip()]


def _emails_padrao(db: Session) -> list[str]:
    cfg = _get_config(db)
    emails = _split_emails(cfg.assessoria_emails)
    if not emails:
        emails = _split_emails(settings.instagram_assessoria_emails)
    if not emails:
        emails = _split_emails(DEFAULT_ASSESSORIA_EMAILS)
    return emails


def _card_base_url() -> str:
    """Base pública do app para montar o link do card (/post/{id})."""
    fu = (settings.frontend_url or "").rstrip("/")
    if fu and "localhost" not in fu and "127.0.0.1" not in fu:
        return fu
    return "https://lexops.fly.dev"


def _mes_ano(sug: InstagramSugestao) -> str:
    d = sug.data_sugerida or date.today()
    return d.strftime("%m-%Y")


def _drive_folder_link(sug: InstagramSugestao) -> str | None:
    """Link da pasta no Drive: /Instagram/{Aprovados}/{MM-AAAA}/ (best-effort)."""
    try:
        from app.services.google_drive import get_folder_link_raiz
        return get_folder_link_raiz(["Instagram", "Aprovados", _mes_ano(sug)])
    except Exception:
        return None


def _build_email_html(sug: InstagramSugestao, observacao: str | None) -> str:
    TEAL = "#1C5A4E"
    data_txt = sug.data_sugerida.strftime("%d/%m/%Y") if sug.data_sugerida else "a definir"
    card_url = f"{_card_base_url()}/post/{sug.id}"
    drive_link = _drive_folder_link(sug)
    fmt_txt = "Carrossel" if sug.formato == "carrossel" else "Post estático"

    obs_html = (
        f"<p style='background:#fff8e1;padding:12px 16px;border-radius:6px;font-size:14px;'>"
        f"<strong>Observação:</strong> {observacao}</p>" if observacao else ""
    )
    drive_html = (
        f"<p style='margin:14px 0 0;font-size:14px;'>📁 <a href='{drive_link}' "
        f"style='color:{TEAL};'>Pasta no Drive</a></p>" if drive_link else ""
    )
    return f"""<!doctype html><html><body style="font-family:Arial,sans-serif;color:#1a1a1a;max-width:600px;margin:0 auto;">
      <div style="background:{TEAL};color:#fff;padding:22px 26px;border-radius:8px 8px 0 0;">
        <div style="letter-spacing:2px;font-size:12px;opacity:.85;">POST PARA PUBLICAR — @dr.lucasjudice</div>
        <h2 style="margin:8px 0 0;">{sug.titulo}</h2>
      </div>
      <div style="padding:24px 26px;border:1px solid #e0e0e0;border-top:none;">
        <p style="font-size:15px;margin:0 0 6px;"><strong>Data de publicação:</strong> {data_txt}</p>
        <p style="font-size:15px;margin:0 0 20px;color:#555;"><strong>Formato:</strong> {fmt_txt}</p>
        {obs_html}
        <a href="{card_url}" style="display:inline-block;background:{TEAL};color:#fff;text-decoration:none;font-weight:700;padding:14px 26px;border-radius:999px;font-size:15px;">Abrir o card para publicar →</a>
        {drive_html}
      </div>
      <p style="text-align:center;font-size:11px;color:#999;margin-top:14px;">Gestor Jurídico — Pimenta Judice Advogados</p>
    </body></html>"""


@router.post("/sugestoes/{sugestao_id}/enviar-assessoria", response_model=EnviarAssessoriaResponse)
def enviar_assessoria(
    sugestao_id: uuid.UUID, payload: EnviarAssessoriaRequest, db: Session = Depends(get_db)
):
    sug = _get(db, sugestao_id)
    destinos = payload.emails or _emails_padrao(db)
    if not destinos:
        raise HTTPException(
            status_code=400,
            detail="Nenhum e-mail de assessoria configurado. Informe destinatários ou defina INSTAGRAM_ASSESSORIA_EMAILS.",
        )

    from app.services.email_service import _send_via_gmail_oauth

    subject = f"[Publicar {sug.data_sugerida.strftime('%d/%m') if sug.data_sugerida else ''}] {sug.titulo}".strip()
    html = _build_email_html(sug, payload.observacao)
    to = destinos[0]
    cc = destinos[1:] or None
    try:
        _send_via_gmail_oauth(to, subject, html, cc=cc)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha ao enviar e-mail: {exc}")

    agora = datetime.now(timezone.utc)
    sug.enviado_assessoria_em = agora
    if sug.status == "sugerido":
        sug.status = "aprovado"
    db.commit()
    db.refresh(sug)
    return EnviarAssessoriaResponse(enviado_para=destinos, enviado_assessoria_em=agora)


def _pasta_status(sug: InstagramSugestao) -> str:
    return "Aprovados" if sug.status in ("aprovado", "publicado") else "Sugeridos"


@router.post("/sugestoes/{sugestao_id}/drive")
def salvar_no_drive(
    sugestao_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """Sobe os PNGs dos slides (+ copy.txt) gerados no navegador para o Drive:
    /Instagram/{Sugeridos|Aprovados}/{MM-AAAA}/{slug}/"""
    from app.services.google_drive import get_folder_link_raiz, upload_arquivo_raiz

    sug = _get(db, sugestao_id)
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", (sug.titulo or "post").lower()).strip("-")[:50] or "post"
    subpath = ["Instagram", _pasta_status(sug), _mes_ano(sug), f"{sug.id.hex[:6]}-{slug}"]

    enviados = 0
    for f in files:
        conteudo = f.file.read()
        if not conteudo:
            continue
        mimetype = f.content_type or ("image/png" if f.filename.endswith(".png") else "text/plain")
        if upload_arquivo_raiz(conteudo, f.filename, subpath, mimetype):
            enviados += 1

    link = get_folder_link_raiz(subpath)
    if not enviados or not link:
        raise HTTPException(status_code=502, detail="Não foi possível salvar no Drive (verifique a autenticação Google).")
    sug.drive_link = link
    db.commit()
    return {"enviados": enviados, "pasta": link}
