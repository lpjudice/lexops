"""Despacho — fila de publicações do Diário que precisam de confirmação de
vínculo (processo/cliente) e, depois de confirmadas, de uma sugestão de ação
do gestor jurídico. Só lê/aciona módulos existentes (Diário, Processos,
Prazos, Tarefas) — não altera a lógica deles.

Quando o vínculo é de altíssima confiança (CNJ exato batendo com um processo
já cadastrado), o pipeline inteiro roda sozinho: confirma, pede sugestão à
IA, cria prazo/tarefas e avisa por Telegram — sem esperar clique. Confiança
média/baixa continua exigindo confirmação humana antes de qualquer ação.
"""
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.cliente import Cliente
from app.models.prazo import Prazo
from app.models.processo import Processo
from app.models.publicacao import Publicacao
from app.models.tarefa import Tarefa
from app.models.usuario import Usuario

router = APIRouter(prefix="/despacho", tags=["despacho"],
                   dependencies=[Depends(get_current_user)])

logger = logging.getLogger(__name__)

TEXTO_SEM_PUBLICACAO = "Sem publicações nesta edição."


def _confianca(pub: Publicacao) -> str:
    if pub.processo_id and pub.numero_cnj:
        return "alta"
    if pub.match_oab:
        return "media"
    if pub.processo_id or pub.cliente_nome_pub:
        return "baixa"
    return "sem_vinculo"


def _usuario_sistema(db: Session) -> Usuario | None:
    """Usuário usado como 'ator' quando o gestor age sozinho (sem humano na tela)."""
    return db.query(Usuario).filter(Usuario.role == "super_admin").first()


def _notificar_telegram(texto: str) -> None:
    try:
        from app.config import settings
        from app.services.telegram_api import send_message

        chat_id_raw = (settings.andamentos_push_chat_id or "").strip()
        if not chat_id_raw:
            return
        send_message(int(chat_id_raw), texto)
    except Exception:
        logger.warning("Falha ao notificar Telegram sobre ação automática", exc_info=True)


class TarefaSugerida(BaseModel):
    titulo: str
    responsavel: str | None = None


def _criar_prazo_e_tarefas(
    db: Session,
    pub: Publicacao,
    processo: Processo,
    *,
    peca_necessaria: str | None,
    dias_prazo: int | None,
    tipo_contagem: str,
    tarefas: list[TarefaSugerida],
    criar_prazo: bool,
    automatico: bool,
) -> dict:
    """Cria Prazo (uma opção escolhida) + N Tarefas e retorna os ids criados.
    Compartilhado entre /aprovar e o pipeline automático."""
    resultado: dict = {"tarefa_ids": []}

    if criar_prazo and peca_necessaria and dias_prazo:
        from app.services.google_calendar import criar_evento
        from app.services.prazo_calc import calcular_prazo

        data_com, data_sem = calcular_prazo(
            db=db,
            data_publicacao=pub.data_publicacao,
            dias=dias_prazo,
            estado=processo.estado,
            tipo_contagem=tipo_contagem,
        )
        responsavel_prazo = tarefas[0].responsavel if tarefas else None
        prazo = Prazo(
            processo_id=processo.id,
            tipo=peca_necessaria,
            descricao=pub.texto_resumo,
            data_publicacao=pub.data_publicacao,
            dias_prazo=dias_prazo,
            tipo_contagem=tipo_contagem,
            data_limite=data_com,
            data_limite_sem_feriado=data_sem,
            responsavel=responsavel_prazo,
            criado_automaticamente=automatico,
        )
        db.add(prazo)
        db.commit()
        db.refresh(prazo)

        if prazo.data_limite:
            titulo_evento = f"[PRAZO] {prazo.tipo.upper()} — {processo.numero_cnj}"
            event_id = criar_evento(titulo_evento, prazo.data_limite, prazo.descricao or "")
            if event_id:
                prazo.google_event_id = event_id
                db.commit()

        pub.prazo_id = prazo.id
        pub.gera_prazo = True
        resultado["prazo_id"] = str(prazo.id)
        resultado["prazo_data_limite"] = prazo.data_limite.isoformat() if prazo.data_limite else None

    for t in tarefas:
        if not t.titulo:
            continue
        tarefa = Tarefa(
            cliente_id=processo.cliente_id,
            processo_id=processo.id,
            titulo=t.titulo,
            responsavel=t.responsavel,
            status="pendente",
            criado_automaticamente=automatico,
        )
        db.add(tarefa)
        db.commit()
        db.refresh(tarefa)
        resultado["tarefa_ids"].append(str(tarefa.id))

    return resultado


