import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.instagram import DEFAULT_ASSESSORIA_EMAILS, InstagramConfig, InstagramSugestao
from app.schemas.instagram import (
    ConfigOut,
    ConfigUpdate,
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


@router.post("/gerar", response_model=GerarResponse)
def gerar(payload: GerarRequest, db: Session = Depends(get_db)):
    if not settings.google_ai_api_key:
        raise HTTPException(status_code=400, detail="GOOGLE_AI_API_KEY não configurada no servidor.")
    quantidade = max(1, min(payload.quantidade or 3, 8))
    try:
        criadas = ia_instagram.gerar_sugestoes(db, quantidade=quantidade, formato=payload.formato)
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
    db.commit()
    db.refresh(sug)
    return sug


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


def _build_email_html(sug: InstagramSugestao, observacao: str | None) -> str:
    TEAL = "#008080"
    data_txt = sug.data_sugerida.strftime("%d/%m/%Y") if sug.data_sugerida else "a definir"
    slides_html = ""
    for i, s in enumerate(sug.slides or [], start=1):
        titulo = (s.get("titulo") or "").strip()
        corpo = (s.get("corpo") or "").strip()
        bullets = s.get("bullets") or []
        cards = s.get("cards") or []
        cta = (s.get("cta") or "").strip()
        linhas = []
        if titulo:
            linhas.append(f"<strong>{titulo}</strong>")
        if corpo:
            linhas.append(corpo)
        for b in bullets:
            linhas.append(f"• {b}")
        for c in cards:
            d = (c.get('destaque') or '').strip()
            linhas.append(f"{d} {c.get('texto','')}".strip())
        if cta:
            linhas.append(f"<em>{cta}</em>")
        corpo_slide = "<br>".join(linhas) if linhas else "—"
        slides_html += (
            f"<tr><td style='padding:10px 14px;border:1px solid #e0e0e0;vertical-align:top;'>"
            f"<span style='color:{TEAL};font-weight:700;'>Slide {i}</span> "
            f"<span style='color:#888;font-size:12px;'>({s.get('variante','light')})</span><br>"
            f"<span style='font-size:14px;color:#333;'>{corpo_slide}</span></td></tr>"
        )

    obs_html = (
        f"<p style='background:#fff8e1;padding:12px 16px;border-radius:6px;font-size:14px;'>"
        f"<strong>Observação:</strong> {observacao}</p>" if observacao else ""
    )
    fmt_txt = "Carrossel" if sug.formato == "carrossel" else "Post estático"
    return f"""<!doctype html><html><body style="font-family:Arial,sans-serif;color:#1a1a1a;max-width:640px;margin:0 auto;">
      <div style="background:{TEAL};color:#fff;padding:20px 24px;border-radius:8px 8px 0 0;">
        <div style="letter-spacing:2px;font-size:12px;opacity:.85;">POST APROVADO — @dr.lucasjudice</div>
        <h2 style="margin:6px 0 0;">{sug.titulo}</h2>
      </div>
      <div style="padding:20px 24px;border:1px solid #e0e0e0;border-top:none;">
        <p style="font-size:14px;margin:0 0 4px;"><strong>Formato:</strong> {fmt_txt} &nbsp;|&nbsp; <strong>Tema de capa:</strong> {sug.tema_capa} &nbsp;|&nbsp; <strong>Data sugerida:</strong> {data_txt}</p>
        <p style="font-size:14px;margin:0 0 16px;color:#555;"><strong>Tema:</strong> {sug.tema}</p>
        {obs_html}
        <h3 style="color:{TEAL};font-size:15px;margin:18px 0 8px;">Roteiro dos slides</h3>
        <table style="border-collapse:collapse;width:100%;">{slides_html}</table>
        <h3 style="color:{TEAL};font-size:15px;margin:18px 0 8px;">Legenda</h3>
        <p style="font-size:14px;white-space:pre-wrap;">{sug.legenda or '—'}</p>
        <p style="font-size:13px;color:{TEAL};">{sug.hashtags or ''}</p>
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

    subject = f"[Post @dr.lucasjudice] {sug.titulo}"
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
