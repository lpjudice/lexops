"""Orquestra o processamento de um bloco de páginas recém-enviado:
extração de texto → segmentação em peças → resumo/keywords/IDs → referências.
"""
import logging
import re
import time
import unicodedata
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.andamento import AndamentoProcesso
from app.models.autos_ia import AutosIACaso, AutosIADocumento, AutosIAPeca, AutosIAReferencia
from app.services.autos_ia.extracao import extrair_paginas
from app.services.autos_ia.resumo import reclassificar_peca, resumir_peca
from app.services.autos_ia.segmentacao import segmentar_paginas

logger = logging.getLogger(__name__)


def _commit_resiliente(db: Session) -> bool:
    """Commit "melhor esforço" para escritas informativas (progresso/custo) —
    nunca a peça em si. Ver mesma função em jusbr_import.py: sem isso, uma
    conexão que cai no meio (o Postgres do Fly já fez isso mais de uma vez)
    deixa a sessão em rollback pendente e qualquer commit seguinte falha em
    cascata, derrubando o lote inteiro em vez de só aquele item. Best-effort
    mesmo se o próprio rollback falhar: esta função nunca pode lançar, quem
    a chama (progresso/custo) não trata exceção — o próximo commit de dado
    real (`_commit_com_retry`) é quem detecta e estoura de forma visível se
    a conexão continuar morta."""
    try:
        db.commit()
        return True
    except Exception as exc:
        logger.warning("Falha ao gravar status/progresso (conexão instável?): %s", exc)
        try:
            db.rollback()
        except Exception:
            logger.exception("Rollback também falhou após commit informativo malsucedido")
        return False


def _commit_com_retry(db: Session, tentativas: int = 2, espera_segundos: float = 1.5) -> None:
    """Commit de dado real (resumo/keywords já pagos à IA) — ver mesma função
    em jusbr_import.py. Nunca desiste silenciosamente: uma retentativa após
    rollback dá tempo do pool trocar uma conexão morta do Postgres do Fly por
    uma nova antes de perder um resumo que já custou dinheiro pra gerar.

    Se o PRÓPRIO rollback falhar (não só o commit), a conexão está morta de
    verdade — desiste na hora em vez de gastar a(s) retentativa(s)
    restante(s) numa sessão que vai continuar quebrada. Visto de verdade
    numa sincronização real: sem isso, ~40 peças seguidas tentaram e
    falharam uma por uma antes do erro estourar — falhar rápido aqui chega
    no mesmo resultado (a rede de segurança do endpoint trata o resto) sem
    esse desperdício."""
    for tentativa in range(tentativas):
        try:
            db.commit()
            return
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                logger.error("Rollback falhou após commit malsucedido — conexão morta, desistindo já")
                raise
            if tentativa == tentativas - 1:
                raise
            logger.warning(
                "Commit falhou (tentativa %d/%d, conexão instável?), tentando de novo em %.1fs: %s",
                tentativa + 1, tentativas, espera_segundos, exc,
            )
            time.sleep(espera_segundos)


# Chamadas de resumo por peça são independentes entre si (só leem, não escrevem
# no banco) — paralelizamos com um pool pequeno pra não estourar rate limit da
# API, mas ainda cortar bastante o tempo total em blocos com muitas peças.
RESUMO_MAX_WORKERS = 5


_ROTULO_ID = re.compile(r"^(id\.?|evento|num\.?|número|protocolo)\s*n?\.?\s*(\d{6,})$", re.IGNORECASE)