def _processar_automaticos(db: Session) -> int:
    """Roda o pipeline inteiro (confirmar → sugerir → criar) para publicações
    de confiança alta (CNJ exato) que ainda não foram tratadas. Usa a
    primeira opção de prazo sugerida e todas as tarefas sugeridas — não há
    humano pra escolher entre caminhos alternativos aqui. Retorna quantas
    foram processadas."""
    candidatas = (
        db.query(Publicacao)
        .filter(
            Publicacao.lida.is_(False),
            Publicacao.rejeitada.is_(False),
            Publicacao.vinculo_confirmado.is_(False),
            Publicacao.processo_id.isnot(None),
            Publicacao.numero_cnj.isnot(None),
        )
        .all()
    )
    if not candidatas:
        return 0

    from app.services.contexto_service import montar_contexto_processo
    from app.services.ia_despacho import sugerir_acao as gerar_sugestao

    usuario = _usuario_sistema(db)
    processadas = 0

    for pub in candidatas:
        processo = db.query(Processo).filter(Processo.id == pub.processo_id).first()
        if not processo or not usuario:
            continue

        pub.vinculo_confirmado = True
        db.commit()

        contexto = montar_contexto_processo(db, processo, usuario)
        texto_publicacao = pub.texto_completo or pub.texto_resumo or ""
        sugestao = gerar_sugestao(contexto, texto_publicacao)
        if sugestao.get("erro"):
            logger.warning("Sugestão automática falhou pra publicação %s: %s", pub.id, sugestao["erro"])
            continue

        pub.sugestao_acao = json.dumps(sugestao, ensure_ascii=False)
        db.commit()

        opcoes = sugestao.get("opcoes_prazo") or []
        opcao = opcoes[0] if opcoes else {}
        tarefas = [TarefaSugerida(**t) for t in (sugestao.get("tarefas_sugeridas") or [])]

        criado = _criar_prazo_e_tarefas(
            db, pub, processo,
            peca_necessaria=opcao.get("peca_necessaria"),
            dias_prazo=opcao.get("dias_prazo"),
            tipo_contagem=opcao.get("tipo_contagem") or "uteis",
            tarefas=tarefas,
            criar_prazo=bool(sugestao.get("requer_prazo")) and bool(opcoes),
            automatico=True,
        )

        pub.lida = True
        db.commit()
        processadas += 1

        if criado.get("prazo_id") or criado.get("tarefa_ids"):
            partes = [f"🤖 *Ação automática* — processo `{processo.numero_cnj}`"]
            if criado.get("prazo_id"):
                partes.append(f"📅 Prazo criado: {opcao.get('label') or opcao.get('peca_necessaria')} — vence {criado.get('prazo_data_limite')}")
            if criado.get("tarefa_ids"):
                partes.append(f"✅ {len(criado['tarefa_ids'])} tarefa(s) criada(s)")
            partes.append(f"_{sugestao.get('resumo_raciocinio', '')}_")
            _notificar_telegram("\n".join(partes))

    return processadas


@router.post("/processar-automaticos")
def processar_automaticos(db: Session = Depends(get_db)):
    """Aciona manualmente o pipeline automático (útil pra ligar em um cron)."""
    total = _processar_automaticos(db)
    return {"processadas": total}


