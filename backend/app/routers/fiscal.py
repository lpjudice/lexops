"""Router /fiscal — emissão e gestão de NFS-e."""
from __future__ import annotations

import uuid
import logging
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.nota_fiscal import NotaFiscal
from app.models.financeiro import Honorario, Recebimento
from app.models.cliente import Cliente
from app.schemas.nota_fiscal import (
    CancelarNFSeIn,
    EmitirNFSeIn,
    NotaFiscalOut,
    NotaFiscalResumo,
    PreFillNFSeOut,
)
from app.services.nfse.dps_builder import (
    DadosDPS,
    EnderecoTomador,
    Retencoes,
    Tomador,
    CTN_ADVOCACIA,
)
from app.services.nfse.emitter import (
    cancelar_nfse,
    consultar_parametros_municipio,
    emitir_nfse,
)

router = APIRouter(prefix="/fiscal", tags=["fiscal"])
log = logging.getLogger(__name__)

BRT = timezone(timedelta(hours=-3))


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _proximo_numero_dps(db: Session) -> int:
    ultimo = (
        db.query(NotaFiscal.numero_dps)
        .filter(NotaFiscal.numero_dps.isnot(None))
        .order_by(NotaFiscal.numero_dps.desc())
        .first()
    )
    return (ultimo[0] or 0) + 1


def _descricao_auto(honorario: Honorario) -> str:
    """Gera descrição da NFS-e a partir do honorário."""
    partes = ["Honorários advocatícios"]
    if honorario.processo:
        proc = honorario.processo
        if proc.numero_cnj:
            partes.append(f"referentes ao Processo nº {proc.numero_cnj}")
        if proc.tribunal:
            partes.append(f"— {proc.tribunal}")
    elif honorario.descricao:
        partes.append(f"— {honorario.descricao}")
    return " ".join(partes)


