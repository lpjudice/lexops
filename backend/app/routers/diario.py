import json
import re
import time
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
from app.services.scraping_tribunais import (
    DiarioScrapingError,
    _limpar_html_publicacao,
    _nome_restrito_no_texto,
    scrape_todos,
)

router = APIRouter(prefix="/diario", tags=["diario"])


class DiarioMonitoringConfig(BaseModel):
    tribunais: list[str]
    termos_extras: list[str]
    advogados_monitorados: list[str] = []
    clientes_monitorados_extras: list[str] = []
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


def _limpar_nome_monitorado(nome: str) -> str:
    nome = re.sub(r"\([^)]*\)", " ", nome or "")
    return re.sub(r"\s+", " ", nome).strip()


def _dedupe_valores(valores: list[str]) -> list[str]:
    vistos: set[str] = set()
    resultado: list[str] = []
    for valor in valores:
        valor_limpo = _limpar_nome_monitorado(str(valor or "").strip())
        chave = _normalizar_cnj(valor_limpo) if len(_normalizar_cnj(valor_limpo)) == 20 else _normalizar_texto_busca(valor_limpo)
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(valor_limpo)
    return resultado


def _processos_por_cnj(db: Session) -> dict[str, Processo]:
    processos = db.query(Processo).all()
    return {
        _normalizar_cnj(processo.numero_cnj): processo
        for processo in processos
        if _normalizar_cnj(processo.numero_cnj)
    }


def _advogados_monitorados() -> list[str]:
    from app.services.diario_monitoring import load_monitoring_config

    config = load_monitoring_config()
    return _dedupe_valores(config.get("advogados_monitorados") or config.get("termos_extras") or [])


def _clientes_monitorados(db: Session) -> list[str]:
    from app.services.diario_monitoring import load_monitoring_config

    config = load_monitoring_config()
    valores = [
        cliente.nome.strip()
        for cliente in db.query(Cliente).all()
        if getattr(cliente, "nome", None) and cliente.nome.strip()
    ]
    valores.extend(config.get("clientes_monitorados_extras") or [])
    return _dedupe_valores(valores)


def _processos_monitorados_para_busca(db: Session) -> list[str]:
    return _dedupe_valores([
        processo.numero_cnj.strip()
        for processo in db.query(Processo).all()
        if getattr(processo, "numero_cnj", None) and processo.numero_cnj.strip()
    ])


def _termos_monitorados_para_busca(db: Session, incluir_clientes: bool = False) -> list[str]:
    valores = [*_processos_monitorados_para_busca(db), *_advogados_monitorados()]
    if incluir_clientes:
        valores.extend(_clientes_monitorados(db))
    return _dedupe_valores(valores)


def _match_publicacao_monitorada(
    item: dict,
    processos_por_cnj: dict[str, Processo],
    advogados_monitorados: list[str],
    clientes_monitorados: list[str] | None = None,
) -> dict | None:
    texto = f"{item.get('_match_text') or ''} {item.get('texto_completo') or ''} {item.get('texto_resumo') or ''}"
    cnj_item = _normalizar_cnj(item.get("numero_cnj"))
    if cnj_item and cnj_item in processos_por_cnj:
        processo = processos_por_cnj[cnj_item]
        return {
            "match_tipo": "processo",
            "match_categoria": "processo",
            "match_nome": processo.numero_cnj,
            "match_processo_id": processo.id,
            "processo_id": processo.id,
            "match_detalhes": {"origem": "numero_cnj_publicado"},
        }

    for cnj, processo in processos_por_cnj.items():
        if cnj and cnj in _normalizar_cnj(texto):
            return {
                "match_tipo": "processo",
                "match_categoria": "processo",
                "match_nome": processo.numero_cnj,
                "match_processo_id": processo.id,
                "processo_id": processo.id,
                "match_detalhes": {"origem": "numero_cnj_no_texto"},
            }

    for nome in advogados_monitorados:
        if _termo_exato_no_texto(texto, nome) or _nome_restrito_no_texto(texto, nome):
            return {
                "match_tipo": "advogado",
                "match_categoria": "advogado",
                "match_nome": nome,
                "match_processo_id": None,
                "match_detalhes": {"origem": "advogado_monitorado"},
            }

    for nome in clientes_monitorados or []:
        if _termo_exato_no_texto(texto, nome) or _nome_restrito_no_texto(texto, nome):
            return {
                "match_tipo": "cliente",
                "match_categoria": "cliente",
                "match_nome": nome,
                "match_processo_id": None,
                "match_detalhes": {"origem": "cliente_monitorado"},
            }

    return None