def _pub_para_dict(db: Session, p: Publicacao) -> dict:
    processo = db.query(Processo).filter(Processo.id == p.processo_id).first() if p.processo_id else None
    cliente = db.query(Cliente).filter(Cliente.id == processo.cliente_id).first() if processo else None
    return {
        "id": str(p.id),
        "data_publicacao": p.data_publicacao.isoformat() if p.data_publicacao else None,
        "tribunal": p.tribunal,
        "tipo_ato": p.tipo_ato,
        "texto_resumo": p.texto_resumo,
        "numero_cnj": p.numero_cnj,
        "cliente_nome_pub": p.cliente_nome_pub,
        "match_oab": p.match_oab,
        "confianca": _confianca(p),
        "processo_id": str(processo.id) if processo else None,
        "processo_numero_cnj": processo.numero_cnj if processo else None,
        "cliente_id": str(cliente.id) if cliente else None,
        "cliente_nome": cliente.nome if cliente else None,
        "vinculo_confirmado": p.vinculo_confirmado,
        "sugestao_acao": json.loads(p.sugestao_acao) if p.sugestao_acao else None,
        "peca_gerada": json.loads(p.peca_gerada) if p.peca_gerada else None,
        "peca_doc_url": p.peca_doc_url,
        "rejeitada": p.rejeitada,
        "prazo_id": str(p.prazo_id) if p.prazo_id else None,
    }


@router.get("/pendentes")
def listar_pendentes(db: Session = Depends(get_db)):
    _processar_automaticos(db)

    pubs = (
        db.query(Publicacao)
        .filter(
            Publicacao.lida.is_(False),
            Publicacao.rejeitada.is_(False),
            Publicacao.texto_resumo != TEXTO_SEM_PUBLICACAO,
        )
        .order_by(Publicacao.data_publicacao.desc())
        .limit(100)
        .all()
    )
    return [_pub_para_dict(db, p) for p in pubs]


@router.get("/tratadas")
def listar_tratadas(db: Session = Depends(get_db)):
    """Histórico do que já foi decidido no Despacho — aprovado ou descartado
    — pra não perder o registro do que aconteceu com cada publicação."""
    pubs = (
        db.query(Publicacao)
        .filter(Publicacao.lida.is_(True))
        .order_by(Publicacao.data_publicacao.desc())
        .limit(200)
        .all()
    )
    return [_pub_para_dict(db, p) for p in pubs]


class ConfirmarRequest(BaseModel):
    processo_id: uuid.UUID | None = None
    confirmado: bool


