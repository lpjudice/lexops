import json
import re
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cliente import Cliente
from app.models.prazo import Prazo
from app.models.publicacao import Publicacao
from app.models.processo import Processo
from app.models.tese import Tese
from app.schemas.publicacao import PublicacaoOut, PublicacaoUpdate, SyncResult
from app.services.gmail_diario import sincronizar_gmail
from app.services.ia_diario import analisar_publicacao
from app.services.scraping_tribunais import scrape_todos

router = APIRouter(prefix="/diario", tags=["diario"])


class DiarioMonitoringConfig(BaseModel):
    tribunais: list[str]
    termos_extras: list[str]
    auto_sync: bool = True


def _normalizar_texto_busca(texto: str) -> str:
    texto = (texto or "").casefold()
    substituicoes = str.maketrans(
        "áàâãäéèêëíìîïóòôõöúùûüç",
        "aaaaaeeeeiiiiooooouuuuc",
    )
    texto = texto.translate(substituicoes)
    return re.sub(r"\s+", " ", texto).strip()


def _normalizar_cnj(numero: str | None) -> str:
    return re.sub(r"\D", "", numero or "")


def _termo_exato_no_texto(texto: str, termo: str) -> bool:
    termo_norm = _normalizar_texto_busca(termo)
    if not termo_norm:
        return False
    padrao = r"(?<![a-z0-9])" + re.escape(termo_norm).replace(r"\ ", r"\s+") + r"(?![a-z0-9])"
    return re.search(padrao, _normalizar_texto_busca(texto)) is not None


def _nomes_monitorados(db: Session, termos_extras: list[str] | None = None) -> list[str]:
    nomes = [c.nome.strip() for c in db.query(Cliente).all() if getattr(c, "nome", None) and c.nome.strip()]
    nomes.extend([t.strip() for t in (termos_extras or []) if t and t.strip()])
    vistos: set[str] = set()
    resultado: list[str] = []
    for nome in nomes:
        chave = _normalizar_texto_busca(nome)
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(nome)
    return resultado


def _processos_por_cnj(db: Session) -> dict[str, Processo]:
    processos = db.query(Processo).all()
    return {
        _normalizar_cnj(processo.numero_cnj): processo
        for processo in processos
        if _normalizar_cnj(processo.numero_cnj)
    }


def _termos_monitorados_para_busca(
    db: Session,
    termos_busca: list[str] | None = None,
) -> list[str]:
    from app.services.diario_monitoring import load_monitoring_config

    config = load_monitoring_config()
    valores: list[str] = []
    valores.extend(termos_busca or [])
    valores.extend(config.get("termos_extras") or [])
    valores.extend(
        cliente.nome.strip()
        for cliente in db.query(Cliente).all()
        if getattr(cliente, "nome", None) and cliente.nome.strip()
    )
    valores.extend(
        processo.numero_cnj.strip()
        for processo in db.query(Processo).all()
        if getattr(processo, "numero_cnj", None) and processo.numero_cnj.strip()
    )

    vistos: set[str] = set()
    resultado: list[str] = []
    for valor in valores:
        valor_limpo = str(valor or "").strip()
        chave = _normalizar_cnj(valor_limpo) if len(_normalizar_cnj(valor_limpo)) == 20 else _normalizar_texto_busca(valor_limpo)
        if not valor_limpo or not chave or chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(valor_limpo)
    return resultado


def _item_tem_match_monitorado_exato(
    item: dict,
    processos_por_cnj: dict[str, Processo],
    nomes_monitorados: list[str],
) -> tuple[bool, uuid.UUID | None]:
    texto = f"{item.get('texto_completo') or ''} {item.get('texto_resumo') or ''}"
    cnj_item = _normalizar_cnj(item.get("numero_cnj"))
    if cnj_item and cnj_item in processos_por_cnj:
        return True, processos_por_cnj[cnj_item].id

    for cnj, processo in processos_por_cnj.items():
        if cnj and cnj in _normalizar_cnj(texto):
            return True, processo.id

    for nome in nomes_monitorados:
        if _termo_exato_no_texto(texto, nome):
            return True, None

    return False, None


