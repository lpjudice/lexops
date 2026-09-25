"""Importa peças diretamente dos andamentos/documentos que o jus.br já baixou
para um Processo do gestor — alternativa ao upload manual de blocos de PDF.

Cada `AndamentoProcesso` já é, tipicamente, um documento discreto (um PDF por
movimentação), então aqui não há segmentação por IA: apenas classificação do
tipo por regra (usando o `tipo`/`descricao` que o jus.br já fornece),
agrupamento de documentos anexados à mesma movimentação (procurações,
comprovantes...) sob a peça principal do grupo, e o mesmo passo de
resumo/keywords/IDs mencionados usado no fluxo de upload manual.
"""
import logging
import unicodedata
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.andamento import AndamentoProcesso
from app.models.autos_ia import AutosIACaso, AutosIAPeca
from app.services.autos_ia.ingestao import (
    _persistir_referencias,
    _resolver_referencias_pendentes,
    resumir_pecas_em_paralelo,
)
from app.services.autos_ia.segmentacao import TIPOS_VALIDOS

logger = logging.getLogger(__name__)

LIMIAR_CHARS_PARA_RESUMO_IA = 200

PALAVRAS_TIPO = {
    "peticao": ["petiç", "manifestaç", "impugnaç", "réplica", "replica", "alegaç"],
    "decisao": ["senten", "decis", "acórdão", "acordao"],
    "despacho": ["despach"],
    "certidao": ["certid"],
    "oficio": ["ofici"],
    "recurso": ["recurso", "apelaç", "apelac", "agravo", "embargo"],
}

PALAVRAS_ANEXO = [
    "procuração", "procuracao", "substabelecimento", "comprovante", "guia de recolhimento",
    "guia darf", "documento de identidade", "documento pessoal", " rg ", "cpf", "contrato social",
    "ata de", "extrato", "comprovante de residência", "comprovante de residencia",
    "declaração de pobreza", "declaracao de pobreza", "carta de preposição", "carta de preposicao",
    "boleto", "darf", "custas processuais", "comprovante de pagamento",
]


def _normalizar(texto: str) -> str:
    v = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in v if unicodedata.category(c) != "Mn")


def _classificar_tipo(andamento: AndamentoProcesso) -> str:
    base = _normalizar(f"{andamento.tipo or ''} {andamento.descricao or ''}")
    for tipo, palavras in PALAVRAS_TIPO.items():
        if any(_normalizar(p) in base for p in palavras):
            return tipo
    return "outro"


def _eh_provavel_anexo(andamento: AndamentoProcesso) -> bool:
    base = _normalizar(f"{andamento.descricao or ''} {andamento.arquivo_nome or ''}")
    return any(_normalizar(p) in base for p in PALAVRAS_ANEXO)


def _obter_bytes(andamento: AndamentoProcesso) -> bytes | None:
    if andamento.arquivo_path:
        try:
            caminho = Path(andamento.arquivo_path)
            if caminho.exists():
                return caminho.read_bytes()
        except Exception as exc:
            logger.warning("Falha ao ler arquivo local do andamento %s: %s", andamento.id, exc)

    if andamento.arquivo_drive_link:
        try:
            from app.services.google_drive import baixar_arquivo_por_id, extrair_file_id
            file_id = extrair_file_id(andamento.arquivo_drive_link)
            if file_id:
                return baixar_arquivo_por_id(file_id)
        except Exception as exc:
            logger.warning("Falha ao baixar do Drive o andamento %s: %s", andamento.id, exc)

    return None


def _extrair_texto(conteudo: bytes, nome_arquivo: str | None) -> str:
    if nome_arquivo and nome_arquivo.lower().endswith((".html", ".htm")):
        try:
            from bs4 import BeautifulSoup
            return BeautifulSoup(conteudo, "html.parser").get_text("\n").strip()
        except Exception as exc:
            logger.warning("Falha ao extrair texto de HTML: %s", exc)
            return ""

    from app.services.pdf_extract import extrair_texto_pdf
    return extrair_texto_pdf(conteudo)


