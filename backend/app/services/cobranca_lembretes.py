"""
Lembretes de pagamento de recebíveis (tom amigável, não cobrança).

Para cada recebível (Honorário) com `cobranca_ativa`, envia ao cliente um e-mail
(com PDF em anexo) lembrando do pagamento, seguindo estágios:
  - 15 dias antes do vencimento (estágio 1)
  - 7 dias antes (estágio 2)
  - 2 dias antes (estágio 3)
  - 5 dias DEPOIS do vencimento, uma única vez, com texto diferente (estágio 4)
Cada estágio sai uma vez só. Funciona tanto para recebíveis PARCELADOS (um
estágio por parcela, em `Parcela.cobranca_estagio`) quanto para recebíveis À
VISTA — sem cronograma, usando `Honorario.data_vencimento` diretamente e
`Honorario.cobranca_estagio`. Para quando o pagamento é confirmado. Espelha o
padrão de `prazo_lembretes`/reembolsos.
"""
import logging
from datetime import date, datetime, timezone
from types import SimpleNamespace

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── Cadência (dias antes do vencimento) + lembrete único após o vencimento ────
LEMBRETES_ANTES = (15, 7, 2)   # estágios 1, 2, 3
POS_VENCIMENTO_DIAS = 5        # estágio 4 (envio único, texto diferente)

