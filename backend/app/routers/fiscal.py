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


def _upsert_pagante_de_nf(db: Session, nf: NotaFiscal, body) -> None:
    """Cria ou atualiza um Pagante a partir do tomador da NF (chave: cpf_cnpj).

    Mantém a aba Pagantes sempre populada com quem recebeu NF, mesmo que não
    seja cliente cadastrado. Atualiza dados básicos (email/endereço) se vierem
    preenchidos na NF.
    """
    from app.models.pagante import Pagante
    doc = (nf.tomador_cpf_cnpj or "").strip()
    if not doc and not nf.tomador_nome:
        return

    pag = None
    if doc:
        pag = db.query(Pagante).filter(Pagante.cpf_cnpj == doc).first()
    if not pag:
        # fallback por nome quando não há documento
        pag = db.query(Pagante).filter(
            Pagante.cpf_cnpj.is_(None), Pagante.nome == nf.tomador_nome
        ).first() if not doc else None

    end = getattr(body, "tomador_endereco", None)
    if pag is None:
        pag = Pagante(
            nome=nf.tomador_nome,
            cpf_cnpj=doc or None,
            email=nf.tomador_email,
            telefone=getattr(body, "tomador_telefone", None),
            logradouro=end.logradouro if end else None,
            numero=end.numero if end else None,
            complemento=end.complemento if end else None,
            bairro=end.bairro if end else None,
            cod_municipio=end.cod_municipio if end else None,
            cep=end.cep if end else None,
            cliente_id=nf.cliente_id,
            origem="nf",
        )
        db.add(pag)
    else:
        # Atualiza campos vazios com o que veio na NF (não sobrescreve dados manuais)
        pag.nome = nf.tomador_nome or pag.nome
        if nf.tomador_email and not pag.email:
            pag.email = nf.tomador_email
        if nf.cliente_id and not pag.cliente_id:
            pag.cliente_id = nf.cliente_id
        if end:
            pag.logradouro = pag.logradouro or end.logradouro
            pag.numero = pag.numero or end.numero
            pag.bairro = pag.bairro or end.bairro
            pag.cep = pag.cep or end.cep
            pag.cod_municipio = pag.cod_municipio or end.cod_municipio
            pag.complemento = pag.complemento or end.complemento
    db.commit()


