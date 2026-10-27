from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy import Float, Integer
from typing import List, Optional
from datetime import date, datetime
import json
import base64
from io import BytesIO
import httpx

from app.models.carteira import (
    CarteiraCliente,
    CarteiraDebentureadotEmissao,
    CarteiraDebenturePosicao,
    CarteiraImobiliarioEmpreendimento,
    CarteiraImobiliarioPosicao,
    CarteiraFundoReferencia,
    CarteiraFundoPosicao,
    CarteiraEstrategia,
    CarteiraCronologia,
    CarteiraAto,
    CarteiraSocioAval,
    CarteiraUploadDocumento,
)
from app.database import get_db
from app.dependencies import get_optional_user
from app.models.usuario import Usuario
from app.models.financeiro import Honorario
from app.services.carteira_ia import CarteiraIAService
from app.services.carteira_relatorios import CarteiraRelatoriosService
from app.services.carteira_drive import CarteiraDriveService
from app.services.carteira_honorarios import calcular_expectativa_exito_carteira

router = APIRouter(prefix="/carteira", tags=["carteira"])


def _limpar_numericos_vazios(model_cls, data: dict) -> dict:
    """Converte '' para None nos campos Float/Integer do model antes de
    criar/atualizar. O frontend manda '' pra campo numérico deixado em
    branco (next de ??''), e Postgres rejeita '' num tipo numérico
    (DataError: invalid input syntax for type double precision/integer).
    Defesa genérica pra não ter que caçar campo por campo cada vez que um
    formulário novo (ou um campo novo num existente) esquece de marcar o
    campo como numérico no lado do cliente."""
    cols = {c.name: c.type for c in model_cls.__table__.columns}
    out = dict(data)
    for k, v in list(out.items()):
        if v == "" and k in cols and isinstance(cols[k], (Float, Integer)):
            out[k] = None
    return out


def _nome_usuario(current_user: Optional[Usuario]) -> Optional[str]:
    """Nome de quem fez a chamada, pra auditoria (criado_por/atualizado_por).
    None quando não autenticado — nunca bloqueia a gravação por causa disso,
    só fica sem autoria registrada."""
    return current_user.nome if current_user else None


_CAMPO_LABEL = {
    "cpf": "CPF/CNPJ", "nome": "Nome", "data_aplicacao": "Data de Aplicação",
    "valor_aplicado": "Valor Aplicado", "data_aquisicao": "Data de Aquisição",
    "numero_cautela": "Nº Cautela", "valor_total_compromissado": "Valor Total Comprometido",
    "nome_fundo": "Nome do Fundo", "nome_venda": "Nome do projeto",
    "nome_serie": "Nome da Série", "numero_emissao": "Nº da Emissão",
    "emissor": "Emissor", "cliente_id": "Cliente", "fundo_id": "Fundo",
    "emissao_id": "Emissão", "empreendimento_id": "Empreendimento",
}


def _commit_amigavel(db: Session, contexto: str = "registro") -> None:
    """Commita a sessão; se faltar um campo obrigatório (NOT NULL) ou colidir
    com um valor único já cadastrado, devolve uma mensagem legível em vez do
    500 cru do Postgres. Sem isso, esquecer um campo marcado com "*" no
    formulário (ex: Data de Aplicação) trava com um erro sem explicação
    nenhuma pro usuário."""
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        orig = getattr(e, "orig", None)
        diag = getattr(orig, "diag", None)
        coluna = getattr(diag, "column_name", None)
        if coluna:
            label = _CAMPO_LABEL.get(coluna, coluna)
            raise HTTPException(status_code=400, detail=f'O campo "{label}" é obrigatório e não foi preenchido.')
        constraint = (getattr(diag, "constraint_name", None) or "").lower()
        if "cpf" in constraint:
            raise HTTPException(status_code=400, detail="Já existe um cliente cadastrado com esse CPF/CNPJ.")
        raise HTTPException(status_code=400, detail=f"Não foi possível salvar o {contexto}: valor duplicado ou inválido.")


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


