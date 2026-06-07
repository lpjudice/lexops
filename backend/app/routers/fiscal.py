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
    CancelarNFSeIn, CodigoTributacaoOut, EmitirNFSeIn,
    NotaFiscalOut, NotaFiscalResumo, OpcaoOut, PreFillNFSeOut,
)
from app.services.nfse.dps_builder import (
    CODIGOS_TRIBUTACAO, NATUREZA_OPERACAO_OPCOES, REG_APURACAO_SN_OPCOES,
    REGIME_TRIBUTARIO_OPCOES, CTN_ADVOCACIA,
    DadosDPS, EnderecoTomador, Intermediario, Retencoes, Tomador,
)
from app.services.nfse.emitter import (
    cancelar_nfse, consultar_parametros_municipio, emitir_nfse,
)

router = APIRouter(prefix="/fiscal", tags=["fiscal"])
log = logging.getLogger(__name__)
BRT = timezone(timedelta(hours=-3))


# ─── Endpoints de referência ──────────────────────────────────────────────────

@router.get("/opcoes/codigos-tributacao", response_model=list[CodigoTributacaoOut])
def listar_codigos_tributacao(_=Depends(get_current_user)):
    return [{"codigo": c, "label": l, "descricao": d} for c, l, d in CODIGOS_TRIBUTACAO]


@router.get("/opcoes/natureza-operacao", response_model=list[OpcaoOut])
def listar_natureza_operacao(_=Depends(get_current_user)):
    return [{"valor": v, "label": l, "descricao": d} for v, l, d in NATUREZA_OPERACAO_OPCOES]


@router.get("/opcoes/regime-tributario", response_model=list[OpcaoOut])
def listar_regime_tributario(_=Depends(get_current_user)):
    return [{"valor": v, "label": l, "descricao": d} for v, l, d in REGIME_TRIBUTARIO_OPCOES]


@router.get("/opcoes/reg-apuracao-sn", response_model=list[OpcaoOut])
def listar_reg_apuracao_sn(_=Depends(get_current_user)):
    return [{"valor": v, "label": l, "descricao": d} for v, l, d in REG_APURACAO_SN_OPCOES]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _proximo_numero_dps(db: Session) -> int:
    ultimo = (
        db.query(NotaFiscal.numero_dps)
        .filter(NotaFiscal.numero_dps.isnot(None))
        .order_by(NotaFiscal.numero_dps.desc())
        .first()
    )
    return (ultimo[0] if ultimo is not None else 0) + 1


def _descricao_auto(honorario: Honorario, tipo_servico: str = "processo") -> str:
    templates = {
        "processo": "Honorários advocatícios",
        "consultoria": "Serviços de consultoria jurídica",
        "planejamento": "Serviços de planejamento jurídico-societário",
        "exito": "Honorários advocatícios de êxito",
    }
    base = templates.get(tipo_servico, "Honorários advocatícios")
    partes = [base]
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
    import os
    out = NotaFiscalOut.model_validate(nf)
    out.tem_pdf = bool(nf.pdf_path and os.path.exists(nf.pdf_path))
    if nf.chave_acesso:
        out.consulta_publica_url = (
            f"https://www.nfse.gov.br/consultapublica?chaveAcesso={nf.chave_acesso}"
        )
    return out


# ─── CRUD de notas ────────────────────────────────────────────────────────────

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


