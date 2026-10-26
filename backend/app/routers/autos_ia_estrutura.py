"""Estrutura do grupo (organograma societário) e relação de créditos (planilha de credores) de um caso."""
import re
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.andamento import AndamentoProcesso
from app.models.autos_ia import AutosIACaso, AutosIAPeca
from app.services.autos_ia import estrutura_grupo as eg

router = APIRouter(prefix="/autos-ia/casos/{caso_id}/estrutura", tags=["autos-ia-estrutura"], dependencies=[Depends(get_current_user)])
MAX_XLSX = 15 * 1024 * 1024


def _caso(db: Session, caso_id: uuid.UUID) -> AutosIACaso:
    c = db.get(AutosIACaso, caso_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Caso não encontrado")
    return c


def _erro(exc: Exception, db: Session, codigo: int | None = None):
    db.rollback()
    msg = str(exc)
    raise HTTPException(status_code=codigo or (404 if "não encontrad" in msg else 422), detail=msg)


class Filtros:
    """Filtros comuns às consultas de créditos (querystring)."""

    def __init__(
        self,
        categoria: list[str] = Query([]), subcategoria: list[str] = Query([]), classe: list[str] = Query([]),
        devedor: list[str] = Query([], description="CNPJ (14 dígitos) das devedoras"), nivel_devedor: list[str] = Query([]),
        credor: list[str] = Query([], description="CNPJ do credor (ou o nome, se não tiver CNPJ)"),
        credor_q: str | None = None, natureza_q: str | None = None, q: str | None = None,
        intragrupo: bool | None = None, vencidos: bool | None = None, com_coobrigado: bool | None = None, no_organograma: bool | None = None,
        valor_min: float | None = Query(None, description="Em reais"), valor_max: float | None = Query(None, description="Em reais"),
        venc_de: date | None = None, venc_ate: date | None = None, lote: uuid.UUID | None = None,
    ):
        self.lote = lote
        self.f = {
            "categoria": categoria, "subcategoria": subcategoria, "classe": classe, "devedor": devedor, "nivel_devedor": nivel_devedor, "credor": credor,
            "credor_q": credor_q, "natureza_q": natureza_q, "q": q, "intragrupo": intragrupo, "vencidos": vencidos, "com_coobrigado": com_coobrigado,
            "no_organograma": no_organograma, "valor_min": None if valor_min is None else round(valor_min * 100), "valor_max": None if valor_max is None else round(valor_max * 100),
            "venc_de": venc_de, "venc_ate": venc_ate,
        }


@router.get("/creditos")
def listar_creditos(
    caso_id: uuid.UUID, filtros: Filtros = Depends(), ordem: str = Query("-valor", pattern=r"^-?(valor|devedora|credor|categoria|vencimento|linha)$"),
    limite: int = Query(2000, ge=1, le=5000), offset: int = Query(0, ge=0), db: Session = Depends(get_db),
):
    _caso(db, caso_id)
    itens = eg.filtrar(eg.creditos(db, caso_id, filtros.lote), filtros.f)
    chave = {"valor": lambda i: i["valor_centavos"], "devedora": lambda i: i["devedor"].casefold(), "credor": lambda i: i["credor"].casefold(),
             "categoria": lambda i: i["categoria"], "vencimento": lambda i: i["vencimento"] or date.max, "linha": lambda i: i["linha"] or 0}[ordem.lstrip("-")]
    itens.sort(key=chave, reverse=ordem.startswith("-"))
    return {"total": len(itens), "total_centavos": sum(i["valor_centavos"] for i in itens), "itens": itens[offset: offset + limite]}


@router.get("/creditos/resumo")
def resumo_creditos(caso_id: uuid.UUID, filtros: Filtros = Depends(), db: Session = Depends(get_db)):
    _caso(db, caso_id)
    return eg.resumo(eg.filtrar(eg.creditos(db, caso_id, filtros.lote), filtros.f))


@router.get("/creditos/opcoes")
def opcoes_creditos(caso_id: uuid.UUID, lote: uuid.UUID | None = None, db: Session = Depends(get_db)):
    _caso(db, caso_id)
    return eg.opcoes(eg.creditos(db, caso_id, lote))


@router.get("/creditos/agrupar")
def agrupar_creditos(
    caso_id: uuid.UUID, linhas: str = Query("devedora"), colunas: str | None = Query("categoria"), filtros: Filtros = Depends(), db: Session = Depends(get_db),
):
    """Tabela dinâmica: `linhas` × `colunas` (devedora, credor, categoria, subcategoria, classe, origem, nivel_devedora, vencimento_mes)."""
    _caso(db, caso_id)
    try:
        return eg.agrupar(eg.filtrar(eg.creditos(db, caso_id, filtros.lote), filtros.f), linhas, colunas or None)
    except eg.EstruturaErro as exc:
        _erro(exc, db)


@router.get("/creditos/lotes")
def lotes(caso_id: uuid.UUID, db: Session = Depends(get_db)):
    _caso(db, caso_id)
    return eg.listar_lotes(db, caso_id)


@router.post("/creditos/importar", status_code=status.HTTP_201_CREATED)
async def importar_creditos(caso_id: uuid.UUID, arquivo: UploadFile = File(...), notas: str | None = Form(None), db: Session = Depends(get_db)):
    """Importa a planilha de credores (.xlsx). Vira o lote ATIVO; os anteriores ficam para comparação."""
    _caso(db, caso_id)
    dados = await arquivo.read()
    if len(dados) > MAX_XLSX:
        raise HTTPException(status_code=413, detail="Planilha acima de 15 MB.")
    if not (arquivo.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=422, detail="Envie a planilha em .xlsx.")
    try:
        return eg.importar_creditos(db, caso_id, dados, arquivo.filename, notas)
    except eg.EstruturaErro as exc:
        _erro(exc, db)
    except Exception as exc:  # noqa: BLE001 — arquivo corrompido / formato inesperado
        db.rollback()
        raise HTTPException(status_code=422, detail=f"Não consegui ler a planilha: {str(exc)[:200]}")


@router.post("/creditos/lotes/{lote_id}/ativar")
def ativar_lote(caso_id: uuid.UUID, lote_id: uuid.UUID, db: Session = Depends(get_db)):
    _caso(db, caso_id)
    try:
        return eg.ativar_lote(db, caso_id, lote_id)
    except eg.EstruturaErro as exc:
        _erro(exc, db)


@router.delete("/creditos/lotes/{lote_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_lote(caso_id: uuid.UUID, lote_id: uuid.UUID, db: Session = Depends(get_db)):
    _caso(db, caso_id)
    try:
        eg.excluir_lote(db, caso_id, lote_id)
    except eg.EstruturaErro as exc:
        _erro(exc, db)


@router.get("/organograma")
def organograma(caso_id: uuid.UUID, lote: uuid.UUID | None = None, db: Session = Depends(get_db)):
    """Empresas do grupo (com nível), participações societárias e, em cada empresa, quanto deve/tem a receber (lote ativo)."""
    _caso(db, caso_id)
    return eg.organograma(db, caso_id, lote)


def _peca_por_arquivo(db: Session, caso_id, padrao: str, id_processual: str | None):
    q = db.query(AutosIAPeca, AndamentoProcesso).outerjoin(AndamentoProcesso, AutosIAPeca.andamento_id == AndamentoProcesso.id).filter(AutosIAPeca.caso_id == caso_id)
    if id_processual:
        q = q.filter(AutosIAPeca.id_processual == id_processual)
    achados = [(p, a) for p, a in q.all() if id_processual or (a and re.search(padrao, a.arquivo_nome or "", re.I))]
    return achados[0] if achados else (None, None)


@router.post("/organograma/importar", status_code=status.HTTP_201_CREATED)
async def importar_organograma(
    caso_id: uuid.UUID, arquivo: UploadFile | None = File(None), id_organograma: str | None = Form(None, description="ID processual da peça com o PDF do organograma"),
    id_doc06: str | None = Form(None, description="ID processual da peça 'Lista de empresas e atividades' (níveis)"), db: Session = Depends(get_db),
):
    """Lê o organograma do PDF (enviado, ou o da peça do processo — por padrão, o arquivo "Organograma" do caso) e os níveis do Doc. 06."""
    _caso(db, caso_id)
    pdf = (await arquivo.read()) if arquivo is not None else None
    if pdf is None:
        peca, andamento = _peca_por_arquivo(db, caso_id, r"organograma", id_organograma)
        if peca is None or andamento is None or not andamento.arquivo_drive_link:
            raise HTTPException(status_code=404, detail="Não achei o PDF do organograma nas peças do caso. Informe o ID da peça ou envie o PDF.")
        from app.services.google_drive import baixar_arquivo_por_id, extrair_file_id
        fid = extrair_file_id(andamento.arquivo_drive_link)
        pdf = baixar_arquivo_por_id(fid) if fid else None
        if not pdf:
            raise HTTPException(status_code=502, detail="Não consegui baixar o PDF do Drive.")
    p6, _ = _peca_por_arquivo(db, caso_id, r"lista de empresas|empresas e atividades", id_doc06)
    try:
        return eg.importar_organograma(db, caso_id, pdf, p6.texto_md if p6 else None)
    except ValueError as exc:
        _erro(exc, db, 422)


class ParticipacaoIn(BaseModel):
    pai: str
    filho: str
    pct: float | None = None
    tracejado: bool = False


class ParticipacaoUpdateIn(BaseModel):
    pct: float | None = None
    status: str | None = None
    nota: str | None = None


class EntidadeUpdateIn(BaseModel):
    nome: str | None = None
    nivel: str | None = None


@router.post("/participacoes", status_code=status.HTTP_201_CREATED)
def criar_participacao(caso_id: uuid.UUID, data: ParticipacaoIn, db: Session = Depends(get_db)):
    _caso(db, caso_id)
    try:
        return eg.criar_participacao(db, caso_id, data.pai, data.filho, data.pct, data.tracejado)
    except eg.EstruturaErro as exc:
        _erro(exc, db)


@router.patch("/participacoes/{part_id}")
def atualizar_participacao(caso_id: uuid.UUID, part_id: uuid.UUID, data: ParticipacaoUpdateIn, db: Session = Depends(get_db)):
    _caso(db, caso_id)
    try:
        return eg.atualizar_participacao(db, caso_id, part_id, pct=data.pct, pct_definido="pct" in data.model_fields_set, status=data.status,
                                         nota=data.nota, nota_definida="nota" in data.model_fields_set)
    except eg.EstruturaErro as exc:
        _erro(exc, db)


@router.patch("/empresas/{cnpj}")
def atualizar_empresa(caso_id: uuid.UUID, cnpj: str, data: EntidadeUpdateIn, db: Session = Depends(get_db)):
    _caso(db, caso_id)
    try:
        return eg.atualizar_entidade(db, caso_id, cnpj, nome=data.nome, nivel=data.nivel, nivel_definido="nivel" in data.model_fields_set)
    except eg.EstruturaErro as exc:
        _erro(exc, db)