def _aplicar_match_item(item: dict, match: dict) -> dict:
    detalhes = match.get("match_detalhes")
    item = {
        **item,
        "match_tipo": match.get("match_tipo"),
        "match_nome": match.get("match_nome"),
        "match_categoria": match.get("match_categoria"),
        "match_processo_id": match.get("match_processo_id"),
        "match_detalhes": json.dumps(detalhes or {}, ensure_ascii=False),
    }
    if match.get("processo_id"):
        item["processo_id"] = match["processo_id"]
    return item


def _filtrar_itens_monitorados(
    itens: list[dict],
    db: Session,
    incluir_clientes: bool = False,
    incluir_advogados: bool = True,
) -> list[dict]:
    processos_por_cnj = _processos_por_cnj(db)
    advogados = _advogados_monitorados() if incluir_advogados else []
    clientes = _clientes_monitorados(db) if incluir_clientes else []

    filtrados: list[dict] = []
    for item in itens:
        match = _match_publicacao_monitorada(item, processos_por_cnj, advogados, clientes)
        if not match:
            continue
        filtrados.append(_aplicar_match_item(item, match))
    return filtrados


def _reclassificar_publicacao(pub: Publicacao, db: Session) -> bool:
    item = {
        "numero_cnj": pub.numero_cnj,
        "texto_resumo": pub.texto_resumo,
        "texto_completo": pub.texto_completo,
    }
    match = _match_publicacao_monitorada(
        item,
        _processos_por_cnj(db),
        _advogados_monitorados(),
        _clientes_monitorados(db),
    )
    if not match:
        match = {
            "match_tipo": "revisar",
            "match_categoria": "revisar",
            "match_nome": None,
            "match_processo_id": None,
            "match_detalhes": {"origem": "sem_match_confiavel"},
        }
    novo_processo_id = match.get("processo_id") or pub.processo_id
    valores = {
        "match_tipo": match.get("match_tipo"),
        "match_nome": match.get("match_nome"),
        "match_categoria": match.get("match_categoria"),
        "match_processo_id": match.get("match_processo_id"),
        "match_detalhes": json.dumps(match.get("match_detalhes") or {}, ensure_ascii=False),
        "processo_id": novo_processo_id,
    }
    alterou = False
    for attr, valor in valores.items():
        if getattr(pub, attr) != valor:
            setattr(pub, attr, valor)
            alterou = True
    return alterou


def _texto_chave_publicacao(texto: str | None) -> str:
    texto_norm = _normalizar_texto_busca(texto or "")
    return texto_norm


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
                texto_resumo_limpo = _limpar_html_publicacao(item.get("texto_resumo") or "")
                texto_completo_limpo = _limpar_html_publicacao(item.get("texto_completo") or "")
                item = {**item, "texto_resumo": texto_resumo_limpo, "texto_completo": texto_completo_limpo}
                texto_chave = _texto_chave_publicacao(texto_resumo_limpo or texto_completo_limpo)
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
                alterou = False
                for attr in ("texto_resumo", "texto_completo"):
                    texto_atual = getattr(existe, attr) or ""
                    texto_limpo = _limpar_html_publicacao(texto_atual)
                    texto_novo = item.get(attr) or ""
                    if texto_novo and texto_novo != texto_atual:
                        setattr(existe, attr, texto_novo)
                        alterou = True
                    elif texto_limpo and texto_limpo != texto_atual:
                        setattr(existe, attr, texto_limpo)
                        alterou = True
                for attr in ("match_tipo", "match_nome", "match_categoria", "match_processo_id", "match_detalhes"):
                    valor_novo = item.get(attr)
                    if valor_novo is not None and getattr(existe, attr) != valor_novo:
                        setattr(existe, attr, valor_novo)
                        alterou = True
                if item.get("processo_id") and existe.processo_id != item.get("processo_id"):
                    existe.processo_id = item.get("processo_id")
                    alterou = True
                if alterou:
                    db.add(existe)
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
                match_tipo=item.get("match_tipo"),
                match_nome=item.get("match_nome"),
                match_categoria=item.get("match_categoria"),
                match_processo_id=item.get("match_processo_id"),
                match_detalhes=item.get("match_detalhes"),
            )
            db.add(pub)
            inseridas += 1
        except Exception:
            erros += 1

    db.commit()
    return inseridas, duplicatas, erros


