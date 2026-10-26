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
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.models.contrato import Contrato, Signatario
from app.services import whatsapp_api

logger = logging.getLogger(__name__)

TEMPLATE_ASSINATURA_PENDENTE = "assinatura_pendente"
# v2 = mesmo aviso + botão de resposta "Já assinei" (link no botão 0, "Já assinei" no botão 1).
TEMPLATE_ASSINATURA_PENDENTE_V2 = "assinatura_pendente_v2"


def template_aviso_assinatura() -> tuple[str, str | None]:
    """(nome do template, status): usa a v2 (com "Já assinei") assim que a Meta aprovar; até lá, a v1."""
    if whatsapp_api.status_template(TEMPLATE_ASSINATURA_PENDENTE_V2) == "APPROVED":
        return TEMPLATE_ASSINATURA_PENDENTE_V2, "APPROVED"
    return TEMPLATE_ASSINATURA_PENDENTE, whatsapp_api.status_template(TEMPLATE_ASSINATURA_PENDENTE)

# ── Só contratos/procurações NOVOS ───────────────────────────────────────────
# Regra do Lucas (25/10/2026): mensagens AUTOMÁTICAS de WhatsApp (lembretes, aviso de cancelamento,
# cópia do contrato assinado) só valem pra contrato/procuração criado depois deste momento — o que já
# estava cadastrado nunca recebe nada. Ações MANUAIS (enviar pra assinatura, botão "Lembrar") seguem livres.
# Dá pra mudar sem deploy com WHATSAPP_CONTRATOS_DESDE (ISO 8601, ex.: 2026-11-01T00:00:00-03:00).
_DESDE_PADRAO = datetime(2026, 10, 25, 22, 15, tzinfo=timezone.utc)


def contratos_desde() -> datetime:
    bruto = os.getenv("WHATSAPP_CONTRATOS_DESDE", "").strip()
    if bruto:
        try:
            dt = datetime.fromisoformat(bruto)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            logger.warning("WHATSAPP_CONTRATOS_DESDE inválida (%r) — usando o padrão", bruto)
    return _DESDE_PADRAO