def _contar_paginas(conteudo: bytes | None, nome_arquivo: str | None) -> int:
    if not conteudo or (nome_arquivo and nome_arquivo.lower().endswith((".html", ".htm"))):
        return 1
    try:
        from pypdf import PdfReader
        import io
        return max(1, len(PdfReader(io.BytesIO(conteudo)).pages))
    except Exception:
        return 1


def sincronizar_caso_jusbr(db: Session, caso: AutosIACaso, session_data: dict | None) -> None:
    """Sincroniza o Processo vinculado (DataJud + jus.br, reaproveitando as
    rotinas já existentes do orquestrador) e importa os andamentos novos como
    peças. Usada tanto pelo job agendado (3x/dia) quanto pelo botão de
    "sincronizar agora" na tela do caso."""
    from datetime import datetime, timezone
    from app.models.processo import Processo
    from app.services.consulta_processual.orchestrator import (
        sincronizar_processo,
        sincronizar_processo_jusbr,
    )

    processo = db.query(Processo).filter(Processo.id == caso.processo_id).first()
    if not processo:
        caso.ultimo_sync_status = "erro"
        caso.ultimo_sync_mensagem = "Processo vinculado não encontrado."
        caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
        db.commit()
        return

    try:
        import asyncio
        asyncio.run(sincronizar_processo(processo, db))
        if session_data:
            asyncio.run(sincronizar_processo_jusbr(processo, db, session_data=session_data))
        novas = importar_andamentos_pendentes(db, caso)
        caso.ultimo_sync_status = "ok"
        caso.ultimo_sync_mensagem = f"{novas} peça(s) nova(s) importada(s)."
    except Exception as exc:
        logger.warning("Autos IA: erro ao sincronizar caso %s: %s", caso.id, exc)
        caso.ultimo_sync_status = "erro"
        caso.ultimo_sync_mensagem = str(exc)
    finally:
        caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
        db.commit()


def importar_apenas_existentes(db: Session, caso: AutosIACaso) -> None:
    """Só importa os andamentos/documentos que o jus.br JÁ baixou pro processo
    vinculado — sem chamar DataJud/jus.br ao vivo. Usado no backfill inicial
    (ex.: caso com centenas de documentos já baixados por outra rotina) e no
    botão "Importar documentos existentes", quando não faz sentido esperar uma
    sincronização de rede só pra reler o que já está salvo."""
    from datetime import datetime, timezone

    try:
        novas = importar_andamentos_pendentes(db, caso)
        caso.ultimo_sync_status = "ok"
        caso.ultimo_sync_mensagem = f"{novas} peça(s) importada(s) a partir dos documentos já baixados."
    except Exception as exc:
        logger.warning("Autos IA: erro ao importar existentes do caso %s: %s", caso.id, exc)
        caso.ultimo_sync_status = "erro"
        caso.ultimo_sync_mensagem = str(exc)
    finally:
        caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
        db.commit()


