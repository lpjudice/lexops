"""Estado REAL das assinaturas no ClickSign, consultado ao vivo.

Por que existe: o nosso status só mudava quando alguém abria o card do contrato (o front dispara a
sincronização) — o webhook do ClickSign não está chegando. Qualquer envio automático ao signatário
(lembrete por WhatsApp) precisa de confirmação de que ele ainda NÃO assinou; senão a pessoa que já
assinou receberia "sua assinatura está pendente". Regra: sem confirmação do ClickSign, não envia.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException

from app.database import SessionLocal
from app.models.contrato import Contrato, Signatario
from app.services import clicksign

logger = logging.getLogger(__name__)

STATUS_ESPERANDO = ("aguardando_assinatura", "parcialmente_assinado")


def consultar_estado(contrato: Contrato) -> dict | None:
    """{"doc_status": "running|closed|canceled|...", "por_key": {...}, "por_email": {...}} ou None
    se não deu pra consultar (sem documento, ClickSign fora do ar). None = NÃO assuma nada."""
    if not contrato.clicksign_document_key:
        return None
    from app.routers.contratos import _extrair_assinados  # import tardio: evita ciclo router↔service

    try:
        doc = clicksign.status_documento(contrato.clicksign_document_key)
    except Exception:
        logger.exception("clicksign_estado: erro consultando documento do contrato %s", contrato.id)
        return None
    if doc is None:
        return None
    por_key, por_email = _extrair_assinados(doc)
    return {"doc_status": (doc.get("status") or "").lower(), "por_key": por_key, "por_email": por_email}


def assinou(estado: dict, sig: Signatario) -> bool:
    """O ClickSign diz que este signatário já assinou? (mesmo critério da sincronização)"""
    if sig.clicksign_signer_key and sig.clicksign_signer_key in estado["por_key"]:
        return True
    return bool(sig.email) and sig.email.lower() in estado["por_email"]


def sincronizar(contrato_id: uuid.UUID) -> bool:
    """Roda a MESMA sincronização de abrir o card (status, quem assinou, baixa o PDF assinado, cancelamento),
    em sessão própria. False se falhou — o chamador decide o que fazer (lembrete: não envia)."""
    from app.routers.contratos import sincronizar_status

    db = SessionLocal()
    try:
        sincronizar_status(contrato_id, db)
        return True
    except HTTPException as e:
        logger.warning("clicksign_estado: sincronizar %s -> %s %s", contrato_id, e.status_code, e.detail)
    except Exception:
        db.rollback()
        logger.exception("clicksign_estado: erro sincronizando %s", contrato_id)
    finally:
        db.close()
    return False


def sincronizar_todos() -> dict:
    """Job periódico: sincroniza todo contrato que ainda espera assinatura, sem depender de alguém abrir o card."""
    db = SessionLocal()
    try:
        ids = [c.id for c in db.query(Contrato).filter(
            Contrato.status.in_(STATUS_ESPERANDO), Contrato.clicksign_document_key.isnot(None)
        ).all()]
    finally:
        db.close()
    ok = sum(1 for i in ids if sincronizar(i))
    logger.info("clicksign_estado: %d/%d contrato(s) sincronizado(s)", ok, len(ids))
    return {"contratos": len(ids), "sincronizados": ok}
