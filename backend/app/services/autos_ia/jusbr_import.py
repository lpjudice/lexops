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
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.andamento import AndamentoProcesso
from app.models.autos_ia import AutosIACaso, AutosIAPeca, AutosIAReferencia
from app.services.autos_ia.ingestao import (
    _eh_citacao_nao_indexavel,
    _normalizar_id,
    _persistir_referencias,
    _resolver_referencias_pendentes,
    resumir_pecas_em_paralelo,
)
from app.services.autos_ia.resumo import resumir_peca
from app.services.autos_ia.segmentacao import TIPOS_VALIDOS
from app.services.pdf_extract import remover_nul

logger = logging.getLogger(__name__)


def _commit_resiliente(db: Session) -> bool:
    """Commit "melhor esforço" para escritas puramente informativas (status,
    progresso, custo acumulado) — nunca a peça/andamento em si. O Postgres do
    Fly já derrubou conexão no meio de uma sincronização mais de uma vez
    (`OperationalError: server closed the connection unexpectedly`); antes,
    isso deixava a sessão inteira em rollback pendente e qualquer commit
    seguinte (inclusive o de status "erro" no except de baixo) falhava em
    cascata, derrubando a sincronização inteira em vez de só aquele item.
    Aqui, se o commit falhar, desfaz a transação e loga — a próxima operação
    real (criar/gravar uma peça) tenta de novo com uma conexão nova do pool
    (pool_pre_ping), sem carregar uma sessão já quebrada. Best-effort mesmo:
    se o PRÓPRIO rollback falhar (conexão realmente morta, não só a
    transação), só loga e engole — esta função nunca pode lançar, porque
    quem a chama (status/progresso/custo) não trata exceção nenhuma; deixar
    a sessão quebrada por mais uma chamada informativa é aceitável, o
    próximo commit de dado real (protegido por `_commit_com_retry`) que vai
    detectar e estourar de forma visível se a conexão continuar morta."""
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
    """Commit de dado real (texto extraído, peça criada) — ao contrário de
    `_commit_resiliente`, nunca pode simplesmente desistir e seguir em frente
    (perderia uma extração/resumo já pago). Uma sincronização real caiu
    exatamente aqui esta madrugada: o OCR de um documento demorou mais de uma
    hora (documento grande, várias páginas), terminou com sucesso, e no
    commit final do texto extraído o Postgres do Fly já tinha derrubado a
    conexão (`server closed the connection unexpectedly`) — sem retry, isso
    propaga e derruba a sincronização inteira, jogando fora o texto que
    acabou de ser extraído (o próximo retomar refaz o OCR do zero, pagando de
    novo). Uma retentativa após rollback dá tempo do pool trocar a conexão
    morta por uma nova (pool_pre_ping) antes de desistir de vez.

    Se o PRÓPRIO rollback falhar (não só o commit), a conexão está morta de
    verdade (não é um soluço passageiro) — nesse caso desiste na hora, sem
    gastar a(s) retentativa(s) restante(s) à toa: elas compartilhariam a
    MESMA sessão quebrada e falhariam do mesmo jeito. Visto de verdade numa
    sincronização real: sem isso, ~40 peças seguidas tentaram e falharam,
    uma por uma, antes do erro finalmente estourar — falhar rápido aqui
    chega no mesmo resultado (a rede de segurança do endpoint trata o
    resto) sem desperdiçar esse tempo todo."""
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


LIMIAR_CHARS_PARA_RESUMO_IA = 200

# PDPJ registra a hora de juntada por DOCUMENTO — documentos de uma mesma
# submissão (petição + anexos) tipicamente têm timestamps a poucos segundos
# um do outro, não idênticos ao segundo. Agrupar só por igualdade exata fazia
# petição e anexos ficarem cada um como peça própria, sem nenhum agrupamento.
# Uma janela de tolerância a partir do primeiro (âncora) documento do grupo
# resolve isso sem custo de IA nem depender de ordem perfeita.
LIMIAR_JANELA_PROTOCOLO_SEGUNDOS = 180

# Rede de segurança contra dados de origem patológicos: se muitos andamentos
# seguidos caírem na mesma chave de agrupamento (ex.: um lote digitalizado
# com data+descrição idênticas em dezenas de itens — visto de verdade no
# Apex, uma sincronização inteira ficou "sem novidade" na tela porque um
# grupo nunca fechava depois de 14/set, embora a leitura seguisse avançando
# por trás), o grupo trava aberto indefinidamente — nenhuma peça é
# persistida, e uma interrupção nesse meio tempo perde TODA a leitura desde
# o último grupo que fechou de verdade. Força o fechamento a cada N itens
# mesmo sem mudança de chave — nunca deveria disparar numa petição+anexos
# real (que tem poucos membros), só nesse cenário patológico.
LIMIAR_TAMANHO_MAXIMO_GRUPO = 20

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
    "documento de comprovação", "documento de comprovacao",
]


def _normalizar(texto: str) -> str:
    v = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in v if unicodedata.category(c) != "Mn")


