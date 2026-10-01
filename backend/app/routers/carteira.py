from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
from typing import List, Optional
from datetime import date, datetime
import json
import base64
from io import BytesIO
import httpx
import os

from app.models.carteira import (
    CarteiraCliente,
    CarteiraDebentureadotEmissao,
    CarteiraDebenturePosicao,
    CarteiraImobiliarioEmpreendimento,
    CarteiraImobiliarioPosicao,
    CarteiraFundoReferencia,
    CarteiraFundoPosicao,
    CarteiraEstrategia,
    CarteiraSocioAval,
    CarteiraUploadDocumento,
)
from app.database import get_db
from app.services.carteira_ia import CarteiraIAService
from app.services.carteira_relatorios import CarteiraRelatoriosService
from app.services.carteira_drive import CarteiraDriveService

router = APIRouter(prefix="/carteira", tags=["carteira"])


# ─────────────────────────────────────────────────────────────────
# CLIENTES
# ─────────────────────────────────────────────────────────────────

@router.get("/clientes")
def listar_clientes(
    skip: int = Query(0),
    limit: int = Query(200),
    ativo: Optional[bool] = None,
    busca: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Lista todos os clientes da carteira"""
    query = db.query(CarteiraCliente)
    if ativo is not None:
        query = query.filter(CarteiraCliente.ativo == ativo)
    if busca:
        query = query.filter(CarteiraCliente.nome.ilike(f"%{busca}%"))

    total = query.count()
    clientes = query.order_by(CarteiraCliente.nome).offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": clientes,
    }


@router.get("/clientes/{cliente_id}")
def obter_cliente(cliente_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes completos de um cliente"""
    cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return cliente


@router.post("/clientes")
def criar_cliente(data: dict, db: Session = Depends(get_db)):
    """Cria novo cliente na carteira"""
    cliente = CarteiraCliente(**data)
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


@router.put("/clientes/{cliente_id}")
def atualizar_cliente(cliente_id: int, data: dict, db: Session = Depends(get_db)):
    """Atualiza dados de um cliente"""
    cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    for key, value in data.items():
        setattr(cliente, key, value)

    db.commit()
    db.refresh(cliente)
    return cliente


# ─────────────────────────────────────────────────────────────────
# DEBÊNTURES - EMISSÕES (Referência)
# ─────────────────────────────────────────────────────────────────

@router.get("/emissoes")
def listar_emissoes(db: Session = Depends(get_db)):
    """Lista todas as emissões de debêntures"""
    emissoes = db.query(CarteiraDebentureadotEmissao).filter(
        CarteiraDebentureadotEmissao.ativo == True
    ).all()
    return emissoes


@router.post("/emissoes")
def criar_emissao(data: dict, db: Session = Depends(get_db)):
    """Cria nova emissão de debênture"""
    emissao = CarteiraDebentureadotEmissao(**data)
    db.add(emissao)
    db.commit()
    db.refresh(emissao)
    return emissao


@router.get("/emissoes/{emissao_id}")
def obter_emissao(emissao_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de uma emissão"""
    emissao = db.query(CarteiraDebentureadotEmissao).filter(
        CarteiraDebentureadotEmissao.id == emissao_id
    ).first()
    if not emissao:
        raise HTTPException(status_code=404, detail="Emissão não encontrada")
    return emissao


# ─────────────────────────────────────────────────────────────────
# DEBÊNTURES - POSIÇÕES DO CLIENTE
# ─────────────────────────────────────────────────────────────────

@router.get("/debentures")
def listar_debentures(
    cliente_id: Optional[int] = None,
    serie: Optional[str] = None,
    status_resgate: Optional[str] = None,
    notificado: Optional[bool] = None,
    skip: int = Query(0),
    limit: int = Query(100),
    db: Session = Depends(get_db),
):
    """Lista posições de debêntures com filtros opcionais"""
    query = db.query(CarteiraDebenturePosicao)

    if cliente_id:
        query = query.filter(CarteiraDebenturePosicao.cliente_id == cliente_id)
    if serie:
        query = query.join(CarteiraDebentureadotEmissao).filter(
            CarteiraDebentureadotEmissao.nome_serie.ilike(f"%{serie}%")
        )
    if status_resgate:
        query = query.filter(CarteiraDebenturePosicao.status_resgate == status_resgate)
    if notificado is not None:
        query = query.filter(CarteiraDebenturePosicao.notificado == notificado)

    total = query.count()
    posicoes = query.offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": posicoes,
    }


@router.post("/debentures")
def criar_debenture(data: dict, db: Session = Depends(get_db)):
    """Cria nova posição de debênture para cliente"""
    posicao = CarteiraDebenturePosicao(**data)
    db.add(posicao)
    db.commit()
    db.refresh(posicao)
    return posicao


@router.get("/debentures/{posicao_id}")
def obter_debenture(posicao_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de uma posição de debênture"""
    posicao = db.query(CarteiraDebenturePosicao).filter(
        CarteiraDebenturePosicao.id == posicao_id
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")
    return posicao


@router.put("/debentures/{posicao_id}")
def atualizar_debenture(posicao_id: int, data: dict, db: Session = Depends(get_db)):
    """Atualiza posição de debênture"""
    posicao = db.query(CarteiraDebenturePosicao).filter(
        CarteiraDebenturePosicao.id == posicao_id
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    for key, value in data.items():
        setattr(posicao, key, value)

    posicao.data_atualizacao = datetime.now()
    db.commit()
    db.refresh(posicao)
    return posicao


@router.delete("/debentures/{posicao_id}")
def deletar_debenture(posicao_id: int, db: Session = Depends(get_db)):
    """Deleta uma posição de debênture"""
    posicao = db.query(CarteiraDebenturePosicao).filter(
        CarteiraDebenturePosicao.id == posicao_id
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    db.delete(posicao)
    db.commit()
    return {"message": "Deletado com sucesso"}


# ─────────────────────────────────────────────────────────────────
# IMOBILIÁRIO - EMPREENDIMENTOS (Referência)
# ─────────────────────────────────────────────────────────────────

@router.get("/empreendimentos")
def listar_empreendimentos(db: Session = Depends(get_db)):
    """Lista todos os empreendimentos"""
    empreendimentos = db.query(CarteiraImobiliarioEmpreendimento).filter(
        CarteiraImobiliarioEmpreendimento.ativo == True
    ).all()
    return empreendimentos


@router.post("/empreendimentos")
def criar_empreendimento(data: dict, db: Session = Depends(get_db)):
    """Cria novo empreendimento"""
    empreendimento = CarteiraImobiliarioEmpreendimento(**data)
    db.add(empreendimento)
    db.commit()
    db.refresh(empreendimento)
    return empreendimento


# ─────────────────────────────────────────────────────────────────
# IMOBILIÁRIO - POSIÇÕES DO CLIENTE
# ─────────────────────────────────────────────────────────────────

@router.get("/imobiliario")
def listar_imobiliario(
    cliente_id: Optional[int] = None,
    tipo_desenvolvimento: Optional[str] = None,
    skip: int = Query(0),
    limit: int = Query(100),
    db: Session = Depends(get_db),
):
    """Lista posições imobiliárias"""
    query = db.query(CarteiraImobiliarioPosicao)

    if cliente_id:
        query = query.filter(CarteiraImobiliarioPosicao.cliente_id == cliente_id)
    if tipo_desenvolvimento:
        query = query.join(CarteiraImobiliarioEmpreendimento).filter(
            CarteiraImobiliarioEmpreendimento.tipo_desenvolvimento == tipo_desenvolvimento
        )

    total = query.count()
    posicoes = query.offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": posicoes,
    }


@router.post("/imobiliario")
def criar_imobiliario(data: dict, db: Session = Depends(get_db)):
    """Cria nova posição imobiliária para cliente"""
    posicao = CarteiraImobiliarioPosicao(**data)
    db.add(posicao)
    db.commit()
    db.refresh(posicao)
    return posicao


@router.get("/imobiliario/{posicao_id}")
def obter_imobiliario(posicao_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de uma posição imobiliária"""
    posicao = db.query(CarteiraImobiliarioPosicao).filter(
        CarteiraImobiliarioPosicao.id == posicao_id
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")
    return posicao


@router.put("/imobiliario/{posicao_id}")
def atualizar_imobiliario(posicao_id: int, data: dict, db: Session = Depends(get_db)):
    """Atualiza posição imobiliária"""
    posicao = db.query(CarteiraImobiliarioPosicao).filter(
        CarteiraImobiliarioPosicao.id == posicao_id
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    for key, value in data.items():
        setattr(posicao, key, value)

    posicao.data_atualizacao = datetime.now()
    db.commit()
    db.refresh(posicao)
    return posicao


# ─────────────────────────────────────────────────────────────────
# FUNDOS - REFERÊNCIAS
# ─────────────────────────────────────────────────────────────────

@router.get("/fundos-referencia")
def listar_fundos_referencia(db: Session = Depends(get_db)):
    """Lista todos os fundos disponíveis"""
    fundos = db.query(CarteiraFundoReferencia).filter(
        CarteiraFundoReferencia.ativo == True
    ).all()
    return fundos


@router.post("/fundos-referencia")
def criar_fundo_referencia(data: dict, db: Session = Depends(get_db)):
    """Cria novo fundo de referência"""
    fundo = CarteiraFundoReferencia(**data)
    db.add(fundo)
    db.commit()
    db.refresh(fundo)
    return fundo


# ─────────────────────────────────────────────────────────────────
# FUNDOS - POSIÇÕES DO CLIENTE
# ─────────────────────────────────────────────────────────────────

@router.get("/fundos")
def listar_fundos(
    cliente_id: Optional[int] = None,
    gestora: Optional[str] = None,
    cnpj_fundo: Optional[str] = None,
    skip: int = Query(0),
    limit: int = Query(100),
    db: Session = Depends(get_db),
):
    """Lista posições em fundos"""
    query = db.query(CarteiraFundoPosicao)

    if cliente_id:
        query = query.filter(CarteiraFundoPosicao.cliente_id == cliente_id)
    if gestora:
        query = query.join(CarteiraFundoReferencia).filter(
            CarteiraFundoReferencia.gestora.ilike(f"%{gestora}%")
        )
    if cnpj_fundo:
        query = query.join(CarteiraFundoReferencia).filter(
            CarteiraFundoReferencia.cnpj_fundo == cnpj_fundo
        )

    total = query.count()
    posicoes = query.offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": posicoes,
    }


@router.post("/fundos")
def criar_fundo(data: dict, db: Session = Depends(get_db)):
    """Cria nova posição em fundo para cliente"""
    posicao = CarteiraFundoPosicao(**data)
    db.add(posicao)
    db.commit()
    db.refresh(posicao)
    return posicao


@router.get("/fundos/{posicao_id}")
def obter_fundo(posicao_id: int, db: Session = Depends(get_db)):
    """Obtém detalhes de uma posição em fundo"""
    posicao = db.query(CarteiraFundoPosicao).filter(
        CarteiraFundoPosicao.id == posicao_id
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")
    return posicao


@router.put("/fundos/{posicao_id}")
def atualizar_fundo(posicao_id: int, data: dict, db: Session = Depends(get_db)):
    """Atualiza posição em fundo"""
    posicao = db.query(CarteiraFundoPosicao).filter(
        CarteiraFundoPosicao.id == posicao_id
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    for key, value in data.items():
        setattr(posicao, key, value)

    posicao.data_atualizacao = datetime.now()
    db.commit()
    db.refresh(posicao)
    return posicao


# ─────────────────────────────────────────────────────────────────
# ESTRATÉGIAS
# ─────────────────────────────────────────────────────────────────

@router.get("/estrategias")
def listar_estrategias(
    publico: bool = True,
    skip: int = Query(0),
    limit: int = Query(100),
    db: Session = Depends(get_db),
):
    """Lista estratégias disponíveis"""
    query = db.query(CarteiraEstrategia).filter(
        CarteiraEstrategia.ativo == True,
        CarteiraEstrategia.publico == publico,
    )
    total = query.count()
    estrategias = query.offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": estrategias,
    }


@router.post("/estrategias")
def criar_estrategia(data: dict, db: Session = Depends(get_db)):
    """Cria nova estratégia"""
    estrategia = CarteiraEstrategia(**data)
    db.add(estrategia)
    db.commit()
    db.refresh(estrategia)
    return estrategia


@router.get("/estrategias/busca/{termo}")
def buscar_estrategia(termo: str, db: Session = Depends(get_db)):
    """Busca estratégias por nome ou descrição"""
    estrategias = db.query(CarteiraEstrategia).filter(
        or_(
            CarteiraEstrategia.nome.ilike(f"%{termo}%"),
            CarteiraEstrategia.descricao.ilike(f"%{termo}%"),
        ),
        CarteiraEstrategia.ativo == True,
    ).all()
    return estrategias


# ─────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    """Retorna KPIs da carteira"""
    total_clientes = db.query(CarteiraCliente).filter(CarteiraCliente.ativo == True).count()

    # Pro-labore total
    clientes = db.query(CarteiraCliente).filter(CarteiraCliente.ativo == True).all()
    pro_labore_total = sum(c.pro_labore_valor or 0 for c in clientes if c.pro_labore_tipo == 'fixo')

    # Carteira total
    total_debentures = db.query(CarteiraDebenturePosicao).with_entities(
        func.sum(CarteiraDebenturePosicao.valor_aplicado)
    ).scalar() or 0

    total_imobiliario = db.query(CarteiraImobiliarioPosicao).with_entities(
        func.sum(CarteiraImobiliarioPosicao.valor_efetivamente_investido)
    ).scalar() or 0

    total_fundos = db.query(CarteiraFundoPosicao).with_entities(
        func.sum(CarteiraFundoPosicao.valor_aplicado)
    ).scalar() or 0

    carteira_total = total_debentures + total_imobiliario + total_fundos

    # Valor atual
    valor_atual_debentures = db.query(CarteiraDebenturePosicao).with_entities(
        func.sum(CarteiraDebenturePosicao.valor_atual_estimado)
    ).scalar() or 0

    valor_atual_fundos = db.query(CarteiraFundoPosicao).with_entities(
        func.sum(CarteiraFundoPosicao.valor_atual_estimado)
    ).scalar() or 0

    valor_atual_total = valor_atual_debentures + valor_atual_fundos

    # Expectativa de honorários
    posicoes_com_honorario = db.query(
        func.sum(CarteiraDebenturePosicao.valor_atual_estimado * CarteiraDebenturePosicao.percentual_sucesso_honor / 100)
    ).filter(CarteiraDebenturePosicao.faz_parte_honorarios == True).scalar() or 0

    return {
        "total_clientes": total_clientes,
        "pro_labore_mensal": pro_labore_total,
        "carteira_total": carteira_total,
        "valor_atual_total": valor_atual_total,
        "variacao_total_percentual": ((valor_atual_total - carteira_total) / carteira_total * 100) if carteira_total > 0 else 0,
        "expectativa_honorarios": posicoes_com_honorario,
        "breakdown": {
            "debentures": total_debentures,
            "imobiliario": total_imobiliario,
            "fundos": total_fundos,
        }
    }


# ─────────────────────────────────────────────────────────────────
# V1.1 - IA & UPLOAD (Claude Vision para leitura de documentos)
# ─────────────────────────────────────────────────────────────────

@router.post("/processar-documento")
async def processar_documento_com_ia(
    file: UploadFile = File(...),
    tipo: str = Query("geral"),
    db: Session = Depends(get_db)
):
    """
    Processa um documento (PDF/imagem) com Claude Vision.
    Tipos: geral, debenture, imobiliario, fundo
    Extrai campos para auto-fill de formulários.
    """
    try:
        conteudo = await file.read()
        mime_type = file.content_type or "application/pdf"

        resultado = await CarteiraIAService.processar_documento(
            conteudo,
            mime_type,
            tipo
        )

        return {
            "status": "sucesso",
            "dados_extraidos": resultado["dados"],
            "nome_arquivo": file.filename,
            "tipo_processado": resultado["tipo"],
            "modelo": resultado["modelo"],
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao processar documento: {str(e)}")


@router.post("/comparar-termo-emissao")
async def comparar_termo_emissao(
    file_termo: UploadFile = File(...),
    file_emissao: UploadFile = File(...),
):
    """
    Compara Termo de Securitização com Emissão.
    Identifica contradições em taxa, vencimento, etc.
    """
    try:
        conteudo_termo = await file_termo.read()
        conteudo_emissao = await file_emissao.read()

        mime_termo = file_termo.content_type or "application/pdf"
        mime_emissao = file_emissao.content_type or "application/pdf"

        resultado_termo = await CarteiraIAService.processar_documento(
            conteudo_termo, mime_termo, "debenture"
        )
        resultado_emissao = await CarteiraIAService.processar_documento(
            conteudo_emissao, mime_emissao, "debenture"
        )

        comparacao = CarteiraIAService.comparar_termo_vs_emissao(
            resultado_termo["dados"],
            resultado_emissao["dados"],
        )

        return {
            "status": "sucesso",
            "termo": resultado_termo["dados"],
            "emissao": resultado_emissao["dados"],
            "comparacao": comparacao,
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao comparar: {str(e)}")


@router.post("/upload-documento")
async def upload_documento(
    cliente_id: int = Query(...),
    tipo: str = Query("geral"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Salva documento na carteira do cliente"""
    try:
        cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")

        conteudo = await file.read()

        documento = CarteiraUploadDocumento(
            cliente_id=cliente_id,
            nome_arquivo=file.filename,
            tipo_documento=tipo,
            mime_type=file.content_type,
            tamanho_bytes=len(conteudo),
            dados_binarios=conteudo,
        )
        db.add(documento)
        db.commit()
        db.refresh(documento)

        return {"id": documento.id, "nome": documento.nome_arquivo, "status": "salvo"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/documentos")
def listar_documentos(cliente_id: int = Query(...), db: Session = Depends(get_db)):
    """Lista documentos de um cliente"""
    documentos = db.query(CarteiraUploadDocumento).filter(
        CarteiraUploadDocumento.cliente_id == cliente_id
    ).order_by(desc(CarteiraUploadDocumento.data_upload)).all()

    return [
        {
            "id": doc.id,
            "nome": doc.nome_arquivo,
            "tipo": doc.tipo_documento,
            "tamanho_kb": doc.tamanho_bytes / 1024,
            "data_upload": doc.data_upload.isoformat(),
        }
        for doc in documentos
    ]


# ─────────────────────────────────────────────────────────────────
# V1.2 - GOOGLE DRIVE INTEGRATION
# ─────────────────────────────────────────────────────────────────

@router.post("/criar-pasta-drive")
def criar_pasta_drive(cliente_id: int = Query(...), db: Session = Depends(get_db)):
    """[V1.2] Cria pasta no Google Drive para o cliente e salva o link"""
    try:
        cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")

        resultado = CarteiraDriveService.criar_pasta_cliente(
            cliente.nome or f"Cliente_{cliente_id}"
        )

        # Armazenar ID da pasta no cliente
        if cliente.dados_adicionais is None:
            cliente.dados_adicionais = {}

        cliente.dados_adicionais['folder_drive_id'] = resultado['folder_id']
        cliente.dados_adicionais['folder_drive_link'] = resultado['folder_link']
        db.commit()

        return {
            "status": "sucesso",
            "folder_id": resultado['folder_id'],
            "folder_link": resultado['folder_link'],
            "cliente_id": cliente_id,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/upload-para-drive")
async def upload_para_drive(
    cliente_id: int = Query(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """[V1.2] Faz upload de documento direto para Google Drive do cliente"""
    try:
        cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")

        pasta_id = cliente.dados_adicionais.get('folder_drive_id') if cliente.dados_adicionais else None
        if not pasta_id:
            raise HTTPException(status_code=400, detail="Cliente não tem pasta no Drive")

        conteudo = await file.read()
        resultado = CarteiraDriveService.fazer_upload_documento(
            conteudo,
            file.filename or "documento",
            pasta_id,
            file.content_type or "application/octet-stream"
        )

        return {
            "status": "sucesso",
            "file_id": resultado['file_id'],
            "file_link": resultado['file_link'],
            "nome_arquivo": resultado['nome_arquivo'],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/listar-arquivos-drive")
def listar_arquivos_drive(cliente_id: int = Query(...), db: Session = Depends(get_db)):
    """[V1.2] Lista arquivos na pasta Drive do cliente"""
    try:
        cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")

        pasta_id = cliente.dados_adicionais.get('folder_drive_id') if cliente.dados_adicionais else None
        if not pasta_id:
            return {"arquivos": [], "mensagem": "Cliente não tem pasta no Drive"}

        arquivos = CarteiraDriveService.listar_arquivos_pasta(pasta_id)
        return {
            "cliente_id": cliente_id,
            "pasta_id": pasta_id,
            "total_arquivos": len(arquivos),
            "arquivos": arquivos
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────────
# V1.3 - RELATÓRIOS & PDF (Stub para próxima fase)
# ─────────────────────────────────────────────────────────────────

@router.get("/cliente/{cliente_id}/pdf")
def gerar_pdf_cliente(cliente_id: int, db: Session = Depends(get_db)):
    """[V1.3] Gera PDF consolidado do cliente com todos os ativos"""
    try:
        pdf_bytes = CarteiraRelatoriosService.gerar_pdf_cliente(db, cliente_id)
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=carteira_cliente_{cliente_id}.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/exportar-qualificacao")
def exportar_qualificacao(cliente_ids: List[int], formato: str = "xlsx", db: Session = Depends(get_db)):
    """[V1.3] Exporta qualificação em XLSX ou PDF"""
    try:
        if formato == "xlsx":
            arquivo_bytes = CarteiraRelatoriosService.exportar_xlsx_qualificacao(db, cliente_ids)
            return StreamingResponse(
                iter([arquivo_bytes]),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f"attachment; filename=qualificacao_carteira_{datetime.now().strftime('%Y%m%d')}.xlsx"}
            )
        else:
            raise HTTPException(status_code=400, detail="Formato PDF não implementado ainda")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