@router.get("/notas/prefill/honorario/{honorario_id}", response_model=PreFillNFSeOut)
def prefill_de_honorario(
    honorario_id: uuid.UUID,
    recebimento_id: Optional[uuid.UUID] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
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
        tomador_cpf_cnpj=_apenas_digitos(getattr(cliente, "cpf_cnpj", "") or ""),
        tomador_nome=cliente.nome if cliente else honorario.descricao,
        tomador_email=getattr(cliente, "email", None),
        tomador_telefone=_apenas_digitos(getattr(cliente, "telefone", "") or ""),
        valor_servicos=valor,
        descricao_servico=_descricao_auto(honorario),
        honorario_id=honorario_id,
        recebimento_id=recebimento_id,
        contrato_id=getattr(honorario, "contrato_id", None),
    )


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
    from app.config import settings
    from app.models.config_fiscal import ConfigFiscal
    from app.services.nfse.documentos import valida_documento

    # Validação de dígito do CPF/CNPJ do tomador (evita rejeição do gov, exceto exterior)
    if not body.tomador_no_exterior:
        ok_doc, tipo_doc = valida_documento(body.tomador_cpf_cnpj)
        if not ok_doc:
            raise HTTPException(422, detail={
                "message": "CPF/CNPJ do tomador inválido",
                "detalhe": f"O documento informado não é um {tipo_doc or 'CPF/CNPJ'} válido. "
                           "Confira os dígitos antes de emitir.",
            })

    cfg = db.query(ConfigFiscal).filter(ConfigFiscal.id == 1).first()
    ambiente = body.ambiente or settings.nfse_ambiente
    numero_dps = _proximo_numero_dps(db)

    endereco = None
    if body.tomador_endereco:
        e = body.tomador_endereco
        endereco = EnderecoTomador(
            logradouro=e.logradouro, numero=e.numero, bairro=e.bairro,
            cod_municipio=e.cod_municipio, cep=e.cep, complemento=e.complemento,
            cod_pais=e.cod_pais,
        )

    tomador = Tomador(
        nome=body.tomador_nome,
        cpf_cnpj=body.tomador_cpf_cnpj,
        email=body.tomador_email or "",
        telefone=body.tomador_telefone or "",
        endereco=endereco,
        no_exterior=body.tomador_no_exterior,
    )

    intermediario = None
    if body.intermediario:
        intermediario = Intermediario(
            nome=body.intermediario.nome,
            cpf_cnpj=body.intermediario.cpf_cnpj,
            inscricao_municipal=body.intermediario.inscricao_municipal,
        )

    retencoes = Retencoes(
        ir=body.retencao_ir, inss=body.retencao_inss, csll=body.retencao_csll,
        cofins=body.retencao_cofins, pis=body.retencao_pis, iss_retido=body.iss_retido,
    )

    dados = DadosDPS(
        serie=body.serie,
        numero=numero_dps,
        competencia=body.competencia,
        tomador=tomador,
        descricao_servico=body.descricao_servico,
        cod_tributacao_nacional=body.cod_tributacao_nacional,
        natureza_operacao=body.natureza_operacao,
        regime_tributario=body.regime_tributario,
        reg_apuracao_sn=body.reg_apuracao_sn,
        valor_servicos=body.valor_servicos,
        retencoes=retencoes,
        intermediario=intermediario,
        ibs_valor=body.ibs_valor,
        cbs_valor=body.cbs_valor,
        ambiente=ambiente,
        data_emissao=datetime.now(tz=BRT),
    )
    # pTotTribSN e alíquota ISS vêm do Config Fiscal (se configurado)
    if cfg:
        from decimal import Decimal as _D
        if cfg.aliquota_efetiva_simples is not None:
            dados.pct_trib_simples = _D(str(cfg.aliquota_efetiva_simples))

    resultado = emitir_nfse(dados)

    # ── Auto-atualiza o cadastro do cliente com dados da NF ───────────────
    _atualizar_cliente_com_dados_nf(db, body)

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
        natureza_operacao=body.natureza_operacao,
        regime_tributario=body.regime_tributario,
        iss_retido=body.iss_retido,
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
        contrato_id=body.contrato_id,
        cliente_id=body.cliente_id,
        processo_id=body.processo_id,
        ambiente=ambiente,
    )
    db.add(nf)
    db.commit()
    db.refresh(nf)

    # Sucesso: gera/baixa e salva o PDF da DANFSe
    if resultado.sucesso and nf.chave_acesso:
        try:
            from app.services.nfse.emitter import baixar_danfse
            pdf = baixar_danfse(nf.chave_acesso)
            if not pdf and (resultado.xml_nfse or nf.xml_nfse):
                from app.services.nfse.danfse_pdf import gerar_danfse_pdf
                pdf = gerar_danfse_pdf(resultado.xml_nfse or nf.xml_nfse, nf.chave_acesso)
            if pdf:
                import os
                pasta = "/app/backend/uploads/nfse"
                os.makedirs(pasta, exist_ok=True)
                caminho = f"{pasta}/{nf.chave_acesso}.pdf"
                with open(caminho, "wb") as f:
                    f.write(pdf)
                nf.pdf_path = caminho
                # Sobe ao Google Drive (cliente/Notas Fiscais + Fiscal/NFe/Mês_Ano)
                # Apenas notas de PRODUÇÃO vão ao Drive (teste não polui o fiscal)
                if ambiente == 1:
                    try:
                        from app.services.nfse.emitter import subir_pdf_drive, _nome_arquivo_nf
                        nome_arq = _nome_arquivo_nf(nf.numero_nfse or nf.chave_acesso,
                                                    nf.competencia, nf.tomador_nome)
                        link = subir_pdf_drive(pdf, nome_arq, nf.tomador_nome, nf.competencia)
                        if link:
                            nf.drive_link = link
                    except Exception as exc:
                        log.warning("Drive upload NF: %s", exc)
                db.commit()
                db.refresh(nf)
        except Exception as exc:
            log.warning("Falha ao gerar/baixar DANFSe: %s", exc)

    if not resultado.sucesso:
        log.error("Falha na emissão NFS-e: [%s] %s", resultado.erro_codigo, resultado.erro_mensagem)
        raise HTTPException(422, detail={
            "message": "Falha na emissão junto ao ADN",
            "codigo": resultado.erro_codigo,
            "detalhe": resultado.erro_mensagem,
            "nf_id": str(nf.id),
        })

    return _nf_to_out(nf)


