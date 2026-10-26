"""Botão "Já assinei" do aviso de assinatura (template assinatura_pendente_v2).

Quando a pessoa toca em "Já assinei", o sistema confere no ClickSign se a assinatura dela
entrou. O ClickSign demora alguns segundos pra refletir uma assinatura recém-feita, então:

  1. consulta com repetições (até ~40 s) antes de dizer qualquer coisa;
  2. se confirmou → sincroniza o contrato (status, PDF assinado e, se TODOS assinaram e for contrato
     novo, a cópia por WhatsApp) e responde dizendo o que aconteceu;
  3. se ainda não → responde "ainda não identifiquei" e agenda novas checagens (2 e 6 min) que avisam
     sozinhas quando a assinatura aparecer — a pessoa não precisa tocar de novo;
  4. documento cancelado/encerrado → diz isso.

A resposta é texto livre dentro das 24 h abertas pelo próprio toque no botão.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models.contrato import Signatario
from app.services import clicksign_estado as ce
from app.services import whatsapp_api

logger = logging.getLogger(__name__)

PREFIXO = "ass"
TENTATIVAS = 8              # consultas seguidas ao ClickSign
ESPERA_S = 5.0              # entre uma e outra (≈ 40 s no total)
RECHECAGENS_MIN = (2, 6)    # novas checagens automáticas se ainda não apareceu

_lock = threading.Lock()
_em_andamento: set[str] = set()   # uma verificação por signatário por vez (toques repetidos)
_ja_confirmados: set[str] = set() # evita avisar duas vezes pelas rechecagens


def payload_ja_assinei(sig_id) -> str:
    return f"{PREFIXO}:{sig_id}:ok"


def eh_payload(payload: str) -> bool:
    partes = (payload or "").split(":")
    return len(partes) == 3 and partes[0] == PREFIXO and partes[2] == "ok"


def _estado_do_signatario(sig_id: uuid.UUID) -> str:
    """Uma consulta ao ClickSign: 'assinou' | 'cancelado' | 'encerrado' | 'pendente' | 'inexistente'."""
    db = SessionLocal()
    try:
        sig = db.get(Signatario, sig_id)
        if not sig or not sig.contrato:
            return "inexistente"
        if sig.status_assinatura == "assinado":
            return "assinou"
        estado = ce.consultar_estado(sig.contrato)
        if estado is None:
            return "pendente"          # ClickSign fora do ar: não afirma nada
        if ce.assinou(estado, sig):
            return "assinou"
        if estado["doc_status"] == "canceled":
            return "cancelado"
        if estado["doc_status"] == "closed":
            return "encerrado"
        return "pendente"
    finally:
        db.close()


def verificar_com_retentativas(sig_id: uuid.UUID, tentativas: int = TENTATIVAS, espera_s: float = ESPERA_S) -> str:
    """Repete a consulta enquanto o resultado for 'pendente' (o ClickSign leva alguns segundos pra refletir)."""
    resultado = "pendente"
    for i in range(tentativas):
        resultado = _estado_do_signatario(sig_id)
        if resultado != "pendente":
            return resultado
        if i < tentativas - 1:
            time.sleep(espera_s)
    return resultado


def _texto_confirmacao(sig_id: uuid.UUID) -> str:
    """Sincroniza o contrato (isso também dispara a cópia por WhatsApp, quando cabe) e monta a resposta."""
    db = SessionLocal()
    try:
        sig = db.get(Signatario, sig_id)
        contrato_id = sig.contrato_id
    finally:
        db.close()
    ce.sincronizar(contrato_id)
    db = SessionLocal()
    try:
        sig = db.get(Signatario, sig_id)
        c = sig.contrato
        todos = all(s.status_assinatura == "assinado" for s in c.signatarios)
        eh_contrato = c.tipo_documento == "contrato"
        if todos and eh_contrato and sig.contrato_assinado_enviado_em:
            return ("✅ Assinatura confirmada! O contrato foi assinado por todas as partes e "
                    "acabei de enviar a cópia assinada nesta conversa.")
        if todos:
            return "✅ Assinatura confirmada! O documento foi assinado por todas as partes."
        extra = " Quando todos assinarem, enviaremos a cópia do contrato por aqui." if eh_contrato else ""
        return f"✅ Sua assinatura foi confirmada, obrigado! Ainda faltam assinaturas de outras partes.{extra}"
    finally:
        db.close()


def _rechecar(sig_id_str: str, telefone: str) -> None:
    """Checagem agendada depois de um "Já assinei" que ainda não tinha aparecido no ClickSign."""
    if sig_id_str in _ja_confirmados:
        return
    try:
        sig_id = uuid.UUID(sig_id_str)
        if verificar_com_retentativas(sig_id, tentativas=2, espera_s=5.0) == "assinou":
            with _lock:
                if sig_id_str in _ja_confirmados:
                    return
                _ja_confirmados.add(sig_id_str)
            whatsapp_api.send_text_message(telefone, _texto_confirmacao(sig_id))
    except Exception:
        logger.exception("já assinei: erro na rechecagem de %s", sig_id_str)


def _agendar_rechecagens(sig_id: uuid.UUID, telefone: str) -> None:
    try:
        from app.scheduler import scheduler

        agora = datetime.now(timezone.utc)
        for minutos in RECHECAGENS_MIN:
            scheduler.add_job(
                _rechecar, "date", run_date=agora + timedelta(minutes=minutos),
                args=[str(sig_id), telefone], id=f"ja_assinei_{sig_id}_{minutos}", replace_existing=True,
            )
    except Exception:
        logger.exception("já assinei: não consegui agendar rechecagens")


def tratar_ja_assinei(telefone: str, payload: str, verificar_telefone: bool = True) -> str | None:
    """Resposta ao toque em "Já assinei". Bloqueia até ~40 s (roda em segundo plano no webhook).
    Devolve o texto a enviar, ou None se o payload não for deste botão."""
    if not eh_payload(payload):
        return None
    try:
        sig_id = uuid.UUID(payload.split(":")[1])
    except ValueError:
        return None
    from app.services.whatsapp_marketing import telefone8

    db = SessionLocal()
    try:
        sig = db.get(Signatario, sig_id)
        if not sig:
            return "Não encontrei este documento. Fale com o escritório: (27) 3345-5501."
        # O botão só existe em mensagens que mandamos pra ESTE número; confere mesmo assim.
        if verificar_telefone and telefone8(sig.whatsapp) != telefone8(telefone):
            return None
    finally:
        db.close()

    chave = str(sig_id)
    with _lock:
        if chave in _em_andamento:
            return "Já estou conferindo a sua assinatura. Aguarde só um instante."
        _em_andamento.add(chave)
    try:
        resultado = verificar_com_retentativas(sig_id)
        if resultado == "assinou":
            _ja_confirmados.add(chave)
            return _texto_confirmacao(sig_id)
        if resultado == "cancelado":
            return "Este documento foi cancelado e não precisa mais ser assinado."
        if resultado == "encerrado":
            return "Este documento já foi encerrado e não aceita mais assinaturas. Fale com o escritório: (27) 3345-5501."
        if resultado == "inexistente":
            return "Não encontrei este documento. Fale com o escritório: (27) 3345-5501."
        _agendar_rechecagens(sig_id, telefone)
        return ("Ainda não identifiquei a sua assinatura. Depois de assinar, o ClickSign pode levar alguns "
                "instantes para confirmar — vou conferir de novo e te aviso por aqui. Se ainda não assinou, "
                "use o botão \"Assinar documento\".")
    finally:
        with _lock:
            _em_andamento.discard(chave)