def _filtrar_itens_monitorados_exatos(
    itens: list[dict],
    db: Session,
    termos_busca: list[str] | None = None,
) -> list[dict]:
    from app.services.diario_monitoring import load_monitoring_config

    config = load_monitoring_config()
    processos_por_cnj = _processos_por_cnj(db)
    termos_extras = [
        termo
        for termo in [*(config.get("termos_extras") or []), *(termos_busca or [])]
        if len(_normalizar_cnj(termo)) != 20
    ]
    nomes_monitorados = _nomes_monitorados(db, termos_extras)

    filtrados: list[dict] = []
    for item in itens:
        ok, processo_id = _item_tem_match_monitorado_exato(item, processos_por_cnj, nomes_monitorados)
        if not ok:
            continue
        if processo_id:
            item = {**item, "processo_id": processo_id}
        filtrados.append(item)
    return filtrados


def _texto_chave_publicacao(texto: str | None) -> str:
    texto_norm = _normalizar_texto_busca(texto or "")
    return texto_norm[:300]


def _inserir_publicacoes(itens: list[dict], db: Session) -> tuple[int, int, int]:
    """Insere publicações evitando duplicatas. Retorna (inseridas, duplicatas, erros)."""
    inseridas = duplicatas = erros = 0
    for item in itens:
        try:
            # Deduplicação por email_message_id (Gmail) ou por cnj+data+fonte
            email_id = item.get("email_message_id")
            if email_id:
                existe = db.query(Publicacao).filter(
                    Publicacao.email_message_id == email_id
                ).first()
            else:
                texto_chave = _texto_chave_publicacao(item.get("texto_resumo") or item.get("texto_completo"))
                q = db.query(Publicacao).filter(
                    Publicacao.data_publicacao == item.get("data_publicacao"),
                    Publicacao.tribunal == item.get("tribunal"),
                )
                if item.get("numero_cnj"):
                    q = q.filter(Publicacao.numero_cnj == item.get("numero_cnj"))
                else:
                    q = q.filter(Publicacao.texto_resumo == item.get("texto_resumo"))
                candidatos = q.all()
                existe = next(
                    (
                        pub
                        for pub in candidatos
                        if _texto_chave_publicacao(pub.texto_resumo or pub.texto_completo) == texto_chave
                    ),
                    None,
                )

            if existe:
                duplicatas += 1
                continue

            # Tenta vincular automaticamente a processo cadastrado
            processo_id = None
            if item.get("processo_id"):
                processo_id = item.get("processo_id")
            if item.get("numero_cnj"):
                proc = db.query(Processo).filter(
                    Processo.numero_cnj == item["numero_cnj"]
                ).first()
                if proc:
                    processo_id = proc.id

            pub = Publicacao(
                fonte=item["fonte"],
                data_publicacao=item["data_publicacao"],
                numero_cnj=item.get("numero_cnj"),
                tipo_ato=item.get("tipo_ato"),
                tribunal=item.get("tribunal"),
                texto_resumo=item.get("texto_resumo"),
                texto_completo=item.get("texto_completo"),
                email_message_id=email_id,
                processo_id=processo_id,
                url_fonte=item.get("url_fonte"),
            )
            db.add(pub)
            inseridas += 1
        except Exception:
            erros += 1

    db.commit()
    return inseridas, duplicatas, erros


# ── Sync endpoints ─────────────────────────────────────────────────────────────

@router.post("/gmail/sync", response_model=SyncResult)
def sync_gmail(days_back: int = Query(3, ge=1, le=30), db: Session = Depends(get_db)):
    """Lê emails dos últimos N dias e importa publicações."""
    itens = sincronizar_gmail(days_back=days_back)
    ins, dup, err = _inserir_publicacoes(itens, db)
    return SyncResult(inseridas=ins, duplicatas=dup, erros=err, fonte="gmail")


@router.post("/scraping/sync", response_model=SyncResult)
def sync_scraping(
    tribunais: list[str] = Query(default=["TJES", "TJSP", "TJAM", "TJRJ"]),
    data: date | None = Query(None),
    days_back: int = Query(1, ge=1, le=30),
    termos: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
):
    """Roda scrapers nos tribunais selecionados para a data informada."""
    tribunais_validos = [t for t in tribunais if t in {"TJES", "TJSP", "TJAM", "TJRJ", "DJEN"}]
    if not tribunais_validos:
        raise HTTPException(status_code=400, detail="Selecione ao menos um tribunal local válido.")
    termos_monitorados = _termos_monitorados_para_busca(db, termos)
    itens = scrape_todos(
        tribunais=tribunais_validos,
        data=data,
        termos=termos_monitorados or None,
        days_back=days_back,
    )
    itens = _filtrar_itens_monitorados_exatos(itens, db, termos_monitorados)
    ins, dup, err = _inserir_publicacoes(itens, db)
    return SyncResult(inseridas=ins, duplicatas=dup, erros=err, fonte="scraping")


