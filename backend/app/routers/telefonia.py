"""Chamadas de voz via Bland.ai:
  - GET  /telefonia/status        — diagnóstico rápido (configurado ou não).
  - POST /telefonia/me-ligar      — dispara uma chamada para o número do
                                     Lucas (settings.telefonia_numero_lucas)
                                     com uma tarefa/aviso em linguagem natural.
  - POST /telefonia/ligar         — dispara uma chamada para um número
                                     informado (ex.: cliente/parte), em nome
                                     do escritório.
  - GET  /telefonia/chamadas/{id} — status de uma chamada disparada.
  - POST /telefonia/webhook-bland — webhook chamado pela Bland.ai ao fim de
                                     uma chamada disparada pelo bot de Pedidos
                                     (telegram_pedidos.py); manda a transcrição
                                     pro Telegram com botões Aprovar/Rejeitar.

Os endpoints de uso manual (me-ligar, ligar, chamadas) exigem usuário
autenticado. O webhook-bland é público (validado por secret na query string,
igual ao webhook do Telegram), pois é chamado pela Bland.ai, não pelo painel.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config import settings
from app.database import SessionLocal
from app.dependencies import get_current_user
from app.models.pedido_voz import PedidoVoz
from app.models.usuario import Usuario
from app.schemas.telefonia import LigarRequest, MeLigarRequest
from app.services import bland_api, pedidos_bot_api

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telefonia", tags=["telefonia"])


@router.get("/status")
def status(usuario: Usuario = Depends(get_current_user)):
    return {
        "configurado": bool(settings.bland_api_key),
        "numero_lucas_configurado": bool(settings.telefonia_numero_lucas),
    }


@router.post("/me-ligar")
def me_ligar(payload: MeLigarRequest, usuario: Usuario = Depends(get_current_user)):
    if not settings.telefonia_numero_lucas:
        raise HTTPException(400, "Número do Lucas não configurado (telefonia_numero_lucas).")
    resultado = bland_api.disparar_chamada(
        telefone=settings.telefonia_numero_lucas,
        tarefa=payload.tarefa,
        voice=payload.voice,
    )
    if resultado is None:
        raise HTTPException(502, "Bland.ai não configurado ou chamada falhou.")
    if "erro" in resultado:
        raise HTTPException(502, f"Erro da Bland.ai: {resultado['erro']}")
    return resultado


@router.post("/ligar")
def ligar(payload: LigarRequest, usuario: Usuario = Depends(get_current_user)):
    resultado = bland_api.disparar_chamada(
        telefone=payload.telefone,
        tarefa=payload.tarefa,
        voice=payload.voice,
    )
    if resultado is None:
        raise HTTPException(502, "Bland.ai não configurado, número inválido ou chamada falhou.")
    if "erro" in resultado:
        raise HTTPException(502, f"Erro da Bland.ai: {resultado['erro']}")
    return resultado


@router.get("/chamadas/{call_id}")
def consultar_chamada(call_id: str, usuario: Usuario = Depends(get_current_user)):
    resultado = bland_api.consultar_chamada(call_id)
    if resultado is None:
        raise HTTPException(502, "Bland.ai não configurado ou consulta falhou.")
    return resultado


def _extrair_transcricao(payload: dict) -> str:
    texto = payload.get("concatenated_transcript") or payload.get("summary")
    if texto:
        return str(texto)
    transcripts = payload.get("transcripts") or []
    linhas = [f"{t.get('user', '?')}: {t.get('text', '')}" for t in transcripts if isinstance(t, dict)]
    return "\n".join(linhas) if linhas else "(sem transcrição disponível)"


@router.post("/webhook-bland")
async def webhook_bland(request: Request, secret: str | None = None):
    esperado = settings.bland_webhook_secret.strip()
    if esperado and secret != esperado:
        raise HTTPException(403, "Secret inválido")

    payload = await request.json()
    call_id = payload.get("call_id") or payload.get("id")
    pedido_id = (payload.get("metadata") or {}).get("pedido_id")

    db = SessionLocal()
    try:
        pedido: PedidoVoz | None = None
        if pedido_id:
            try:
                pedido = db.query(PedidoVoz).filter(PedidoVoz.id == uuid.UUID(hex=pedido_id)).first()
            except ValueError:
                pedido = None
        if not pedido and call_id:
            pedido = db.query(PedidoVoz).filter(PedidoVoz.call_id == call_id).first()

        if not pedido:
            logger.warning("webhook-bland: pedido não encontrado (call_id=%s, pedido_id=%s)", call_id, pedido_id)
            return {"ok": True}

        transcricao = _extrair_transcricao(payload)
        pedido.transcricao = transcricao
        pedido.resumo_pedido = str(payload.get("summary") or "")[:2000] or transcricao[:2000]
        pedido.status = "aguardando_aprovacao"
        db.commit()

        texto = (
            f"📞 *Pedido capturado na ligação:*\n\n{pedido.resumo_pedido}\n\n"
            "Aprovar para implementar?"
        )
        botoes = [[
            ("✅ Aprovar", f"pedido:aprovar:{pedido.id.hex}"),
            ("❌ Rejeitar", f"pedido:rejeitar:{pedido.id.hex}"),
        ]]
        resp = pedidos_bot_api.send_message(pedido.chat_id, texto, botoes)
        if resp and resp.get("message_id"):
            pedido.telegram_message_id = str(resp["message_id"])
            db.commit()
        return {"ok": True}
    finally:
        db.close()