def _classificar_tipo(andamento: AndamentoProcesso) -> str:
    # Checa anexo ANTES de tentar bater com PALAVRAS_TIPO: a descrição do
    # andamento no PDPJ é compartilhada por todo o lote de uma submissão
    # (petição + seus anexos têm a MESMA "Juntada de Petição de X..."), então
    # "petiç" bate igual em todo mundo — sem essa checagem, cada comprovante/
    # procuração do lote também virava tipo="peticao" só por causa da
    # descrição do lote, e um deles podia acabar virando o "principal" do
    # grupo antes de qualquer correção (reproduzido de verdade no Apex: um
    # "Documento de comprovação" venceu o "Pedido de Providências" real).
    if _eh_provavel_anexo(andamento):
        return "documento"
    base = _normalizar(f"{andamento.tipo or ''} {andamento.descricao or ''}")
    for tipo, palavras in PALAVRAS_TIPO.items():
        if any(_normalizar(p) in base for p in palavras):
            return tipo
    return "outro"


def _eh_provavel_anexo(andamento: AndamentoProcesso) -> bool:
    base = _normalizar(f"{andamento.descricao or ''} {andamento.arquivo_nome or ''}")
    return any(_normalizar(p) in base for p in PALAVRAS_ANEXO)


def _obter_bytes(andamento: AndamentoProcesso, on_status=None, deve_parar=None) -> bytes | None:
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
                return baixar_arquivo_por_id(file_id, on_status=on_status, deve_parar=deve_parar)
        except Exception as exc:
            logger.warning("Falha ao baixar do Drive o andamento %s: %s", andamento.id, exc)

    return None


def _extrair_texto(
    conteudo: bytes, nome_arquivo: str | None, on_custo=None, on_status=None, deve_parar=None,
) -> str:
    if nome_arquivo and nome_arquivo.lower().endswith((".html", ".htm")):
        try:
            from bs4 import BeautifulSoup
            return remover_nul(BeautifulSoup(conteudo, "html.parser").get_text("\n").strip())
        except Exception as exc:
            logger.warning("Falha ao extrair texto de HTML: %s", exc)
            return ""

    from app.services.autos_ia.ocr_providers import ocr_pagina_rotativo
    from app.services.pdf_extract import extrair_texto_pdf
    return extrair_texto_pdf(
        conteudo, on_custo=on_custo, ocr_pagina=ocr_pagina_rotativo, on_status=on_status, deve_parar=deve_parar,
    )


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
        db.refresh(caso)
        if caso.ultimo_sync_status != "cancelado":
            caso.ultimo_sync_status = "ok"
            caso.ultimo_sync_mensagem = f"{novas} peça(s) nova(s) importada(s)."
    except Exception as exc:
        logger.warning("Autos IA: erro ao sincronizar caso %s: %s", caso.id, exc)
        caso.ultimo_sync_status = "erro"
        caso.ultimo_sync_mensagem = str(exc)
    finally:
        caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
        db.commit()


def atualizar_metadados_jusbr(db: Session, caso: AutosIACaso, session_data: dict | None) -> None:
    """Só consulta o jus.br pra atualizar metadados dos andamentos já conhecidos
    (em especial a hora de protocolo — ver protocolado_em) e cadastrar andamentos
    novos como pendentes — sem processar nenhum em peça. Zero custo de IA: é só
    a consulta em si (rede) e o backfill/cadastro no banco. Útil pra testar o
    agrupamento por hora de protocolo (ver reagrupar_pecas_jusbr) sem forçar o
    processamento de um backlog grande de documentos pendentes de uma vez."""
    from app.models.processo import Processo
    from app.services.consulta_processual.orchestrator import sincronizar_processo_jusbr

    processo = db.query(Processo).filter(Processo.id == caso.processo_id).first()
    if not processo:
        caso.ultimo_sync_status = "erro"
        caso.ultimo_sync_mensagem = "Processo vinculado não encontrado."
        caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
        db.commit()
        return
    if not session_data:
        caso.ultimo_sync_status = "erro"
        caso.ultimo_sync_mensagem = "Sessão do jus.br não encontrada — cole o token novamente."
        caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
        db.commit()
        return

    try:
        import asyncio
        asyncio.run(sincronizar_processo_jusbr(processo, db, session_data=session_data))
        caso.ultimo_sync_status = "ok"
        caso.ultimo_sync_mensagem = (
            "Metadados atualizados (hora de protocolo etc.) — nenhuma peça nova foi processada."
        )
    except Exception as exc:
        logger.warning("Autos IA: erro ao atualizar metadados do caso %s: %s", caso.id, exc)
        caso.ultimo_sync_status = "erro"
        caso.ultimo_sync_mensagem = str(exc)
    finally:
        caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
        db.commit()