# ── Dados de pagamento exibidos no PDF/e-mail (comunicação com a Monielly) ────
# TODO: mover para ConfigFiscal quando houver tela de configuração.
PAGAMENTO = {
    "pix_chave": "10.901.611/0001-64",
    "pix_tipo": "CNPJ",
    "favorecido": "Pimenta Judice Advogados",
    "contato_nome": "Monielly Moreira Vieira",
    "contato_email": "moni@pimentajudice.com.br",
    "contato_whatsapp": "5527997568819",       # dígitos com DDI+DDD, para link wa.me
    "contato_whatsapp_fmt": "(27) 9.9756-8819",  # exibição formatada
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


def _stage_alvo(venc: date, hoje: date) -> int:
    """Estágio de lembrete que a parcela DEVE ter atingido hoje (0..4)."""
    dias = (venc - hoje).days
    if dias <= -POS_VENCIMENTO_DIAS:
        return 4
    if dias <= LEMBRETES_ANTES[2]:
        return 3
    if dias <= LEMBRETES_ANTES[1]:
        return 2
    if dias <= LEMBRETES_ANTES[0]:
        return 1
    return 0


def _enviar_parcela(*, db, h, cliente, alvo, destino, escr, pos_vencimento, hoje, agora,
                    n_parcelas_pend) -> None:
    """Monta o PDF + e-mail e envia para o alvo (parcela real ou o próprio honorário
    à vista). Marca `ultimo_lembrete_em` quando o alvo suportar (parcela real)."""
    from app.services.cobranca_pdf import _brl, _fmt_data, gerar_pdf_cobranca
    from app.services.email_service import _send_via_gmail_oauth, build_cobranca_html

    if h.parcelas:
        parcelas_info = [
            {
                "numero": p.numero, "valor": float(p.valor), "vencimento": p.data_vencimento,
                "status": p.status,
                "atrasada": (p.status == "pendente" and p.data_vencimento < hoje),
            }
            for p in sorted(h.parcelas, key=lambda x: x.numero)
        ]
    else:
        # Recebível à vista (sem cronograma): uma única "parcela" sintética.
        parcelas_info = [{
            "numero": 1, "valor": float(h.valor_total), "vencimento": h.data_vencimento,
            "status": "pendente",
            "atrasada": (h.data_vencimento < hoje),
        }]

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
    html = build_cobranca_html(
        nome=(cliente.nome if cliente else ""),
        descricao=h.descricao,
        parcela_numero=alvo.numero,
        parcela_valor=_brl(float(alvo.valor)),
        parcela_venc=_fmt_data(alvo.data_vencimento),
        valor_total=_brl(float(h.valor_total)),
        n_parcelas_total=len(parcelas_info),
        n_parcelas_pend=n_parcelas_pend,
        pos_vencimento=pos_vencimento,
        pagamento=PAGAMENTO,
    )
    assunto = f"Lembrete de pagamento — {h.descricao}" if pos_vencimento else f"Lembrete — {h.descricao}"
    _send_via_gmail_oauth(
        destino, assunto, html,
        attachments=[(f"lembrete_parcela_{alvo.numero}.pdf", pdf)],
    )
    if hasattr(alvo, "ultimo_lembrete_em"):
        alvo.ultimo_lembrete_em = agora


def enviar_cobrancas(db: Session, *, hoje: date | None = None, forcar: bool = False,
                     honorario_id=None) -> dict:
    """
    Cron: envia os lembretes cujos estágios venceram hoje (um por honorário/parcela).
    Manual (honorario_id ou forcar): envia agora o lembrete do próximo vencimento,
    sem depender de estágio.
    """
    from app.models.cliente import Cliente
    from app.models.financeiro import Honorario

    hoje = hoje or date.today()
    agora = datetime.now(timezone.utc)
    escr = _escritorio_dict(db)
    manual = honorario_id is not None or forcar

    q = db.query(Honorario)
    if honorario_id is not None:
        q = q.filter(Honorario.id == honorario_id)
    else:
        q = q.filter(Honorario.cobranca_ativa.is_(True))
    honorarios = q.all()

    enviados, pulados = 0, 0
    erros: list[str] = []

    for h in honorarios:
        if h.status in ("pago", "cancelado"):
            continue

        cliente = db.query(Cliente).filter(Cliente.id == h.cliente_id).first()
        # Prioridade: lista de e-mails (nova) → e-mail único (legado) → e-mail do cliente.
        destinos_brutos = h.cobranca_emails or ([h.cobranca_email] if h.cobranca_email else None) \
            or ([cliente.email] if cliente and cliente.email else [])
        destinos = [d.strip() for d in destinos_brutos if d and d.strip()]
        if not destinos:
            pulados += 1
            logger.info("Lembrete: honorário %s sem e-mail de destino — pulado", h.id)
            continue
        destino = ", ".join(destinos)

        if h.parcelas:
            # ── Recebível parcelado: um estágio por parcela ──────────────────
            pendentes = sorted(
                (p for p in h.parcelas if p.status == "pendente"),
                key=lambda p: p.data_vencimento,
            )
            if not pendentes:
                continue

            if manual:
                alvo = pendentes[0]
                pos = alvo.data_vencimento < hoje
                try:
                    _enviar_parcela(db=db, h=h, cliente=cliente, alvo=alvo, destino=destino,
                                    escr=escr, pos_vencimento=pos, hoje=hoje, agora=agora,
                                    n_parcelas_pend=len(pendentes))
                    db.commit()
                    enviados += 1
                except Exception as e:  # noqa: BLE001
                    db.rollback()
                    erros.append(f"{h.id}: {e}")
                    logger.warning("Lembrete: falha ao enviar honorário %s: %s", h.id, e)
                continue

            for p in pendentes:
                target = _stage_alvo(p.data_vencimento, hoje)
                if target <= (p.cobranca_estagio or 0):
                    continue
                try:
                    _enviar_parcela(db=db, h=h, cliente=cliente, alvo=p, destino=destino,
                                    escr=escr, pos_vencimento=(target == 4), hoje=hoje, agora=agora,
                                    n_parcelas_pend=len(pendentes))
                    p.cobranca_estagio = target
                    db.commit()
                    enviados += 1
                except Exception as e:  # noqa: BLE001
                    db.rollback()
                    erros.append(f"{h.id}: {e}")
                    logger.warning("Lembrete: falha ao enviar honorário %s: %s", h.id, e)
                break

        else:
            # ── Recebível à vista (sem cronograma): usa data_vencimento do honorário ──
            if not h.data_vencimento:
                continue
            alvo = SimpleNamespace(numero=1, valor=float(h.valor_total), data_vencimento=h.data_vencimento)

            if manual:
                pos = alvo.data_vencimento < hoje
                try:
                    _enviar_parcela(db=db, h=h, cliente=cliente, alvo=alvo, destino=destino,
                                    escr=escr, pos_vencimento=pos, hoje=hoje, agora=agora,
                                    n_parcelas_pend=1)
                    db.commit()
                    enviados += 1
                except Exception as e:  # noqa: BLE001
                    db.rollback()
                    erros.append(f"{h.id}: {e}")
                    logger.warning("Lembrete: falha ao enviar honorário %s: %s", h.id, e)
                continue

            target = _stage_alvo(alvo.data_vencimento, hoje)
            if target <= (h.cobranca_estagio or 0):
                continue
            try:
                _enviar_parcela(db=db, h=h, cliente=cliente, alvo=alvo, destino=destino,
                                escr=escr, pos_vencimento=(target == 4), hoje=hoje, agora=agora,
                                n_parcelas_pend=1)
                h.cobranca_estagio = target
                db.commit()
                enviados += 1
            except Exception as e:  # noqa: BLE001
                db.rollback()
                erros.append(f"{h.id}: {e}")
                logger.warning("Lembrete: falha ao enviar honorário %s: %s", h.id, e)

    return {"enviados": enviados, "pulados": pulados, "erros": erros}
