"""WhatsApp Business Platform (Meta Cloud API):
  - GET  /whatsapp/webhook       — handshake de verificação (Meta exige na hora
                                    de configurar o webhook no app).
  - POST /whatsapp/webhook       — recebe mensagens inbound do cliente.
  - GET  /whatsapp/status        — diagnóstico rápido (configurado ou não).
  - POST /whatsapp/push/executar — dispara manualmente a notificação de
                                    andamentos (útil pra testar com o número
                                    de teste antes de existir cron/aprovação).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response

from app.config import settings
from app.database import SessionLocal
from app.dependencies import get_current_user
from app.services import whatsapp_api, whatsapp_bot, whatsapp_marketing

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.get("/webhook")
def verificar_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    """Handshake exigido pela Meta ao registrar a URL do webhook no app."""
    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_webhook_verify_token and settings.whatsapp_webhook_verify_token:
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(status_code=403)


def _processar_mensagem(telefone: str, texto: str, message_id: str | None) -> None:
    if message_id:
        whatsapp_api.mark_as_read(message_id)
    db = SessionLocal()
    try:
        # Pedido de sair da lista de marketing vale pra qualquer remetente.
        if whatsapp_marketing.eh_pedido_de_parar(texto):
            whatsapp_marketing.registrar_optout(db, telefone, origem="texto")
            whatsapp_api.send_text_message(telefone, "Combinado, você não receberá mais mensagens de divulgação por WhatsApp. Obrigado!")
            return
        # Convidado de evento que responde por texto não é cliente: o bot de
        # processos não tem o que dizer a ele. Fica no log até existir caixa de entrada.
        if whatsapp_marketing.eh_contato_do_conselho_sem_ser_cliente(db, telefone):
            logger.info("whatsapp webhook: texto de contato do Conselho (%s) sem resposta automática", telefone)
            return
    finally:
        db.close()
    resposta = whatsapp_bot.responder_mensagem(telefone, texto)
    whatsapp_api.send_text_message(telefone, resposta)


def _processar_botao(telefone: str, payload: str, message_id: str | None) -> None:
    """Clique em botão de resposta rápida de um template (ex.: convite de evento)."""
    db = SessionLocal()
    try:
        resposta = whatsapp_marketing.tratar_resposta_botao(db, telefone, payload)
    except Exception:
        db.rollback()
        logger.exception("whatsapp webhook: erro tratando botão %r de %s", payload, telefone)
        resposta = None
    finally:
        db.close()
    if resposta:
        whatsapp_api.send_text_message(telefone, resposta)
    else:
        logger.info("whatsapp webhook: botão %r de %s sem tratamento", payload, telefone)


@router.post("/webhook")
async def receber_webhook(request: Request, background_tasks: BackgroundTasks):
    raw = await request.body()
    assinatura = request.headers.get("X-Hub-Signature-256")
    if not whatsapp_api.verify_signature(raw, assinatura):
        logger.warning("whatsapp webhook: assinatura inválida")
        return Response(status_code=403)

    payload = await request.json()
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                valor = change.get("value", {})
                for msg in valor.get("messages", []):
                    telefone = msg.get("from")
                    message_id = msg.get("id")
                    if msg.get("type") == "button":
                        payload_botao = (msg.get("button") or {}).get("payload") or ""
                        if telefone and payload_botao:
                            background_tasks.add_task(_processar_botao, telefone, payload_botao, message_id)
                        continue
                    if msg.get("type") == "text":
                        texto = msg.get("text", {}).get("body", "")
                    else:
                        texto = ""  # áudio/imagem/documento: sem transcrição por ora
                    if telefone and texto:
                        background_tasks.add_task(_processar_mensagem, telefone, texto, message_id)
                    elif telefone:
                        logger.info("whatsapp webhook: mensagem tipo=%s de %s sem tratamento ainda", msg.get("type"), telefone)
                # Atualizações de status de entrega (sent/delivered/read/failed) das
                # mensagens QUE NÓS enviamos — sem isso não dá pra saber se um envio
                # (template ou push de andamento) realmente chegou ou falhou.
                for st in valor.get("statuses", []):
                    status_tipo = st.get("status")
                    destinatario = st.get("recipient_id")
                    erro = st.get("errors")
                    if status_tipo == "failed" or erro:
                        logger.warning(
                            "whatsapp status: FALHA msg=%s destinatario=%s erro=%s",
                            st.get("id"), destinatario, erro,
                        )
                    else:
                        logger.info(
                            "whatsapp status: msg=%s destinatario=%s status=%s",
                            st.get("id"), destinatario, status_tipo,
                        )
                    # Casa o status com o convite de evento (se for um).
                    db = SessionLocal()
                    try:
                        titulo_erro = ((erro or [{}])[0] or {}).get("title") if erro else None
                        whatsapp_marketing.atualizar_status_entrega(db, st.get("id") or "", status_tipo or "", titulo_erro)
                    except Exception:
                        db.rollback()
                        logger.exception("whatsapp status: erro atualizando convite")
                    finally:
                        db.close()
    except Exception:
        logger.exception("whatsapp webhook: erro processando payload")

    # Meta exige 200 rápido, senão reentrega e pode desativar o webhook.
    return Response(status_code=200)


@router.get("/status")
def status():
    return {
        "configurado": bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id),
        "webhook_verify_token_definido": bool(settings.whatsapp_webhook_verify_token),
        "app_secret_definido": bool(settings.whatsapp_app_secret),
        "phone_number_id": settings.whatsapp_phone_number_id or None,
    }


@router.post("/push/executar", dependencies=[Depends(get_current_user)])
def executar_push_manual():
    """Dispara agora a notificação de andamentos por WhatsApp — sem esperar o
    cron. Útil pra validar o template com o número de teste."""
    from app.services.andamentos_whatsapp_push import push_andamentos_whatsapp

    return push_andamentos_whatsapp()
