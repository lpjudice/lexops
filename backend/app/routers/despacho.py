"""Despacho — fila de publicações do Diário que precisam de confirmação de
vínculo (processo/cliente) e, depois de confirmadas, de uma sugestão de ação
do gestor jurídico. Só lê/aciona módulos existentes (Diário, Processos,
Prazos, Tarefas) — não altera a lógica deles.
"""
import json
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


def _confianca(pub: Publicacao) -> str:
    if pub.processo_id and pub.numero_cnj:
        return "alta"
    if pub.match_oab:
        return "media"
    if pub.processo_id or pub.cliente_nome_pub:
        return "baixa"
    return "sem_vinculo"


@router.get("/pendentes")
def listar_pendentes(db: Session = Depends(get_db)):
    pubs = (
        db.query(Publicacao)
        .filter(Publicacao.lida.is_(False), Publicacao.rejeitada.is_(False))
        .order_by(Publicacao.data_publicacao.desc())
        .limit(100)
        .all()
    )
    resultado = []
    for p in pubs:
        processo = db.query(Processo).filter(Processo.id == p.processo_id).first() if p.processo_id else None
        cliente = db.query(Cliente).filter(Cliente.id == processo.cliente_id).first() if processo else None
        resultado.append({
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
        })
    return resultado


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


class AprovarRequest(BaseModel):
    criar_prazo: bool = True
    criar_tarefa: bool = True
    # Permite o usuário editar a sugestão antes de aprovar
    peca_necessaria: str | None = None
    dias_prazo: int | None = None
    tipo_contagem: str = "uteis"
    tarefa_titulo: str | None = None
    tarefa_responsavel: str | None = None


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

    resultado: dict = {}

    if body.criar_prazo and body.peca_necessaria and body.dias_prazo:
        from app.services.google_calendar import criar_evento
        from app.services.prazo_calc import calcular_prazo

        data_com, data_sem = calcular_prazo(
            db=db,
            data_publicacao=pub.data_publicacao,
            dias=body.dias_prazo,
            estado=processo.estado,
            tipo_contagem=body.tipo_contagem,
        )
        prazo = Prazo(
            processo_id=processo.id,
            tipo=body.peca_necessaria,
            descricao=pub.texto_resumo,
            data_publicacao=pub.data_publicacao,
            dias_prazo=body.dias_prazo,
            tipo_contagem=body.tipo_contagem,
            data_limite=data_com,
            data_limite_sem_feriado=data_sem,
            responsavel=body.tarefa_responsavel,
        )
        db.add(prazo)
        db.commit()
        db.refresh(prazo)

        if prazo.data_limite:
            titulo = f"[PRAZO] {prazo.tipo.upper()} — {processo.numero_cnj}"
            event_id = criar_evento(titulo, prazo.data_limite, prazo.descricao or "")
            if event_id:
                prazo.google_event_id = event_id
                db.commit()

        pub.prazo_id = prazo.id
        pub.gera_prazo = True
        resultado["prazo_id"] = str(prazo.id)

    if body.criar_tarefa and body.tarefa_titulo:
        tarefa = Tarefa(
            cliente_id=processo.cliente_id,
            processo_id=processo.id,
            titulo=body.tarefa_titulo,
            responsavel=body.tarefa_responsavel,
            status="pendente",
        )
        db.add(tarefa)
        db.commit()
        db.refresh(tarefa)
        resultado["tarefa_id"] = str(tarefa.id)

    pub.lida = True
    db.commit()
    resultado["ok"] = True
    return resultado