@router.get("/monitoramento", response_model=DiarioMonitoringConfig)
def obter_monitoramento():
    from app.services.diario_monitoring import load_monitoring_config

    return DiarioMonitoringConfig(**load_monitoring_config())


@router.put("/monitoramento", response_model=DiarioMonitoringConfig)
def salvar_monitoramento(body: DiarioMonitoringConfig):
    from app.services.diario_monitoring import save_monitoring_config

    saved = save_monitoring_config(body.model_dump())
    return DiarioMonitoringConfig(**saved)


# ── CRUD ───────────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[PublicacaoOut])
def listar_publicacoes(
    lida: bool | None = Query(None),
    processo_id: uuid.UUID | None = Query(None),
    tribunal: str | None = Query(None),
    data_inicio: date | None = Query(None),
    data_fim: date | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Publicacao)
    if lida is not None:
        q = q.filter(Publicacao.lida == lida)
    if processo_id:
        q = q.filter(Publicacao.processo_id == processo_id)
    if tribunal:
        q = q.filter(Publicacao.tribunal == tribunal)
    if data_inicio:
        q = q.filter(Publicacao.data_publicacao >= data_inicio)
    if data_fim:
        q = q.filter(Publicacao.data_publicacao <= data_fim)
    return q.order_by(Publicacao.data_publicacao.desc(), Publicacao.created_at.desc()).all()