def _nf_to_out(nf: NotaFiscal) -> NotaFiscalOut:
    return NotaFiscalOut.model_validate(nf)


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/notas", response_model=list[NotaFiscalResumo])
def listar_notas(
    status: Optional[str] = Query(None),
    competencia: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(NotaFiscal).order_by(NotaFiscal.created_at.desc())
    if status:
        q = q.filter(NotaFiscal.status == status)
    if competencia:
        q = q.filter(NotaFiscal.competencia == competencia)
    return [NotaFiscalResumo.model_validate(nf) for nf in q.all()]


@router.get("/notas/{nf_id}", response_model=NotaFiscalOut)
def obter_nota(
    nf_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    nf = db.query(NotaFiscal).filter(NotaFiscal.id == nf_id).first()
    if not nf:
        raise HTTPException(404, "Nota fiscal não encontrada")
    return _nf_to_out(nf)


@router.post("/notas", response_model=NotaFiscalOut, status_code=201)
def emitir_nota(
    body: EmitirNFSeIn,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    numero_dps = _proximo_numero_dps(db)

    # Monta objetos do builder
    endereco = None
    if body.tomador_endereco:
        e = body.tomador_endereco
        endereco = EnderecoTomador(
            logradouro=e.logradouro,
            numero=e.numero,
            bairro=e.bairro,
            cod_municipio=e.cod_municipio,
            cep=e.cep,
            complemento=e.complemento,
        )

    tomador = Tomador(
        nome=body.tomador_nome,
        cpf_cnpj=body.tomador_cpf_cnpj,
        email=body.tomador_email or "",
        telefone=body.tomador_telefone or "",
        endereco=endereco,
    )

    retencoes = Retencoes(
        ir=body.retencao_ir,
        inss=body.retencao_inss,
        csll=body.retencao_csll,
        cofins=body.retencao_cofins,
        pis=body.retencao_pis,
    )

    from app.config import settings
    dados = DadosDPS(
        serie=body.serie,
        numero=numero_dps,
        competencia=body.competencia,
        tomador=tomador,
        descricao_servico=body.descricao_servico,
        cod_tributacao_nacional=body.cod_tributacao_nacional,
        valor_servicos=body.valor_servicos,
        retencoes=retencoes,
        ibs_valor=body.ibs_valor,
        cbs_valor=body.cbs_valor,
        ambiente=settings.nfse_ambiente,
        data_emissao=datetime.now(tz=BRT),
    )

    resultado = emitir_nfse(dados)

    # Persiste a NF independentemente do resultado (para auditoria)
    nf = NotaFiscal(
        numero_nfse=resultado.numero_nfse,
        chave_acesso=resultado.chave_acesso,
        serie=body.serie,
        numero_dps=numero_dps,
        competencia=body.competencia,
        data_emissao=date.today() if resultado.sucesso else None,
        tomador_cpf_cnpj=body.tomador_cpf_cnpj,
        tomador_nome=body.tomador_nome,
        tomador_email=body.tomador_email,
        tomador_telefone=body.tomador_telefone,
        tomador_logradouro=body.tomador_endereco.logradouro if body.tomador_endereco else None,
        tomador_numero=body.tomador_endereco.numero if body.tomador_endereco else None,
        tomador_complemento=body.tomador_endereco.complemento if body.tomador_endereco else None,
        tomador_bairro=body.tomador_endereco.bairro if body.tomador_endereco else None,
        tomador_cod_municipio=body.tomador_endereco.cod_municipio if body.tomador_endereco else None,
        tomador_cep=body.tomador_endereco.cep if body.tomador_endereco else None,
        cod_tributacao_nacional=body.cod_tributacao_nacional,
        descricao_servico=body.descricao_servico,
        valor_servicos=float(body.valor_servicos),
        retencao_ir=float(body.retencao_ir) if body.retencao_ir else None,
        retencao_inss=float(body.retencao_inss) if body.retencao_inss else None,
        retencao_csll=float(body.retencao_csll) if body.retencao_csll else None,
        retencao_cofins=float(body.retencao_cofins) if body.retencao_cofins else None,
        retencao_pis=float(body.retencao_pis) if body.retencao_pis else None,
        ibs_valor=float(body.ibs_valor) if body.ibs_valor else None,
        cbs_valor=float(body.cbs_valor) if body.cbs_valor else None,
        status="emitida" if resultado.sucesso else "erro",
        erro_mensagem=resultado.erro_mensagem,
        xml_nfse=resultado.xml_nfse,
        honorario_id=body.honorario_id,
        recebimento_id=body.recebimento_id,
    )
    db.add(nf)
    db.commit()
    db.refresh(nf)

    if not resultado.sucesso:
        log.error("Falha na emissão NFS-e: %s — %s", resultado.erro_codigo, resultado.erro_mensagem)
        raise HTTPException(
            422,
            detail={
                "message": "Falha na emissão junto ao ADN",
                "codigo": resultado.erro_codigo,
                "detalhe": resultado.erro_mensagem,
                "nf_id": str(nf.id),
            },
        )

    return _nf_to_out(nf)


@router.post("/notas/{nf_id}/cancelar", response_model=NotaFiscalOut)
def cancelar_nota(
    nf_id: uuid.UUID,
    body: CancelarNFSeIn,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    nf = db.query(NotaFiscal).filter(NotaFiscal.id == nf_id).first()
    if not nf:
        raise HTTPException(404, "Nota fiscal não encontrada")
    if nf.status != "emitida":
        raise HTTPException(400, f"Não é possível cancelar NFS-e com status '{nf.status}'")
    if not nf.chave_acesso:
        raise HTTPException(400, "NFS-e sem chave de acesso — não pode ser cancelada via API")

    resultado = cancelar_nfse(nf.chave_acesso, body.motivo)
    if not resultado.sucesso:
        raise HTTPException(422, detail=resultado.erro_mensagem)

    nf.status = "cancelada"
    db.commit()
    db.refresh(nf)
    return _nf_to_out(nf)


@router.get("/notas/prefill/honorario/{honorario_id}", response_model=PreFillNFSeOut)
def prefill_de_honorario(
    honorario_id: uuid.UUID,
    recebimento_id: Optional[uuid.UUID] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Retorna dados pré-preenchidos para emissão de NFS-e a partir de um honorário."""
    honorario = db.query(Honorario).filter(Honorario.id == honorario_id).first()
    if not honorario:
        raise HTTPException(404, "Honorário não encontrado")

    recebimento = None
    valor = float(honorario.valor_total)
    competencia = datetime.now(tz=BRT).strftime("%Y-%m")

    if recebimento_id:
        recebimento = db.query(Recebimento).filter(Recebimento.id == recebimento_id).first()
        if recebimento:
            valor = float(recebimento.valor)
            competencia = recebimento.data_recebimento.strftime("%Y-%m")

    cliente = honorario.cliente
    return PreFillNFSeOut(
        competencia=competencia,
        tomador_cpf_cnpj=getattr(cliente, "cpf_cnpj", None),
        tomador_nome=cliente.nome if cliente else honorario.descricao,
        tomador_email=getattr(cliente, "email", None),
        valor_servicos=valor,
        descricao_servico=_descricao_auto(honorario),
        honorario_id=honorario_id,
        recebimento_id=recebimento_id,
    )


@router.get("/parametros-municipais")
def parametros_municipais(_=Depends(get_current_user)):
    """Consulta parametrizações de Vitória/ES na API nacional (alíquotas, etc.)."""
    dados = consultar_parametros_municipio("3205309")
    if dados is None:
        raise HTTPException(503, "Não foi possível consultar os parâmetros municipais")
    return dados
