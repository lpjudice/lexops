"""Router /config-fiscal — configuração fiscal singleton."""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.config_fiscal import ConfigFiscal
from app.schemas.config_fiscal import ConfigFiscalOut, ConfigFiscalUpdate

router = APIRouter(prefix="/config-fiscal", tags=["config-fiscal"])

# Anexo IV do Simples Nacional: (limite_superior_RBT12, aliquota_nominal%, parcela_deduzir)
ANEXO_IV = [
    (Decimal("180000.00"),  Decimal("4.50"),  Decimal("0")),
    (Decimal("360000.00"),  Decimal("9.00"),  Decimal("8100")),
    (Decimal("720000.00"),  Decimal("10.20"), Decimal("12420")),
    (Decimal("1800000.00"), Decimal("14.00"), Decimal("39780")),
    (Decimal("3600000.00"), Decimal("22.00"), Decimal("183780")),
    (Decimal("4800000.00"), Decimal("33.00"), Decimal("828000")),
]


def _sugerir_aliquota(rbt12: Decimal | None) -> tuple[Decimal | None, str | None]:
    """Alíquota efetiva sugerida pelo Anexo IV a partir da RBT12."""
    if not rbt12 or rbt12 <= 0:
        return None, None
    for i, (limite, aliq_nom, deduzir) in enumerate(ANEXO_IV, start=1):
        if rbt12 <= limite:
            efetiva = (rbt12 * aliq_nom / 100 - deduzir) / rbt12 * 100
            return efetiva.quantize(Decimal("0.01")), f"Faixa {i} (Anexo IV)"
    return Decimal("33.00"), "Acima do limite do Simples"


def _get_or_create(db: Session) -> ConfigFiscal:
    cfg = db.query(ConfigFiscal).filter(ConfigFiscal.id == 1).first()
    if not cfg:
        cfg = ConfigFiscal(id=1)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def _rbt12_acumulado(db: Session) -> Decimal:
    """RBT12 legal (LC 123/2006, art. 18 §1º): receita bruta dos 12 meses
    ANTERIORES ao período de apuração (mês corrente), rolling — sem incluir o
    mês corrente. ATENÇÃO: soma apenas as NFs conhecidas pelo sistema
    (emitidas aqui + importadas via DFe). Notas antigas emitidas direto no
    portal antes da integração podem não constar — o valor oficial vem da
    contabilidade. Serve como sugestão/checagem, não como fonte da verdade."""
    from datetime import date
    from app.models.nota_fiscal import NotaFiscal
    hoje = date.today()
    # comp_fim = mês anterior ao corrente; comp_ini = 11 meses antes de comp_fim
    ano_fim, mes_fim = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
    # 12 meses terminando em (ano_fim, mes_fim): subtrai 11 meses
    total_meses = ano_fim * 12 + (mes_fim - 1) - 11
    ano_ini, mes_ini = divmod(total_meses, 12)
    mes_ini += 1
    comp_fim = f"{ano_fim:04d}-{mes_fim:02d}"
    comp_ini = f"{ano_ini:04d}-{mes_ini:02d}"
    total = Decimal("0")
    notas = (db.query(NotaFiscal)
             .filter(NotaFiscal.status == "emitida", NotaFiscal.ambiente == 1,
                     NotaFiscal.competencia >= comp_ini,
                     NotaFiscal.competencia <= comp_fim).all())
    for n in notas:
        total += Decimal(str(n.valor_servicos or 0))
    return total.quantize(Decimal("0.01"))


def _to_out(cfg: ConfigFiscal, db: Session | None = None) -> ConfigFiscalOut:
    out = ConfigFiscalOut.model_validate(cfg)
    sug, faixa = _sugerir_aliquota(Decimal(str(cfg.rbt12)) if cfg.rbt12 else None)
    out.aliquota_simples_sugerida = sug
    out.faixa_simples = faixa
    if db is not None:
        rbt = _rbt12_acumulado(db)
        out.rbt12_acumulado_12m = float(rbt)
        sug2, fx2 = _sugerir_aliquota(rbt)
        out.aliquota_pelo_acumulado = float(sug2) if sug2 else None
    return out


@router.get("", response_model=ConfigFiscalOut)
def obter_config(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _to_out(_get_or_create(db), db)


@router.put("", response_model=ConfigFiscalOut)
def atualizar_config(
    body: ConfigFiscalUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    cfg = _get_or_create(db)
    dados = body.model_dump()
    for campo, valor in dados.items():
        # JSONB de pydantic models → dicts
        if campo in ("codigos_favoritos", "templates_descricao"):
            valor = [v if isinstance(v, dict) else v.model_dump() for v in (valor or [])]
        setattr(cfg, campo, valor)
    db.commit()
    db.refresh(cfg)
    return _to_out(cfg, db)


@router.post("/link-publico")
def gerar_link_publico(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Gera (ou regenera) o token do link público de reforma para o contador."""
    import secrets
    cfg = _get_or_create(db)
    cfg.link_publico_token = secrets.token_urlsafe(24)
    db.commit()
    return {"token": cfg.link_publico_token,
            "url": f"/p/reforma/{cfg.link_publico_token}"}


@router.delete("/link-publico")
def revogar_link_publico(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Revoga o link público (o contador deixa de acessar)."""
    cfg = _get_or_create(db)
    cfg.link_publico_token = None
    db.commit()
    return {"ok": True}
