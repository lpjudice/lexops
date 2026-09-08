"""Link público (somente leitura) para o contador validar a transição da
Reforma Tributária (IBS/CBS). Sem autenticação — protegido por token opaco.

Expõe apenas o material da TRANSIÇÃO: projeção plurianual IBS/CBS, alíquotas
vigentes por ano e um resumo de receita/DAS por competência. Não expõe dados
de clientes, processos ou qualquer informação sensível além do fiscal agregado.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.config_fiscal import ConfigFiscal
from app.models.nota_fiscal import NotaFiscal

router = APIRouter(prefix="/publico", tags=["publico"])


@router.get("/instagram/{sugestao_id}")
def card_instagram_publico(sugestao_id: str, db: Session = Depends(get_db)):
    """Card de post (somente leitura, sem login) para a assessoria abrir e publicar.

    Protegido pelo próprio UUID opaco. Expõe só o conteúdo do post — nada sensível."""
    import uuid as _uuid

    from app.models.instagram import InstagramSugestao
    from app.schemas.instagram import CardPublicoOut

    try:
        sid = _uuid.UUID(sugestao_id)
    except ValueError:
        raise HTTPException(404, "Link inválido")
    sug = db.get(InstagramSugestao, sid)
    if not sug:
        raise HTTPException(404, "Post não encontrado")
    return CardPublicoOut.model_validate(sug)


def _brinde_slug(titulo: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", (titulo or "brinde").lower()).strip("-")[:50] or "brinde"


def _brinde_publicado(db: Session, sugestao_id: str):
    """Busca o brinde marcado como publicado_no_site para este post — é o
    único material que a URL pública fixa (por post) expõe."""
    import uuid as _uuid

    from app.models.instagram import InstagramBrinde

    try:
        sid = _uuid.UUID(sugestao_id)
    except ValueError:
        raise HTTPException(404, "Link inválido")
    brinde = (
        db.query(InstagramBrinde)
        .filter(InstagramBrinde.sugestao_id == sid, InstagramBrinde.publicado_no_site.is_(True))
        .order_by(InstagramBrinde.publicado_em.desc())
        .first()
    )
    if not brinde:
        raise HTTPException(404, "Nenhum material publicado para este post")
    return brinde


def _resp_html(html: str, filename: str | None = None):
    from fastapi import Response
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'} if filename else {}
    return Response(content=html, media_type="text/html; charset=utf-8", headers=headers)


def _resp_pdf(html: str, filename: str):
    from fastapi import Response
    from app.services import brinde_instagram
    pdf = brinde_instagram.html_para_pdf(html)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _resp_pdf_bytes(pdf: bytes, filename: str):
    from fastapi import Response
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _material_view_ou_html(db: Session, sugestao_id: str, para_download: bool):
    from app.services import brinde_instagram
    brinde = _brinde_publicado(db, sugestao_id)
    if brinde.formato == "manual" or not brinde.conteudo:
        raise HTTPException(404, "Este material foi subido como PDF — sem versão HTML")
    html = brinde_instagram.render(brinde.conteudo, brinde.formato, "site", para_pdf=False)
    return _resp_html(html, f"{_brinde_slug(brinde.titulo)}.html" if para_download else None)


def _material_pdf(db: Session, sugestao_id: str, sufixo: str = ""):
    from app.services.google_drive import baixar_arquivo_por_id, extrair_file_id
    from app.services import brinde_instagram
    brinde = _brinde_publicado(db, sugestao_id)
    slug = _brinde_slug(brinde.titulo)
    if brinde.formato == "manual" or not brinde.conteudo:
        file_id = extrair_file_id(brinde.drive_link or "")
        pdf = baixar_arquivo_por_id(file_id) if file_id else None
        if not pdf:
            raise HTTPException(404, "PDF não encontrado no Drive")
        return _resp_pdf_bytes(pdf, f"{slug}{sufixo}.pdf")
    html = brinde_instagram.render(brinde.conteudo, brinde.formato, "site", para_pdf=True)
    return _resp_pdf(html, f"{slug}{sufixo}.pdf")


def _brinde_por_id(db: Session, brinde_id: str):
    import uuid as _uuid

    from app.models.instagram import InstagramBrinde

    try:
        bid = _uuid.UUID(brinde_id)
    except ValueError:
        raise HTTPException(404, "Link inválido")
    brinde = db.get(InstagramBrinde, bid)
    if not brinde:
        raise HTTPException(404, "Brinde não encontrado")
    return brinde


def _render_brinde_html(db: Session, brinde_id: str, para_download: bool):
    from app.services import brinde_instagram
    brinde = _brinde_por_id(db, brinde_id)
    if brinde.formato == "manual" or not brinde.conteudo:
        raise HTTPException(404, "Este material foi subido como PDF — sem versão HTML")
    html = brinde_instagram.render(brinde.conteudo, brinde.formato, "site", para_pdf=False)
    return _resp_html(html, f"{_brinde_slug(brinde.titulo)}.html" if para_download else None)


def _render_brinde_pdf(db: Session, brinde_id: str):
    from app.services.google_drive import baixar_arquivo_por_id, extrair_file_id
    from app.services import brinde_instagram
    brinde = _brinde_por_id(db, brinde_id)
    slug = _brinde_slug(brinde.titulo)
    if brinde.formato == "manual" or not brinde.conteudo:
        file_id = extrair_file_id(brinde.drive_link or "")
        pdf = baixar_arquivo_por_id(file_id) if file_id else None
        if not pdf:
            raise HTTPException(404, "PDF não encontrado no Drive")
        return _resp_pdf_bytes(pdf, f"{slug}.pdf")
    html = brinde_instagram.render(brinde.conteudo, brinde.formato, "site", para_pdf=True)
    return _resp_pdf(html, f"{slug}.pdf")


# Link direto por brinde (qualquer versão, publicada ou não) — usado nos botões
# Ver/PDF/HTML de cada item da lista, e nos 3 exemplos fixos de referência.
@router.get("/instagram/brinde/{brinde_id}")
def brinde_por_id_view(brinde_id: str, db: Session = Depends(get_db)):
    return _render_brinde_html(db, brinde_id, para_download=False)


@router.get("/instagram/brinde/{brinde_id}.html")
def brinde_por_id_html(brinde_id: str, db: Session = Depends(get_db)):
    return _render_brinde_html(db, brinde_id, para_download=True)


@router.get("/instagram/brinde/{brinde_id}.pdf")
def brinde_por_id_pdf(brinde_id: str, db: Session = Depends(get_db)):
    return _render_brinde_pdf(db, brinde_id)


# Mantém as duas famílias de rota (histórico) — ambas servem o mesmo material
# publicado do post (único estilo hoje é o "site").
@router.get("/instagram/{sugestao_id}/brinde")
def brinde_view(sugestao_id: str, db: Session = Depends(get_db)):
    return _material_view_ou_html(db, sugestao_id, para_download=False)


@router.get("/instagram/{sugestao_id}/brinde.html")
def brinde_html(sugestao_id: str, db: Session = Depends(get_db)):
    return _material_view_ou_html(db, sugestao_id, para_download=True)


@router.get("/instagram/{sugestao_id}/brinde.pdf")
def brinde_pdf(sugestao_id: str, db: Session = Depends(get_db)):
    return _material_pdf(db, sugestao_id)


@router.get("/instagram/{sugestao_id}/brinde-site")
def brinde_site_view(sugestao_id: str, db: Session = Depends(get_db)):
    return _material_view_ou_html(db, sugestao_id, para_download=False)


@router.get("/instagram/{sugestao_id}/brinde-site.html")
def brinde_site_html(sugestao_id: str, db: Session = Depends(get_db)):
    return _material_view_ou_html(db, sugestao_id, para_download=True)


@router.get("/instagram/{sugestao_id}/brinde-site.pdf")
def brinde_site_pdf(sugestao_id: str, db: Session = Depends(get_db)):
    return _material_pdf(db, sugestao_id, sufixo="-site")


def _cfg_por_token(db: Session, token: str) -> ConfigFiscal:
    if not token or len(token) < 16:
        raise HTTPException(404, "Link inválido")
    cfg = db.query(ConfigFiscal).filter(ConfigFiscal.link_publico_token == token).first()
    if not cfg:
        raise HTTPException(404, "Link inválido ou revogado")
    return cfg


@router.get("/reforma/{token}")
def reforma_publica(token: str, db: Session = Depends(get_db)):
    from app.services.nfse.visao_fiscal import (
        transicao_reforma, projecao_reforma, aliquota_efetiva, faixa_de,
    )
    cfg = _cfg_por_token(db, token)

    hoje = date.today()
    comp_atual = hoje.strftime("%Y-%m")
    ibs_pct = Decimal(str(cfg.ibs_pct)) if cfg.ibs_pct else Decimal("0")
    cbs_pct = Decimal(str(cfg.cbs_pct)) if cfg.cbs_pct else Decimal("0")

    # Receita do mês corrente (base da projeção) — só notas de produção emitidas
    receita_mes = db.query(sqlfunc.coalesce(sqlfunc.sum(NotaFiscal.valor_servicos), 0)).filter(
        NotaFiscal.status == "emitida", NotaFiscal.ambiente == 1,
        NotaFiscal.competencia == comp_atual,
    ).scalar() or 0
    receita_mes = Decimal(str(receita_mes))

    reforma = transicao_reforma(hoje.year, receita_mes, ibs_pct, cbs_pct,
                                bool(cfg.piloto_ibscbs), hoje.month)
    reforma["projecao"] = projecao_reforma(receita_mes, ibs_pct, cbs_pct)

    # Resumo dos últimos 12 meses por competência (receita + DAS estimado)
    rbt12 = Decimal(str(cfg.rbt12)) if cfg.rbt12 else None
    aliq = aliquota_efetiva(rbt12) if rbt12 else None
    linhas = (db.query(NotaFiscal.competencia,
                       sqlfunc.sum(NotaFiscal.valor_servicos).label("receita"),
                       sqlfunc.count(NotaFiscal.id).label("qtd"))
              .filter(NotaFiscal.status == "emitida", NotaFiscal.ambiente == 1)
              .group_by(NotaFiscal.competencia)
              .order_by(NotaFiscal.competencia.desc()).limit(12).all())
    competencias = []
    for comp, rec, qtd in linhas:
        rec = Decimal(str(rec or 0))
        das = (rec * aliq / 100).quantize(Decimal("0.01")) if aliq else None
        competencias.append({
            "competencia": comp, "qtd_notas": int(qtd),
            "receita": float(rec), "das_estimado": float(das) if das is not None else None,
        })

    return {
        "escritorio": cfg.razao_social,
        "cnpj": cfg.cnpj,
        "municipio": f"{cfg.municipio_nome}/{cfg.uf}",
        "regime": cfg.regime_tributario,
        "anexo": cfg.anexo_simples,
        "gerado_em": hoje.isoformat(),
        "competencia_referencia": comp_atual,
        "receita_referencia": float(receita_mes),
        "aliquota_efetiva_simples": float(aliq) if aliq else None,
        "carga_media_pct": float(cfg.carga_media_pct) if cfg.carga_media_pct else 16.33,
        "reforma": reforma,
        "competencias": competencias,
        "observacao": (
            "Material de apoio para validação contábil da transição IBS/CBS. "
            "Valores estimados a partir das notas conhecidas pelo sistema; alíquotas "
            "de 2027+ dependem de regulamentação."
        ),
    }