def reagrupar_pecas_jusbr(db: Session, caso: AutosIACaso) -> int:
    """Reaplica o agrupamento petição/anexo nas peças JÁ IMPORTADAS do jus.br/
    Drive deste caso, preferindo a hora de protocolo quando disponível — sem
    chamar IA nem a rede, só reorganiza peca_pai_id entre peças que já existem
    (o resumo/keywords de cada uma não mudam). Também corrige o tipo de
    qualquer peça marcada "peticao" cujo nome/descrição bata com um sinal de
    anexo explícito (procuração, comprovante, "Documento de Comprovação"...)
    pra "documento" — a classificação por conteúdo da IA (rodada uma vez,
    antes deste sinal existir) pode ter errado nesses casos. Retorna quantas
    peças tiveram o pai reatribuído ou o tipo corrigido."""
    from datetime import date

    pecas = (
        db.query(AutosIAPeca)
        .filter(AutosIAPeca.caso_id == caso.id, AutosIAPeca.andamento_id.isnot(None))
        .all()
    )
    if not pecas:
        return 0

    andamentos = {
        a.id: a for a in db.query(AndamentoProcesso)
        .filter(AndamentoProcesso.id.in_([p.andamento_id for p in pecas]))
        .all()
    }

    reagrupadas = 0

    # Corrige o tipo ANTES de escolher o principal de cada grupo — não depois.
    # A descrição do andamento no PDPJ é compartilhada por toda uma submissão
    # (petição + anexos têm a MESMA "Juntada de Petição de X..."), então um
    # "Documento de comprovação" podia vir com tipo="peticao" (herdado de
    # _classificar_tipo na importação original, antes desta função existir)
    # e, por estar mais cedo na ordem do grupo, virar o principal ANTES da
    # correção abaixo ter chance de rebaixá-lo — a correção rodava depois,
    # tarde demais pra mudar quem já tinha sido escolhido (reproduzido de
    # verdade no Apex: um comprovante venceu a petição real do lote).
    for p in pecas:
        a = andamentos.get(p.andamento_id)
        if a and p.tipo == "peticao" and _eh_provavel_anexo(a):
            p.tipo = "documento"
            reagrupadas += 1

    DATA_MAX = date(9999, 12, 31)
    DT_MAX = datetime(9999, 12, 31, tzinfo=timezone.utc)

    def _ordenar(p: AutosIAPeca):
        a = andamentos.get(p.andamento_id)
        return (
            (a.data_andamento if a else None) or DATA_MAX,
            (a.protocolado_em if a else None) or DT_MAX,
            p.criado_em,
        )

    pecas_ordenadas = sorted(pecas, key=_ordenar)

    # Mesma janela de tolerância usada na importação (ver LIMIAR_JANELA_
    # PROTOCOLO_SEGUNDOS): documentos de uma mesma submissão têm timestamps a
    # poucos segundos um do outro, não necessariamente idênticos.
    grupos: list[list[AutosIAPeca]] = []
    grupo_atual: list[AutosIAPeca] = []
    ancora_protocolo: datetime | None = None
    ancora_dia = None
    chave_atual = None
    for p in pecas_ordenadas:
        a = andamentos.get(p.andamento_id)
        if a and a.protocolado_em:
            continua_grupo_protocolo = (
                ancora_protocolo is not None
                and ancora_dia == a.data_andamento
                and (a.protocolado_em - ancora_protocolo).total_seconds() <= LIMIAR_JANELA_PROTOCOLO_SEGUNDOS
            )
            if not continua_grupo_protocolo:
                ancora_protocolo = a.protocolado_em
                ancora_dia = a.data_andamento
            chave = ("protocolo", ancora_protocolo, ancora_dia)
        else:
            ancora_protocolo = None
            ancora_dia = None
            chave = ("descricao", a.data_andamento if a else None, (a.descricao or "").strip() if a else "")

        if chave_atual is not None and chave != chave_atual:
            grupos.append(grupo_atual)
            grupo_atual = []
        chave_atual = chave
        grupo_atual.append(p)
    if grupo_atual:
        grupos.append(grupo_atual)

    for membros in grupos:
        if len(membros) == 1:
            if membros[0].peca_pai_id is not None:
                membros[0].peca_pai_id = None
                reagrupadas += 1
            continue

        # Lógica processual, não só ordem de submissão: prefere como principal
        # um membro já classificado como "peticao" de verdade — só cai pra
        # "primeiro que não bate com sinal de anexo" quando nenhum membro
        # classifica como petição (certidões/procurações não flagadas como
        # anexo não podem "furar a fila" na frente da petição real do grupo).
        principal = (
            next((m for m in membros if m.tipo == "peticao"), None)
            or next(
                (m for m in membros if (a := andamentos.get(m.andamento_id)) is None or not _eh_provavel_anexo(a)),
                None,
            )
            or membros[0]
        )

        if principal.peca_pai_id is not None:
            principal.peca_pai_id = None
            reagrupadas += 1
        for m in membros:
            if m is principal:
                continue
            if m.peca_pai_id != principal.id:
                m.peca_pai_id = principal.id
                reagrupadas += 1

    db.commit()
    # Reaproveita o clique em "Reagrupar" pra também tentar resolver de novo
    # as referências (menções a outros IDs) que ficaram sem peça de destino —
    # útil sobretudo depois da correção do fix de formato "id. NNNNN" em
    # _normalizar_id, que agora resolve referências que antes nunca batiam.
    _resolver_referencias_pendentes(db, caso.id)
    return reagrupadas