def _normalizar_cpf_vazio(data: dict) -> dict:
    """cpf é UNIQUE — '' não é "sem CPF" pro Postgres (só NULL é), então duas
    linhas com cpf='' colidem na constraint. Normaliza '' para None antes de
    gravar (clientes importados do XLS costumam vir sem CPF)."""
    if data.get("cpf") == "":
        data = {**data, "cpf": None}
    return data


@router.post("/clientes")
def criar_cliente(data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Cria novo cliente na carteira"""
    data = _normalizar_cpf_vazio(_limpar_numericos_vazios(CarteiraCliente, data))
    nome_usuario = _nome_usuario(current_user)
    data["criado_por"] = nome_usuario
    data["atualizado_por"] = nome_usuario
    cliente = CarteiraCliente(**data)
    db.add(cliente)
    _commit_amigavel(db, "cliente")
    db.refresh(cliente)

    try:
        resultado = CarteiraDriveService.criar_pasta_cliente(cliente.nome or f"Cliente_{cliente.id}")
        cliente.folder_drive_principal_id = resultado["folder_id"]
        cliente.folder_drive_url = resultado["folder_link"]
        if cliente.email:
            CarteiraDriveService.compartilhar_com_email(cliente.nome, cliente.email, role="reader")
        db.commit()
    except Exception as _e:
        import logging
        logging.getLogger("app").warning(f"Drive auto-create falhou para cliente {cliente.id}: {_e}")

    return cliente


@router.put("/clientes/{cliente_id}")
def atualizar_cliente(cliente_id: int, data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Atualiza dados de um cliente"""
    cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    data = _normalizar_cpf_vazio(_limpar_numericos_vazios(CarteiraCliente, data))
    data["atualizado_por"] = _nome_usuario(current_user)
    for key, value in data.items():
        setattr(cliente, key, value)

    _commit_amigavel(db, "cliente")
    db.refresh(cliente)
    return cliente


@router.post("/clientes/{cliente_id}/puxar-honorarios-financeiro")
def puxar_honorarios_financeiro(cliente_id: int, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Ação pontual (não é sincronização contínua): ao linkar um contrato, puxa
    pra cá o % de êxito e o fee fixo já cadastrados em Financeiro > Honorários
    pra esse cliente — pra não ter que digitar o mesmo número duas vezes em
    dois lugares que hoje não se falam. Prioriza o honorário do MESMO contrato
    recém-linkado quando existir; senão usa qualquer honorário do cliente."""
    import uuid as uuid_mod

    cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if not cliente.cliente_uuid:
        raise HTTPException(status_code=400, detail="Cliente não vinculado ao cadastro principal — não há como achar os honorários em Financeiro.")

    try:
        cliente_uuid = uuid_mod.UUID(cliente.cliente_uuid)
    except ValueError:
        raise HTTPException(status_code=400, detail="cliente_uuid inválido")

    honorarios = db.query(Honorario).filter(Honorario.cliente_id == cliente_uuid).all()
    if cliente.contrato_vinculado_id:
        try:
            contrato_uuid = uuid_mod.UUID(cliente.contrato_vinculado_id)
            do_contrato = [h for h in honorarios if h.contrato_id == contrato_uuid]
            if do_contrato:
                honorarios = do_contrato
        except ValueError:
            pass

    campos: dict = {}
    exito_h = next((h for h in honorarios if h.tipo == "exito" and h.percentual_exito is not None), None)
    if exito_h:
        cliente.percentual_sucesso_geral = float(exito_h.percentual_exito)
        campos["percentual_sucesso_geral"] = float(exito_h.percentual_exito)

    fixo_h = next((h for h in honorarios if h.tipo == "fixo"), None)
    if fixo_h:
        cliente.pro_labore_tipo = "fixo"
        cliente.pro_labore_valor = float(fixo_h.valor_total)
        campos["pro_labore_tipo"] = "fixo"
        campos["pro_labore_valor"] = float(fixo_h.valor_total)

    if not campos:
        return {"puxado": False, "campos": {}, "cliente": cliente}

    cliente.atualizado_por = _nome_usuario(current_user)
    _commit_amigavel(db, "cliente")
    db.refresh(cliente)
    return {"puxado": True, "campos": campos, "cliente": cliente}


@router.delete("/clientes/{cliente_id}")
def deletar_cliente(cliente_id: int, db: Session = Depends(get_db)):
    """Deleta cliente (apenas se sem posições vinculadas)"""
    cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    if cliente.debentures or cliente.imobiliarios or cliente.fundos:
        raise HTTPException(status_code=400, detail="Cliente possui posições vinculadas (debêntures/imobiliário/fundos) — remova-as antes de excluir")
    db.delete(cliente)
    db.commit()
    return {"ok": True}


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
def criar_emissao(data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Cria nova emissão de debênture"""
    data = _limpar_numericos_vazios(CarteiraDebentureadotEmissao, data)
    nome_usuario = _nome_usuario(current_user)
    data["criado_por"] = nome_usuario
    data["atualizado_por"] = nome_usuario
    emissao = CarteiraDebentureadotEmissao(**data)
    db.add(emissao)
    _commit_amigavel(db, "emissão")
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


@router.put("/emissoes/{emissao_id}")
def atualizar_emissao(emissao_id: int, data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Atualiza emissão de debênture"""
    emissao = db.query(CarteiraDebentureadotEmissao).filter(
        CarteiraDebentureadotEmissao.id == emissao_id
    ).first()
    if not emissao:
        raise HTTPException(status_code=404, detail="Emissão não encontrada")
    data = _limpar_numericos_vazios(CarteiraDebentureadotEmissao, data)
    data["atualizado_por"] = _nome_usuario(current_user)
    for key, value in data.items():
        setattr(emissao, key, value)
    _commit_amigavel(db, "emissão")
    db.refresh(emissao)
    return emissao


@router.delete("/emissoes/{emissao_id}")
def deletar_emissao(emissao_id: int, db: Session = Depends(get_db)):
    """Deleta emissão (apenas se sem posições de debêntures vinculadas)"""
    emissao = db.query(CarteiraDebentureadotEmissao).filter(
        CarteiraDebentureadotEmissao.id == emissao_id
    ).first()
    if not emissao:
        raise HTTPException(status_code=404, detail="Emissão não encontrada")
    if emissao.posicoes:
        raise HTTPException(status_code=400, detail="Emissão possui posições de debêntures vinculadas — remova-as antes de excluir")
    db.delete(emissao)
    db.commit()
    return {"ok": True}


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
def criar_debenture(data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Cria nova posição de debênture para cliente"""
    data = _limpar_numericos_vazios(CarteiraDebenturePosicao, data)
    nome_usuario = _nome_usuario(current_user)
    data["criado_por"] = nome_usuario
    data["atualizado_por"] = nome_usuario
    posicao = CarteiraDebenturePosicao(**data)
    db.add(posicao)
    _commit_amigavel(db, "posição de debênture")
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
def atualizar_debenture(posicao_id: int, data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Atualiza posição de debênture"""
    posicao = db.query(CarteiraDebenturePosicao).filter(
        CarteiraDebenturePosicao.id == posicao_id
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    data = _limpar_numericos_vazios(CarteiraDebenturePosicao, data)
    data["atualizado_por"] = _nome_usuario(current_user)
    for key, value in data.items():
        setattr(posicao, key, value)

    posicao.data_atualizacao = datetime.now()
    _commit_amigavel(db, "posição de debênture")
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
def criar_empreendimento(data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Cria novo empreendimento"""
    data = _limpar_numericos_vazios(CarteiraImobiliarioEmpreendimento, data)
    nome_usuario = _nome_usuario(current_user)
    data["criado_por"] = nome_usuario
    data["atualizado_por"] = nome_usuario
    empreendimento = CarteiraImobiliarioEmpreendimento(**data)
    db.add(empreendimento)
    _commit_amigavel(db, "empreendimento")
    db.refresh(empreendimento)
    return empreendimento


@router.put("/empreendimentos/{emp_id}")
def atualizar_empreendimento(emp_id: int, data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Atualiza empreendimento"""
    emp = db.query(CarteiraImobiliarioEmpreendimento).filter(
        CarteiraImobiliarioEmpreendimento.id == emp_id
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Empreendimento não encontrado")
    data = _limpar_numericos_vazios(CarteiraImobiliarioEmpreendimento, data)
    data["atualizado_por"] = _nome_usuario(current_user)
    for key, value in data.items():
        setattr(emp, key, value)
    _commit_amigavel(db, "empreendimento")
    db.refresh(emp)
    return emp


@router.delete("/empreendimentos/{emp_id}")
def deletar_empreendimento(emp_id: int, db: Session = Depends(get_db)):
    """Deleta empreendimento (apenas se sem posições vinculadas)"""
    emp = db.query(CarteiraImobiliarioEmpreendimento).filter(
        CarteiraImobiliarioEmpreendimento.id == emp_id
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Empreendimento não encontrado")
    if emp.posicoes:
        raise HTTPException(status_code=400, detail="Empreendimento possui posições vinculadas")
    db.delete(emp)
    db.commit()
    return {"ok": True}


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
def criar_imobiliario(data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Cria nova posição imobiliária para cliente"""
    data = _limpar_numericos_vazios(CarteiraImobiliarioPosicao, data)
    nome_usuario = _nome_usuario(current_user)
    data["criado_por"] = nome_usuario
    data["atualizado_por"] = nome_usuario
    posicao = CarteiraImobiliarioPosicao(**data)
    db.add(posicao)
    _commit_amigavel(db, "posição imobiliária")
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
def atualizar_imobiliario(posicao_id: int, data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Atualiza posição imobiliária"""
    posicao = db.query(CarteiraImobiliarioPosicao).filter(
        CarteiraImobiliarioPosicao.id == posicao_id
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    data = _limpar_numericos_vazios(CarteiraImobiliarioPosicao, data)
    data["atualizado_por"] = _nome_usuario(current_user)
    for key, value in data.items():
        setattr(posicao, key, value)

    posicao.data_atualizacao = datetime.now()
    _commit_amigavel(db, "posição imobiliária")
    db.refresh(posicao)
    return posicao


@router.delete("/imobiliario/{posicao_id}")
def deletar_imobiliario(posicao_id: int, db: Session = Depends(get_db)):
    """Deleta uma posição imobiliária"""
    posicao = db.query(CarteiraImobiliarioPosicao).filter(
        CarteiraImobiliarioPosicao.id == posicao_id
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")
    db.delete(posicao)
    db.commit()
    return {"ok": True}


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


@router.put("/fundos-referencia/{fundo_id}")
def atualizar_fundo_referencia(fundo_id: int, data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Atualiza fundo de referência"""
    fundo = db.query(CarteiraFundoReferencia).filter(CarteiraFundoReferencia.id == fundo_id).first()
    if not fundo:
        raise HTTPException(status_code=404, detail="Fundo não encontrado")
    data = _limpar_numericos_vazios(CarteiraFundoReferencia, data)
    data["atualizado_por"] = _nome_usuario(current_user)
    for key, value in data.items():
        setattr(fundo, key, value)
    _commit_amigavel(db, "fundo de referência")
    db.refresh(fundo)
    return fundo


@router.post("/fundos-referencia")
def criar_fundo_referencia(data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Cria novo fundo de referência"""
    data = _limpar_numericos_vazios(CarteiraFundoReferencia, data)
    nome_usuario = _nome_usuario(current_user)
    data["criado_por"] = nome_usuario
    data["atualizado_por"] = nome_usuario
    fundo = CarteiraFundoReferencia(**data)
    db.add(fundo)
    _commit_amigavel(db, "fundo de referência")
    db.refresh(fundo)
    return fundo


@router.delete("/fundos-referencia/{fundo_id}")
def deletar_fundo_referencia(fundo_id: int, db: Session = Depends(get_db)):
    """Deleta fundo de referência (apenas se sem posições vinculadas)"""
    fundo = db.query(CarteiraFundoReferencia).filter(CarteiraFundoReferencia.id == fundo_id).first()
    if not fundo:
        raise HTTPException(status_code=404, detail="Fundo não encontrado")
    if fundo.posicoes:
        raise HTTPException(status_code=400, detail="Fundo possui posições vinculadas — remova-as antes de excluir")
    db.delete(fundo)
    db.commit()
    return {"ok": True}


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
def criar_fundo(data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Cria nova posição em fundo para cliente"""
    data = _limpar_numericos_vazios(CarteiraFundoPosicao, data)
    nome_usuario = _nome_usuario(current_user)
    data["criado_por"] = nome_usuario
    data["atualizado_por"] = nome_usuario
    posicao = CarteiraFundoPosicao(**data)
    db.add(posicao)
    _commit_amigavel(db, "posição em fundo")
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
def atualizar_fundo(posicao_id: int, data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Atualiza posição em fundo"""
    posicao = db.query(CarteiraFundoPosicao).filter(
        CarteiraFundoPosicao.id == posicao_id
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    data = _limpar_numericos_vazios(CarteiraFundoPosicao, data)
    data["atualizado_por"] = _nome_usuario(current_user)
    for key, value in data.items():
        setattr(posicao, key, value)

    posicao.data_atualizacao = datetime.now()
    _commit_amigavel(db, "posição em fundo")
    db.refresh(posicao)
    return posicao


@router.delete("/fundos/{posicao_id}")
def deletar_fundo(posicao_id: int, db: Session = Depends(get_db)):
    """Deleta uma posição em fundo"""
    posicao = db.query(CarteiraFundoPosicao).filter(
        CarteiraFundoPosicao.id == posicao_id
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")
    db.delete(posicao)
    db.commit()
    return {"ok": True}


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
def criar_estrategia(data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Cria nova estratégia"""
    data = _limpar_numericos_vazios(CarteiraEstrategia, data)
    nome_usuario = _nome_usuario(current_user)
    data["criado_por"] = nome_usuario
    data["atualizado_por"] = nome_usuario
    estrategia = CarteiraEstrategia(**data)
    db.add(estrategia)
    _commit_amigavel(db, "estratégia")
    db.refresh(estrategia)
    return estrategia


@router.put("/estrategias/{estrategia_id}")
def atualizar_estrategia(estrategia_id: int, data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Atualiza estratégia"""
    estrategia = db.query(CarteiraEstrategia).filter(CarteiraEstrategia.id == estrategia_id).first()
    if not estrategia:
        raise HTTPException(status_code=404, detail="Estratégia não encontrada")
    data = _limpar_numericos_vazios(CarteiraEstrategia, data)
    data["atualizado_por"] = _nome_usuario(current_user)
    for key, value in data.items():
        setattr(estrategia, key, value)
    _commit_amigavel(db, "estratégia")
    db.refresh(estrategia)
    return estrategia


@router.delete("/estrategias/{estrategia_id}")
def deletar_estrategia(estrategia_id: int, db: Session = Depends(get_db)):
    """Deleta estratégia (se não estiver vinculada a nenhuma posição)"""
    estrategia = db.query(CarteiraEstrategia).filter(CarteiraEstrategia.id == estrategia_id).first()
    if not estrategia:
        raise HTTPException(status_code=404, detail="Estratégia não encontrada")
    try:
        db.delete(estrategia)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Estratégia vinculada a posições — remova-a dos ativos antes de excluir")
    return {"ok": True}


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
# CRONOLOGIAS (modelo reutilizável de etapas — vinculado a cliente/
# estratégia/ativo via *_ids do lado de quem usa, igual estrategia_ids)
# ─────────────────────────────────────────────────────────────────

@router.get("/cronologias")
def listar_cronologias(db: Session = Depends(get_db)):
    """Lista cronologias (modelos de caminho de ações) disponíveis"""
    cronologias = db.query(CarteiraCronologia).filter(
        CarteiraCronologia.ativo == True
    ).order_by(CarteiraCronologia.nome).all()
    return cronologias


@router.post("/cronologias")
def criar_cronologia(data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Cria nova cronologia (caminho de ações reutilizável)"""
    nome_usuario = _nome_usuario(current_user)
    data["criado_por"] = nome_usuario
    data["atualizado_por"] = nome_usuario
    cronologia = CarteiraCronologia(**data)
    db.add(cronologia)
    _commit_amigavel(db, "cronologia")
    db.refresh(cronologia)
    return cronologia


@router.get("/cronologias/{cronologia_id}")
def obter_cronologia(cronologia_id: int, db: Session = Depends(get_db)):
    cronologia = db.query(CarteiraCronologia).filter(CarteiraCronologia.id == cronologia_id).first()
    if not cronologia:
        raise HTTPException(status_code=404, detail="Cronologia não encontrada")
    return cronologia


@router.put("/cronologias/{cronologia_id}")
def atualizar_cronologia(cronologia_id: int, data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    cronologia = db.query(CarteiraCronologia).filter(CarteiraCronologia.id == cronologia_id).first()
    if not cronologia:
        raise HTTPException(status_code=404, detail="Cronologia não encontrada")
    data["atualizado_por"] = _nome_usuario(current_user)
    for key, value in data.items():
        setattr(cronologia, key, value)
    _commit_amigavel(db, "cronologia")
    db.refresh(cronologia)
    return cronologia


@router.delete("/cronologias/{cronologia_id}")
def deletar_cronologia(cronologia_id: int, db: Session = Depends(get_db)):
    cronologia = db.query(CarteiraCronologia).filter(CarteiraCronologia.id == cronologia_id).first()
    if not cronologia:
        raise HTTPException(status_code=404, detail="Cronologia não encontrada")
    db.delete(cronologia)
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────
# AÇÕES (ATOS) — registro real, com data, do que foi feito por cliente/ativo
# ─────────────────────────────────────────────────────────────────

@router.get("/atos")
def listar_atos(
    cliente_id: Optional[int] = None,
    ativo_tipo: Optional[str] = None,
    ativo_id: Optional[int] = None,
    estrategia_id: Optional[int] = None,
    cronologia_id: Optional[int] = None,
    status: Optional[str] = None,
    busca: Optional[str] = None,
    skip: int = Query(0),
    limit: int = Query(500),
    db: Session = Depends(get_db),
):
    """Lista atos (ações registradas) — visão global (aba Ações) ou filtrada
    por cliente/ativo/estratégia/cronologia (ex: linha do tempo de 1 cliente)."""
    query = db.query(CarteiraAto).filter(CarteiraAto.ativo == True)
    if cliente_id is not None:
        query = query.filter(CarteiraAto.cliente_id == cliente_id)
    if ativo_tipo is not None:
        query = query.filter(CarteiraAto.ativo_tipo == ativo_tipo)
    if ativo_id is not None:
        query = query.filter(CarteiraAto.ativo_id == ativo_id)
    if estrategia_id is not None:
        query = query.filter(CarteiraAto.estrategia_id == estrategia_id)
    if cronologia_id is not None:
        query = query.filter(CarteiraAto.cronologia_id == cronologia_id)
    if status is not None:
        query = query.filter(CarteiraAto.status == status)
    if busca:
        query = query.filter(or_(
            CarteiraAto.titulo.ilike(f"%{busca}%"),
            CarteiraAto.descricao.ilike(f"%{busca}%"),
        ))

    total = query.count()
    atos = query.order_by(desc(CarteiraAto.data_ato)).offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "data": atos,
    }


@router.post("/atos")
def criar_ato(data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    """Registra um novo ato (notificação, contra-notificação, ação judicial etc.)"""
    data = _limpar_numericos_vazios(CarteiraAto, data)
    nome_usuario = _nome_usuario(current_user)
    data["criado_por"] = nome_usuario
    data["atualizado_por"] = nome_usuario
    ato = CarteiraAto(**data)
    db.add(ato)
    _commit_amigavel(db, "ato")
    db.refresh(ato)
    return ato


@router.get("/atos/{ato_id}")
def obter_ato(ato_id: int, db: Session = Depends(get_db)):
    ato = db.query(CarteiraAto).filter(CarteiraAto.id == ato_id).first()
    if not ato:
        raise HTTPException(status_code=404, detail="Ato não encontrado")
    return ato


@router.put("/atos/{ato_id}")
def atualizar_ato(ato_id: int, data: dict, db: Session = Depends(get_db), current_user: Optional[Usuario] = Depends(get_optional_user)):
    ato = db.query(CarteiraAto).filter(CarteiraAto.id == ato_id).first()
    if not ato:
        raise HTTPException(status_code=404, detail="Ato não encontrado")
    data = _limpar_numericos_vazios(CarteiraAto, data)
    data["atualizado_por"] = _nome_usuario(current_user)
    for key, value in data.items():
        setattr(ato, key, value)
    ato.data_atualizacao = datetime.now()
    _commit_amigavel(db, "ato")
    db.refresh(ato)
    return ato


@router.delete("/atos/{ato_id}")
def deletar_ato(ato_id: int, db: Session = Depends(get_db)):
    ato = db.query(CarteiraAto).filter(CarteiraAto.id == ato_id).first()
    if not ato:
        raise HTTPException(status_code=404, detail="Ato não encontrado")
    db.delete(ato)
    db.commit()
    return {"ok": True}


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

    # Expectativa de honorários de êxito — mesma conta usada no card "Expectativa
    # Êxito" da Carteira (só posições com faz_parte_honorarios=True; ver
    # calcular_expectativa_exito_carteira para a lógica completa de % e fallback).
    expectativa_exito = calcular_expectativa_exito_carteira(db)

    return {
        "total_clientes": total_clientes,
        "pro_labore_mensal": pro_labore_total,
        "carteira_total": carteira_total,
        "valor_atual_total": valor_atual_total,
        "variacao_total_percentual": ((valor_atual_total - carteira_total) / carteira_total * 100) if carteira_total > 0 else 0,
        "expectativa_honorarios": expectativa_exito["total"],
        "expectativa_honorarios_por_cliente": expectativa_exito["por_cliente"],
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

        if resultado.get("erro"):
            raise HTTPException(status_code=502, detail=resultado["erro"])

        return {
            "status": "sucesso",
            "dados_extraidos": resultado["dados"],
            "nome_arquivo": file.filename,
            "tipo_processado": resultado["tipo"],
            "modelo": resultado["modelo"],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao processar documento: {str(e)}")


@router.post("/processar-e-salvar-documento")
async def processar_e_salvar_documento(
    file: UploadFile = File(...),
    tipo: str = Query("geral"),
    cliente_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Processa com IA, salva no DB e envia ao Drive (se o cliente tiver pasta)."""
    try:
        conteudo = await file.read()
        mime_type = file.content_type or "application/pdf"

        resultado_ia = await CarteiraIAService.processar_documento(conteudo, mime_type, tipo)

        drive_file_id: Optional[str] = None
        drive_file_link: Optional[str] = None

        if cliente_id:
            cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
            if cliente and cliente.nome:
                try:
                    dr = CarteiraDriveService.fazer_upload_documento(
                        conteudo,
                        file.filename or "documento",
                        cliente.nome,
                        mime_type,
                    )
                    drive_file_id = dr["file_id"]
                    drive_file_link = dr["file_link"]
                except Exception:
                    pass

            if cliente:
                doc = CarteiraUploadDocumento(
                    cliente_id=cliente_id,
                    nome_arquivo=file.filename,
                    tipo_documento=tipo,
                    mime_type=mime_type,
                    tamanho_bytes=len(conteudo),
                    dados_binarios=conteudo,
                )
                db.add(doc)
                db.commit()

        return {
            "status": "sucesso",
            "dados_extraidos": resultado_ia["dados"],
            "nome_arquivo": file.filename,
            "tipo_processado": resultado_ia["tipo"],
            "modelo": resultado_ia["modelo"],
            "drive_file_id": drive_file_id,
            "drive_file_link": drive_file_link,
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
def criar_pasta_drive(
    cliente_id: int = Query(...),
    usar_pasta_id: Optional[str] = Query(None, description="Reusa esta pasta já existente em vez de criar uma nova"),
    confirmar_nova: bool = Query(False, description="Pula a checagem de pasta parecida e cria mesmo assim"),
    db: Session = Depends(get_db),
):
    """[V1.2] Cria (ou reaproveita) a pasta do cliente no Google Drive.

    Evita duplicar pasta de um cliente que já tem uma: se `folder_drive_principal_id`
    já está salvo, retorna direto sem chamar o Drive. Para cliente sem pasta,
    antes de criar verifica se já existe pasta de nome PARECIDO no Drive — se
    achar, devolve os candidatos (status "ambiguo") para o usuário confirmar
    se é o mesmo cliente (usar_pasta_id) ou se é para criar mesmo assim
    (confirmar_nova=true).
    """
    try:
        cliente = db.query(CarteiraCliente).filter(CarteiraCliente.id == cliente_id).first()
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente não encontrado")

        nome_cliente = cliente.nome or f"Cliente_{cliente_id}"

        if cliente.folder_drive_principal_id and not usar_pasta_id:
            return {
                "status": "sucesso",
                "folder_id": cliente.folder_drive_principal_id,
                "folder_link": cliente.folder_drive_url,
                "cliente_id": cliente_id,
            }

        if usar_pasta_id:
            resultado = CarteiraDriveService.vincular_pasta_existente(nome_cliente, usar_pasta_id)
        else:
            if not confirmar_nova:
                candidatos = CarteiraDriveService.buscar_pastas_similares(nome_cliente)
                if candidatos:
                    return {"status": "ambiguo", "candidatos": candidatos, "cliente_id": cliente_id}
            resultado = CarteiraDriveService.criar_pasta_cliente(nome_cliente)

        cliente.folder_drive_principal_id = resultado['folder_id']
        cliente.folder_drive_url = resultado['folder_link']
        db.commit()

        return {
            "status": "sucesso",
            "folder_id": resultado['folder_id'],
            "folder_link": resultado['folder_link'],
            "cliente_id": cliente_id,
        }
    except HTTPException:
        raise
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

        if not cliente.nome:
            raise HTTPException(status_code=400, detail="Cliente sem nome cadastrado")

        conteudo = await file.read()
        resultado = CarteiraDriveService.fazer_upload_documento(
            conteudo,
            file.filename or "documento",
            cliente.nome,
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

        if not cliente.nome:
            return {"arquivos": [], "mensagem": "Cliente sem nome cadastrado"}

        arquivos = CarteiraDriveService.listar_arquivos_pasta(cliente.nome)
        return {
            "cliente_id": cliente_id,
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
        pdf_bytes, nome_cliente = CarteiraRelatoriosService.gerar_pdf_cliente(db, cliente_id)
        import unicodedata
        slug = unicodedata.normalize('NFD', nome_cliente)
        slug = ''.join(c for c in slug if unicodedata.category(c) != 'Mn')
        slug = slug.lower().replace(' ', '_')[:40]
        date_str = datetime.now().strftime('%Y%m%d')
        filename = f"carteira_{slug}_{date_str}.pdf"
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/pdf-geral")
def gerar_pdf_geral(
    incluir_honorarios: bool = Query(True),
    redigir_nomes: bool = Query(False),
    db: Session = Depends(get_db),
):
    """PDF único com todos os clientes que têm posição na carteira (1 por
    cliente, mesmo layout do relatório individual), com honorários e nomes
    opcionalmente ocultados."""
    try:
        pdf_bytes = CarteiraRelatoriosService.gerar_pdf_todos_clientes(
            db, incluir_honorarios=incluir_honorarios, redigir_nomes=redigir_nomes,
        )
        date_str = datetime.now().strftime('%Y%m%d')
        sufixo = []
        if not incluir_honorarios:
            sufixo.append('sem_honorarios')
        if redigir_nomes:
            sufixo.append('redigido')
        sufixo_str = ('_' + '_'.join(sufixo)) if sufixo else ''
        filename = f"carteira_geral{sufixo_str}_{date_str}.pdf"
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
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