@router.post("/{publicacao_id}/confirmar")
def confirmar_vinculo(publicacao_id: uuid.UUID, body: ConfirmarRequest, db: Session = Depends(get_db)):
    pub = db.query(Publicacao).filter(Publicacao.id == publicacao_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")

    if not body.confirmado:
        # Marca só pra revisão manual futura — não conta como rejeitada.
        pub.vinculo_confirmado = False
        pub.processo_id = None
        db.commit()
        return {"ok": True, "vinculo_confirmado": False}

    processo_id = body.processo_id or pub.processo_id
    if not processo_id:
        raise HTTPException(status_code=400, detail="Informe o processo_id pra confirmar o vínculo")
    processo = db.query(Processo).filter(Processo.id == processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    pub.processo_id = processo.id
    pub.vinculo_confirmado = True
    db.commit()
    return {"ok": True, "vinculo_confirmado": True, "processo_id": str(processo.id)}


@router.post("/{publicacao_id}/rejeitar")
def rejeitar_publicacao(publicacao_id: uuid.UUID, db: Session = Depends(get_db)):
    pub = db.query(Publicacao).filter(Publicacao.id == publicacao_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    pub.rejeitada = True
    pub.lida = True
    db.commit()
    return {"ok": True}


@router.post("/{publicacao_id}/sugerir")
def sugerir_acao(
    publicacao_id: uuid.UUID,
    db: Session = Depends(get_db),
    current: Usuario = Depends(get_current_user),
):
    pub = db.query(Publicacao).filter(Publicacao.id == publicacao_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    if not pub.vinculo_confirmado or not pub.processo_id:
        raise HTTPException(status_code=400, detail="Confirme o vínculo com o processo antes de pedir sugestão")

    processo = db.query(Processo).filter(Processo.id == pub.processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    from app.services.contexto_service import montar_contexto_processo
    from app.services.ia_despacho import sugerir_acao as gerar_sugestao

    contexto = montar_contexto_processo(db, processo, current)
    texto_publicacao = pub.texto_completo or pub.texto_resumo or ""
    sugestao = gerar_sugestao(contexto, texto_publicacao)

    if sugestao.get("erro"):
        raise HTTPException(status_code=502, detail=sugestao["erro"])

    pub.sugestao_acao = json.dumps(sugestao, ensure_ascii=False)
    db.commit()
    return sugestao


class GerarPecaRequest(BaseModel):
    opcao_prazo: dict
    prompt_extra: str = ""


@router.post("/{publicacao_id}/gerar-peca")
def gerar_peca(
    publicacao_id: uuid.UUID,
    body: GerarPecaRequest,
    db: Session = Depends(get_db),
    current: Usuario = Depends(get_current_user),
):
    """Gera o conteúdo da peça (texto estruturado, sem inventar fatos — usa
    XXX pro que faltar) pra uma das opções de prazo sugeridas."""
    pub = db.query(Publicacao).filter(Publicacao.id == publicacao_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    if not pub.vinculo_confirmado or not pub.processo_id:
        raise HTTPException(status_code=400, detail="Vínculo com processo não confirmado")

    processo = db.query(Processo).filter(Processo.id == pub.processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    from app.services.contexto_service import montar_contexto_processo
    from app.services.ia_despacho import gerar_peca as gerar_peca_ia

    contexto = montar_contexto_processo(db, processo, current)
    texto_publicacao = pub.texto_completo or pub.texto_resumo or ""
    peca = gerar_peca_ia(contexto, texto_publicacao, body.opcao_prazo, body.prompt_extra)

    if peca.get("erro"):
        raise HTTPException(status_code=502, detail=peca["erro"])

    pub.peca_gerada = json.dumps(peca, ensure_ascii=False)
    db.commit()

    from app.services.google_docs import gerar_documento_peca

    nome_doc = f"{peca.get('titulo_peca', 'Peça')} - {processo.numero_cnj}"
    doc = gerar_documento_peca(peca, nome_doc)
    if doc:
        pub.peca_doc_url = doc.get("webViewLink")
        db.commit()

    return {**peca, "doc_url": pub.peca_doc_url}


class AprovarRequest(BaseModel):
    criar_prazo: bool = True
    peca_necessaria: str | None = None
    dias_prazo: int | None = None
    tipo_contagem: str = "uteis"
    tarefas: list[TarefaSugerida] = []


@router.post("/{publicacao_id}/aprovar")
def aprovar_acao(publicacao_id: uuid.UUID, body: AprovarRequest, db: Session = Depends(get_db)):
    pub = db.query(Publicacao).filter(Publicacao.id == publicacao_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publicação não encontrada")
    if not pub.vinculo_confirmado or not pub.processo_id:
        raise HTTPException(status_code=400, detail="Vínculo com processo não confirmado")

    processo = db.query(Processo).filter(Processo.id == pub.processo_id).first()
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    resultado = _criar_prazo_e_tarefas(
        db, pub, processo,
        peca_necessaria=body.peca_necessaria,
        dias_prazo=body.dias_prazo,
        tipo_contagem=body.tipo_contagem,
        tarefas=body.tarefas,
        criar_prazo=body.criar_prazo,
        automatico=False,
    )

    pub.lida = True
    db.commit()
    resultado["ok"] = True
    return resultado
