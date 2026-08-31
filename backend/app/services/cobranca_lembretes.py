"""
Cobrança automática de recebíveis parcelados.

Para cada recebível (Honorário) com `cobranca_ativa`, envia ao cliente um e-mail
com PDF de cobrança para as parcelas pendentes já vencidas, uma vez por dia por
parcela (dedup por `ultimo_lembrete_em`), até a parcela ser marcada como paga.
Espelha o padrão de `prazo_lembretes`/reembolsos.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── Cadência da cobrança ──────────────────────────────────────────────────────
# Começa a lembrar esta quantidade de dias ANTES do vencimento (e segue depois de
# vencida), reenviando a cada INTERVALO_DIAS dias, até a parcela ser paga.
DIAS_ANTES_VENCIMENTO = 7
INTERVALO_DIAS = 3

# ── Dados de pagamento exibidos no PDF/e-mail (comunicação com a Monielly) ────
# Preencher com a chave PIX real do escritório.
PAGAMENTO = {
    "pix_chave": "10.901.611/0001-64",
    "pix_tipo": "CNPJ",
    "favorecido": "Pimenta Judice Advogados",
    "contato": "Monielly Moreira Vieira — moni@pimentajudice.com.br · WhatsApp (27) 9.9756-8819",
}


def _escritorio_dict(db: Session) -> dict:
    try:
        from app.models.config_fiscal import ConfigFiscal
        cfg = db.query(ConfigFiscal).first()
        if cfg:
            return {
                "razao_social": getattr(cfg, "razao_social", None),
                "cnpj": getattr(cfg, "cnpj", None),
                "endereco": getattr(cfg, "endereco", None),
            }
    except Exception:
        pass
    return {"razao_social": "Pimenta Júdice Advogados", "cnpj": None, "endereco": None}


def _html_cobranca(cliente_nome: str, descricao: str, parcela_numero: int,
                   parcela_valor: float, parcela_venc, saldo: float) -> str:
    from app.services.cobranca_pdf import _brl, _fmt_data
    return f"""
    <div style="font-family:Arial,sans-serif;font-size:14px;color:#1f2937;max-width:560px">
      <p>Olá, {cliente_nome},</p>
      <p>Consta em aberto a <b>parcela {parcela_numero}</b> referente a
         <b>{descricao}</b>, no valor de <b>{_brl(parcela_valor)}</b>,
         com vencimento em <b>{_fmt_data(parcela_venc)}</b>.</p>
      <p>Saldo total em aberto deste recebível: <b>{_brl(saldo)}</b>.</p>
      <p>Segue em anexo o aviso de cobrança com o cronograma completo. Caso o
         pagamento já tenha sido realizado, por favor desconsidere e, se possível,
         responda a este e-mail com o comprovante.</p>
      <p style="color:#6b7280;font-size:12px">Mensagem automática — Pimenta Júdice Advogados.</p>
    </div>
    """


def enviar_cobrancas(db: Session, *, hoje: date | None = None, forcar: bool = False,
                     honorario_id=None) -> dict:
    """
    Envia as cobranças devidas. Se `honorario_id` for passado, processa só aquele
    (uso manual/teste) e ignora o opt-in `cobranca_ativa`. `forcar` ignora o dedup diário.
    """
    from app.models.cliente import Cliente
    from app.models.financeiro import Honorario
    from app.services.cobranca_pdf import gerar_pdf_cobranca
    from app.services.email_service import _send_via_gmail_oauth

    hoje = hoje or date.today()
    agora = datetime.now(timezone.utc)
    escr = _escritorio_dict(db)

    q = db.query(Honorario)
    if honorario_id is not None:
        q = q.filter(Honorario.id == honorario_id)
    else:
        q = q.filter(Honorario.cobranca_ativa.is_(True))
    honorarios = q.all()

    enviados, pulados = 0, 0
    erros: list[str] = []

    manual = honorario_id is not None
    limite_janela = hoje + timedelta(days=DIAS_ANTES_VENCIMENTO)

    for h in honorarios:
        if h.status in ("pago", "cancelado"):
            continue
        if not h.parcelas:
            continue
        pendentes_todas = [p for p in h.parcelas if p.status == "pendente"]
        if not pendentes_todas:
            continue
        # No envio manual, qualquer parcela pendente pode ser cobrada; no cron, só as
        # que já entraram na janela (a vencer em até DIAS_ANTES ou já vencidas).
        elegiveis = pendentes_todas if manual else [p for p in pendentes_todas if p.data_vencimento <= limite_janela]
        if not elegiveis:
            continue

        def _pode(p):
            if forcar:
                return True
            if not p.ultimo_lembrete_em:
                return True
            return (hoje - p.ultimo_lembrete_em.date()).days >= INTERVALO_DIAS

        a_enviar = [p for p in elegiveis if _pode(p)]
        if not a_enviar:
            continue

        cliente = db.query(Cliente).filter(Cliente.id == h.cliente_id).first()
        destino = (h.cobranca_email or (cliente.email if cliente else None) or "").strip()
        if not destino:
            pulados += 1
            logger.info("Cobrança: honorário %s sem e-mail de destino — pulado", h.id)
            continue

        # Cobra a próxima parcela a vencer (ou a mais atrasada) da vez.
        alvo = sorted(a_enviar, key=lambda p: p.data_vencimento)[0]
        parcelas_info = [
            {
                "numero": p.numero, "valor": float(p.valor), "vencimento": p.data_vencimento,
                "status": p.status,
                "atrasada": (p.status == "pendente" and p.data_vencimento < hoje),
            }
            for p in sorted(h.parcelas, key=lambda x: x.numero)
        ]
        try:
            pdf = gerar_pdf_cobranca(
                escritorio=escr,
                cliente_nome=(cliente.nome if cliente else "Cliente"),
                descricao=h.descricao,
                parcelas=parcelas_info,
                total=float(h.valor_total),
                saldo=h.saldo_pendente,
                destaque_numero=alvo.numero,
                pagamento=PAGAMENTO,
            )
            html = _html_cobranca(
                cliente.nome if cliente else "Cliente", h.descricao,
                alvo.numero, float(alvo.valor), alvo.data_vencimento, h.saldo_pendente,
            )
            _send_via_gmail_oauth(
                destino, f"Cobrança — {h.descricao}", html,
                attachments=[(f"cobranca_parcela_{alvo.numero}.pdf", pdf)],
            )
            alvo.ultimo_lembrete_em = agora
            db.commit()
            enviados += 1
        except Exception as e:  # noqa: BLE001
            db.rollback()
            erros.append(f"{h.id}: {e}")
            logger.warning("Cobrança: falha ao enviar honorário %s: %s", h.id, e)

    return {"enviados": enviados, "pulados": pulados, "erros": erros}