def recalcular_ids_processuais(db: Session, caso: AutosIACaso) -> tuple[int, int]:
    """Backfill de id_processual pras peças já importadas deste caso, puxando
    o documento_id que o jus.br já entrega pronto no andamento (a mesma fonte
    usada em _criar_peca pra peças novas) — sem chamar IA, sem reler nada, sem
    mexer em peca_pai_id/tipo (ao contrário de reagrupar_pecas_jusbr, que
    reatribui isso e desfaria uma reorganização manual feita pelo usuário).
    Corrige tanto peças sem id_processual quanto as que ficaram com um número
    curto/local errado (ex.: "107", "Evento 57") vindo do palpite da IA antes
    dessa fonte existir — e quando não há documento_id disponível pra corrigir
    (andamento sem essa informação), LIMPA um id_processual que não pareça um
    ID de peça de verdade (mesma regra de _eh_citacao_nao_indexavel: só dígitos
    puros de 6+ conta), pra não deixar lixo tipo "107" na tela como se fosse um
    ID válido. Por fim, apaga referências já persistidas que continuam sem
    destino E não são mais indexáveis pela regra atual (jurisprudência,
    número de processo, texto livre) — ruído que uma versão antiga desta
    função persistiu antes do filtro existir. Retorna (peças atualizadas,
    referências reconectadas)."""
    antes_nao_localizadas = (
        db.query(AutosIAReferencia)
        .filter(AutosIAReferencia.caso_id == caso.id, AutosIAReferencia.peca_destino_id.is_(None))
        .count()
    )

    pecas = (
        db.query(AutosIAPeca)
        .filter(AutosIAPeca.caso_id == caso.id, AutosIAPeca.andamento_id.isnot(None))
        .all()
    )
    andamentos = {
        a.id: a for a in db.query(AndamentoProcesso)
        .filter(AndamentoProcesso.id.in_([p.andamento_id for p in pecas]))
        .all()
    }
    atualizadas = 0
    for peca in pecas:
        andamento = andamentos.get(peca.andamento_id)
        documento_id = andamento.documento_id[:100] if andamento and andamento.documento_id else None
        if documento_id:
            if peca.id_processual != documento_id:
                peca.id_processual = documento_id
                atualizadas += 1
        elif peca.id_processual:
            normalizado = _normalizar_id(peca.id_processual)
            if not (normalizado.isdigit() and len(normalizado) >= 6):
                peca.id_processual = None
                atualizadas += 1
    db.commit()

    _resolver_referencias_pendentes(db, caso.id)

    pendentes = (
        db.query(AutosIAReferencia)
        .filter(AutosIAReferencia.caso_id == caso.id, AutosIAReferencia.peca_destino_id.is_(None))
        .all()
    )
    for ref in pendentes:
        if _eh_citacao_nao_indexavel(ref.id_mencionado):
            db.delete(ref)
    db.commit()

    depois_nao_localizadas = (
        db.query(AutosIAReferencia)
        .filter(AutosIAReferencia.caso_id == caso.id, AutosIAReferencia.peca_destino_id.is_(None))
        .count()
    )
    return atualizadas, antes_nao_localizadas - depois_nao_localizadas


def reler_peca(db: Session, peca: AutosIAPeca) -> None:
    """Rebaixa e reprocessa UMA peça específica que falhou (ou ficou
    incompleta) na leitura original — baixa de novo do Drive (já com o fix de
    Google Doc/Planilha/Apresentação nativos, ver google_drive.
    baixar_arquivo_por_id) e roda a IA de resumo só nela. Sempre uma peça de
    cada vez: nunca reprocessa o caso inteiro, só o que pontualmente falhou —
    pedido do Lucas pra poder corrigir leituras ruins sem sobrecarregar o
    sistema de novo."""
    if not peca.andamento_id:
        raise ValueError("Esta peça não veio do jus.br — releitura ainda não é suportada para uploads manuais.")
    andamento = db.query(AndamentoProcesso).filter(AndamentoProcesso.id == peca.andamento_id).first()
    if not andamento:
        raise ValueError("Andamento de origem não encontrado.")

    conteudo = _obter_bytes(andamento)
    if not conteudo:
        raise ValueError("Não foi possível baixar o arquivo do Drive novamente.")
    texto = _extrair_texto(conteudo, andamento.arquivo_nome)
    if not texto or not texto.strip():
        raise ValueError("O arquivo foi baixado, mas não foi possível extrair texto dele.")
    peca.texto_md = remover_nul(texto)

    resultado = resumir_peca(peca.texto_md, peca.titulo, peca.tipo)
    peca.resumo = resultado.resumo
    peca.keywords = [k[:100] for k in (resultado.keywords or [])]
    peca.ids_mencionados = [i[:100] for i in (resultado.ids_mencionados or [])]
    peca.custo_usd = (peca.custo_usd or 0) + resultado.custo_usd
    peca.status = "resumida"
    peca.erro_mensagem = None
    if not peca.autor and resultado.peticionante:
        peca.autor = resultado.peticionante[:255]
    if resultado.id_proprio and not peca.id_processual:
        peca.id_processual = resultado.id_proprio[:100]
    if peca.peca_pai_id is None:
        peca.tipo = resultado.tipo

    caso = db.query(AutosIACaso).filter(AutosIACaso.id == peca.caso_id).first()
    if caso:
        caso.custo_usd_total = (caso.custo_usd_total or 0) + resultado.custo_usd
    db.commit()

    # Apaga as referências antigas desta peça antes de persistir as novas —
    # senão uma releitura duplicava toda menção que já tinha sido salva na
    # primeira leitura (mesma origem, texto novo, IDs mencionados diferentes).
    db.query(AutosIAReferencia).filter(AutosIAReferencia.peca_origem_id == peca.id).delete()
    db.commit()
    _persistir_referencias(db, peca, peca.ids_mencionados)