def contrato_novo(contrato: Contrato) -> bool:
    """Criado depois do corte? Sem data de criação, trata como antigo (nunca envia)."""
    return bool(contrato.created_at) and contrato.created_at >= contratos_desde()


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
    nome_template, status = template_aviso_assinatura()
    if status not in (None, "APPROVED"):
        logger.warning("assinatura_pendente: %s NÃO avisado — template %s com status %s", sig.nome, nome_template, status)
        return False, f"o template de aviso ainda não foi aprovado pela Meta (status: {status})"
    extras: dict = {}
    if nome_template == TEMPLATE_ASSINATURA_PENDENTE_V2 and getattr(sig, "id", None):
        from app.services.whatsapp_assinatura import payload_ja_assinei

        extras = {"botoes_resposta_payload": [payload_ja_assinei(sig.id)], "botoes_resposta_indice_inicial": 1}
    try:
        resultado = whatsapp_api.send_template_message(
            to=sig.whatsapp,
            template_name=nome_template,
            parametros={
                "nome": sig.nome,
                "documento": _rotulo_documento(contrato.tipo_documento),
            },
            botao_url_param=sig.clicksign_request_key,
            **extras,
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

    if not contrato_novo(contrato):
        return 0
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

# Dias depois do envio em que o signatário que ainda não assinou recebe lembrete por WhatsApp — cada
# lembrete tem o SEU horário: envio + N dias (mesma hora do dia do envio). O ClickSign dá 30 dias
# (prazo padrão do documento): o último cai 3 dias antes de vencer.
ESTAGIOS_LEMBRETE_DIAS = (3, 7, 14, 27)
PRAZO_ASSINATURA_DIAS = 30
FUSO = ZoneInfo("America/Sao_Paulo")
JANELA_ENVIO_HORAS = (8, 20)                      # lembrete só sai entre 8h e 20h (Brasília)
ANTECEDENCIA_VALIDACAO = timedelta(minutes=30)    # confirma no ClickSign 30 min antes do lembrete
INTERVALO_MIN_VALIDACAO = timedelta(minutes=25)   # não repete a confirmação dentro da mesma janela


def vencimento_estagio(enviada_em: datetime, estagio: int) -> datetime:
    """Quando o lembrete do estágio (1..4) vence: envio + N dias."""
    return enviada_em + timedelta(days=ESTAGIOS_LEMBRETE_DIAS[estagio - 1])


def estagio_a_enviar(enviada_em: datetime, agora: datetime, ja_enviados: int) -> int:
    """Estágio (1..4) a enviar agora, ou 0. Se vários venceram sem envio (servidor parado, fora da
    janela de horário), manda UM lembrete só — nunca uma rajada. Depois do prazo do ClickSign, nada."""
    if agora >= enviada_em + timedelta(days=PRAZO_ASSINATURA_DIAS):
        return 0
    vencidos = sum(1 for n in range(1, len(ESTAGIOS_LEMBRETE_DIAS) + 1) if agora >= vencimento_estagio(enviada_em, n))
    return vencidos if vencidos > ja_enviados else 0


def na_janela_de_validacao(enviada_em: datetime, agora: datetime, ja_enviados: int) -> bool:
    """Faltam 30 min ou menos pro PRÓXIMO lembrete deste signatário? É a hora de confirmar o status no ClickSign."""
    proximo = ja_enviados + 1
    if proximo > len(ESTAGIOS_LEMBRETE_DIAS):
        return False
    venc = vencimento_estagio(enviada_em, proximo)
    return venc - ANTECEDENCIA_VALIDACAO <= agora < venc


def _pode_receber_lembrete(sig: Signatario) -> bool:
    return bool(
        sig.status_assinatura == "pendente" and sig.whatsapp and sig.avisar_whatsapp
        and not sig.assinar_via_whatsapp and sig.clicksign_request_key and not sig.clicksign_erro
    )


def enviar_lembretes_assinatura(agora: datetime | None = None) -> dict:
    """Roda a cada 15 min (só olha o banco; o ClickSign é consultado só quando há lembrete chegando):

      1. 30 min antes de um lembrete vencer, sincroniza o contrato com o ClickSign (status em dia);
      2. na hora do lembrete (entre 8h e 20h), consulta o ClickSign DE NOVO e só envia se o signatário
         ainda não assinou e o documento segue aberto. Sem resposta do ClickSign, não envia.

    Só contratos/procurações NOVOS (ver `contrato_novo`) com `assinatura_enviada_em`."""
    from app.database import SessionLocal
    from app.services import clicksign_estado as ce

    agora = agora or datetime.now(timezone.utc)
    pode_enviar = JANELA_ENVIO_HORAS[0] <= agora.astimezone(FUSO).hour < JANELA_ENVIO_HORAS[1]
    db = SessionLocal()
    enviados = validados = 0
    try:
        candidatos = [
            c for c in db.query(Contrato)
            .filter(Contrato.status.in_(("aguardando_assinatura", "parcialmente_assinado")),
                    Contrato.assinatura_enviada_em.isnot(None))
            .all()
            if contrato_novo(c) and agora < c.assinatura_enviada_em + timedelta(days=PRAZO_ASSINATURA_DIAS)
        ]
        status_tpl = None
        for c in candidatos:
            pendentes = [s for s in c.signatarios if _pode_receber_lembrete(s)]
            if not pendentes:
                continue
            enviada = c.assinatura_enviada_em

            # 1) pré-validação 30 min antes
            if any(na_janela_de_validacao(enviada, agora, s.lembretes_whatsapp or 0) for s in pendentes):
                ultima = c.ultima_validacao_clicksign_em
                if ultima is None or agora - ultima >= INTERVALO_MIN_VALIDACAO:
                    ce.sincronizar(c.id)
                    db.expire_all()
                    c.ultima_validacao_clicksign_em = agora
                    db.commit()
                    validados += 1
                    pendentes = [s for s in c.signatarios if _pode_receber_lembrete(s)]

            # 2) hora do lembrete
            devidos = [(s, estagio_a_enviar(enviada, agora, s.lembretes_whatsapp or 0)) for s in pendentes]
            devidos = [(s, e) for s, e in devidos if e]
            if not devidos or not pode_enviar:
                continue
            if status_tpl is None:
                status_tpl = template_aviso_assinatura()[1] or "?"
            if status_tpl not in ("?", "APPROVED"):
                logger.warning("lembrete assinatura: template não aprovado (%s) — nada enviado", status_tpl)
                return {"enviados": enviados, "validados": validados, "motivo": f"template {status_tpl}"}
            estado = ce.consultar_estado(c)   # confirmação FRESCA, na hora de enviar
            if estado is None:
                logger.warning("lembrete assinatura: sem confirmação do ClickSign (contrato %s) — não enviado", c.id)
                continue
            if estado["doc_status"] != "running":
                ce.sincronizar(c.id)          # fechado/cancelado/vencido: atualiza e não lembra ninguém
                continue
            for sig, estagio in devidos:
                if ce.assinou(estado, sig):
                    continue
                ok, motivo = avisar_assinatura_pendente_detalhe(sig, c)
                if ok:
                    sig.lembretes_whatsapp = estagio
                    sig.ultimo_lembrete_whatsapp_em = agora
                    enviados += 1
                    db.commit()
                else:
                    logger.warning("lembrete assinatura: %s não recebeu (%s)", sig.nome, motivo)
    except Exception:
        db.rollback()
        logger.exception("lembrete assinatura: erro")
    finally:
        db.close()
    if enviados or validados:
        logger.info("lembrete assinatura: %d enviado(s), %d contrato(s) validado(s)", enviados, validados)
    return {"enviados": enviados, "validados": validados}


# ── Cópia do contrato assinado ───────────────────────────────────────────────

TEMPLATE_CONTRATO_ASSINADO = "contrato_assinado"
_LIMITE_PDF_BYTES = 90 * 1024 * 1024  # a Meta aceita até 100 MB por documento


def _nome_arquivo_pdf(titulo: str | None) -> str:
    base = re.sub(r"[^\w\- .]", " ", titulo or "Contrato", flags=re.UNICODE)
    base = re.sub(r"\s+", " ", base).strip()[:80] or "Contrato"
    return f"{base} - assinado.pdf"


def enviar_contrato_assinado(db, contrato: Contrato) -> int:
    """Quando TODOS assinam, manda o PDF assinado por WhatsApp (template com o documento no cabeçalho)
    ao(s) contratante(s) que tem número e aceitou aviso por WhatsApp. SÓ contrato — procuração não.
    Só contratos novos. Idempotente por signatário. O arquivo sobe direto pra Meta (sem link público).
    Falha aqui nunca derruba a sincronização. O commit é de quem chama. Devolve quantos saíram."""
    if contrato.tipo_documento != "contrato" or contrato.status != "assinado" or not contrato_novo(contrato):
        return 0
    candidatos = [
        s for s in contrato.signatarios
        if s.papel == "contratante" and s.whatsapp and (s.avisar_whatsapp or s.assinar_via_whatsapp)
        and not s.contrato_assinado_enviado_em
    ]
    if not candidatos:
        return 0
    caminho = Path(contrato.arquivo_assinado_path) if contrato.arquivo_assinado_path else None
    if not caminho or not caminho.is_file():
        logger.warning("contrato_assinado: PDF assinado indisponível no disco (contrato %s)", contrato.id)
        return 0
    status = whatsapp_api.status_template(TEMPLATE_CONTRATO_ASSINADO)
    if status not in (None, "APPROVED"):
        logger.warning("contrato_assinado: template não aprovado (%s) — será tentado de novo", status)
        return 0
    conteudo = caminho.read_bytes()
    if len(conteudo) > _LIMITE_PDF_BYTES:
        logger.warning("contrato_assinado: PDF grande demais (%d bytes) — não enviado", len(conteudo))
        return 0
    nome_arquivo = _nome_arquivo_pdf(contrato.titulo)
    media_id = whatsapp_api.upload_media(conteudo, "application/pdf", nome_arquivo)
    if not media_id:
        logger.warning("contrato_assinado: upload do PDF pra Meta falhou (contrato %s)", contrato.id)
        return 0
    enviados = 0
    for sig in candidatos:
        try:
            resp = whatsapp_api.send_template_message(
                to=sig.whatsapp, template_name=TEMPLATE_CONTRATO_ASSINADO,
                parametros={"nome": sig.nome}, header_documento=(media_id, nome_arquivo),
            )
        except Exception:
            logger.exception("contrato_assinado: erro enviando a %s", sig.nome)
            continue
        if whatsapp_api.id_da_mensagem(resp):
            sig.contrato_assinado_enviado_em = datetime.now(timezone.utc)
            enviados += 1
        else:
            logger.warning("contrato_assinado: falha enviando a %s: %s", sig.nome, resp)
    return enviados


def reenviar_contratos_assinados_pendentes() -> int:
    """Rede de segurança (roda no job diário): contratos novos já assinados nos últimos 14 dias cuja cópia
    não saiu — template ainda em análise, falha de rede etc. — são tentados de novo."""
    from app.database import SessionLocal

    db = SessionLocal()
    total = 0
    try:
        desde = datetime.now(timezone.utc) - timedelta(days=14)
        for c in db.query(Contrato).filter(
            Contrato.tipo_documento == "contrato", Contrato.status == "assinado", Contrato.updated_at >= desde
        ).all():
            n = enviar_contrato_assinado(db, c)
            if n:
                db.commit()
                total += n
    except Exception:
        db.rollback()
        logger.exception("contrato_assinado: erro no reenvio")
    finally:
        db.close()
    return total
