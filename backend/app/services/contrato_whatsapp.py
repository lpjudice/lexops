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


# ── Cancelamento ─────────────────────────────────────────────────────────────

TEMPLATE_ASSINATURA_CANCELADA = "assinatura_cancelada"


def avisar_cancelamento(db, contrato: Contrato) -> int:
    """Avisa por WhatsApp quem recebeu o link e tem número, quando o documento é cancelado.
    Idempotente por signatário (`cancelamento_avisado_em`), porque o cancelamento chega por até
    três caminhos (botão do sistema, webhook e sincronização do ClickSign). Quem assina pelo
    WhatsApp do ClickSign também é avisado: o ClickSign só manda o cancelamento por e-mail.
    Devolve quantos avisos saíram; falha aqui nunca derruba o cancelamento. O commit é de quem chama."""
    from datetime import datetime, timezone

    candidatos = [
        s for s in contrato.signatarios
        if s.whatsapp and s.clicksign_request_key and not s.cancelamento_avisado_em
        and (s.avisar_whatsapp or s.assinar_via_whatsapp)
    ]
    if not candidatos:
        return 0
    status = whatsapp_api.status_template(TEMPLATE_ASSINATURA_CANCELADA)
    if status not in (None, "APPROVED"):
        logger.warning("assinatura_cancelada: template não aprovado (%s) — avisos não enviados", status)
        return 0
    enviados = 0
    for sig in candidatos:
        try:
            resp = whatsapp_api.send_template_message(
                to=sig.whatsapp,
                template_name=TEMPLATE_ASSINATURA_CANCELADA,
                parametros={"nome": sig.nome, "documento": _rotulo_documento(contrato.tipo_documento)},
            )
        except Exception:
            logger.exception("assinatura_cancelada: erro avisando %s", sig.nome)
            continue
        if whatsapp_api.id_da_mensagem(resp):
            sig.cancelamento_avisado_em = datetime.now(timezone.utc)
            enviados += 1
        else:
            logger.warning("assinatura_cancelada: falha avisando %s: %s", sig.nome, resp)
    return enviados


# ── Lembretes automáticos ────────────────────────────────────────────────────

# Dias depois do envio em que o signatário que ainda não assinou recebe lembrete por WhatsApp.
# O ClickSign dá 30 dias (prazo padrão do documento): o último cai 3 dias antes de vencer.
ESTAGIOS_LEMBRETE_DIAS = (3, 7, 14, 27)
PRAZO_ASSINATURA_DIAS = 30


def estagio_devido(dias_desde_envio: int, ja_enviados: int) -> int:
    """Estágio (1..4) a enviar agora, ou 0 se nada é devido. Se vários estágios passaram sem
    envio (ex.: servidor parado), manda UM lembrete só — nunca uma rajada."""
    if dias_desde_envio < 0 or dias_desde_envio >= PRAZO_ASSINATURA_DIAS:
        return 0
    alcancados = sum(1 for d in ESTAGIOS_LEMBRETE_DIAS if dias_desde_envio >= d)
    return alcancados if alcancados > ja_enviados else 0


def enviar_lembretes_assinatura(hoje=None) -> dict:
    """Roda todo dia: lembra por WhatsApp (template assinatura_pendente) quem tem número, não assinou
    e ainda está dentro do prazo do ClickSign. Só contratos enviados DEPOIS desta função existir
    (precisam de `assinatura_enviada_em`) — os antigos não recebem nada."""
    from datetime import date, datetime, timezone

    from app.database import SessionLocal

    hoje = hoje or date.today()
    status = whatsapp_api.status_template(TEMPLATE_ASSINATURA_PENDENTE)
    if status not in (None, "APPROVED"):
        logger.warning("lembrete assinatura: template não aprovado (%s) — nada enviado", status)
        return {"enviados": 0, "motivo": f"template {status}"}
    db = SessionLocal()
    enviados = 0
    try:
        contratos = (
            db.query(Contrato)
            .filter(Contrato.status.in_(("aguardando_assinatura", "parcialmente_assinado")),
                    Contrato.assinatura_enviada_em.isnot(None))
            .all()
        )
        from app.services import clicksign_estado as ce

        for c in contratos:
            dias = (hoje - c.assinatura_enviada_em.date()).days
            # CONFIRMA no ClickSign antes de qualquer envio: o status do nosso lado pode estar velho
            # (só atualizava ao abrir o card). Sem resposta do ClickSign, ninguém é lembrado.
            estado = ce.consultar_estado(c)
            if estado is None:
                logger.warning("lembrete assinatura: sem confirmação do ClickSign (contrato %s) — pulado", c.id)
                continue
            ce.sincronizar(c.id)          # persiste quem já assinou / documento fechado ou cancelado
            db.expire_all()
            if estado["doc_status"] != "running":
                continue                  # fechado, cancelado ou vencido: não há mais o que lembrar
            for sig in c.signatarios:
                if ce.assinou(estado, sig):
                    continue
                if (sig.status_assinatura != "pendente" or not sig.whatsapp or not sig.avisar_whatsapp
                        or sig.assinar_via_whatsapp or not sig.clicksign_request_key or sig.clicksign_erro):
                    continue
                estagio = estagio_devido(dias, sig.lembretes_whatsapp or 0)
                if not estagio:
                    continue
                ok, motivo = avisar_assinatura_pendente_detalhe(sig, c)
                if ok:
                    sig.lembretes_whatsapp = estagio
                    sig.ultimo_lembrete_whatsapp_em = datetime.now(timezone.utc)
                    enviados += 1
                    db.commit()
                else:
                    logger.warning("lembrete assinatura: %s não recebeu (%s)", sig.nome, motivo)
    except Exception:
        db.rollback()
        logger.exception("lembrete assinatura: erro")
    finally:
        db.close()
    logger.info("lembrete assinatura: %d enviado(s)", enviados)
    return {"enviados": enviados}
