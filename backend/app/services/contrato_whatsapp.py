"""Aviso de assinatura pendente ao SIGNATÁRIO via WhatsApp (template `assinatura_pendente`).

Complementa — não substitui — o convite por e-mail do ClickSign: o botão abre a
mesma página de assinatura (app.clicksign.com/sign/{request_signature_key}) e o
signatário continua precisando do token enviado ao e-mail dele (auths=["email"]),
então o link sozinho não assina nada.

Só envia quando o signatário tem `whatsapp` preenchido (opt-in) e já foi
registrado no ClickSign. Falha aqui nunca derruba o envio/lembrete do ClickSign.

Template esperado no WhatsApp Manager (UTILITY, pt_BR, parâmetros nomeados):
corpo com {{nome}} e {{documento}}, mais um botão de link
https://app.clicksign.com/sign/{{1}}.
"""
from __future__ import annotations

import logging

from app.models.contrato import Contrato, Signatario
from app.services import whatsapp_api

logger = logging.getLogger(__name__)

TEMPLATE_ASSINATURA_PENDENTE = "assinatura_pendente"


def _rotulo_documento(tipo_documento: str | None) -> str:
    return "Procuração" if tipo_documento == "procuracao" else "Contrato"


def avisar_assinatura_pendente_detalhe(sig: Signatario, contrato: Contrato) -> tuple[bool, str | None]:
    """(enviou, motivo). `motivo` explica por que NÃO enviou, quando faz sentido
    mostrar ao usuário (template em análise, Meta recusou); None se simplesmente
    não se aplica (sem número, aviso desmarcado, assina via ClickSign)."""
    if not sig.whatsapp or not sig.clicksign_request_key:
        return False, None
    # Desmarcado pelo usuário, ou o próprio ClickSign já convida por WhatsApp
    # (mandar o nosso também duplicaria a mensagem).
    if not sig.avisar_whatsapp or sig.assinar_via_whatsapp:
        return False, None
    status = whatsapp_api.status_template(TEMPLATE_ASSINATURA_PENDENTE)
    if status not in (None, "APPROVED"):
        return False, f"o template de aviso ainda não foi aprovado pela Meta (status: {status})"
    try:
        resultado = whatsapp_api.send_template_message(
            to=sig.whatsapp,
            template_name=TEMPLATE_ASSINATURA_PENDENTE,
            parametros={
                "nome": sig.nome,
                "documento": _rotulo_documento(contrato.tipo_documento),
            },
            botao_url_param=sig.clicksign_request_key,
        )
    except Exception:
        logger.exception("assinatura_pendente: erro inesperado ao avisar %s", sig.nome)
        return False, "erro inesperado ao enviar (veja os logs)"
    if not resultado or resultado.get("erro"):
        logger.warning("assinatura_pendente: falha ao avisar %s: %s", sig.nome, resultado)
        return False, "a Meta recusou o envio (veja os logs)"
    return True, None


def avisar_assinatura_pendente(sig: Signatario, contrato: Contrato) -> bool:
    """Manda o aviso por WhatsApp. True se a Meta aceitou o envio."""
    return avisar_assinatura_pendente_detalhe(sig, contrato)[0]
