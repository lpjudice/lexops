"""Monta um único PDF com o conteúdo das peças de um caso — por padrão só as
peças principais (sem os documentos/anexos), permitindo baixar em massa "só
as petições/decisões" sem os anexos que vieram junto (procurações,
comprovantes etc.)."""
import io
import logging

from sqlalchemy.orm import Session

from app.models.andamento import AndamentoProcesso
from app.models.autos_ia import AutosIADocumento, AutosIAPeca

logger = logging.getLogger(__name__)


def _pagina_placeholder(peca: AutosIAPeca, motivo: str) -> bytes:
    from app.services.gerar_pdf_texto import texto_para_pdf
    conteudo = (
        f"O arquivo original desta peça não pôde ser recuperado ({motivo}).\n\n"
        f"Resumo indexado:\n{peca.resumo or '(sem resumo)'}"
    )
    return texto_para_pdf(
        conteudo,
        titulo=peca.titulo,
        subtitulo=f"págs. {peca.pagina_inicio}-{peca.pagina_fim} — {peca.tipo}",
    )


def _paginas_de_bytes(conteudo: bytes):
    from pypdf import PdfReader
    return list(PdfReader(io.BytesIO(conteudo)).pages)


def _paginas_upload(peca: AutosIAPeca, documentos: list[AutosIADocumento]) -> list:
    from pypdf import PdfReader

    paginas = []
    relevantes = [
        d for d in documentos
        if d.pagina_fim >= peca.pagina_inicio and d.pagina_inicio <= peca.pagina_fim
    ]
    for doc in sorted(relevantes, key=lambda d: d.pagina_inicio):
        try:
            reader = PdfReader(doc.caminho_arquivo)
        except Exception as exc:
            logger.warning("Falha ao abrir %s para montar PDF: %s", doc.caminho_arquivo, exc)
            continue
        inicio_local = max(peca.pagina_inicio, doc.pagina_inicio) - doc.pagina_inicio
        fim_local = min(peca.pagina_fim, doc.pagina_fim) - doc.pagina_inicio
        for i in range(inicio_local, fim_local + 1):
            if 0 <= i < len(reader.pages):
                paginas.append(reader.pages[i])
    return paginas


def _paginas_andamento(db: Session, peca: AutosIAPeca) -> list:
    from app.services.autos_ia.jusbr_import import _obter_bytes

    andamento = db.query(AndamentoProcesso).filter(AndamentoProcesso.id == peca.andamento_id).first()
    if not andamento:
        return []
    conteudo = _obter_bytes(andamento)
    if not conteudo:
        return []

    nome = (andamento.arquivo_nome or "").lower()
    if nome.endswith((".html", ".htm")):
        try:
            from weasyprint import HTML
            texto_html = conteudo.decode("utf-8", errors="ignore")
            pdf_bytes = HTML(string=texto_html).write_pdf()
            return _paginas_de_bytes(pdf_bytes)
        except Exception as exc:
            logger.warning("Falha ao converter HTML→PDF do andamento %s: %s", andamento.id, exc)
            return []

    try:
        return _paginas_de_bytes(conteudo)
    except Exception as exc:
        logger.warning("Falha ao abrir PDF do andamento %s: %s", andamento.id, exc)
        return []


def montar_pdf_pecas(
    db: Session,
    caso_id,
    apenas_principais: bool = True,
    tipo: str | None = None,
    peca_ids: list | None = None,
) -> bytes:
    from pypdf import PdfWriter

    query = db.query(AutosIAPeca).filter(AutosIAPeca.caso_id == caso_id)
    if peca_ids:
        query = query.filter(AutosIAPeca.id.in_(peca_ids))
    elif apenas_principais:
        query = query.filter(AutosIAPeca.peca_pai_id.is_(None))
    if tipo:
        query = query.filter(AutosIAPeca.tipo == tipo)
    pecas = query.order_by(AutosIAPeca.pagina_inicio.asc()).all()

    documentos = db.query(AutosIADocumento).filter(AutosIADocumento.caso_id == caso_id).all()

    writer = PdfWriter()
    for peca in pecas:
        paginas = []
        if peca.documento_id:
            paginas = _paginas_upload(peca, documentos)
        elif peca.andamento_id:
            paginas = _paginas_andamento(db, peca)

        if not paginas:
            for pagina in _paginas_de_bytes(_pagina_placeholder(peca, "arquivo original indisponível")):
                writer.add_page(pagina)
            continue

        for pagina in paginas:
            writer.add_page(pagina)

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()