@router.get("/{pub_id}", response_model=PublicacaoOut)
def obter_publicacao(pub_id: uuid.UUID, db: Session = Depends(get_db)):
    pub = db.query(Publicacao).filter(Publicacao.id == pub_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    return pub


@router.patch("/{pub_id}", response_model=PublicacaoOut)
def atualizar_publicacao(
    pub_id: uuid.UUID, data: PublicacaoUpdate, db: Session = Depends(get_db)
):
    pub = db.query(Publicacao).filter(Publicacao.id == pub_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(pub, field, value)
    db.commit()
    db.refresh(pub)
    return pub


@router.patch("/{pub_id}/lida", response_model=PublicacaoOut)
def marcar_lida(pub_id: uuid.UUID, db: Session = Depends(get_db)):
    pub = db.query(Publicacao).filter(Publicacao.id == pub_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    pub.lida = True
    db.commit()
    db.refresh(pub)
    return pub


@router.delete("/{pub_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_publicacao(pub_id: uuid.UUID, db: Session = Depends(get_db)):
    pub = db.query(Publicacao).filter(Publicacao.id == pub_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    db.delete(pub)
    db.commit()


# ── IA endpoints ──────────────────────────────────────────────────────────────

@router.post("/{pub_id}/analisar", response_model=PublicacaoOut)
def analisar_publicacao_ia(pub_id: uuid.UUID, db: Session = Depends(get_db)):
    """Envia o texto da publicação ao Claude e salva a análise estruturada."""
    pub = db.query(Publicacao).filter(Publicacao.id == pub_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")

    texto = pub.texto_completo or pub.texto_resumo or ""
    if not texto:
        raise HTTPException(status_code=400, detail="Publicação sem texto para analisar")

    analise = analisar_publicacao(texto)
    pub.analise_ia = json.dumps(analise, ensure_ascii=False)

    # Extrai cliente_nome da análise para mostrar no card
    if "cliente_nome" in analise and analise["cliente_nome"]:
        pub.cliente_nome_pub = analise["cliente_nome"]

    # Tenta vincular processo pelo CNJ extraído pela IA, se ainda não vinculado
    if not pub.processo_id and analise.get("numero_cnj"):
        proc = db.query(Processo).filter(
            Processo.numero_cnj == analise["numero_cnj"]
        ).first()
        if proc:
            pub.processo_id = proc.id

    db.commit()
    db.refresh(pub)
    return pub


@router.post("/{pub_id}/criar-prazo")
def criar_prazo_da_publicacao(pub_id: uuid.UUID, db: Session = Depends(get_db)):
    """Cria um Prazo baseado na análise IA da publicação."""
    pub = db.query(Publicacao).filter(Publicacao.id == pub_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    if not pub.processo_id:
        raise HTTPException(
            status_code=400,
            detail="Vincule a publicação a um processo antes de criar o prazo",
        )
    if not pub.analise_ia:
        raise HTTPException(status_code=400, detail="Execute a análise IA primeiro")

    analise = json.loads(pub.analise_ia)
    if analise.get("erro"):
        raise HTTPException(status_code=400, detail=f"Análise com erro: {analise['erro']}")
    if not analise.get("requer_resposta"):
        raise HTTPException(status_code=400, detail="A IA indicou que esta publicação não requer resposta")

    # Mapeia peça → tipo_prazo
    MAPA_TIPO: dict[str, str] = {
        "contestacao": "contestacao",
        "recurso": "recurso",
        "contrarrazoes": "contrarrazoes",
        "manifestacao": "manifestacao",
        "audiencia": "audiencia",
        "pericia": "pericia",
    }
    tipo = MAPA_TIPO.get(analise.get("peca_necessaria", ""), "outro")
    dias = analise.get("dias_prazo") or 15
    tipo_contagem = analise.get("tipo_contagem", "uteis")
    data_pub = analise.get("data_publicacao") or str(pub.data_publicacao)

    from datetime import date as _date
    from app.services.prazo_calc import calcular_prazo

    # Estado do processo vinculado, senão usa SP como padrão
    estado = "SP"
    if pub.processo_id:
        proc = db.query(Processo).filter(Processo.id == pub.processo_id).first()
        if proc:
            estado = proc.estado if proc.estado != "outro" else "SP"

    dp = _date.fromisoformat(data_pub) if isinstance(data_pub, str) else data_pub
    data_limite, data_limite_sf = calcular_prazo(
        db=db,
        data_publicacao=dp,
        dias=dias,
        estado=estado,
        tipo_contagem=tipo_contagem,
    )

    prazo = Prazo(
        processo_id=pub.processo_id,
        tipo=tipo,
        descricao=analise.get("resumo", ""),
        data_publicacao=data_pub,
        dias_prazo=dias,
        tipo_contagem=tipo_contagem,
        data_limite=data_limite,
        data_limite_sem_feriado=data_limite_sf,
        status="pendente",
    )
    db.add(prazo)

    # Vincula prazo à publicação
    pub.prazo_id = prazo.id
    pub.gera_prazo = True

    db.commit()
    db.refresh(prazo)
    return {"prazo_id": str(prazo.id), "data_limite": str(prazo.data_limite), "tipo": tipo}


@router.post("/{pub_id}/criar-tese")
def criar_tese_da_publicacao(pub_id: uuid.UUID, db: Session = Depends(get_db)):
    """Cria uma Tese pré-preenchida com o contexto da publicação."""
    pub = db.query(Publicacao).filter(Publicacao.id == pub_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    if not pub.analise_ia:
        raise HTTPException(status_code=400, detail="Execute a análise IA primeiro")

    analise = json.loads(pub.analise_ia)
    cliente_id = None
    if pub.processo_id:
        proc = db.query(Processo).filter(Processo.id == pub.processo_id).first()
        if proc:
            cliente_id = proc.cliente_id

    resumo = analise.get("resumo", "")
    peca = analise.get("peca_necessaria", "")
    texto = (
        f"Publicação do DJe em {pub.data_publicacao}:\n\n"
        f"{resumo}\n\n"
        f"Peça necessária: {peca}\n\n"
        f"Texto completo da publicação:\n{pub.texto_completo or pub.texto_resumo or ''}"
    )

    tese = Tese(
        titulo=f"{'Análise — ' + (analise.get('numero_cnj') or str(pub.data_publicacao))}",
        texto_input=texto,
        processo_id=pub.processo_id,
        cliente_id=cliente_id,
        modelo_ativo="claude",
    )
    db.add(tese)
    db.commit()
    db.refresh(tese)
    return {"tese_id": str(tese.id)}