def _normalizar_id(valor: str) -> str:
    """Normaliza um ID/referência textual para comparação tolerante a formatação
    (ex.: 'Evento 45', 'evento nº 045' e 'EVENTO-45' devem casar).

    Um rótulo como "id." antes do número (ex.: "id. 103876454") não é removido
    pela normalização abaixo — ela só tira símbolos/espaços, não palavras —
    então "id103876454" nunca batia com o alvo, guardado como "103876454"
    puro. Reproduzido de verdade no Apex: 99,5% das referências ficavam
    permanentemente "não localizadas" mesmo com o alvo já indexado. "Num."
    (rótulo do próprio jus.br pro número do evento/documento, tão comum
    quanto "Id.") ficou de fora dessa lista na primeira correção — auditoria
    posterior no Apex achou dezenas de "Num. NNNNNNN" com alvo já indexado
    ainda presos em "não localizado" só por causa disso. Só os rótulos
    id/evento/num/número/protocolo são tratados assim (número de 6+
    dígitos) — um "DOC. 2" ou "fls. 228" não é um ID de peça, é uma citação
    local/de página, e não deve virar um match forçado com qualquer coisa."""
    texto = valor.strip()
    rotulo = _ROTULO_ID.match(texto)
    if rotulo:
        texto = rotulo.group(2)
    v = unicodedata.normalize("NFD", texto.lower())
    v = "".join(c for c in v if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", v)


_PADRAO_FLS = re.compile(r"^fls?\.?\s*\d+", re.IGNORECASE)
_PADRAO_CNJ = re.compile(r"^\d{7}-?\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$")
_PADRAO_DOC_N = re.compile(r"^doc\.?\s*0*(\d+)(?:\.\d+)?$", re.IGNORECASE)
_PADRAO_ARQUIVO_DOC_N = re.compile(r"\(doc\.?\s*0*(\d+)\)", re.IGNORECASE)


_ID_MINIMO_DIGITOS = 6


def _eh_citacao_nao_indexavel(texto: str) -> bool:
    """Citações que por natureza nunca correspondem a uma peça indexada deste
    caso: número de página ("fls. 228/232" — aponta um trecho DENTRO de um
    documento já referenciado por outro ID, não um documento em si), número de
    processo no formato CNJ, e qualquer outra citação que não seja um ID de
    peça de verdade — jurisprudência (REsp, AREsp, Súmula, Informativo...),
    pareceres/decisões referidos por data ("Parecer do MP de 10/09/2026"),
    ou um número curto/local (2-3 dígitos) que não é o ID global do jus.br.

    A regra central: no PJE (nosso foco agora), um ID de peça É SEMPRE um
    número puro de 6+ dígitos (com ou sem rótulo "Id./Num./Evento/Protocolo"
    na frente — removido por _normalizar_id antes de chegar aqui). Qualquer
    citação cujo texto, depois de normalizado, sobre com UMA LETRA SEQUER
    (ex.: "REsp nº 2.164.771/SP", "CC nº 147.927/SP", "Súmula 417 STF") não é
    um ID de peça — é jurisprudência, número de processo ou texto livre, e
    não tem pra que virar um chip cinza "não localizado" pra sempre.
    "DOC. N" é a exceção: não é um ID global, mas resolve localmente contra
    os anexos do mesmo grupo (ver _resolver_doc_n_local) — precisa continuar
    indexável mesmo não sendo um número puro. Pedido do Lucas pra não ter
    ruído nas menções."""
    bruto = texto.strip()
    if _PADRAO_FLS.match(bruto):
        return True
    if _PADRAO_CNJ.match(bruto.replace(" ", "")):
        return True
    if _PADRAO_DOC_N.match(bruto):
        return False
    # Regra geral (cobre CNJ com rótulo na frente, jurisprudência, texto livre
    # etc. sem precisar de um padrão específico pra cada formato): um ID de
    # peça de verdade normaliza pra dígitos puros — sobrou letra, não é ID.
    normalizado = _normalizar_id(bruto)
    return not (normalizado.isdigit() and len(normalizado) >= _ID_MINIMO_DIGITOS)


def _grupo_da_peca(db: Session, peca: AutosIAPeca) -> list[AutosIAPeca]:
    """Peças do mesmo grupo petição+anexos de `peca` (a peça principal e
    todos os anexos sob ela) — usado pra resolver menções locais tipo
    "DOC. 5", que no jus.br não é um ID global, é só um trecho do nome do
    arquivo dentro de UMA submissão específica; o mesmo "DOC. 5" em outra
    submissão é outro documento completamente diferente."""
    raiz_id = peca.peca_pai_id or peca.id
    return (
        db.query(AutosIAPeca)
        .filter(AutosIAPeca.caso_id == peca.caso_id)
        .filter((AutosIAPeca.id == raiz_id) | (AutosIAPeca.peca_pai_id == raiz_id))
        .all()
    )


def _resolver_doc_n_local(db: Session, ref: AutosIAReferencia, peca_origem: AutosIAPeca) -> AutosIAPeca | None:
    """Resolve uma menção "DOC. N" contra o nome de arquivo dos anexos do
    MESMO grupo (petição + seus anexos) da peça que menciona — sem ID global,
    a única forma de saber a qual documento "DOC. 5" se refere é olhar quem
    são os anexos daquela submissão específica."""
    m = _PADRAO_DOC_N.match(ref.id_mencionado.strip())
    if not m:
        return None
    numero = m.group(1)
    grupo = _grupo_da_peca(db, peca_origem)
    andamento_ids = [p.andamento_id for p in grupo if p.andamento_id and p.id != peca_origem.id]
    if not andamento_ids:
        return None
    andamentos = db.query(AndamentoProcesso).filter(AndamentoProcesso.id.in_(andamento_ids)).all()
    for a in andamentos:
        arq = _PADRAO_ARQUIVO_DOC_N.search(a.arquivo_nome or "")
        if arq and arq.group(1).lstrip("0") == numero.lstrip("0"):
            candidata = next((p for p in grupo if p.andamento_id == a.id), None)
            if candidata:
                return candidata
    return None


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
        if _eh_citacao_nao_indexavel(id_mencionado):
            continue
        destino = mapa_normalizado.get(_normalizar_id(id_mencionado))
        ref = AutosIAReferencia(
            caso_id=peca.caso_id,
            peca_origem_id=peca.id,
            peca_destino_id=destino.id if destino else None,
            id_mencionado=id_mencionado[:100],
        )
        if not destino:
            destino_local = _resolver_doc_n_local(db, ref, peca)
            if destino_local:
                ref.peca_destino_id = destino_local.id
        db.add(ref)
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
    pecas_origem = {
        p.id: p for p in db.query(AutosIAPeca)
        .filter(AutosIAPeca.id.in_([r.peca_origem_id for r in pendentes]))
        .all()
    }
    for ref in pendentes:
        destino = mapa_normalizado.get(_normalizar_id(ref.id_mencionado))
        if not destino:
            origem = pecas_origem.get(ref.peca_origem_id)
            if origem:
                destino = _resolver_doc_n_local(db, ref, origem)
        if destino and destino.id != ref.peca_origem_id:
            ref.peca_destino_id = destino.id
    db.commit()


def resumir_pecas_em_paralelo(
    db: Session,
    pecas: list[AutosIAPeca],
    on_progresso: Callable[[int], None] | None = None,
    on_custo: Callable[[float], None] | None = None,
    deve_cancelar: Callable[[], bool] | None = None,
    on_status: Callable[[str], None] | None = None,
) -> None:
    """Resume várias peças concorrentemente (só a chamada à IA é paralela; toda
    escrita no banco acontece de volta na thread principal, sem sessão concorrente).

    Depois de cada peça concluída, se `deve_cancelar()` retornar True, para de
    aguardar/submeter novas peças — as que já estavam em voo terminam e têm seu
    resultado salvo normalmente, mas nenhuma peça nova é iniciada. As peças que
    nem chegaram a começar ficam com status "pendente_resumo", prontas para
    serem retomadas depois.

    `on_status(msg)`, quando informado, recebe uma frase curta a cada peça
    concluída (sucesso ou falha) — é o que dá visibilidade de qual peça está
    sendo resumida agora em vez de só um contador."""
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
                # keywords/ids_mencionados são ARRAY(String(100)) no banco — sem
                # truncar cada item, uma palavra-chave ou ID mais longo que o
                # normal derruba o commit (StringDataRightTruncation) e deixa a
                # sessão inteira em rollback pendente, quebrando em cascata todo
                # commit seguinte na mesma leva até a sincronização inteira cair.
                peca.keywords = [k[:100] for k in (resultado.keywords or [])]
                peca.ids_mencionados = [i[:100] for i in (resultado.ids_mencionados or [])]
                peca.custo_usd = resultado.custo_usd
                peca.status = "resumida"
                if not peca.autor and resultado.peticionante:
                    peca.autor = resultado.peticionante[:255]
                # id_proprio (o número que a própria IA leu no texto) só preenche
                # id_processual quando o jus.br não deu um documento_id confiável na
                # criação da peça (ver jusbr_import._criar_peca) — ex.: peça de upload
                # manual, sem andamento associado. Quando já existe um documento_id
                # real, ele nunca é sobrescrito pelo palpite da IA: auditoria no Apex
                # achou dezenas de casos em que a IA "achava" um número curto/local
                # (tipo "107" ou "Evento 57") em vez do ID de verdade.
                if resultado.id_proprio and not peca.id_processual:
                    peca.id_processual = resultado.id_proprio[:100]
                # Peça-mãe (não é anexo de outra): confia na classificação da IA, que
                # leu o texto inteiro — mais precisa que o rótulo bruto do tribunal ou
                # o palpite por palavra-chave usado antes de chamar a IA. Anexos ficam
                # com o tipo "documento" decidido no agrupamento (ver jusbr_import.py).
                if peca.peca_pai_id is None:
                    peca.tipo = resultado.tipo
                _commit_com_retry(db)
                _persistir_referencias(db, peca, peca.ids_mencionados)
                if on_custo:
                    on_custo(resultado.custo_usd)
                if on_status:
                    on_status(f"Resumida: {peca.titulo}")
            except Exception as exc:
                logger.error("Falha ao resumir peça %s: %s", peca.id, exc)
                # Um commit que falhou no flush deixa a sessão em rollback
                # pendente — sem isso, o commit de erro abaixo falha também, e
                # ISSO derruba a thread inteira (toda peça seguinte na mesma
                # leva também falha, em cascata).
                try:
                    db.rollback()
                except Exception:
                    # Não é só o commit desta peça que falhou — o PRÓPRIO
                    # rollback falhou, ou seja a conexão está morta de
                    # verdade (não um soluço passageiro). Continuar tentando
                    # as peças seguintes com essa mesma sessão quebrada só
                    # repete o mesmo erro em cascata — visto de verdade numa
                    # sincronização real, ~40 peças seguidas falharam assim
                    # antes do erro finalmente estourar. Falha rápido em vez
                    # disso: propaga pra fora do loop, a rede de segurança do
                    # endpoint trata o resto.
                    logger.error("Rollback falhou para a peça %s — conexão morta, desistindo do lote", peca.id)
                    raise
                try:
                    peca.status = "erro"
                    peca.erro_mensagem = str(exc)[:2000]
                    db.commit()
                except Exception:
                    logger.exception(
                        "Falha ao gravar status de erro da peça %s (conexão instável?) — "
                        "fica pendente_resumo para retomar depois", peca.id,
                    )
                    try:
                        db.rollback()
                    except Exception:
                        pass
                if on_status:
                    on_status(f"Falhou ao resumir: {peca.titulo} ({exc.__class__.__name__})")
            feitas += 1
            if on_progresso:
                on_progresso(feitas)
            if not cancelado and deve_cancelar and deve_cancelar():
                cancelado = True
                executor.shutdown(wait=False, cancel_futures=True)


def reclassificar_pecas_em_paralelo(
    db: Session,
    pecas: list[AutosIAPeca],
    on_progresso: Callable[[int], None] | None = None,
    on_custo: Callable[[float], None] | None = None,
    deve_cancelar: Callable[[], bool] | None = None,
) -> None:
    """Como resumir_pecas_em_paralelo, mas só atualiza tipo/autor/id_processual
    (via reclassificar_peca) — não regenera resumo/keywords/ids_mencionados, que
    já existem e não mudam. Usada para atualizar peças resumidas antes desses
    três campos existirem (ver /casos/{id}/reclassificar), a um custo bem menor
    que resumir tudo de novo."""
    if not pecas:
        return

    with ThreadPoolExecutor(max_workers=min(RESUMO_MAX_WORKERS, len(pecas))) as executor:
        futuros = {
            executor.submit(reclassificar_peca, peca.texto_md, peca.titulo, peca.tipo): peca
            for peca in pecas
        }
        feitas = 0
        cancelado = False
        for futuro in as_completed(futuros):
            peca = futuros[futuro]
            try:
                resultado = futuro.result()
                if not peca.autor and resultado.peticionante:
                    peca.autor = resultado.peticionante[:255]
                if resultado.id_proprio and not peca.id_processual:
                    peca.id_processual = resultado.id_proprio[:100]
                if peca.peca_pai_id is None:
                    peca.tipo = resultado.tipo
                peca.custo_usd = (peca.custo_usd or 0) + resultado.custo_usd
                db.commit()
                if on_custo:
                    on_custo(resultado.custo_usd)
            except Exception as exc:
                logger.error("Falha ao reclassificar peça %s: %s", peca.id, exc)
                # Mesmo motivo de resumir_pecas_em_paralelo: sem isso, uma sessão
                # que falhou no flush fica presa em rollback pendente e derruba
                # em cascata todo commit seguinte na mesma leva.
                db.rollback()
            feitas += 1
            if on_progresso:
                on_progresso(feitas)
            if not cancelado and deve_cancelar and deve_cancelar():
                cancelado = True
                executor.shutdown(wait=False, cancel_futures=True)


def reclassificar_caso(db: Session, caso: AutosIACaso) -> int:
    """Reclassifica as peças-mãe (não-anexo) já resumidas de um caso — tipo,
    peticionante e ID próprio, pelo conteúdo real, sem regenerar resumo/
    keywords. Retorna quantas peças foram reclassificadas."""
    from datetime import datetime, timezone

    pecas = (
        db.query(AutosIAPeca)
        .filter(
            AutosIAPeca.caso_id == caso.id,
            AutosIAPeca.peca_pai_id.is_(None),
            AutosIAPeca.status == "resumida",
        )
        .all()
    )
    if not pecas:
        caso.ultimo_sync_status = "ok"
        caso.ultimo_sync_mensagem = "Nenhuma peça elegível para reclassificar."
        caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
        db.commit()
        return 0

    caso.sync_cancelar = False
    caso.ultimo_sync_status = "processando"
    caso.sync_etapa = "reclassificando"
    caso.sync_total_itens = len(pecas)
    caso.sync_itens_processados = 0
    caso.sync_iniciado_em = datetime.now(timezone.utc)
    db.commit()

    def _progresso(feitas: int) -> None:
        caso.sync_itens_processados = feitas
        db.commit()

    def _custo(valor: float) -> None:
        caso.custo_usd_total = (caso.custo_usd_total or 0) + valor
        db.commit()

    def _cancelar() -> bool:
        db.refresh(caso)
        return caso.sync_cancelar

    reclassificar_pecas_em_paralelo(db, pecas, on_progresso=_progresso, on_custo=_custo, deve_cancelar=_cancelar)

    db.refresh(caso)
    cancelado = caso.sync_cancelar
    caso.ultimo_sync_status = "cancelado" if cancelado else "ok"
    caso.ultimo_sync_mensagem = (
        f"Cancelado: {caso.sync_itens_processados or 0}/{len(pecas)} peça(s) reclassificada(s)."
        if cancelado else f"{len(pecas)} peça(s) reclassificada(s)."
    )
    caso.sync_etapa = None
    caso.sync_total_itens = None
    caso.sync_itens_processados = None
    caso.sync_detalhe = None
    caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
    db.commit()
    return len(pecas)


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
        caso.sync_detalhe = None
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
