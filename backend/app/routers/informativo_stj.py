import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.informativo_stj import InformativoStjConfig, InformativoStjEdicao, InformativoStjItem
from app.schemas.informativo_stj import (
    CandidatoOut,
    ConfigOut,
    ConfigUpdate,
    EdicaoDetalheOut,
    EdicaoOut,
    ItemOut,
    SyncResponse,
)
from app.services import ia_informativo_stj, scraping_informativo_stj

router = APIRouter(
    prefix="/informativo-stj",
    tags=["informativo-stj"],
    dependencies=[Depends(get_current_user)],
)


def _get_config(db: Session) -> InformativoStjConfig:
    config = db.get(InformativoStjConfig, 1)
    if not config:
        config = InformativoStjConfig(id=1, areas_selecionadas=[], keywords_livres=[])
        db.add(config)
        db.commit()
    return config


@router.get("/edicoes", response_model=list[EdicaoOut])
def listar_edicoes(db: Session = Depends(get_db), limit: int = Query(20, le=100)):
    edicoes = db.scalars(
        select(InformativoStjEdicao).order_by(InformativoStjEdicao.numero.desc()).limit(limit)
    ).all()
    out = []
    for edicao in edicoes:
        total = db.scalar(
            select(func.count()).select_from(InformativoStjItem).where(InformativoStjItem.edicao_id == edicao.id)
        ) or 0
        destacados = db.scalar(
            select(func.count())
            .select_from(InformativoStjItem)
            .where(InformativoStjItem.edicao_id == edicao.id)
            .where(InformativoStjItem.destacado.is_(True))
        ) or 0
        item = EdicaoOut.model_validate(edicao)
        item.total_itens = total
        item.total_destacados = destacados
        out.append(item)
    return out


@router.get("/edicoes/{edicao_id}", response_model=EdicaoDetalheOut)
def obter_edicao(edicao_id: uuid.UUID, db: Session = Depends(get_db)):
    edicao = db.get(InformativoStjEdicao, edicao_id)
    if not edicao:
        raise HTTPException(status_code=404, detail="Edição não encontrada")
    itens = db.scalars(
        select(InformativoStjItem)
        .where(InformativoStjItem.edicao_id == edicao_id)
        .order_by(InformativoStjItem.orgao_julgador, InformativoStjItem.ordem)
    ).all()
    out = EdicaoDetalheOut.model_validate(edicao)
    out.itens = [ItemOut.model_validate(i) for i in itens]
    out.total_itens = len(itens)
    out.total_destacados = sum(1 for i in itens if i.destacado)
    return out


@router.get("/itens", response_model=list[ItemOut])
def listar_itens(
    db: Session = Depends(get_db),
    area: str | None = None,
    destacado: bool | None = None,
    status_ia: str | None = None,
    q: str | None = None,
    limit: int = Query(50, le=200),
):
    stmt = select(InformativoStjItem).order_by(InformativoStjItem.criado_em.desc())
    if area:
        stmt = stmt.where(InformativoStjItem.ramo_direito.ilike(f"%{area}%"))
    if destacado is not None:
        stmt = stmt.where(InformativoStjItem.destacado.is_(destacado))
    if status_ia:
        stmt = stmt.where(InformativoStjItem.status_ia == status_ia)
    if q:
        stmt = stmt.where(InformativoStjItem.titulo.ilike(f"%{q}%"))
    itens = db.scalars(stmt.limit(limit)).all()
    return [ItemOut.model_validate(i) for i in itens]


@router.get("/config", response_model=ConfigOut)
def obter_config(db: Session = Depends(get_db)):
    return ConfigOut.model_validate(_get_config(db))


@router.put("/config", response_model=ConfigOut)
def atualizar_config(payload: ConfigUpdate, db: Session = Depends(get_db)):
    config = _get_config(db)
    config.areas_selecionadas = payload.areas_selecionadas
    config.keywords_livres = payload.keywords_livres
    db.commit()
    return ConfigOut.model_validate(config)


@router.post("/reclassificar")
def reclassificar(db: Session = Depends(get_db)):
    config = _get_config(db)
    itens = db.scalars(select(InformativoStjItem)).all()
    alterados = 0
    for item in itens:
        item_dados = {
            "ramo_direito": item.ramo_direito,
            "titulo": item.titulo,
            "destaque_oficial": item.destaque_oficial,
        }
        destacado, motivo = scraping_informativo_stj.calcular_destaque(item_dados, config)
        if destacado != item.destacado:
            item.destacado = destacado
            item.motivo_destaque = motivo
            if destacado and item.status_ia == "nao_aplicavel":
                item.status_ia = "pendente"
            alterados += 1
    db.commit()
    return {"total_itens": len(itens), "alterados": alterados}


@router.post("/itens/{item_id}/reprocessar", response_model=ItemOut)
def reprocessar_item(item_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        item = ia_informativo_stj.processar_item(item_id, db, forcar=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ItemOut.model_validate(item)


@router.post("/sync", response_model=SyncResponse)
def sincronizar_agora(db: Session = Depends(get_db)):
    resultado = scraping_informativo_stj.sincronizar_processar_e_notificar(db)
    return SyncResponse(**resultado)


@router.get("/candidatos", response_model=list[CandidatoOut])
def listar_candidatos(db: Session = Depends(get_db)):
    return scraping_informativo_stj.listar_candidatos(db)


@router.get("/busca", response_model=list[ItemOut])
def buscar(q: str = Query(..., min_length=2), db: Session = Depends(get_db)):
    itens = scraping_informativo_stj.buscar_itens(db, q)
    return [ItemOut.model_validate(i) for i in itens]


@router.get("/favoritos", response_model=list[ItemOut])
def listar_favoritos(db: Session = Depends(get_db)):
    itens = scraping_informativo_stj.listar_favoritos(db)
    return [ItemOut.model_validate(i) for i in itens]


@router.post("/itens/{item_id}/favoritar", response_model=ItemOut)
def favoritar_item(item_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        item = scraping_informativo_stj.toggle_favorito(item_id, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return ItemOut.model_validate(item)


@router.post("/itens/{item_id}/forcar-instagram")
def forcar_instagram(item_id: uuid.UUID, db: Session = Depends(get_db)):
    from app.services import ia_instagram

    try:
        sugestao = ia_instagram.gerar_sugestao_forcada_informativo_stj(db, item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"sugestao_id": str(sugestao.id)}
