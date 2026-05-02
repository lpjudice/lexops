import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.anotacao import Anotacao
from app.models.cliente import Cliente
from app.models.contrato import Contrato
from app.models.processo import Processo
from app.models.reuniao import Reuniao
from app.models.tarefa import Tarefa
from app.schemas.reuniao import ConfirmarAcoesRequest, ReuniaoCreate, ReuniaoOut, ReuniaoUpdate

router = APIRouter(prefix="/reunioes", tags=["reunioes"])


def _enrich(r: Reuniao, db: Session) -> ReuniaoOut:
    out = ReuniaoOut.model_validate(r)
    if r.cliente_id:
        c = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
        if c:
            out.cliente_nome = c.nome
    if r.processo_id:
        p = db.query(Processo).filter(Processo.id == r.processo_id).first()
        if p:
            out.processo_numero = p.numero_cnj
    return out


@router.get("/", response_model=list[ReuniaoOut])
def listar_reunioes(
    cliente_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Reuniao)
    if cliente_id:
        q = q.filter(Reuniao.cliente_id == cliente_id)
    if status:
        q = q.filter(Reuniao.status == status)
    reunioes = q.order_by(Reuniao.data_reuniao.desc().nullslast(), Reuniao.created_at.desc()).all()
    return [_enrich(r, db) for r in reunioes]


@router.post("/", response_model=ReuniaoOut, status_code=status.HTTP_201_CREATED)
def criar_reuniao(data: ReuniaoCreate, db: Session = Depends(get_db)):
    reuniao = Reuniao(**data.model_dump())
    db.add(reuniao)
    db.commit()
    db.refresh(reuniao)
    return _enrich(reuniao, db)


@router.post("/sync-drive", response_model=list[ReuniaoOut])
def sync_drive(db: Session = Depends(get_db)):
    """Varre a pasta Meet Recordings no Drive e importa novas transcrições."""
    from app.services.ia_reuniao import match_cliente
    from app.services.meet_sync import (
        baixar_conteudo_arquivo,
        extrair_titulo,
        listar_novas_transcricoes,
        _parse_data_reuniao,
    )

    # Busca data do último sync para evitar duplicatas
    ultima = db.query(Reuniao).filter(Reuniao.fonte == "drive_auto").order_by(Reuniao.created_at.desc()).first()
    ultimo_sync = ultima.created_at.isoformat() if ultima else None

    arquivos = listar_novas_transcricoes(ultimo_sync=ultimo_sync)
    if not arquivos:
        return []

    # Carrega clientes para matching
    clientes = db.query(Cliente).filter(Cliente.incompleto.is_(False)).all()
    clientes_data = [{"id": str(c.id), "nome": c.nome} for c in clientes]

    criadas = []
    for arq in arquivos:
        # Verifica se já foi importado (pelo file_id)
        existente = db.query(Reuniao).filter(Reuniao.drive_transcricao_file_id == arq["file_id"]).first()
        if existente:
            continue

        titulo = extrair_titulo(arq["nome"])
        data_reuniao = _parse_data_reuniao(arq["nome"], arq.get("criado_em"))
        conteudo = baixar_conteudo_arquivo(arq["file_id"], arq["mime_type"])

        # Auto-match de cliente
        match = match_cliente(titulo, clientes_data)
        cliente_id = None
        if match.get("confianca", 0) >= 0.8 and match.get("cliente_id"):
            try:
                cliente_id = uuid.UUID(match["cliente_id"])
            except (ValueError, TypeError):
                pass

        reuniao = Reuniao(
            titulo=titulo,
            data_reuniao=data_reuniao,
            transcricao_texto=conteudo,
            drive_transcricao_file_id=arq["file_id"],
            cliente_id=cliente_id,
            fonte="drive_auto",
            status="pendente",
        )
        db.add(reuniao)
        db.flush()
        criadas.append(reuniao)

    db.commit()
    for r in criadas:
        db.refresh(r)

    return [_enrich(r, db) for r in criadas]