def _mensagem_erro_scraping(exc: DiarioScrapingError) -> str:
    detalhe = str(exc)
    if re.search(r"(?<!\d)429(?!\d)", detalhe):
        return (
            "A fonte do Diário limitou temporariamente as consultas por excesso de buscas "
            "em sequência. Aguarde alguns minutos e tente novamente."
        )
    if re.search(r"(?<!\d)403(?!\d)", detalhe):
        return (
            "A fonte do Diário bloqueou temporariamente a consulta automática. "
            "Tente novamente mais tarde."
        )
    if re.search(r"(?<!\d)5\d{2}(?!\d)", detalhe):
        return (
            "A fonte do Diário está instável neste momento. "
            "Tente novamente em alguns minutos."
        )
    return (
        "Não foi possível consultar o Diário Oficial agora. "
        "Tente novamente em alguns minutos."
    )


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
    termos_monitorados = _termos_monitorados_para_busca(db, incluir_clientes=False)
    try:
        itens = scrape_todos(
            tribunais=tribunais_validos,
            data=data,
            termos=termos_monitorados or None,
            days_back=days_back,
        )
    except DiarioScrapingError as exc:
        return SyncResult(
            inseridas=0,
            duplicatas=0,
            erros=1,
            fonte="scraping",
            mensagem=_mensagem_erro_scraping(exc),
        )
    itens = _filtrar_itens_monitorados(itens, db, incluir_clientes=False, incluir_advogados=True)
    ins, dup, err = _inserir_publicacoes(itens, db)
    return SyncResult(inseridas=ins, duplicatas=dup, erros=err, fonte="scraping")


@router.post("/scraping/clientes/sync", response_model=SyncResult)
def sync_scraping_clientes(
    data: date | None = Query(None),
    days_back: int = Query(1, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """Busca manual separada por nomes de clientes em todas as fontes do Diário."""
    tribunais_validos = ["DJEN", "TJSP", "TJES", "TJAM", "TJRJ"]
    termos_clientes = _dedupe_valores([*_processos_monitorados_para_busca(db), *_clientes_monitorados(db)])
    if not termos_clientes:
        return SyncResult(inseridas=0, duplicatas=0, erros=0, fonte="scraping_clientes", mensagem="Nenhum cliente monitorado para buscar.")
    totais = {"inseridas": 0, "duplicatas": 0, "erros": 0}
    mensagens: list[str] = []
    for tribunal in tribunais_validos:
        try:
            itens = scrape_todos(
                tribunais=[tribunal],
                data=data,
                termos=termos_clientes,
                days_back=days_back,
            )
            itens = _filtrar_itens_monitorados(itens, db, incluir_clientes=True, incluir_advogados=False)
            ins, dup, err = _inserir_publicacoes(itens, db)
            totais["inseridas"] += ins
            totais["duplicatas"] += dup
            totais["erros"] += err
        except DiarioScrapingError as exc:
            totais["erros"] += 1
            mensagens.append(_mensagem_erro_scraping(exc))
        except Exception:
            totais["erros"] += 1
        time.sleep(1)
    mensagem = mensagens[0] if mensagens else None
    return SyncResult(
        inseridas=totais["inseridas"],
        duplicatas=totais["duplicatas"],
        erros=totais["erros"],
        fonte="scraping_clientes",
        mensagem=mensagem,
    )


@router.get("/monitoramento", response_model=DiarioMonitoringConfig)
def obter_monitoramento():
    from app.services.diario_monitoring import load_monitoring_config

    return DiarioMonitoringConfig(**load_monitoring_config())


@router.put("/monitoramento", response_model=DiarioMonitoringConfig)
def salvar_monitoramento(body: DiarioMonitoringConfig):
    from app.services.diario_monitoring import save_monitoring_config

    saved = save_monitoring_config(body.model_dump())
    return DiarioMonitoringConfig(**saved)


@router.post("/reclassificar", response_model=SyncResult)
def reclassificar_publicacoes(db: Session = Depends(get_db)):
    publicacoes = db.query(Publicacao).all()
    alteradas = 0
    for pub in publicacoes:
        if _reclassificar_publicacao(pub, db):
            alteradas += 1
    if alteradas:
        db.commit()
    return SyncResult(inseridas=0, duplicatas=alteradas, erros=0, fonte="reclassificacao")


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
    publicacoes = q.order_by(Publicacao.data_publicacao.desc(), Publicacao.created_at.desc()).all()
    alterou = False
    for pub in publicacoes:
        for attr in ("texto_resumo", "texto_completo"):
            texto_atual = getattr(pub, attr) or ""
            texto_limpo = _limpar_html_publicacao(texto_atual)
            if texto_limpo and texto_limpo != texto_atual:
                setattr(pub, attr, texto_limpo)
                alterou = True
        if not pub.match_tipo:
            alterou = _reclassificar_publicacao(pub, db) or alterou
    if alterou:
        db.commit()
    return publicacoes


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
