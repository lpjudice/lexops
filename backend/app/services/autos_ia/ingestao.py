"""Orquestra o processamento de um bloco de páginas recém-enviado:
extração de texto → segmentação em peças → resumo/keywords/IDs → referências.
"""
import logging
import re
import unicodedata
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.autos_ia import AutosIACaso, AutosIADocumento, AutosIAPeca, AutosIAReferencia
from app.services.autos_ia.extracao import extrair_paginas
from app.services.autos_ia.resumo import resumir_peca
from app.services.autos_ia.segmentacao import segmentar_paginas

logger = logging.getLogger(__name__)

# Chamadas de resumo por peça são independentes entre si (só leem, não escrevem
# no banco) — paralelizamos com um pool pequeno pra não estourar rate limit da
# API, mas ainda cortar bastante o tempo total em blocos com muitas peças.
RESUMO_MAX_WORKERS = 5


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


def resumir_pecas_em_paralelo(
    db: Session,
    pecas: list[AutosIAPeca],
    on_progresso: Callable[[int], None] | None = None,
    on_custo: Callable[[float], None] | None = None,
    deve_cancelar: Callable[[], bool] | None = None,
) -> None:
    """Resume várias peças concorrentemente (só a chamada à IA é paralela; toda
    escrita no banco acontece de volta na thread principal, sem sessão concorrente).

    Depois de cada peça concluída, se `deve_cancelar()` retornar True, para de
    aguardar/submeter novas peças — as que já estavam em voo terminam e têm seu
    resultado salvo normalmente, mas nenhuma peça nova é iniciada. As peças que
    nem chegaram a começar ficam com status "pendente_resumo", prontas para
    serem retomadas depois."""
    if not pecas:
        return

    with ThreadPoolExecutor(max_workers=min(RESUMO_MAX_WORKERS, len(pecas))) as executor:
        futuros = {
            executor.submit(resumir_peca, peca.texto_md, peca.titulo, peca.tipo): peca
            for peca in pecas
        }
        feitas = 0
        cancelado = False
        for futuro in as_completed(futuros):
            peca = futuros[futuro]
            try:
                resultado = futuro.result()
                peca.resumo = resultado.resumo
                peca.keywords = resultado.keywords
                peca.ids_mencionados = resultado.ids_mencionados
                peca.custo_usd = resultado.custo_usd
                peca.status = "resumida"
                if not peca.autor and resultado.peticionante:
                    peca.autor = resultado.peticionante[:255]
                # id_proprio (o número pelo qual a peça se autorreferencia) é mais
                # confiável que um ID interno do sistema de origem pra casar com
                # menções de outras peças — sobrescreve quando a IA encontrar um.
                if resultado.id_proprio:
                    peca.id_processual = resultado.id_proprio[:100]
                # Peça-mãe (não é anexo de outra): confia na classificação da IA, que
                # leu o texto inteiro — mais precisa que o rótulo bruto do tribunal ou
                # o palpite por palavra-chave usado antes de chamar a IA. Anexos ficam
                # com o tipo "documento" decidido no agrupamento (ver jusbr_import.py).
                if peca.peca_pai_id is None:
                    peca.tipo = resultado.tipo
                db.commit()
                _persistir_referencias(db, peca, resultado.ids_mencionados)
                if on_custo:
                    on_custo(resultado.custo_usd)
            except Exception as exc:
                logger.error("Falha ao resumir peça %s: %s", peca.id, exc)
                peca.status = "erro"
                peca.erro_mensagem = str(exc)
                db.commit()
            feitas += 1
            if on_progresso:
                on_progresso(feitas)
            if not cancelado and deve_cancelar and deve_cancelar():
                cancelado = True
                executor.shutdown(wait=False, cancel_futures=True)