@router.get("/{reuniao_id}", response_model=ReuniaoOut)
def obter_reuniao(reuniao_id: uuid.UUID, db: Session = Depends(get_db)):
    r = db.query(Reuniao).filter(Reuniao.id == reuniao_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    return _enrich(r, db)


@router.patch("/{reuniao_id}", response_model=ReuniaoOut)
def atualizar_reuniao(reuniao_id: uuid.UUID, data: ReuniaoUpdate, db: Session = Depends(get_db)):
    r = db.query(Reuniao).filter(Reuniao.id == reuniao_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(r, field, value)
    db.commit()
    db.refresh(r)
    return _enrich(r, db)


@router.post("/{reuniao_id}/processar", response_model=ReuniaoOut)
def processar_reuniao(reuniao_id: uuid.UUID, db: Session = Depends(get_db)):
    """Processa a transcrição com IA: gera TLDR e lista de ações sugeridas."""
    from app.services.ia_reuniao import processar_transcricao

    r = db.query(Reuniao).filter(Reuniao.id == reuniao_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if not r.transcricao_texto:
        raise HTTPException(status_code=400, detail="Reunião sem texto de transcrição")

    data_ref = r.data_reuniao.date() if r.data_reuniao else None
    resultado = processar_transcricao(r.transcricao_texto, data_ref)

    if "erro" in resultado:
        raise HTTPException(status_code=502, detail=f"Erro ao processar IA: {resultado['erro']}")

    acoes: list[dict] = []

    for tarefa in resultado.get("tarefas", []):
        acoes.append({
            "tipo": "tarefa",
            "aprovada": None,
            "titulo": tarefa.get("titulo", ""),
            "descricao": tarefa.get("descricao", ""),
            "data_limite": tarefa.get("data_sugerida"),
            "responsavel": None,
        })

    for contrato in resultado.get("contratos", []):
        acoes.append({
            "tipo": "contrato",
            "aprovada": None,
            "titulo": contrato.get("titulo", ""),
            "descricao": contrato.get("descricao", ""),
            "valor_mencionado": contrato.get("valor_mencionado"),
        })

    if resultado.get("anotacao"):
        acoes.append({
            "tipo": "anotacao",
            "aprovada": None,
            "titulo": f"Reunião: {r.titulo}",
            "conteudo": resultado["anotacao"],
        })

    r.resumo_ia = resultado.get("resumo", "")
    r.acoes_sugeridas = acoes
    r.status = "em_revisao"
    db.commit()
    db.refresh(r)
    return _enrich(r, db)


@router.post("/{reuniao_id}/confirmar-acoes", response_model=ReuniaoOut)
def confirmar_acoes(reuniao_id: uuid.UUID, data: ConfirmarAcoesRequest, db: Session = Depends(get_db)):
    """Cria no sistema as ações marcadas como aprovada=True."""
    r = db.query(Reuniao).filter(Reuniao.id == reuniao_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if not r.cliente_id:
        raise HTTPException(status_code=400, detail="Vincule a reunião a um cliente antes de confirmar ações")

    data_base = (r.data_reuniao.date() if r.data_reuniao else date.today())

    for acao in data.acoes_sugeridas:
        if not acao.get("aprovada"):
            continue

        tipo = acao.get("tipo")

        if tipo == "tarefa":
            data_limite = None
            if acao.get("data_limite"):
                try:
                    data_limite = date.fromisoformat(acao["data_limite"])
                except (ValueError, TypeError):
                    pass
            tarefa = Tarefa(
                cliente_id=r.cliente_id,
                processo_id=r.processo_id,
                titulo=acao.get("titulo", "Tarefa da reunião"),
                descricao=acao.get("descricao"),
                responsavel=acao.get("responsavel"),
                data_limite=data_limite,
                status="pendente",
                resumo_ia=f"Gerado automaticamente da reunião: {r.titulo}",
            )
            db.add(tarefa)

        elif tipo == "contrato":
            contrato = Contrato(
                cliente_id=r.cliente_id,
                processo_id=r.processo_id,
                titulo=acao.get("titulo", "Contrato"),
                descricao=acao.get("descricao"),
                status="rascunho",
                arquivos=[],
            )
            db.add(contrato)

        elif tipo == "anotacao":
            anotacao = Anotacao(
                cliente_id=r.cliente_id,
                processo_id=r.processo_id,
                tipo="reuniao",
                data_evento=data_base,
                titulo=acao.get("titulo"),
                texto=acao.get("conteudo", ""),
            )
            db.add(anotacao)

    # Salva TLDR no Drive do cliente se houver resumo
    if r.resumo_ia and r.cliente_id:
        cliente = db.query(Cliente).filter(Cliente.id == r.cliente_id).first()
        if cliente:
            try:
                from app.services.meet_sync import salvar_tldr_drive

                data_str = data_base.isoformat()
                nome_arquivo = f"{data_str} - {r.titulo[:80]}.txt"
                conteudo_tldr = f"# {r.titulo}\nData: {data_str}\n\n## Resumo\n{r.resumo_ia}"
                drive_link = salvar_tldr_drive(conteudo_tldr, nome_arquivo, cliente.nome)
                if drive_link:
                    # Guarda o link como file_id (simplificado — sem extrair ID real)
                    r.drive_tldr_file_id = drive_link
            except Exception:
                pass  # Falha no Drive não bloqueia criação das ações

    # Atualiza acoes_sugeridas com o estado final e marca como processada
    r.acoes_sugeridas = data.acoes_sugeridas
    r.status = "processada"
    db.commit()
    db.refresh(r)
    return _enrich(r, db)


@router.delete("/{reuniao_id}", status_code=status.HTTP_204_NO_CONTENT)
def deletar_reuniao(reuniao_id: uuid.UUID, db: Session = Depends(get_db)):
    r = db.query(Reuniao).filter(Reuniao.id == reuniao_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    db.delete(r)
    db.commit()