@router.get("/clientes/{cliente_id}/historico", response_model=list[NotaFiscalResumo])
def historico_nfs_cliente(
    cliente_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Todas as NFS-e emitidas para um cliente (pelo CPF/CNPJ)."""
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")
    from sqlalchemy import or_
    cpf_cnpj = _apenas_digitos(cliente.cpf_cnpj or "")
    filtros = [NotaFiscal.cliente_id == cliente_id]
    if cpf_cnpj:
        filtros.append(NotaFiscal.tomador_cpf_cnpj == cpf_cnpj)
    notas = (
        db.query(NotaFiscal)
        .filter(or_(*filtros))
        .order_by(NotaFiscal.created_at.desc())
        .all()
    )
    return [NotaFiscalResumo.model_validate(n) for n in notas]


@router.get("/notas/{nf_id}/danfse")
def baixar_danfse_pdf(
    nf_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Retorna o PDF da DANFSe. Baixa do gov se ainda não estiver em cache."""
    import os
    from fastapi.responses import FileResponse
    from app.services.nfse.emitter import baixar_danfse

    nf = db.query(NotaFiscal).filter(NotaFiscal.id == nf_id).first()
    if not nf:
        raise HTTPException(404, "Nota fiscal não encontrada")
    if not nf.chave_acesso:
        raise HTTPException(400, "NFS-e sem chave de acesso")

    # Cache em disco
    if not (nf.pdf_path and os.path.exists(nf.pdf_path)):
        # 1) tenta o PDF oficial do gov; 2) gera o nosso a partir do XML
        pdf = baixar_danfse(nf.chave_acesso)
        if not pdf and nf.xml_nfse:
            try:
                from app.services.nfse.danfse_pdf import gerar_danfse_pdf
                pdf = gerar_danfse_pdf(nf.xml_nfse, nf.chave_acesso)
            except Exception as exc:
                log.error("Falha ao gerar DANFSe PDF: %s", exc)
        if not pdf:
            raise HTTPException(503, "Não foi possível obter nem gerar o PDF da NFS-e.")
        pasta = "/app/backend/uploads/nfse"
        os.makedirs(pasta, exist_ok=True)
        caminho = f"{pasta}/{nf.chave_acesso}.pdf"
        with open(caminho, "wb") as f:
            f.write(pdf)
        nf.pdf_path = caminho
        db.commit()

    return FileResponse(
        nf.pdf_path,
        media_type="application/pdf",
        filename=f"NFSe_{nf.numero_nfse or nf.chave_acesso}.pdf",
    )


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
        raise HTTPException(400, "NFS-e sem chave de acesso")

    resultado = cancelar_nfse(nf.chave_acesso, body.motivo)
    if not resultado.sucesso:
        raise HTTPException(422, detail=resultado.erro_mensagem)

    nf.status = "cancelada"
    db.commit()
    db.refresh(nf)
    return _nf_to_out(nf)


@router.post("/notas/backfill-numero")
def backfill_numero(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Recalcula numero_nfse a partir do <nNFSe> do XML salvo (corrige notas antigas)."""
    from app.services.nfse.emitter import _numero_do_xml
    notas = db.query(NotaFiscal).filter(NotaFiscal.xml_nfse.isnot(None)).all()
    corrigidas = 0
    for n in notas:
        num = _numero_do_xml(n.xml_nfse)
        if num and num != n.numero_nfse:
            n.numero_nfse = num
            corrigidas += 1
    db.commit()
    return {"corrigidas": corrigidas, "total": len(notas)}


@router.get("/visao")
def visao_fiscal(
    mes: Optional[str] = Query(None, description="YYYY-MM (default: mês atual)"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Visão fiscal do mês: receita, DAS estimado, quebra por tributo, carga, alertas."""
    from decimal import Decimal
    from sqlalchemy import func as sqlfunc
    from app.models.config_fiscal import ConfigFiscal
    from app.services.nfse.visao_fiscal import (
        faixa_de, quebra_das, gerar_alertas, ANEXO_IV_FAIXAS,
        repart_pct, transicao_reforma,
    )

    competencia = mes or datetime.now(tz=BRT).strftime("%Y-%m")
    cfg = db.query(ConfigFiscal).filter(ConfigFiscal.id == 1).first()

    # Receita do mês = NFs emitidas na competência
    emitidas = (
        db.query(NotaFiscal)
        .filter(NotaFiscal.status == "emitida", NotaFiscal.competencia == competencia,
                NotaFiscal.ambiente == 1)
        .all()
    )
    receita = sum((Decimal(str(n.valor_servicos)) for n in emitidas), Decimal("0"))
    qtd = len(emitidas)
    ret_total = sum(
        (Decimal(str(n.retencao_ir or 0)) + Decimal(str(n.retencao_inss or 0)) +
         Decimal(str(n.retencao_csll or 0)) + Decimal(str(n.retencao_pis or 0)) +
         Decimal(str(n.retencao_cofins or 0)) for n in emitidas),
        Decimal("0"),
    )

    aliq = Decimal(str(cfg.aliquota_efetiva_simples)) if cfg and cfg.aliquota_efetiva_simples else Decimal("0")
    rbt12 = Decimal(str(cfg.rbt12)) if cfg and cfg.rbt12 else None
    das = (receita * aliq / 100).quantize(Decimal("0.01"))
    faixa = faixa_de(rbt12) if rbt12 else 0
    quebra = quebra_das(das, faixa) if das > 0 else {}
    carga = (das / receita * 100).quantize(Decimal("0.01")) if receita > 0 else Decimal("0")

    # Progresso até o limite da faixa atual
    limite = ANEXO_IV_FAIXAS[faixa][0]
    piso = ANEXO_IV_FAIXAS[faixa - 1][0] if faixa > 0 else Decimal("0")
    progresso = None
    if rbt12:
        progresso = float(((rbt12 - piso) / (limite - piso) * 100).quantize(Decimal("0.1")))

    # Reforma tributária (IBS/CBS + transição ISS)
    ano = int(competencia.split("-")[0])
    ibs_pct = Decimal(str(cfg.ibs_pct)) if cfg and cfg.ibs_pct else Decimal("0")
    cbs_pct = Decimal(str(cfg.cbs_pct)) if cfg and cfg.cbs_pct else Decimal("0")
    piloto = bool(cfg and cfg.piloto_ibscbs)
    reforma = transicao_reforma(ano, receita, ibs_pct, cbs_pct, piloto)

    return {
        "competencia": competencia,
        "receita_mes": float(receita),
        "qtd_notas": qtd,
        "aliquota_efetiva": float(aliq),
        "das_estimado": float(das),
        "quebra_tributos": {k: float(v) for k, v in quebra.items()},
        "quebra_tributos_pct": repart_pct(faixa),
        "progresso_faixa_pct": progresso,
        "reforma": reforma,
        "retencoes_sofridas": float(ret_total),
        "das_liquido_estimado": float(max(das - ret_total, Decimal("0"))),
        "carga_tributaria_pct": float(carga),
        "rbt12": float(rbt12) if rbt12 else None,
        "faixa_simples": faixa + 1 if rbt12 else None,
        "limite_faixa": float(ANEXO_IV_FAIXAS[faixa][0]) if rbt12 else None,
        "alertas": gerar_alertas(rbt12),
        "obs": "CPP/INSS patronal não está no DAS do Anexo IV — recolhido à parte sobre a folha.",
    }


@router.get("/alertas")
def alertas_fiscais(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Alertas fiscais para o dashboard."""
    from decimal import Decimal
    from app.models.config_fiscal import ConfigFiscal
    from app.services.nfse.visao_fiscal import gerar_alertas
    cfg = db.query(ConfigFiscal).filter(ConfigFiscal.id == 1).first()
    rbt12 = Decimal(str(cfg.rbt12)) if cfg and cfg.rbt12 else None
    return {"alertas": gerar_alertas(rbt12)}


@router.get("/relatorio/preview")
def preview_relatorio(
    mes: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Prévia do resumo do relatório (sem enviar)."""
    from app.services.nfse.relatorio_contador import coletar_dados
    from datetime import timedelta
    competencia = mes
    if not competencia:
        hoje = datetime.now(tz=BRT).date()
        ant = hoje.replace(day=1) - timedelta(days=1)
        competencia = ant.strftime("%Y-%m")
    d = coletar_dados(db, competencia)
    return {
        "competencia": competencia,
        "nf_qtd": d["nf_qtd"], "nf_total": d["nf_total"],
        "receb_total": d["receb_total"], "reemb_total": d["reemb_total"],
    }


@router.post("/relatorio/enviar")
def enviar_relatorio_agora(
    mes: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Envia o relatório ao contador agora (manual)."""
    from app.services.nfse.relatorio_contador import enviar_relatorio
    resultado = enviar_relatorio(db, mes)
    if not resultado.get("enviado"):
        raise HTTPException(422, detail=resultado.get("motivo", "Falha ao enviar"))
    return resultado


@router.get("/parametros-municipais")
def parametros_municipais(_=Depends(get_current_user)):
    dados = consultar_parametros_municipio("3205309")
    if dados is None:
        raise HTTPException(503, "Não foi possível consultar os parâmetros municipais")
    return dados


# ─── Helpers internos ────────────────────────────────────────────────────────

def _apenas_digitos(v: str) -> str:
    import re
    return re.sub(r"\D", "", v or "")


def _atualizar_cliente_com_dados_nf(db: Session, body: EmitirNFSeIn) -> None:
    """Preenche/atualiza o cadastro do cliente com os dados informados na NF.

    Prioriza o cliente_id (vínculo explícito feito na tela); se ausente, tenta
    achar por CPF/CNPJ. Preenche campos em branco — cpf/cnpj, telefone, email.
    """
    cliente = None
    if body.cliente_id:
        cliente = db.query(Cliente).filter(Cliente.id == body.cliente_id).first()
    if cliente is None:
        cpf_cnpj = _apenas_digitos(body.tomador_cpf_cnpj)
        if cpf_cnpj:
            cliente = db.query(Cliente).filter(
                Cliente.cpf_cnpj.ilike(f"%{cpf_cnpj}%")
            ).first()
    if not cliente:
        return

    cpf_cnpj = _apenas_digitos(body.tomador_cpf_cnpj)
    atualizado = False
    if not _apenas_digitos(cliente.cpf_cnpj or "") and cpf_cnpj:
        cliente.cpf_cnpj = cpf_cnpj
        atualizado = True
    if not (cliente.telefone or "").strip() and body.tomador_telefone:
        cliente.telefone = body.tomador_telefone
        atualizado = True
    if not (cliente.email or "").strip() and body.tomador_email:
        cliente.email = body.tomador_email
        atualizado = True
    if atualizado:
        db.commit()