def reler_pecas_pendentes(db: Session, caso: AutosIACaso) -> tuple[int, int]:
    """Roda reler_peca em TODAS as peças deste caso que ficaram com
    erro_mensagem (falha de leitura) — inclui as que já viraram "resumida" com
    um resumo genérico (o resumo da IA não falha, só fica pobre, então
    status sozinho não identifica essas — só erro_mensagem, que a rotina de
    resumo normal nunca limpa). Sequencial, uma peça de cada vez (rede + IA
    por peça) — pedido do Lucas pra não sobrecarregar o sistema de novo como
    uma sincronização paralela faria. Retorna (relidas com sucesso, falharam
    de novo)."""
    pendentes = (
        db.query(AutosIAPeca)
        .filter(
            AutosIAPeca.caso_id == caso.id,
            AutosIAPeca.andamento_id.isnot(None),
            AutosIAPeca.erro_mensagem.isnot(None),
        )
        .all()
    )
    if not pendentes:
        return 0, 0

    caso.sync_etapa = "resumindo"
    caso.sync_total_itens = len(pendentes)
    caso.sync_itens_processados = 0
    db.commit()

    sucesso = 0
    falha = 0
    for i, peca in enumerate(pendentes, start=1):
        if _cancelar_sync_solicitado(db, caso):
            break
        peca_id = peca.id
        # Sessão dedicada por item, em vez de reusar `db` pro lote inteiro:
        # reler_peca pode ficar bastante tempo numa chamada externa (Drive
        # ou IA), segurando a conexão do Postgres o tempo todo. Com uma
        # sessão só pra todo o lote, essa conexão ficava presa pela duração
        # do backlog inteiro — combinado com outras abas abertas, isso
        # esgotava o pool de conexões e derrubava até o login (mesmo
        # sintoma já documentado em app/database.py). Sessão por item limita
        # o pior caso a UM item, e uma conexão morta aqui não derruba o
        # resto do lote: a próxima iteração já abre uma sessão nova.
        db_item = SessionLocal()
        try:
            peca_item = db_item.query(AutosIAPeca).filter(AutosIAPeca.id == peca_id).first()
            if peca_item is None:
                continue
            reler_peca(db_item, peca_item)
            sucesso += 1
        except Exception as exc:
            logger.warning("Falha ao reler peça %s em lote: %s", peca_id, exc)
            try:
                db_item.rollback()
                peca_item = db_item.query(AutosIAPeca).filter(AutosIAPeca.id == peca_id).first()
                if peca_item is not None:
                    peca_item.erro_mensagem = str(exc)[:2000]
                    db_item.commit()
            except Exception:
                logger.exception("Falha ao gravar erro da peça %s (conexão instável?) — segue pra próxima", peca_id)
            falha += 1
        finally:
            db_item.close()
        caso.sync_itens_processados = i
        _commit_resiliente(db)

    _resolver_referencias_pendentes(db, caso.id)
    return sucesso, falha


def importar_apenas_existentes(db: Session, caso: AutosIACaso) -> None:
    """Só importa os andamentos/documentos que o jus.br JÁ baixou pro processo
    vinculado — sem chamar DataJud/jus.br ao vivo. Usado no backfill inicial
    (ex.: caso com centenas de documentos já baixados por outra rotina) e no
    botão "Importar documentos existentes", quando não faz sentido esperar uma
    sincronização de rede só pra reler o que já está salvo."""
    try:
        novas = importar_andamentos_pendentes(db, caso)
        db.refresh(caso)
        if caso.ultimo_sync_status != "cancelado":
            caso.ultimo_sync_status = "ok"
            caso.ultimo_sync_mensagem = f"{novas} peça(s) importada(s) a partir dos documentos já baixados."
    except Exception as exc:
        logger.warning("Autos IA: erro ao importar existentes do caso %s: %s", caso.id, exc)
        caso.ultimo_sync_status = "erro"
        caso.ultimo_sync_mensagem = str(exc)
    finally:
        caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
        db.commit()


def listar_andamentos_pendentes(db: Session, caso: AutosIACaso) -> list[AndamentoProcesso]:
    """Andamentos do processo vinculado ainda não trazidos como peça para este
    caso — mesma consulta usada pela importação e pela estimativa prévia, pra
    não haver divergência entre o que se estima e o que de fato é processado."""
    if not caso.processo_id:
        return []

    ja_importados = {
        row[0] for row in db.query(AutosIAPeca.andamento_id)
        .filter(AutosIAPeca.caso_id == caso.id, AutosIAPeca.andamento_id.isnot(None))
        .all()
    }

    query = db.query(AndamentoProcesso).filter(AndamentoProcesso.processo_id == caso.processo_id)
    if ja_importados:
        query = query.filter(~AndamentoProcesso.id.in_(ja_importados))
    return query.order_by(
        AndamentoProcesso.data_andamento.asc().nulls_last(),
        AndamentoProcesso.protocolado_em.asc().nulls_last(),
        AndamentoProcesso.created_at.asc(),
    ).all()


def _cancelar_sync_solicitado(db: Session, caso: AutosIACaso) -> bool:
    db.refresh(caso)
    return caso.sync_cancelar


def _criar_verificador_pular(db: Session, caso: AutosIACaso, intervalo_segundos: float = 1.0):
    """Cria um `deve_parar()` para passar ao download/OCR do documento atual —
    checa a flag `sync_pular_atual` (endpoint /pular-documento-atual), mas no
    máximo 1x por `intervalo_segundos`: sem esse limite, chamar isso a cada
    chunk de um download (podem ser dezenas por segundo) bateria no banco
    demais vezes à toa, agravando exatamente o esgotamento de conexão que já
    causou problema esta madrugada."""
    ultimo_check = 0.0

    def _deve_parar() -> bool:
        nonlocal ultimo_check
        agora = time.monotonic()
        if agora - ultimo_check < intervalo_segundos:
            return False
        ultimo_check = agora
        db.refresh(caso)
        return caso.sync_pular_atual

    return _deve_parar