def importar_andamentos_pendentes(db: Session, caso: AutosIACaso) -> int:
    """Importa como peças os andamentos do processo vinculado ainda não trazidos
    para este caso. Retorna quantas peças novas foram criadas."""
    if not caso.processo_id:
        return 0

    ja_importados = {
        row[0] for row in db.query(AutosIAPeca.andamento_id)
        .filter(AutosIAPeca.caso_id == caso.id, AutosIAPeca.andamento_id.isnot(None))
        .all()
    }

    query = db.query(AndamentoProcesso).filter(AndamentoProcesso.processo_id == caso.processo_id)
    if ja_importados:
        query = query.filter(~AndamentoProcesso.id.in_(ja_importados))
    pendentes = query.order_by(
        AndamentoProcesso.data_andamento.asc().nulls_last(), AndamentoProcesso.created_at.asc()
    ).all()

    if not pendentes:
        return 0

    caso.ultimo_sync_status = "processando"
    caso.ultimo_sync_mensagem = f"Lendo documentos: 0/{len(pendentes)}"
    db.commit()

    # ── Monta os dados de cada andamento (texto, tipo, página) antes de gravar ──
    itens = []
    for indice, andamento in enumerate(pendentes, start=1):
        conteudo = None
        texto = andamento.texto_extraido
        if not texto:
            conteudo = _obter_bytes(andamento)
            if conteudo:
                texto = _extrair_texto(conteudo, andamento.arquivo_nome)
                if texto:
                    andamento.texto_extraido = texto
                    db.commit()
        if not texto:
            texto = andamento.descricao or ""

        if indice % 5 == 0 or indice == len(pendentes):
            caso.ultimo_sync_mensagem = f"Lendo documentos: {indice}/{len(pendentes)}"
            db.commit()

        paginas = _contar_paginas(conteudo, andamento.arquivo_nome)
        pagina_inicio = caso.total_paginas + 1
        caso.total_paginas += paginas

        itens.append({
            "andamento": andamento,
            "texto": texto,
            "tipo": _classificar_tipo(andamento),
            "eh_anexo": _eh_provavel_anexo(andamento),
            "pagina_inicio": pagina_inicio,
            "pagina_fim": pagina_inicio + paginas - 1,
            "grupo": (andamento.data_andamento, (andamento.descricao or "").strip()),
        })
    db.commit()

    # ── Agrupa por movimentação (mesma data + descrição) para achar a peça principal ──
    grupos: dict[tuple, list[dict]] = {}
    for item in itens:
        grupos.setdefault(item["grupo"], []).append(item)

    criadas: list[AutosIAPeca] = []
    for membros in grupos.values():
        principal = next((m for m in membros if not m["eh_anexo"]), membros[0])
        peca_principal = _criar_peca(db, caso, principal, peca_pai_id=None)
        criadas.append(peca_principal)
        for membro in membros:
            if membro is principal:
                continue
            criadas.append(_criar_peca(db, caso, membro, peca_pai_id=peca_principal.id))
    db.commit()

    pecas_curtas = [p for p in criadas if len(p.texto_md) < LIMIAR_CHARS_PARA_RESUMO_IA]
    pecas_para_ia = [p for p in criadas if p not in pecas_curtas]

    for peca in pecas_curtas:
        peca.resumo = peca.texto_md
        peca.keywords = []
        peca.ids_mencionados = []
        peca.status = "resumida"
    caso.ultimo_sync_mensagem = f"Resumindo peças: 0/{len(pecas_para_ia)}"
    db.commit()

    def _progresso_resumo(feitas: int) -> None:
        caso.ultimo_sync_mensagem = f"Resumindo peças: {feitas}/{len(pecas_para_ia)}"
        db.commit()

    resumir_pecas_em_paralelo(db, pecas_para_ia, on_progresso=_progresso_resumo)

    _resolver_referencias_pendentes(db, caso.id)
    caso.ultimo_sync_mensagem = f"{len(criadas)} peça(s) nova(s) importada(s)."
    db.commit()
    return len(criadas)


def _criar_peca(db: Session, caso: AutosIACaso, item: dict, peca_pai_id) -> AutosIAPeca:
    andamento: AndamentoProcesso = item["andamento"]
    tipo = item["tipo"] if item["tipo"] in TIPOS_VALIDOS else "outro"
    if peca_pai_id is not None and tipo == "outro":
        tipo = "documento"

    peca = AutosIAPeca(
        caso_id=caso.id,
        andamento_id=andamento.id,
        peca_pai_id=peca_pai_id,
        tipo=tipo,
        titulo=(andamento.tipo or andamento.descricao or "Andamento sem título").strip()[:500],
        autor=None,
        data_peca=andamento.data_andamento,
        id_processual=andamento.documento_id,
        pagina_inicio=item["pagina_inicio"],
        pagina_fim=item["pagina_fim"],
        texto_md=item["texto"] or "(sem texto extraído)",
        status="pendente_resumo",
    )
    db.add(peca)
    db.flush()
    return peca
