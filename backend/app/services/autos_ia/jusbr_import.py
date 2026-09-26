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
from datetime import datetime, timezone
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
    "documento de comprovação", "documento de comprovacao",
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


def _extrair_texto(conteudo: bytes, nome_arquivo: str | None, on_custo=None) -> str:
    if nome_arquivo and nome_arquivo.lower().endswith((".html", ".htm")):
        try:
            from bs4 import BeautifulSoup
            return BeautifulSoup(conteudo, "html.parser").get_text("\n").strip()
        except Exception as exc:
            logger.warning("Falha ao extrair texto de HTML: %s", exc)
            return ""

    from app.services.pdf_extract import extrair_texto_pdf
    return extrair_texto_pdf(conteudo, on_custo=on_custo)


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

    DATA_MAX = date(9999, 12, 31)
    DT_MAX = datetime(9999, 12, 31, tzinfo=timezone.utc)

    def _ordenar(p: AutosIAPeca):
        a = andamentos.get(p.andamento_id)
        return (
            (a.data_andamento if a else None) or DATA_MAX,
            (a.protocolado_em if a else None) or DT_MAX,
            p.criado_em,
        )

    def _chave(p: AutosIAPeca):
        a = andamentos.get(p.andamento_id)
        if a and a.protocolado_em:
            return ("protocolo", a.protocolado_em)
        return ("descricao", a.data_andamento if a else None, (a.descricao or "").strip() if a else "")

    pecas_ordenadas = sorted(pecas, key=_ordenar)

    grupos: list[list[AutosIAPeca]] = []
    grupo_atual: list[AutosIAPeca] = []
    chave_atual = None
    for p in pecas_ordenadas:
        chave = _chave(p)
        if chave_atual is not None and chave != chave_atual:
            grupos.append(grupo_atual)
            grupo_atual = []
        chave_atual = chave
        grupo_atual.append(p)
    if grupo_atual:
        grupos.append(grupo_atual)

    reagrupadas = 0
    for membros in grupos:
        if len(membros) == 1:
            if membros[0].peca_pai_id is not None:
                membros[0].peca_pai_id = None
                reagrupadas += 1
            continue

        primeiro_andamento = andamentos.get(membros[0].andamento_id)
        eh_grupo_protocolo = bool(primeiro_andamento and primeiro_andamento.protocolado_em)
        if eh_grupo_protocolo:
            # Mesma hora exata de protocolo: o primeiro protocolado é a petição
            # (regra combinada com o Lucas) — não depende de heurística de tipo,
            # exceto quando o próprio nome/descrição bate com um sinal de anexo
            # explícito (procuração, comprovante, "Documento de Comprovação"...),
            # caso em que nunca deve ser escolhido como principal do grupo.
            principal = next(
                (m for m in membros if (a := andamentos.get(m.andamento_id)) is None or not _eh_provavel_anexo(a)),
                membros[0],
            )
        else:
            # Fallback (sem hora de protocolo): usa a classificação real que a
            # IA já deu à peça (mais confiável que a palavra-chave usada na
            # importação original) — prefere a primeira que não seja "documento".
            principal = next((m for m in membros if m.tipo != "documento"), membros[0])

        if principal.peca_pai_id is not None:
            principal.peca_pai_id = None
            reagrupadas += 1
        for m in membros:
            if m is principal:
                continue
            if m.peca_pai_id != principal.id:
                m.peca_pai_id = principal.id
                reagrupadas += 1

    # Corrige o tipo mesmo fora de um grupo multi-membro (ex.: um "Documento de
    # Comprovação" protocolado sozinho, sem petição junto no mesmo grupo) —
    # esse sinal de nome/descrição é forte o bastante pra sobrepor uma
    # classificação de IA anterior.
    for p in pecas:
        a = andamentos.get(p.andamento_id)
        if a and p.tipo == "peticao" and _eh_provavel_anexo(a):
            p.tipo = "documento"
            reagrupadas += 1

    db.commit()
    return reagrupadas


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
        db.commit()

    def _custo(valor: float) -> None:
        caso.custo_usd_total = (caso.custo_usd_total or 0) + valor
        db.commit()

    def _cancelar() -> bool:
        return _cancelar_sync_solicitado(db, caso)

    resumir_pecas_em_paralelo(db, pendentes, on_progresso=_progresso, on_custo=_custo, deve_cancelar=_cancelar)
    _resolver_referencias_pendentes(db, caso.id)
    return len(pendentes)


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
        db.commit()
        return total_retomadas

    pendentes = listar_andamentos_pendentes(db, caso)
    if not pendentes:
        caso.sync_etapa = None
        caso.sync_total_itens = None
        caso.sync_itens_processados = None
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
    cancelado = False

    def _flush_grupo() -> None:
        nonlocal grupo_atual
        if not grupo_atual:
            return
        # Confia na ordem de submissão dentro do grupo (por hora exata de
        # protocolo, regra combinada com o Lucas, ou por data+descrição no
        # fallback) — mas nunca escolhe como principal um membro cujo nome/
        # descrição bate com um sinal de anexo explícito (procuração,
        # comprovante, "Documento de Comprovação"...).
        principal = next((m for m in grupo_atual if not m["eh_anexo"]), grupo_atual[0])
        peca_principal = _criar_peca(db, caso, principal, peca_pai_id=None)
        criadas.append(peca_principal)
        for membro in grupo_atual:
            if membro is principal:
                continue
            criadas.append(_criar_peca(db, caso, membro, peca_pai_id=peca_principal.id))
        db.commit()
        grupo_atual = []

    for indice, andamento in enumerate(pendentes, start=1):
        conteudo = None
        texto = andamento.texto_extraido
        if not texto:
            conteudo = _obter_bytes(andamento)
            if conteudo:
                def _custo_ocr(valor: float, _caso=caso) -> None:
                    _caso.custo_usd_total = (_caso.custo_usd_total or 0) + valor
                    db.commit()
                texto = _extrair_texto(conteudo, andamento.arquivo_nome, on_custo=_custo_ocr)
                if texto:
                    andamento.texto_extraido = texto
                    db.commit()
        if not texto:
            texto = andamento.descricao or ""

        paginas = _contar_paginas(conteudo, andamento.arquivo_nome)
        pagina_inicio = caso.total_paginas + 1
        caso.total_paginas += paginas

        item = {
            "andamento": andamento,
            "texto": texto,
            "tipo": _classificar_tipo(andamento),
            "eh_anexo": _eh_provavel_anexo(andamento),
            "pagina_inicio": pagina_inicio,
            "pagina_fim": pagina_inicio + paginas - 1,
        }
        # Preferência pela hora exata de protocolo (PDPJ/jus.br) pra agrupar
        # petição+anexos: documentos protocolados juntos, na mesma transação de
        # juntada, tipicamente vêm com o mesmo timestamp — sem custo de IA e mais
        # confiável que casar por data+descrição. Andamentos sem essa granularidade
        # (DataJud, ou sincronizados antes deste campo existir) caem no critério
        # antigo. Os dois nunca se misturam (chave marcada por tipo), então um
        # grupo por protocolo nunca "absorve" um grupo por descrição por engano.
        if andamento.protocolado_em:
            chave = ("protocolo", andamento.protocolado_em)
        else:
            chave = ("descricao", andamento.data_andamento, (andamento.descricao or "").strip())
        # Andamentos vêm ordenados por data/hora de protocolo/criação, então itens
        # do mesmo grupo são sempre contíguos na lista — dá pra fechar (persistir)
        # um grupo assim que o próximo item muda de chave, em vez de esperar ler
        # tudo antes de criar qualquer peça.
        if chave_atual is not None and chave != chave_atual:
            _flush_grupo()
        chave_atual = chave
        grupo_atual.append(item)

        caso.sync_itens_processados = indice
        db.commit()

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
        db.commit()

    def _custo_resumo(valor: float) -> None:
        caso.custo_usd_total = (caso.custo_usd_total or 0) + valor
        db.commit()

    def _cancelar() -> bool:
        return _cancelar_sync_solicitado(db, caso)

    resumir_pecas_em_paralelo(
        db, pecas_para_ia, on_progresso=_progresso_resumo, on_custo=_custo_resumo, deve_cancelar=_cancelar,
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
        titulo=(andamento.tipo or andamento.descricao or "Andamento sem título").strip()[:500],
        autor=None,
        data_peca=andamento.data_andamento,
        # Não usa andamento.documento_id aqui: é um ID interno do jus.br, não o número
        # (ex.: "Evento 45") que outras peças de fato citam no texto. O resumo (IA)
        # preenche id_processual com o que a própria peça diz ser sua referência —
        # ver ResumoPeca.id_proprio em services/autos_ia/resumo.py.
        id_processual=None,
        pagina_inicio=item["pagina_inicio"],
        pagina_fim=item["pagina_fim"],
        texto_md=item["texto"] or "(sem texto extraído)",
        status="pendente_resumo",
    )
    db.add(peca)
    db.flush()
    return peca