def _retomar_pecas_pendentes(db: Session, caso: AutosIACaso) -> int:
    """Retoma peças já criadas (desta caso, de uma execução anterior cancelada
    ou que falhou) que ainda não foram resumidas, antes de importar andamentos
    novos — assim um "importar existentes" depois de um cancelamento primeiro
    termina o que ficou pra trás em vez de deixar pra sempre como pendente.

    Só peças de origem jus.br/Drive (`andamento_id` preenchido) — peças de um
    upload manual cancelado têm seu próprio fluxo de retomada, por documento
    (POST /documentos/{id}/retomar), pra manter os contadores de cada
    AutosIADocumento consistentes com o que de fato foi resumido."""
    pendentes = (
        db.query(AutosIAPeca)
        .filter(
            AutosIAPeca.caso_id == caso.id,
            AutosIAPeca.andamento_id.isnot(None),
            AutosIAPeca.status.in_(["pendente_resumo", "erro"]),
        )
        .all()
    )
    if not pendentes:
        return 0

    caso.sync_etapa = "resumindo"
    caso.sync_total_itens = len(pendentes)
    caso.sync_itens_processados = 0
    db.commit()

    def _progresso(feitas: int) -> None:
        caso.sync_itens_processados = feitas
        _commit_resiliente(db)

    def _custo(valor: float) -> None:
        caso.custo_usd_total = (caso.custo_usd_total or 0) + valor
        _commit_resiliente(db)

    def _cancelar() -> bool:
        return _cancelar_sync_solicitado(db, caso)

    def _status(msg: str) -> None:
        caso.sync_detalhe = msg[:500]
        _commit_resiliente(db)

    resumir_pecas_em_paralelo(
        db, pendentes, on_progresso=_progresso, on_custo=_custo, deve_cancelar=_cancelar, on_status=_status,
    )
    _resolver_referencias_pendentes(db, caso.id)
    return len(pendentes)


def contar_pecas_pendentes_resumo(db: Session, caso: AutosIACaso) -> int:
    """Quantas peças já lidas (texto extraído, já viraram peça) ainda esperam
    o resumo por IA — o backlog que `resumir_pendentes_agora` processa sem
    precisar reler nada. Pedido do Lucas pra ter visibilidade desse número
    sem precisar esperar uma sincronização inteira de novos andamentos."""
    return (
        db.query(AutosIAPeca)
        .filter(
            AutosIAPeca.caso_id == caso.id,
            AutosIAPeca.andamento_id.isnot(None),
            AutosIAPeca.status.in_(["pendente_resumo", "erro"]),
        )
        .count()
    )


def resumir_pendentes_agora(db: Session, caso: AutosIACaso) -> int:
    """Só resume o backlog de peças já lidas mas ainda não resumidas — sem
    consultar jus.br/PDPJ nem ler nenhum andamento novo. Pedido do Lucas: uma
    sincronização grande interrompida no meio da LEITURA pode deixar
    centenas de peças já lidas esperando resumo (ver _retomar_pecas_
    pendentes) — antes, só rodava automaticamente no início da PRÓXIMA
    sincronização completa; isso deixa acionar só essa etapa, sem esperar
    reler o resto dos documentos pendentes."""
    caso.sync_cancelar = False
    caso.sync_iniciado_em = datetime.now(timezone.utc)
    db.commit()

    total = _retomar_pecas_pendentes(db, caso)

    caso.ultimo_sync_status = "cancelado" if _cancelar_sync_solicitado(db, caso) else "ok"
    caso.ultimo_sync_mensagem = f"{total} peça(s) pendente(s) resumida(s)." if total else "Nenhuma peça pendente de resumo."
    caso.sync_etapa = None
    caso.sync_total_itens = None
    caso.sync_itens_processados = None
    caso.sync_detalhe = None
    caso.ultima_sincronizacao_em = datetime.now(timezone.utc)
    db.commit()
    return total