def processar_documento(db: Session, documento_id: uuid.UUID) -> None:
    doc = db.query(AutosIADocumento).filter(AutosIADocumento.id == documento_id).first()
    if not doc:
        return
    caso = db.query(AutosIACaso).filter(AutosIACaso.id == doc.caso_id).first()

    doc.status = "processando"
    doc.etapa = "extraindo"
    db.commit()

    def _cancelado() -> bool:
        db.refresh(doc)
        return doc.cancelar

    def _marcar_cancelado() -> None:
        doc.status = "cancelado"
        doc.etapa = "cancelado"
        db.commit()

    def _progresso_extracao(feitas: int, total: int) -> None:
        if feitas % 10 == 0 or feitas == total:
            doc.paginas_processadas = feitas
            db.commit()

    def _progresso_segmentacao(feitas: int, total: int) -> None:
        doc.paginas_processadas = feitas
        db.commit()

    def _custo_extracao(valor: float) -> None:
        doc.custo_usd = (doc.custo_usd or 0) + valor
        caso.custo_usd_total = (caso.custo_usd_total or 0) + valor
        db.commit()

    def _custo_segmentacao(valor: float) -> None:
        doc.custo_usd = (doc.custo_usd or 0) + valor
        caso.custo_usd_total = (caso.custo_usd_total or 0) + valor
        db.commit()

    def _progresso_resumo(feitas: int) -> None:
        doc.pecas_resumidas = feitas
        db.commit()

    def _custo_resumo(valor: float) -> None:
        doc.custo_usd = (doc.custo_usd or 0) + valor
        caso.custo_usd_total = (caso.custo_usd_total or 0) + valor
        db.commit()

    try:
        content = Path(doc.caminho_arquivo).read_bytes()
        paginas = extrair_paginas(
            content, doc.pagina_inicio, on_progresso=_progresso_extracao, on_custo=_custo_extracao,
        )
        doc.paginas_ocr = sum(1 for p in paginas if p.ocr_usado)
        db.commit()

        if _cancelado():
            return _marcar_cancelado()

        doc.etapa = "segmentando"
        doc.paginas_processadas = 0
        db.commit()

        segmentos, novo_buffer, novo_buffer_inicio = segmentar_paginas(
            paginas, caso.buffer_incompleto, caso.buffer_pagina_inicio,
            on_progresso=_progresso_segmentacao, on_custo=_custo_segmentacao,
        )

        if _cancelado():
            return _marcar_cancelado()

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

        # Atualiza buffer/total_paginas do caso já aqui (não só no final) — assim,
        # se o cancelamento acontecer durante o resumo (a etapa mais demorada), a
        # continuação por página do caso não fica pra trás nem se perde.
        caso.buffer_incompleto = novo_buffer
        caso.buffer_pagina_inicio = novo_buffer_inicio
        caso.total_paginas = max(caso.total_paginas, doc.pagina_fim)
        doc.etapa = "resumindo"
        doc.pecas_geradas = len(pecas_criadas)
        doc.pecas_resumidas = 0
        db.commit()

        if _cancelado():
            return _marcar_cancelado()

        resumir_pecas_em_paralelo(
            db, pecas_criadas, on_progresso=_progresso_resumo, on_custo=_custo_resumo, deve_cancelar=_cancelado,
        )

        _resolver_referencias_pendentes(db, caso.id)

        if _cancelado():
            # As peças já resumidas continuam salvas; as que não chegaram a
            # começar ficam "pendente_resumo" para retomar depois.
            return _marcar_cancelado()

        doc.status = "concluido"
        doc.etapa = "concluido"
        db.commit()
    except Exception as exc:
        logger.error("Falha ao processar documento %s: %s", documento_id, exc)
        doc.status = "erro"
        doc.erro_mensagem = str(exc)
        db.commit()


def retomar_documento(db: Session, documento_id: uuid.UUID) -> None:
    """Retoma um documento cancelado (ou com erro) antes de terminar. Se o
    cancelamento aconteceu antes da segmentação (nenhuma peça criada ainda),
    reprocessa o bloco do zero; se já havia peças criadas, só retoma o resumo
    das que ainda estão pendentes — não repete extração nem segmentação."""
    doc = db.query(AutosIADocumento).filter(AutosIADocumento.id == documento_id).first()
    if not doc:
        return
    doc.cancelar = False
    db.commit()

    if doc.etapa not in ("segmentando", "resumindo", "concluido", "cancelado") or doc.pecas_geradas == 0:
        processar_documento(db, documento_id)
        return

    caso = db.query(AutosIACaso).filter(AutosIACaso.id == doc.caso_id).first()
    pendentes = (
        db.query(AutosIAPeca)
        .filter(AutosIAPeca.documento_id == doc.id, AutosIAPeca.status.in_(["pendente_resumo", "erro"]))
        .all()
    )
    if not pendentes:
        doc.status = "concluido"
        doc.etapa = "concluido"
        db.commit()
        return

    doc.status = "processando"
    doc.etapa = "resumindo"
    ja_resumidas = doc.pecas_geradas - len(pendentes)
    db.commit()

    def _cancelado() -> bool:
        db.refresh(doc)
        return doc.cancelar

    def _progresso(feitas: int) -> None:
        doc.pecas_resumidas = ja_resumidas + feitas
        db.commit()

    def _custo(valor: float) -> None:
        doc.custo_usd = (doc.custo_usd or 0) + valor
        caso.custo_usd_total = (caso.custo_usd_total or 0) + valor
        db.commit()

    resumir_pecas_em_paralelo(db, pendentes, on_progresso=_progresso, on_custo=_custo, deve_cancelar=_cancelado)
    _resolver_referencias_pendentes(db, caso.id)

    if _cancelado():
        doc.status = "cancelado"
        doc.etapa = "cancelado"
    else:
        doc.status = "concluido"
        doc.etapa = "concluido"
    db.commit()


def resetar_processamentos_travados(db: Session) -> int:
    """Chamado no startup do servidor: nenhuma tarefa em background sobrevive a
    um restart/deploy, então qualquer caso ou documento que ficou "processando"
    pertence a uma execução que foi interrompida à força (não a um cancelamento
    gracioso) — sem isso, o status fica preso em "processando" pra sempre,
    bloqueando novas sincronizações e a exclusão do caso. Retorna quantos itens
    foram destravados."""
    from datetime import datetime, timezone

    MENSAGEM = "Cancelado automaticamente: o servidor reiniciou durante o processamento."
    afetados = 0

    casos = db.query(AutosIACaso).filter(AutosIACaso.ultimo_sync_status == "processando").all()
    for caso in casos:
        caso.ultimo_sync_status = "cancelado"
        caso.ultimo_sync_mensagem = MENSAGEM
        caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
        caso.sync_etapa = None
        caso.sync_total_itens = None
        caso.sync_itens_processados = None
        caso.sync_cancelar = False
        afetados += 1

    documentos = db.query(AutosIADocumento).filter(AutosIADocumento.status == "processando").all()
    for doc in documentos:
        doc.status = "cancelado"
        doc.etapa = "cancelado"
        doc.cancelar = False
        doc.erro_mensagem = MENSAGEM
        afetados += 1

    if afetados:
        db.commit()
    return afetados
