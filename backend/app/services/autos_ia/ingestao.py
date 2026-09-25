"""Orquestra o processamento de um bloco de páginas recém-enviado:
extração de texto → segmentação em peças → resumo/keywords/IDs → referências.
"""
import logging
import re
import unicodedata
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.autos_ia import AutosIACaso, AutosIADocumento, AutosIAPeca, AutosIAReferencia
from app.services.autos_ia.extracao import extrair_paginas
from app.services.autos_ia.resumo import resumir_peca
from app.services.autos_ia.segmentacao import segmentar_paginas

logger = logging.getLogger(__name__)


def _normalizar_id(valor: str) -> str:
    """Normaliza um ID/referência textual para comparação tolerante a formatação
    (ex.: 'Evento 45', 'evento nº 045' e 'EVENTO-45' devem casar)."""
    v = unicodedata.normalize("NFD", valor.lower())
    v = "".join(c for c in v if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", v)


def _parse_data(valor: str | None) -> date | None:
    if not valor:
        return None
    try:
        return date.fromisoformat(valor[:10])
    except ValueError:
        return None


def _persistir_referencias(db: Session, peca: AutosIAPeca, ids_mencionados: list[str]) -> None:
    if not ids_mencionados:
        return
    outras_pecas = (
        db.query(AutosIAPeca)
        .filter(AutosIAPeca.caso_id == peca.caso_id, AutosIAPeca.id_processual.isnot(None))
        .filter(AutosIAPeca.id != peca.id)
        .all()
    )
    mapa_normalizado = {_normalizar_id(p.id_processual): p for p in outras_pecas if p.id_processual}

    for id_mencionado in ids_mencionados:
        destino = mapa_normalizado.get(_normalizar_id(id_mencionado))
        db.add(AutosIAReferencia(
            caso_id=peca.caso_id,
            peca_origem_id=peca.id,
            peca_destino_id=destino.id if destino else None,
            id_mencionado=id_mencionado,
        ))
    db.commit()


def _resolver_referencias_pendentes(db: Session, caso_id: uuid.UUID) -> None:
    """Ao final do lote, tenta resolver referências que apontavam para peças ainda não
    existentes no momento em que foram registradas (menções a peças futuras/posteriores)."""
    pendentes = (
        db.query(AutosIAReferencia)
        .filter(AutosIAReferencia.caso_id == caso_id, AutosIAReferencia.peca_destino_id.is_(None))
        .all()
    )
    if not pendentes:
        return
    pecas_com_id = (
        db.query(AutosIAPeca)
        .filter(AutosIAPeca.caso_id == caso_id, AutosIAPeca.id_processual.isnot(None))
        .all()
    )
    mapa_normalizado = {_normalizar_id(p.id_processual): p for p in pecas_com_id if p.id_processual}
    for ref in pendentes:
        destino = mapa_normalizado.get(_normalizar_id(ref.id_mencionado))
        if destino and destino.id != ref.peca_origem_id:
            ref.peca_destino_id = destino.id
    db.commit()


def processar_documento(db: Session, documento_id: uuid.UUID) -> None:
    doc = db.query(AutosIADocumento).filter(AutosIADocumento.id == documento_id).first()
    if not doc:
        return
    caso = db.query(AutosIACaso).filter(AutosIACaso.id == doc.caso_id).first()

    doc.status = "processando"
    db.commit()

    try:
        content = Path(doc.caminho_arquivo).read_bytes()
        paginas = extrair_paginas(content, doc.pagina_inicio)
        doc.paginas_ocr = sum(1 for p in paginas if p.ocr_usado)

        segmentos, novo_buffer, novo_buffer_inicio = segmentar_paginas(
            paginas, caso.buffer_incompleto, caso.buffer_pagina_inicio
        )

        pecas_criadas: list[AutosIAPeca] = []
        for seg in segmentos:
            peca = AutosIAPeca(
                caso_id=caso.id,
                documento_id=doc.id,
                tipo=seg.tipo,
                titulo=seg.titulo,
                autor=seg.autor,
                data_peca=_parse_data(seg.data_peca),
                id_processual=seg.id_processual,
                pagina_inicio=seg.pagina_inicio,
                pagina_fim=seg.pagina_fim,
                texto_md=seg.texto_md,
                status="pendente_resumo",
            )
            db.add(peca)
            pecas_criadas.append(peca)
        db.commit()

        for peca in pecas_criadas:
            try:
                resultado = resumir_peca(peca.texto_md, peca.titulo, peca.tipo)
                peca.resumo = resultado.resumo
                peca.keywords = resultado.keywords
                peca.ids_mencionados = resultado.ids_mencionados
                peca.status = "resumida"
                db.commit()
                _persistir_referencias(db, peca, resultado.ids_mencionados)
            except Exception as exc:
                logger.error("Falha ao resumir peça %s: %s", peca.id, exc)
                peca.status = "erro"
                peca.erro_mensagem = str(exc)
                db.commit()

        _resolver_referencias_pendentes(db, caso.id)

        caso.buffer_incompleto = novo_buffer
        caso.buffer_pagina_inicio = novo_buffer_inicio
        caso.total_paginas = max(caso.total_paginas, doc.pagina_fim)
        db.commit()

        doc.status = "concluido"
        doc.pecas_geradas = len(pecas_criadas)
        db.commit()
    except Exception as exc:
        logger.error("Falha ao processar documento %s: %s", documento_id, exc)
        doc.status = "erro"
        doc.erro_mensagem = str(exc)
        db.commit()