def importar_andamentos_pendentes(db: Session, caso: AutosIACaso) -> int:
    """Importa como peças os andamentos do processo vinculado ainda não trazidos
    para este caso. Lê e cria as peças em grupos pequenos (streaming, não tudo
    de uma vez no final) para que o grafo/timeline reflitam o progresso real
    mesmo se a importação for cancelada no meio. Retorna quantas peças novas
    foram criadas (incluindo as retomadas de uma execução anterior)."""
    if not caso.processo_id:
        return 0

    caso.sync_cancelar = False
    caso.sync_iniciado_em = datetime.now(timezone.utc)
    db.commit()

    total_retomadas = _retomar_pecas_pendentes(db, caso)

    if _cancelar_sync_solicitado(db, caso):
        caso.ultimo_sync_status = "cancelado"
        caso.ultimo_sync_mensagem = f"Cancelado: {total_retomadas} peça(s) retomada(s)."
        caso.sync_etapa = None
        caso.sync_total_itens = None
        caso.sync_itens_processados = None
        caso.sync_detalhe = None
        db.commit()
        return total_retomadas

    pendentes = listar_andamentos_pendentes(db, caso)
    if not pendentes:
        caso.sync_etapa = None
        caso.sync_total_itens = None
        caso.sync_itens_processados = None
        caso.sync_detalhe = None
        db.commit()
        return total_retomadas

    caso.ultimo_sync_status = "processando"
    caso.sync_etapa = "lendo"
    caso.sync_total_itens = len(pendentes)
    caso.sync_itens_processados = 0
    db.commit()

    criadas: list[AutosIAPeca] = []
    grupo_atual: list[dict] = []
    chave_atual: tuple | None = None
    ancora_protocolo: datetime | None = None
    ancora_dia = None
    cancelado = False

    def _flush_grupo() -> None:
        nonlocal grupo_atual
        if not grupo_atual:
            return
        # Lógica processual, não só ordem de submissão: prefere como principal
        # um membro cuja classificação seja "peticao" de verdade — só cai pra
        # "primeiro que não bate com sinal de anexo" (procuração, comprovante,
        # "Documento de Comprovação"...) quando nenhum membro classifica como
        # petição (ex.: certidões e procurações não flagadas como anexo não
        # podem "furar a fila" na frente da petição real do grupo).
        principal = (
            next((m for m in grupo_atual if m["tipo"] == "peticao"), None)
            or next((m for m in grupo_atual if not m["eh_anexo"]), None)
            or grupo_atual[0]
        )
        peca_principal = _criar_peca(db, caso, principal, peca_pai_id=None)
        criadas.append(peca_principal)
        for membro in grupo_atual:
            if membro is principal:
                continue
            criadas.append(_criar_peca(db, caso, membro, peca_pai_id=peca_principal.id))
        _commit_com_retry(db)
        grupo_atual = []

    def _status_leitura(msg: str, _idx=None, _total=len(pendentes)) -> None:
        prefixo = f"Documento {_idx}/{_total}: " if _idx is not None else ""
        caso.sync_detalhe = f"{prefixo}{msg}"[:500]
        _commit_resiliente(db)

    for indice, andamento in enumerate(pendentes, start=1):
        # Sempre atualiza a mensagem de status ao iniciar o documento, mesmo
        # quando ele não precisa de OCR — sem isso, um documento com texto
        # nativo (a maioria) nunca chama _status_ocr, e a tela fica mostrando
        # o número do ÚLTIMO documento que precisou de OCR (que pode já ter
        # ficado várias dezenas de documentos para trás), dando a falsa
        # impressão de estar travado num documento antigo.
        _status_leitura(f"lendo {andamento.arquivo_nome or 'andamento sem arquivo'}...", indice, len(pendentes))
        conteudo = None
        texto = andamento.texto_extraido
        tem_arquivo = bool(andamento.arquivo_path or andamento.arquivo_drive_link)
        if not texto:
            def _status_ocr(msg: str, _i=indice, _n=len(pendentes)) -> None:
                _status_leitura(msg, _i, _n)
            _deve_pular_atual = _criar_verificador_pular(db, caso)
            conteudo = _obter_bytes(andamento, on_status=_status_ocr, deve_parar=_deve_pular_atual)
            if conteudo:
                def _custo_ocr(valor: float, _caso=caso) -> None:
                    _caso.custo_usd_total = (_caso.custo_usd_total or 0) + valor
                    _commit_resiliente(db)
                texto = _extrair_texto(
                    conteudo, andamento.arquivo_nome, on_custo=_custo_ocr, on_status=_status_ocr,
                    deve_parar=_deve_pular_atual,
                )
                if texto:
                    andamento.texto_extraido = texto
                    _commit_com_retry(db)
        # Confere (sem throttle, uma vez por documento) se "pular este documento"
        # foi pedido durante a leitura acima — consome a flag na hora pra não
        # aplicar ao PRÓXIMO documento sem querer.
        db.refresh(caso)
        pulado_pelo_usuario = caso.sync_pular_atual
        if pulado_pelo_usuario:
            caso.sync_pular_atual = False
            _commit_resiliente(db)

        # Só é "leitura incompleta" quando HÁ arquivo mas nada saiu dele (download
        # falhou, ou pypdf/pdfminer/OCR falharam todos) — não quando o andamento
        # nunca teve arquivo pra começo de conversa, nem quando foi pulado a
        # pedido do usuário (essa tem sua própria mensagem, ver _criar_peca).
        leitura_incompleta = tem_arquivo and not texto and not pulado_pelo_usuario
        if not texto:
            texto = remover_nul(andamento.descricao or "")

        paginas = _contar_paginas(conteudo, andamento.arquivo_nome)
        pagina_inicio = caso.total_paginas + 1
        caso.total_paginas += paginas

        item = {
            "andamento": andamento,
            "texto": texto,
            "leitura_incompleta": leitura_incompleta,
            "pulado_pelo_usuario": pulado_pelo_usuario,
            "tipo": _classificar_tipo(andamento),
            "eh_anexo": _eh_provavel_anexo(andamento),
            "pagina_inicio": pagina_inicio,
            "pagina_fim": pagina_inicio + paginas - 1,
        }
        # Preferência pela hora de protocolo (PDPJ/jus.br) pra agrupar petição+
        # anexos: documentos protocolados juntos, na mesma transação de juntada,
        # tipicamente vêm com timestamps a poucos segundos um do outro — não
        # necessariamente idênticos ao segundo — por isso usa uma janela de
        # tolerância a partir do primeiro (âncora) documento do grupo, em vez de
        # igualdade exata. Andamentos sem essa granularidade (DataJud, ou
        # sincronizados antes deste campo existir) caem no critério antigo por
        # data+descrição. Os dois nunca se misturam, então um grupo por
        # protocolo nunca "absorve" um grupo por descrição por engano.
        if andamento.protocolado_em:
            continua_grupo_protocolo = (
                ancora_protocolo is not None
                and ancora_dia == andamento.data_andamento
                and (andamento.protocolado_em - ancora_protocolo).total_seconds() <= LIMIAR_JANELA_PROTOCOLO_SEGUNDOS
            )
            if not continua_grupo_protocolo:
                ancora_protocolo = andamento.protocolado_em
                ancora_dia = andamento.data_andamento
            chave = ("protocolo", ancora_protocolo, ancora_dia)
        else:
            ancora_protocolo = None
            ancora_dia = None
            chave = ("descricao", andamento.data_andamento, (andamento.descricao or "").strip())
        # Andamentos vêm ordenados por data/hora de protocolo/criação, então itens
        # do mesmo grupo são sempre contíguos na lista — dá pra fechar (persistir)
        # um grupo assim que o próximo item muda de chave, em vez de esperar ler
        # tudo antes de criar qualquer peça.
        if chave_atual is not None and chave != chave_atual:
            _flush_grupo()
        chave_atual = chave
        grupo_atual.append(item)
        if len(grupo_atual) >= LIMIAR_TAMANHO_MAXIMO_GRUPO:
            logger.warning(
                "Grupo de agrupamento passou de %d itens sem fechar (andamento %s) — "
                "forçando fechamento; provável dado de origem com data/descrição repetidas.",
                LIMIAR_TAMANHO_MAXIMO_GRUPO, andamento.id,
            )
            _flush_grupo()
            chave_atual = None

        caso.sync_itens_processados = indice
        _commit_resiliente(db)

        if indice % 5 == 0 or indice == len(pendentes):
            if _cancelar_sync_solicitado(db, caso):
                cancelado = True
                break

    _flush_grupo()  # fecha o grupo em aberto mesmo se cancelou, pra não perder o que já foi lido

    if cancelado:
        caso.ultimo_sync_status = "cancelado"
        caso.ultimo_sync_mensagem = f"Cancelado: {len(criadas)} peça(s) lida(s) antes de parar (ainda sem resumo)."
        caso.sync_etapa = None
        caso.sync_total_itens = None
        caso.sync_itens_processados = None
        caso.sync_detalhe = None
        db.commit()
        return len(criadas) + total_retomadas

    pecas_curtas = [p for p in criadas if len(p.texto_md) < LIMIAR_CHARS_PARA_RESUMO_IA]
    pecas_para_ia = [p for p in criadas if p not in pecas_curtas]

    for peca in pecas_curtas:
        peca.resumo = peca.texto_md
        peca.keywords = []
        peca.ids_mencionados = []
        peca.status = "resumida"
    db.commit()

    caso.sync_etapa = "resumindo"
    caso.sync_total_itens = len(pecas_para_ia)
    caso.sync_itens_processados = 0
    db.commit()

    def _progresso_resumo(feitas: int) -> None:
        caso.sync_itens_processados = feitas
        _commit_resiliente(db)

    def _custo_resumo(valor: float) -> None:
        caso.custo_usd_total = (caso.custo_usd_total or 0) + valor
        _commit_resiliente(db)

    def _cancelar() -> bool:
        return _cancelar_sync_solicitado(db, caso)

    def _status_resumo(msg: str) -> None:
        caso.sync_detalhe = msg[:500]
        _commit_resiliente(db)

    resumir_pecas_em_paralelo(
        db, pecas_para_ia, on_progresso=_progresso_resumo, on_custo=_custo_resumo, deve_cancelar=_cancelar,
        on_status=_status_resumo,
    )

    _resolver_referencias_pendentes(db, caso.id)

    total = len(criadas) + total_retomadas
    if _cancelar_sync_solicitado(db, caso):
        caso.ultimo_sync_status = "cancelado"
        caso.ultimo_sync_mensagem = f"Cancelado: {total} peça(s) processada(s) antes de parar."
    else:
        caso.ultimo_sync_status = "ok"
        caso.ultimo_sync_mensagem = f"{total} peça(s) nova(s) importada(s)."
    caso.sync_etapa = None
    caso.sync_total_itens = None
    caso.sync_itens_processados = None
    caso.sync_detalhe = None
    db.commit()
    return total


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
        titulo=remover_nul((andamento.tipo or andamento.descricao or "Andamento sem título").strip())[:500],
        autor=None,
        data_peca=andamento.data_andamento,
        # andamento.documento_id É o número que outras peças citam no texto (ex.:
        # "Id. 103876454", "Num. 103876454") — confirmado auditando o Apex: 158
        # referências "não localizadas" eram exatamente isso, só que id_processual
        # tinha ficado None (ou um número curto/local errado, tipo "107", vindo do
        # palpite da IA abaixo) em vez do documento_id real já salvo no andamento.
        # A IA (resumo) só sobrescreve isso se documento_id não existir — ver
        # ResumoPeca.id_proprio em services/autos_ia/resumo.py e o guard em
        # ingestao.py (resumir/reclassificar).
        id_processual=(andamento.documento_id[:100] if andamento.documento_id else None),
        pagina_inicio=item["pagina_inicio"],
        pagina_fim=item["pagina_fim"],
        texto_md=remover_nul(item["texto"]) or "(sem texto extraído)",
        status="pendente_resumo",
        erro_mensagem=(
            "Leitura pulada a pedido do usuário — veja o arquivo completo no Drive; "
            "clique para reler o documento inteiro depois."
        ) if item.get("pulado_pelo_usuario") else (
            "Não foi possível ler o conteúdo do arquivo (download ou OCR falharam) — "
            "esta peça ficou só com a descrição do andamento, sem o texto do documento."
        ) if item.get("leitura_incompleta") else None,
    )
    db.add(peca)
    db.flush()
    return peca
