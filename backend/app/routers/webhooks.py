"""
Webhook para Google Drive Push Notifications.

O Drive chama POST /webhooks/drive quando algo muda na pasta monitorada.
O app então roda a importação de novas transcrições em background.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, Request, Response
from sqlalchemy.orm import Session

from app.database import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _importar_novas(ultimo_sync: str | None) -> None:
    """Roda em background: busca novas transcrições e cria Reuniao records."""
    from app.models.cliente import Cliente
    from app.models.reuniao import Reuniao
    from app.services.ia_reuniao import match_cliente
    from app.services.meet_sync import (
        _parse_data_reuniao,
        baixar_conteudo_arquivo,
        extrair_titulo,
        listar_novas_transcricoes,
    )
    import uuid

    db: Session = SessionLocal()
    try:
        arquivos = listar_novas_transcricoes(ultimo_sync=ultimo_sync)
        if not arquivos:
            return

        clientes = db.query(Cliente).filter(Cliente.incompleto.is_(False)).all()
        clientes_data = [{"id": str(c.id), "nome": c.nome} for c in clientes]

        for arq in arquivos:
            existente = db.query(Reuniao).filter(Reuniao.drive_transcricao_file_id == arq["file_id"]).first()
            if existente:
                continue

            titulo = extrair_titulo(arq["nome"])
            data_reuniao = _parse_data_reuniao(arq["nome"], arq.get("criado_em"))
            conteudo = baixar_conteudo_arquivo(arq["file_id"], arq["mime_type"])

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
            logger.info("Nova reunião importada do Drive: %s", titulo)

        db.commit()
    except Exception as exc:
        logger.warning("Erro ao importar transcrições após webhook: %s", exc)
        db.rollback()
    finally:
        db.close()


@router.post("/drive")
async def receber_notificacao_drive(
    request: Request,
    background_tasks: BackgroundTasks,
    x_goog_channel_id: Annotated[str | None, Header()] = None,
    x_goog_resource_state: Annotated[str | None, Header()] = None,
    x_goog_resource_id: Annotated[str | None, Header()] = None,
):
    """
    Recebe notificações do Google Drive Push.
    Estados possíveis: sync (inicial), add, update, remove, trash.
    """
    state = x_goog_resource_state or ""
    logger.info("Drive webhook: state=%s channel=%s", state, x_goog_channel_id)

    # "sync" é enviado ao registrar o channel — sem ação necessária
    if state == "sync":
        return Response(status_code=200)

    # Qualquer mudança na pasta dispara a importação
    if state in ("add", "update", "change"):
        from app.models.reuniao import Reuniao
        db: Session = SessionLocal()
        try:
            ultima = db.query(Reuniao).filter(Reuniao.fonte == "drive_auto").order_by(Reuniao.created_at.desc()).first()
            ultimo_sync = ultima.created_at.isoformat() if ultima else None
        finally:
            db.close()

        background_tasks.add_task(_importar_novas, ultimo_sync)

    return Response(status_code=200)


@router.post("/drive/registrar")
def registrar_watch(base_url: str | None = None):
    """
    Registra (ou renova) o watch channel no Google Drive.
    Chame uma vez após o deploy. base_url é a URL pública do app (ex: https://lexops.fly.dev).
    """
    from app.services.drive_watch import registrar_watch as _registrar

    resultado = _registrar(base_url)
    if "erro" in resultado:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=resultado["erro"])
    return resultado


@router.get("/drive/status")
def status_watch():
    """Retorna informações do watch channel ativo."""
    from app.services.drive_watch import channel_ativo
    ch = channel_ativo()
    if not ch:
        return {"ativo": False}
    import time
    exp_ms = ch.get("expiration_ms")
    restante_h = round((int(exp_ms) - int(time.time() * 1000)) / 3_600_000, 1) if exp_ms else None
    return {"ativo": True, "channel_id": ch.get("channel_id"), "expira_em_horas": restante_h}


@router.delete("/drive/parar")
def parar_watch():
    """Para o watch channel ativo."""
    from app.services.drive_watch import parar_watch as _parar
    ok = _parar()
    return {"parado": ok}