def _nf_to_out(nf: NotaFiscal) -> NotaFiscalOut:
    import os
    out = NotaFiscalOut.model_validate(nf)
    out.tem_pdf = bool(nf.pdf_path and os.path.exists(nf.pdf_path))
    if nf.chave_acesso:
        out.consulta_publica_url = (
            f"https://www.nfse.gov.br/consultapublica?chaveAcesso={nf.chave_acesso}"
        )
    # Monta EnderecoIn a partir dos campos individuais
    if nf.tomador_logradouro or nf.tomador_cep:
        from app.schemas.nota_fiscal import EnderecoIn
        out.tomador_endereco = EnderecoIn(
            logradouro=nf.tomador_logradouro,
            numero=nf.tomador_numero,
            bairro=nf.tomador_bairro,
            cod_municipio=nf.tomador_cod_municipio,
            cep=nf.tomador_cep,
            complemento=nf.tomador_complemento,
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
    # Competência retroativa? (mês anterior ao corrente)
    mes_atual = datetime.now(tz=BRT).strftime("%Y-%m")
    retroativa = body.competencia < mes_atual

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

    # Auto-cálculo de IBS/CBS baseado no estágio da reforma — se o usuário não informou
    ibs_v = body.ibs_valor
    cbs_v = body.cbs_valor
    if cfg and (cfg.estagio_reforma or "pre_reforma") != "pre_reforma":
        if ibs_v is None and cfg.ibs_pct:
            from decimal import Decimal as _D
            ibs_v = _D(str(body.valor_servicos)) * _D(str(cfg.ibs_pct)) / _D("100")
        if cbs_v is None and cfg.cbs_pct:
            from decimal import Decimal as _D
            cbs_v = _D(str(body.valor_servicos)) * _D(str(cfg.cbs_pct)) / _D("100")

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
        ibs_valor=ibs_v,
        cbs_valor=cbs_v,
        ambiente=ambiente,
        data_emissao=datetime.now(tz=BRT),
        chave_substituida=body.substitui_chave,
        motivo_substituicao=body.motivo_substituicao,
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
        ibs_valor=float(ibs_v) if ibs_v else None,
        cbs_valor=float(cbs_v) if cbs_v else None,
        status="emitida" if resultado.sucesso else "erro",
        erro_mensagem=resultado.erro_mensagem,
        xml_nfse=resultado.xml_nfse,
        honorario_id=body.honorario_id,
        recebimento_id=body.recebimento_id,
        contrato_id=body.contrato_id,
        cliente_id=body.cliente_id,
        processo_id=body.processo_id,
        cliente_compensacao_id=body.cliente_compensacao_id,
        contrato_compensacao_id=body.contrato_compensacao_id,
        honorario_compensacao_id=body.honorario_compensacao_id,
        valor_compensacao=float(body.valor_compensacao) if body.valor_compensacao else None,
        ambiente=ambiente,
        retroativa=retroativa,
        substitui_chave=body.substitui_chave,
    )
    db.add(nf)
    db.commit()
    db.refresh(nf)

    # Substituição: marca a NF antiga como substituída pela nova
    if resultado.sucesso and body.substitui_chave:
        try:
            antiga = (db.query(NotaFiscal)
                      .filter(NotaFiscal.chave_acesso == body.substitui_chave).first())
            if antiga:
                antiga.status = "substituida"
                antiga.substituida_por = nf.chave_acesso
                db.commit()
                log.info(f"NF {antiga.numero_nfse} marcada como substituída por {nf.numero_nfse}")
        except Exception as exc:
            log.warning("Falha ao marcar NF substituída: %s", exc)

    # Upsert do pagante (tomador vira/atualiza um registro persistente de Pagante)
    if resultado.sucesso:
        try:
            _upsert_pagante_de_nf(db, nf, body)
        except Exception as exc:
            log.warning("Upsert pagante falhou: %s", exc)

    # Sucesso: gera/baixa e salva o PDF da DANFSe
    if resultado.sucesso and nf.chave_acesso:
        try:
            from app.services.nfse.emitter import baixar_danfse
            pdf = baixar_danfse(nf.chave_acesso)
            if not pdf and (resultado.xml_nfse or nf.xml_nfse):
                from app.services.nfse.danfse_pdf import gerar_danfse_pdf
                pdf = gerar_danfse_pdf(resultado.xml_nfse or nf.xml_nfse, nf.chave_acesso,
                                       (cfg.danfse_prefixo_numero if cfg else "") or "",
                                       float(cfg.carga_media_pct) if cfg and cfg.carga_media_pct else 16.33)
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
                # Envia a NFS-e ao tomador por e-mail (cc master) — só produção
                if ambiente == 1 and nf.tomador_email:
                    try:
                        from app.services.nfse.email_nota_cliente import enviar_nf_ao_cliente
                        master = cfg.email_master if cfg else None
                        enviar_nf_ao_cliente(nf, pdf, master)
                    except Exception as exc:
                        log.warning("Envio NF ao cliente: %s", exc)
        except Exception as exc:
            log.warning("Falha ao gerar/baixar DANFSe: %s", exc)

    if not resultado.sucesso:
        log.error("Falha na emissão NFS-e: [%s] %s", resultado.erro_codigo, resultado.erro_mensagem)
        detalhe = resultado.erro_mensagem
        # E0014: a DPS já gerou uma NFS-e (envio anterior). NÃO re-emitir — sincronizar.
        if (resultado.erro_codigo or "").upper() == "E0014" or "já existe em uma NFS-e" in (detalhe or ""):
            detalhe = (
                "Esta DPS já gerou uma NFS-e em um envio anterior (provável queda de conexão "
                "após o Sefin processar). NÃO emita novamente — clique em 'Sincronizar' para "
                "trazer a nota já gerada. Detalhe técnico: " + (detalhe or "")
            )
        raise HTTPException(422, detail={
            "message": "Falha na emissão junto ao ADN",
            "codigo": resultado.erro_codigo,
            "detalhe": detalhe,
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
    filtros = [
        NotaFiscal.cliente_id == cliente_id,
        # Compensação: NF emitida contra terceiro, mas crédito é deste cliente (beneficiário)
        NotaFiscal.cliente_compensacao_id == cliente_id,
    ]
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

    # Sempre regenera do XML (garante layout atual: pagamento, prefixo). Fallback no gov/cache.
    pdf = None
    if nf.xml_nfse:
        try:
            from app.services.nfse.danfse_pdf import gerar_danfse_pdf
            from app.models.config_fiscal import ConfigFiscal
            _cfg = db.query(ConfigFiscal).filter(ConfigFiscal.id == 1).first()
            _pref = (_cfg.danfse_prefixo_numero if _cfg else "") or ""
            _carga = float(_cfg.carga_media_pct) if _cfg and _cfg.carga_media_pct else 16.33
            pdf = gerar_danfse_pdf(nf.xml_nfse, nf.chave_acesso, _pref, _carga)
        except Exception as exc:
            log.error("Falha ao gerar DANFSe PDF: %s", exc)
    if not pdf:
        pdf = baixar_danfse(nf.chave_acesso)
    if not pdf and nf.pdf_path and os.path.exists(nf.pdf_path):
        return FileResponse(nf.pdf_path, media_type="application/pdf",
                            filename=f"NFSe_{nf.numero_nfse or nf.chave_acesso}.pdf")
    if not pdf:
        raise HTTPException(503, "Não foi possível obter nem gerar o PDF da NFS-e.")
    pasta = "/app/backend/uploads/nfse"
    os.makedirs(pasta, exist_ok=True)
    caminho = f"{pasta}/{nf.chave_acesso}.pdf"
    with open(caminho, "wb") as f:
        f.write(pdf)
    nf.pdf_path = caminho
    db.commit()
    return FileResponse(caminho, media_type="application/pdf",
                        filename=f"NFSe_{nf.numero_nfse or nf.chave_acesso}.pdf")


def _analise_cancelamento(nf) -> dict:
    """Implicações legais do cancelamento conforme o momento (ISS/DAS e prazo municipal).
    Vitória/ES: cancelamento no sistema nacional; após o recolhimento do ISS, o
    cancelamento gera crédito/retificação do PGDAS-D."""
    from datetime import date
    hoje = date.today()
    alertas = []
    nivel = "ok"
    comp = nf.competencia or hoje.strftime("%Y-%m")
    ano, mes = int(comp[:4]), int(comp[5:7])
    # Vencimento do DAS = dia 20 do mês seguinte à competência
    venc_ano, venc_mes = (ano, mes + 1) if mes < 12 else (ano + 1, 1)
    venc_das = date(venc_ano, venc_mes, 20)
    mesmo_mes = (hoje.year == ano and hoje.month == mes)

    if mesmo_mes:
        alertas.append({"nivel": "ok", "titulo": "Dentro da competência",
                        "detalhe": "Cancelamento simples — o ISS ainda não foi apurado/recolhido nesta competência."})
    elif hoje <= venc_das:
        nivel = "atencao"
        alertas.append({"nivel": "atencao", "titulo": "DAS ainda não vencido",
                        "detalhe": f"Cancele ANTES de gerar/pagar o DAS (vencimento {venc_das.strftime('%d/%m/%Y')}) "
                                   f"para não recolher ISS sobre uma nota cancelada."})
    else:
        nivel = "alerta"
        alertas.append({"nivel": "alerta", "titulo": "ISS provavelmente já recolhido",
                        "detalhe": f"O DAS da competência {comp} venceu em {venc_das.strftime('%d/%m/%Y')}. "
                                   f"O cancelamento exige RETIFICAÇÃO do PGDAS-D; a diferença vira crédito a "
                                   f"compensar e a retificação pode gerar multa/juros se houver imposto a pagar. "
                                   f"Alinhe com o contador antes."})

    if nf.pago:
        nivel = "alerta"
        alertas.append({"nivel": "alerta", "titulo": "Nota marcada como paga",
                        "detalhe": "Há recebimento lançado no Financeiro. Cancelar a NF irá estornar esse "
                                   "recebimento — verifique se o valor foi de fato devolvido ao cliente."})

    alertas.append({"nivel": "info", "titulo": "Substituição vs. cancelamento",
                    "detalhe": "Se o objetivo é corrigir dados (valor, tomador, descrição), prefira emitir uma "
                               "nota de SUBSTITUIÇÃO em vez de cancelar e reemitir."})
    return {"nivel": nivel, "pode_cancelar": True, "vencimento_das": venc_das.isoformat(),
            "alertas": alertas}


@router.get("/notas/{nf_id}/cancelamento-analise")
def cancelamento_analise(nf_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(get_current_user)):
    nf = db.query(NotaFiscal).filter(NotaFiscal.id == nf_id).first()
    if not nf:
        raise HTTPException(404, "Nota fiscal não encontrada")
    return _analise_cancelamento(nf)


@router.post("/notas/{nf_id}/cancelar", response_model=NotaFiscalOut)
def cancelar_nota(
    nf_id: uuid.UUID,
    body: CancelarNFSeIn,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    import logging
    log = logging.getLogger(__name__)

    nf = db.query(NotaFiscal).filter(NotaFiscal.id == nf_id).first()
    if not nf:
        raise HTTPException(404, "Nota fiscal não encontrada")
    if nf.status != "emitida":
        raise HTTPException(400, f"Não é possível cancelar NFS-e com status '{nf.status}'")
    if not nf.chave_acesso:
        raise HTTPException(400, "NFS-e sem chave de acesso")

    log.info(f"Cancelando NF {nf.numero_nfse} (chave={nf.chave_acesso}, motivo={body.motivo[:50]}...)")
    resultado = cancelar_nfse(nf.chave_acesso, body.motivo)
    if not resultado.sucesso:
        log.error(f"Falha cancelamento: {resultado.erro_mensagem}")
        raise HTTPException(422, detail=resultado.erro_mensagem)

    log.info(f"Cancelamento bem-sucedido para NF {nf.numero_nfse}")
    nf.status = "cancelada"
    # Estorna o recebimento no Financeiro, se a NF estava marcada como paga
    if nf.pago and nf.honorario_id:
        from app.models.financeiro import Recebimento, Honorario
        marca = f"[NF {nf.numero_nfse or nf.chave_acesso}]"
        rec = (db.query(Recebimento)
               .filter(Recebimento.honorario_id == nf.honorario_id,
                       Recebimento.observacao.like(f"%{marca}%")).first())
        if rec:
            db.delete(rec)
            log.info(f"Recebimento estornado: {rec.id}")
        hon = db.query(Honorario).filter(Honorario.id == nf.honorario_id).first()
        if hon:
            db.flush()
            hon.status = "pago" if hon.saldo_pendente <= 0 else ("parcial" if hon.total_recebido > 0 else "pendente")
    nf.pago = False
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
    aliq_iss = Decimal(str(cfg.aliquota_iss)) if cfg and cfg.aliquota_iss else Decimal("0")
    carga_media = Decimal(str(cfg.carga_media_pct)) if cfg and cfg.carga_media_pct else Decimal("16.33")
    rbt12 = Decimal(str(cfg.rbt12)) if cfg and cfg.rbt12 else None
    das = (receita * aliq / 100).quantize(Decimal("0.01"))
    faixa = faixa_de(rbt12) if rbt12 else 0

    # CARGA TRIBUTÁRIA por tributo (efetivo sobre a receita), não composição do DAS:
    #   ISS = alíquota ISS do município (ex.: 2%)
    #   Federais = (alíq. efetiva do Simples − ISS) rateado pelas proporções federais do Anexo IV
    rep = repart_pct(faixa)  # {IRPJ,CSLL,COFINS,PIS,ISS} em % do DAS
    fed_keys = ["IRPJ", "CSLL", "COFINS", "PIS"]
    soma_fed = sum(Decimal(str(rep[k])) for k in fed_keys) or Decimal("1")
    aliq_fed = max(aliq - aliq_iss, Decimal("0"))
    quebra_pct = {"ISS": aliq_iss}
    for k in fed_keys:
        quebra_pct[k] = (aliq_fed * Decimal(str(rep[k])) / soma_fed).quantize(Decimal("0.01"))
    quebra = {k: (receita * p / 100).quantize(Decimal("0.01")) for k, p in quebra_pct.items()}
    carga = aliq  # carga efetiva do DAS sobre a receita

    # Progresso até o limite da faixa atual
    limite = ANEXO_IV_FAIXAS[faixa][0]
    piso = ANEXO_IV_FAIXAS[faixa - 1][0] if faixa > 0 else Decimal("0")
    progresso = None
    if rbt12:
        progresso = float(((rbt12 - piso) / (limite - piso) * 100).quantize(Decimal("0.1")))

    # Reforma tributária (IBS/CBS + transição ISS)
    from app.services.nfse.visao_fiscal import projecao_reforma
    partes = competencia.split("-")
    ano = int(partes[0])
    mes = int(partes[1]) if len(partes) > 1 else 1
    ibs_pct = Decimal(str(cfg.ibs_pct)) if cfg and cfg.ibs_pct else Decimal("0")
    cbs_pct = Decimal(str(cfg.cbs_pct)) if cfg and cfg.cbs_pct else Decimal("0")
    piloto = bool(cfg and cfg.piloto_ibscbs)
    reforma = transicao_reforma(ano, receita, ibs_pct, cbs_pct, piloto, mes)
    reforma["projecao"] = projecao_reforma(receita, ibs_pct, cbs_pct)

    alertas = gerar_alertas(rbt12)
    if reforma.get("cbs_destaque_obrigatorio"):
        alertas.insert(0, {
            "nivel": "alerta",
            "titulo": "CBS — destaque obrigatório (Reforma Tributária)",
            "detalhe": (f"A partir de ago/2026 a CBS ({reforma['cbs_aliq']}% já com a redução "
                        f"de 30% da advocacia) deve ser destacada na nota, ainda que compensável "
                        f"com PIS/COFINS em 2026. Confirme o enquadramento com o contador."),
        })

    return {
        "competencia": competencia,
        "receita_mes": float(receita),
        "qtd_notas": qtd,
        "aliquota_efetiva": float(aliq),
        "das_estimado": float(das),
        "quebra_tributos": {k: float(v) for k, v in quebra.items()},
        # % efetivo de cada tributo sobre a receita (ISS = alíquota do município)
        "quebra_tributos_pct": {k: float(p) for k, p in quebra_pct.items()},
        "progresso_faixa_pct": progresso,
        "reforma": reforma,
        "retencoes_sofridas": float(ret_total),
        "das_liquido_estimado": float(max(das - ret_total, Decimal("0"))),
        "carga_tributaria_pct": float(carga),
        # Carga média total (IBPT / Lei 12.741) — informativa, vai na nota
        "carga_media_pct": float(carga_media),
        "carga_media_valor": float((receita * carga_media / 100).quantize(Decimal("0.01"))),
        "rbt12": float(rbt12) if rbt12 else None,
        "faixa_simples": faixa + 1 if rbt12 else None,
        "limite_faixa": float(ANEXO_IV_FAIXAS[faixa][0]) if rbt12 else None,
        "alertas": alertas,
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
    destinatario: Optional[str] = Query(None, description="Override do destinatário (teste)"),
    parcial: bool = Query(False, description="True = corta no dia atual (mes ainda nao fechado)"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Envia o relatório ao contador agora (manual)."""
    from app.services.nfse.relatorio_contador import enviar_relatorio
    resultado = enviar_relatorio(db, mes, destinatario_override=destinatario, parcial=parcial)
    if not resultado.get("enviado"):
        raise HTTPException(422, detail=resultado.get("motivo", "Falha ao enviar"))
    return resultado


@router.get("/relatorio/historico")
def historico_relatorios(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Histórico de relatórios enviados + texto do próximo envio automático."""
    from app.models.relatorio_fiscal_log import RelatorioFiscalLog
    from app.models.config_fiscal import ConfigFiscal
    from datetime import timedelta as _td

    logs = (db.query(RelatorioFiscalLog)
            .order_by(RelatorioFiscalLog.enviado_em.desc()).limit(50).all())
    out = []
    for r in logs:
        gmail = (f"https://mail.google.com/mail/u/0/#all/{r.gmail_message_id}"
                 if r.gmail_message_id else None)
        out.append({
            "id": str(r.id), "competencia": r.competencia,
            "enviado_em": r.enviado_em.isoformat() if r.enviado_em else None,
            "destinatarios": r.destinatarios, "cc": r.cc,
            "nf_qtd": r.nf_qtd, "anexos": r.anexos, "status": r.status,
            "gmail_link": gmail, "drive_pasta_link": r.drive_pasta_link,
        })

    # Próximo envio automático
    cfg = db.query(ConfigFiscal).filter(ConfigFiscal.id == 1).first()
    proximo = None
    if cfg and cfg.enviar_relatorio_auto:
        hoje = datetime.now(tz=BRT).date()
        dia = cfg.dia_envio_relatorio or 1
        if hoje.day < dia:
            prox = hoje.replace(day=dia)
        else:
            m = hoje.replace(day=1) + _td(days=32)
            prox = m.replace(day=dia)
        ref = (prox.replace(day=1) - _td(days=1)).strftime("%m/%Y")
        proximo = {"data": prox.strftime("%d/%m/%Y"), "competencia_ref": ref,
                   "destinatarios": cfg.emails_contador or []}
    return {"historico": out, "proximo_envio": proximo}


@router.patch("/notas/{nf_id}/pago", response_model=NotaFiscalOut)
def marcar_pago(
    nf_id: uuid.UUID,
    pago: bool = Query(True),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Marca/desmarca a NF como paga."""
    from datetime import date as _date
    nf = db.query(NotaFiscal).filter(NotaFiscal.id == nf_id).first()
    if not nf:
        raise HTTPException(404, "Nota fiscal não encontrada")
    nf.pago = pago
    nf.data_pagamento = _date.today() if pago else None

    # Reflete no Financeiro — INTEGRAÇÃO CROSS-MENU
    # (a) NF direta ao cliente: cria recebimento no honorario_id
    # (b) NF com compensação: cria recebimento no honorario_compensacao_id
    #     (pagamento por terceiro — ex.: NF contra Lucas quita recebível da Mangrove)
    # Aparece em: Financeiro (recebíveis), Reembolsos (se há caixa), Lançamentos
    if nf.honorario_id or nf.honorario_compensacao_id:
        from app.models.financeiro import Recebimento, Honorario
        marca = f"[NF {nf.numero_nfse or nf.chave_acesso}]"
        valor_rec = float(nf.valor_compensacao or nf.valor_servicos)

        # Detecta qual honorário recebe o crédito
        if nf.honorario_compensacao_id:
            # Compensação: crédito vai para o honorário do beneficiário (reduz saldo devedor dele)
            hon_id = nf.honorario_compensacao_id
            obs = f"Pagamento via NFS-e {marca} (tomador: {nf.tomador_nome})"
        else:
            # Caso padrão: recebimento vai para o honorario_id da NF
            hon_id = nf.honorario_id
            obs = f"Pagamento da NFS-e {marca}"

        if hon_id:
            existente = (db.query(Recebimento)
                         .filter(Recebimento.honorario_id == hon_id,
                                 Recebimento.observacao.like(f"%{marca}%")).first())
            if pago and not existente:
                db.add(Recebimento(
                    honorario_id=hon_id, valor=valor_rec,
                    data_recebimento=_date.today(), forma_pagamento="pix",
                    observacao=obs,
                ))
            elif not pago and existente:
                db.delete(existente)
            # Atualiza status do honorário (pago/parcial/pendente)
            hon = db.query(Honorario).filter(Honorario.id == hon_id).first()
            if hon:
                db.flush()
                if hon.saldo_pendente <= 0:
                    hon.status = "pago"
                elif hon.total_recebido > 0:
                    hon.status = "parcial"
                else:
                    hon.status = "pendente"

    db.commit()
    db.refresh(nf)
    return _nf_to_out(nf)


@router.post("/dfe/sincronizar")
def sincronizar_dfe_gov(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Reconcilia notas do governo (DFe) — inclusive emitidas direto no portal."""
    from app.services.nfse.dfe_sync import sincronizar_dfe
    return sincronizar_dfe(db)


@router.delete("/notas/erros")
def deletar_notas_erro(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Remove notas com status 'erro' (limpeza de testes que não emitiram)."""
    qs = db.query(NotaFiscal).filter(NotaFiscal.status == "erro").all()
    n = len(qs)
    for nf in qs:
        db.delete(nf)
    db.commit()
    return {"removidas": n}


@router.patch("/notas/{nf_id}/vinculos", response_model=NotaFiscalOut)
def vincular_nota(
    nf_id: uuid.UUID,
    processo_id: Optional[uuid.UUID] = Query(None),
    processos_ids: Optional[str] = Query(None, description="IDs separados por vírgula (multi)"),
    contrato_id: Optional[uuid.UUID] = Query(None),
    cliente_id: Optional[uuid.UUID] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Vincula a NF (já emitida) a processo(s)/contrato/cliente — info interna."""
    nf = db.query(NotaFiscal).filter(NotaFiscal.id == nf_id).first()
    if not nf:
        raise HTTPException(404, "Nota fiscal não encontrada")
    if processos_ids is not None:
        ids = [p.strip() for p in processos_ids.split(",") if p.strip()]
        nf.processos_ids = ids
        nf.processo_id = ids[0] if ids else None  # primário p/ compatibilidade
    elif processo_id is not None:
        nf.processo_id = processo_id
        nf.processos_ids = [str(processo_id)]
    if contrato_id is not None:
        nf.contrato_id = contrato_id
    if cliente_id is not None:
        nf.cliente_id = cliente_id
    db.commit()
    db.refresh(nf)
    return _nf_to_out(nf)


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
