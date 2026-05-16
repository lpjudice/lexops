"""Orchestrates process consultation via DataJud (primary) and saves andamentos."""
from __future__ import annotations

import logging
import mimetypes
import os
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.models.andamento import AndamentoProcesso, SincronizacaoLog
from app.models.cliente import Cliente
from app.models.processo import Processo
from app.services.google_drive import upload_arquivo
from app.services.pasta_cliente import pasta_processo as pasta_cliente_processo, salvar_arquivo

from .datajud import buscar_via_datajud
from .pdpj import _conteudo_documento_valido, buscar_via_pdpj

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[dict], None]

# CNJ format: NNNNNNN-DD.AAAA.J.TT.OOOO
_CNJ_RE = re.compile(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$")

# DataJud supports essentially all Brazilian tribunals
# We validate the field is present, not a fixed list
TRIBUNAIS_CONHECIDOS = {
    "TJES", "TJSP", "TJAM", "TJRJ", "TJMG", "TJRS", "TJPR", "TJSC",
    "TJBA", "TJGO", "TJPE", "TJCE", "TJMA", "TJPA", "TJPB", "TJPI",
    "TJAL", "TJSE", "TJRN", "TJMT", "TJMS", "TJRO", "TJTO", "TJAC",
    "TJAP", "TJRR", "TJAM", "TRF1", "TRF2", "TRF3", "TRF4", "TRF5",
    "TRF6", "STJ", "TST", "TSE", "STM",
}

UPLOADS_DIR = Path("/app/uploads/processos")


def _deve_manter_copia_app_uploads() -> bool:
    return os.getenv("KEEP_JUSBR_LOCAL_UPLOADS", "false").lower() in {"1", "true", "yes"}


def _classificar_erro(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if isinstance(exc, PermissionError):
        return msg
    if isinstance(exc, ValueError):
        return msg
    if "timeout" in low or "timed out" in low:
        return "DataJud não respondeu a tempo. Tente novamente em instantes."
    if isinstance(exc, ConnectionError) or "connection" in low:
        return "Não foi possível conectar ao DataJud/CNJ. Verifique sua conexão."
    if "404" in msg:
        return f"Índice do tribunal não encontrado no DataJud: {msg[:120]}"
    return f"Erro inesperado: {msg[:200]}"


def _sanitizar_nome_arquivo(nome: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", (nome or "").strip())
    return cleaned or "documento_jusbr.pdf"


def _extensao_documento(nome_arquivo: str, mimetype: str | None) -> str:
    mime = (mimetype or "").lower()
    nome_lower = (nome_arquivo or "").lower()
    if mime == "application/pdf" or nome_lower.endswith(".pdf"):
        return ".pdf"
    if mime in {"text/html", "application/xhtml+xml"} or nome_lower.endswith((".html", ".htm")):
        return ".html"
    ext = Path(nome_arquivo or "").suffix
    if ext:
        return ext
    return (mimetypes.guess_extension(mime) if mime else None) or ".bin"


def _trecho_nome_andamento(descricao: str | None, tipo: str | None) -> str:
    texto = re.sub(r"<[^>]+>", " ", descricao or "")
    texto = re.sub(r"\s+", " ", texto).strip()
    if tipo:
        texto = re.sub(rf"^{re.escape(tipo)}\s*[-:–—]*\s*", "", texto, flags=re.IGNORECASE)
    texto = texto[:90].strip(" .,-:;")
    return _sanitizar_nome_arquivo(texto) if texto else "documento"


def _nome_documento_andamento(
    sequencial: int | None,
    data_andamento: date | None,
    tipo: str | None,
    descricao: str | None,
    nome_original: str,
    mimetype: str | None,
) -> str:
    numero = f"{sequencial or 999:03d}"
    data_txt = data_andamento.isoformat() if data_andamento else "sem-data"
    tipo_txt = _sanitizar_nome_arquivo(tipo or Path(nome_original).stem or "Documento")[:45].strip(" .,-")
    resumo = _trecho_nome_andamento(descricao, tipo_txt)
    ext = _extensao_documento(nome_original, mimetype)
    stem = f"{numero} - {data_txt} - {tipo_txt} - {resumo}"
    stem = _sanitizar_nome_arquivo(stem)[:160].strip(" .,-")
    return f"{stem}{ext}"


def _nome_drive_documento(nome_arquivo: str, mimetype: str | None) -> str:
    nome_lower = (nome_arquivo or "").lower()
    if (mimetype or "").lower() in {"text/html", "application/xhtml+xml"} or nome_lower.endswith((".html", ".htm")):
        return Path(nome_arquivo).with_suffix("").name
    return nome_arquivo


def _caminho_documento_unico(processo_id, nome_arquivo: str) -> Path:
    pasta = UPLOADS_DIR / str(processo_id)
    pasta.mkdir(parents=True, exist_ok=True)
    candidato = pasta / nome_arquivo
    if not candidato.exists():
        return candidato
    stem = candidato.stem
    suffix = candidato.suffix
    idx = 2
    while True:
        alternativo = pasta / f"{stem} ({idx}){suffix}"
        if not alternativo.exists():
            return alternativo
        idx += 1


def _persistir_documento_jusbr(
    processo: Processo,
    db: Session,
    nome_arquivo: str | None,
    conteudo: bytes | None,
    mimetype: str | None,
    data_andamento: date | None = None,
    descricao: str | None = None,
    tipo: str | None = None,
    sequencial: int | None = None,
    caminho_atual: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    if not nome_arquivo or not conteudo:
        return None, None, None

    nome_limpo = _nome_documento_andamento(
        sequencial,
        data_andamento,
        tipo,
        descricao,
        _sanitizar_nome_arquivo(nome_arquivo),
        mimetype,
    )

    destino = Path(caminho_atual) if caminho_atual else _caminho_documento_unico(processo.id, nome_limpo)
    if destino.name != nome_limpo:
        destino = _caminho_documento_unico(processo.id, nome_limpo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)

    drive_link = None
    cliente = db.query(Cliente).filter(Cliente.id == processo.cliente_id).first()
    if cliente and processo.numero_cnj:
        try:
            pasta_local = pasta_cliente_processo(cliente.nome, processo.numero_cnj)
            if pasta_local.exists():
                pasta_local = pasta_local / "Andamentos"
                pasta_local.mkdir(parents=True, exist_ok=True)
            salvar_arquivo(pasta_local, destino.name, conteudo)
        except Exception:
            pass
        try:
            drive_mimetype = "text/html" if destino.name.lower().endswith((".html", ".htm")) else (mimetype or "application/pdf")
            drive_link = upload_arquivo(
                conteudo,
                _nome_drive_documento(destino.name, mimetype),
                cliente.nome,
                processo.numero_cnj,
                drive_mimetype,
                sub_subfolder="Andamentos",
                converter_html_para_google_docs=True,
            )
        except Exception:
            logger.exception("Falha ao enviar documento JusBR para o Google Drive")
            drive_link = None

    if drive_link and not _deve_manter_copia_app_uploads():
        try:
            destino.unlink(missing_ok=True)
        except Exception:
            logger.exception("Falha ao remover copia local temporaria do documento JusBR")
        return destino.name, None, drive_link

    return destino.name, str(destino), drive_link


def _arquivo_local_valido(caminho: str | None) -> bool:
    if not caminho:
        return False
    try:
        path = Path(caminho)
        if not path.exists() or not path.is_file():
            return False
        content_type = mimetypes.guess_type(str(path))[0] or path.suffix
        return _conteudo_documento_valido(path.read_bytes(), content_type)
    except Exception:
        return False


def _arquivo_andamento_util(andamento: AndamentoProcesso) -> bool:
    if andamento.arquivo_drive_link:
        return True
    return _arquivo_local_valido(andamento.arquivo_path)


def _normalizar_descricao_andamento(texto: str | None) -> str:
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    texto = texto.split(" — ", 1)[0]
    texto = texto.split(" – ", 1)[0]
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = texto.lower()
    texto = re.sub(r"#\{[^}]+\}", " ", texto)
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _descricoes_compativeis(nova: str | None, existente: str | None) -> bool:
    nova_norm = _normalizar_descricao_andamento(nova)
    existente_norm = _normalizar_descricao_andamento(existente)
    if not nova_norm or not existente_norm:
        return False
    if nova_norm == existente_norm:
        return True
    menor, maior = sorted([nova_norm, existente_norm], key=len)
    if len(menor) >= 18 and menor in maior:
        return True
    return SequenceMatcher(None, nova_norm, existente_norm).ratio() >= 0.74


def _buscar_andamento_existente_compativel(
    db: Session,
    processo: Processo,
    data_andamento: date | None,
    descricao: str | None,
    hash_unico: str,
) -> AndamentoProcesso | None:
    existente = db.query(AndamentoProcesso).filter(AndamentoProcesso.hash_unico == hash_unico).first()
    if existente:
        return existente

    candidatos = (
        db.query(AndamentoProcesso)
        .filter(
            AndamentoProcesso.processo_id == processo.id,
            AndamentoProcesso.data_andamento == data_andamento,
            AndamentoProcesso.fonte.ilike("JusBR%"),
        )
        .order_by(AndamentoProcesso.created_at.asc())
        .all()
    )
    compat = [c for c in candidatos if _descricoes_compativeis(descricao, c.descricao)]
    if not compat:
        return None
    compat.sort(key=lambda c: (not _arquivo_andamento_util(c), c.created_at or datetime.min.replace(tzinfo=timezone.utc)))
    return compat[0]


def _sequenciais_documentos(processo: Processo, raw_andamentos: list) -> dict[str, int]:
    documentos = []
    for idx, andamento in enumerate(raw_andamentos):
        if not (andamento.arquivo_nome or andamento.documento_detectado):
            continue
        h = AndamentoProcesso.calcular_hash(
            str(processo.id),
            str(andamento.data_andamento) if andamento.data_andamento else None,
            andamento.descricao,
        )
        documentos.append((andamento.data_andamento or date.max, idx, h))
    documentos.sort(key=lambda item: (item[0], item[1]))
    return {h: idx + 1 for idx, (_, __, h) in enumerate(documentos)}


def _mensagem_sessao_documentos(session_data: dict | None) -> str:
    if not session_data:
        return (
            "Os andamentos foram sincronizados, mas alguns documentos nao puderam ser baixados. "
            "Reconecte o jus.br com um cURL ou headers autenticados do portal e sincronize novamente."
        )

    capture_kind = str(session_data.get("capture_kind") or "")
    detected_url = str(session_data.get("detected_url") or "").strip()
    host = urlparse(detected_url).netloc.lower() if detected_url else ""

    if capture_kind == "token_json":
        return (
            "Os andamentos foram sincronizados, mas os documentos nao baixaram porque a sessao atual veio so do JSON de token. "
            "Para documentos, conecte o jus.br usando o cURL ou os headers de uma requisicao autenticada do portal."
        )
    if host.startswith("sso.") or "sso.cloud.pje.jus.br" in host:
        return (
            "Os andamentos foram sincronizados, mas os documentos nao baixaram porque o cURL atual parece ser da autenticacao SSO, "
            "e nao de uma chamada do portal de processos. Copie o cURL de uma requisicao em "
            "portaldeservicos.pdpj.jus.br/api/... e sincronize novamente."
        )
    if detected_url and "portaldeservicos.pdpj.jus.br/api" not in detected_url:
        return (
            "Os andamentos foram sincronizados, mas os documentos nao baixaram porque a captura atual nao veio de uma chamada "
            "portaldeservicos.pdpj.jus.br/api/.... Copie o cURL ou os headers de uma requisicao autenticada do portal e tente de novo."
        )
    return (
        "Os andamentos foram sincronizados, mas alguns documentos nao puderam ser baixados. "
        "O cURL ou os headers atuais nao trouxeram os cookies necessarios da sessao do portal. "
        "Copie uma requisicao autenticada do proprio portal de processos e sincronize novamente."
    )


async def sincronizar_processo(processo: Processo, db: Session) -> SincronizacaoLog:
    log = SincronizacaoLog(
        processo_id=processo.id,
        tribunal=processo.tribunal,
        status="ok",
        novos_andamentos=0,
        iniciado_em=datetime.now(timezone.utc),
    )
    db.add(log)

    # ── Validações rápidas ──────────────────────────────────────────────
    if not _CNJ_RE.match(processo.numero_cnj or ""):
        log.status = "erro"
        log.mensagem = (
            f"Número CNJ inválido: '{processo.numero_cnj}'. "
            "Formato esperado: NNNNNNN-DD.AAAA.J.TT.OOOO (ex: 0001234-56.2023.8.08.0001)."
        )
        log.finalizado_em = datetime.now(timezone.utc)
        db.commit()
        return log

    tribunal = (processo.tribunal or "").strip().upper()
    if not tribunal:
        log.status = "erro"
        log.mensagem = "Tribunal não informado. Edite o processo e preencha o campo Tribunal."
        log.finalizado_em = datetime.now(timezone.utc)
        db.commit()
        return log

    # ── Busca no DataJud ────────────────────────────────────────────────
    try:
        raw_andamentos = await buscar_via_datajud(processo.numero_cnj, tribunal)
    except Exception as exc:
        logger.exception("Erro DataJud para %s", processo.numero_cnj)
        log.status = "erro"
        log.mensagem = _classificar_erro(exc)
        processo.tentativas_falha = (processo.tentativas_falha or 0) + 1
        processo.ultimo_check = datetime.now(timezone.utc)
        log.finalizado_em = datetime.now(timezone.utc)
        db.commit()
        return log

    if not raw_andamentos:
        log.status = "nenhum"
        log.mensagem = (
            "Processo não encontrado no DataJud para o tribunal informado. "
            "Possíveis causas: número CNJ sem dados ainda indexados, "
            "tribunal incorreto, ou processo muito recente (indexação pode levar horas)."
        )
        processo.tentativas_falha = 0
        processo.ultimo_check = datetime.now(timezone.utc)
        log.finalizado_em = datetime.now(timezone.utc)
        db.commit()
        return log

    # ── Persiste andamentos novos (deduplicação por hash) ──────────────
    novos = 0
    for a in raw_andamentos:
        h = AndamentoProcesso.calcular_hash(
            str(processo.id),
            str(a.data_andamento) if a.data_andamento else None,
            a.descricao,
        )
        if db.query(AndamentoProcesso).filter(AndamentoProcesso.hash_unico == h).first():
            continue

        db.add(AndamentoProcesso(
            processo_id=processo.id,
            data_andamento=a.data_andamento,
            descricao=a.descricao,
            tipo=a.tipo,
            fonte=tribunal,
            grau=a.grau,
            hash_unico=h,
            lido=False,
            notificado=False,
        ))
        novos += 1

    # ── Atualiza metadados de sync no processo ──────────────────────────
    if novos > 0:
        mais_recente = max(
            (a for a in raw_andamentos if a.data_andamento),
            key=lambda a: a.data_andamento,
            default=None,
        )
        if mais_recente and (
            processo.ultimo_andamento_data is None
            or mais_recente.data_andamento > processo.ultimo_andamento_data
        ):
            processo.ultimo_andamento_data = mais_recente.data_andamento
            processo.ultimo_andamento_desc = mais_recente.descricao[:500]
        processo.andamentos_nao_lidos = (processo.andamentos_nao_lidos or 0) + novos

    processo.tentativas_falha = 0
    processo.ultimo_check = datetime.now(timezone.utc)
    log.novos_andamentos = novos
    log.status = "ok"
    log.finalizado_em = datetime.now(timezone.utc)
    db.commit()
    return log


async def sincronizar_processo_jusbr(
    processo: Processo,
    db: Session,
    token: str | None = None,
    session_data: dict | None = None,
    progress_callback: ProgressCallback | None = None,
) -> SincronizacaoLog:
    def progress(**payload) -> None:
        if progress_callback:
            progress_callback(payload)

    log = SincronizacaoLog(
        processo_id=processo.id,
        tribunal=processo.tribunal,
        status="ok",
        novos_andamentos=0,
        iniciado_em=datetime.now(timezone.utc),
    )
    db.add(log)

    if not _CNJ_RE.match(processo.numero_cnj or ""):
        log.status = "erro"
        log.mensagem = (
            f"Número CNJ inválido: '{processo.numero_cnj}'. "
            "Formato esperado: NNNNNNN-DD.AAAA.J.TT.OOOO."
        )
        log.finalizado_em = datetime.now(timezone.utc)
        db.commit()
        return log

    tribunal = (processo.tribunal or "").strip().upper()
    if not tribunal:
        log.status = "erro"
        log.mensagem = "Tribunal não informado. Edite o processo e preencha o campo Tribunal."
        log.finalizado_em = datetime.now(timezone.utc)
        db.commit()
        return log

    try:
        progress(stage="consultando", message="Consultando o jus.br...")
        raw_andamentos = await buscar_via_pdpj(
            processo.numero_cnj,
            tribunal,
            token=token,
            session_data=session_data,
        )
    except Exception as exc:
        logger.exception("Erro PDPJ/JusBR para %s", processo.numero_cnj)
        log.status = "erro"
        log.mensagem = _classificar_erro(exc)
        processo.tentativas_falha = (processo.tentativas_falha or 0) + 1
        processo.ultimo_check = datetime.now(timezone.utc)
        log.finalizado_em = datetime.now(timezone.utc)
        db.commit()
        return log

    if not raw_andamentos:
        log.status = "nenhum"
        log.mensagem = (
            "Processo não encontrado no jus.br com este token. "
            "Verifique se a sessao do jus.br ainda está válida e se o processo está acessível no portal."
        )
        processo.tentativas_falha = 0
        processo.ultimo_check = datetime.now(timezone.utc)
        log.finalizado_em = datetime.now(timezone.utc)
        db.commit()
        return log

    docs_total = sum(1 for a in raw_andamentos if a.arquivo_nome or a.documento_detectado)
    progress(
        stage="processando",
        message=f"{len(raw_andamentos)} andamento(s) encontrados. Preparando documentos...",
        total=docs_total,
        processed=0,
        uploaded=0,
    )

    novos = 0
    docs_detectados_sem_arquivo = 0
    docs_processados = 0
    docs_enviados = 0
    sequenciais_docs = _sequenciais_documentos(processo, raw_andamentos)
    for a in raw_andamentos:
        h = AndamentoProcesso.calcular_hash(
            str(processo.id),
            str(a.data_andamento) if a.data_andamento else None,
            a.descricao,
        )
        existente = _buscar_andamento_existente_compativel(db, processo, a.data_andamento, a.descricao, h)
        if existente:
            precisa_reprocessar = not _arquivo_andamento_util(existente)
            if precisa_reprocessar and a.arquivo_nome and a.arquivo_bytes:
                docs_processados += 1
                progress(
                    stage="documentos",
                    message=f"Enviando documento {docs_processados}/{docs_total}: {a.arquivo_nome}",
                    total=docs_total,
                    processed=docs_processados,
                    uploaded=docs_enviados,
                )
                arquivo_nome, arquivo_path, arquivo_drive_link = _persistir_documento_jusbr(
                    processo,
                    db,
                    a.arquivo_nome,
                    a.arquivo_bytes,
                    a.arquivo_mimetype,
                    data_andamento=a.data_andamento,
                    descricao=a.descricao,
                    tipo=a.tipo,
                    sequencial=sequenciais_docs.get(h),
                    caminho_atual=existente.arquivo_path,
                )
                existente.arquivo_nome = arquivo_nome
                existente.arquivo_path = arquivo_path
                existente.arquivo_drive_link = arquivo_drive_link
                if arquivo_drive_link:
                    docs_enviados += 1
            elif precisa_reprocessar and a.documento_detectado:
                docs_processados += 1
                docs_detectados_sem_arquivo += 1
            elif a.arquivo_nome or a.documento_detectado:
                docs_processados += 1
                if existente.arquivo_drive_link:
                    docs_enviados += 1
            if a.arquivo_nome or a.documento_detectado:
                progress(
                    stage="documentos",
                    message=f"Documentos processados: {docs_processados}/{docs_total}",
                    total=docs_total,
                    processed=docs_processados,
                    uploaded=docs_enviados,
                )
            continue
        if a.arquivo_nome and a.arquivo_bytes:
            docs_processados += 1
            progress(
                stage="documentos",
                message=f"Enviando documento {docs_processados}/{docs_total}: {a.arquivo_nome}",
                total=docs_total,
                processed=docs_processados,
                uploaded=docs_enviados,
            )
        elif a.documento_detectado:
            docs_processados += 1
        arquivo_nome, arquivo_path, arquivo_drive_link = _persistir_documento_jusbr(
            processo,
            db,
            a.arquivo_nome,
            a.arquivo_bytes,
            a.arquivo_mimetype,
            data_andamento=a.data_andamento,
            descricao=a.descricao,
            tipo=a.tipo,
            sequencial=sequenciais_docs.get(h),
        )
        db.add(AndamentoProcesso(
            processo_id=processo.id,
            data_andamento=a.data_andamento,
            descricao=a.descricao,
            tipo=a.tipo,
            fonte=f"JusBR/{tribunal}",
            grau=a.grau,
            arquivo_nome=arquivo_nome,
            arquivo_path=arquivo_path,
            arquivo_drive_link=arquivo_drive_link,
            hash_unico=h,
            lido=False,
            notificado=False,
        ))
        if a.documento_detectado and not arquivo_drive_link:
            docs_detectados_sem_arquivo += 1
        if arquivo_drive_link:
            docs_enviados += 1
        if a.arquivo_nome or a.documento_detectado:
            progress(
                stage="documentos",
                message=f"Documentos processados: {docs_processados}/{docs_total}",
                total=docs_total,
                processed=docs_processados,
                uploaded=docs_enviados,
            )
        novos += 1

    if novos > 0:
        mais_recente = max(
            (a for a in raw_andamentos if a.data_andamento),
            key=lambda a: a.data_andamento,
            default=None,
        )
        if mais_recente and (
            processo.ultimo_andamento_data is None
            or mais_recente.data_andamento > processo.ultimo_andamento_data
        ):
            processo.ultimo_andamento_data = mais_recente.data_andamento
            processo.ultimo_andamento_desc = mais_recente.descricao[:500]
        processo.andamentos_nao_lidos = (processo.andamentos_nao_lidos or 0) + novos

    processo.tentativas_falha = 0
    processo.ultimo_check = datetime.now(timezone.utc)
    log.novos_andamentos = novos
    log.status = "ok"
    if docs_detectados_sem_arquivo > 0 and session_data and not session_data.get("cookies"):
        log.mensagem = _mensagem_sessao_documentos(session_data)
    elif docs_total == 0 and session_data and session_data.get("capture_kind") == "token_json":
        log.mensagem = (
            "Andamentos sincronizados. Para baixar documentos pelo jus.br, reconecte usando o cURL ou headers "
            "de uma requisicao autenticada do portal, nao apenas o JSON do token."
        )
    log.finalizado_em = datetime.now(timezone.utc)
    db.commit()
    progress(
        stage="finalizado",
        message="Sincronização concluída.",
        total=docs_total,
        processed=docs_processados,
        uploaded=docs_enviados,
    )
    return log


async def sincronizar_batch(processo_ids: list[str], db: Session) -> list[dict]:
    from app.models.processo import Processo as ProcessoModel

    results = []
    for pid in processo_ids:
        p = db.query(ProcessoModel).filter(ProcessoModel.id == pid).first()
        if not p:
            results.append({"processo_id": pid, "status": "erro", "mensagem": "Processo não encontrado"})
            continue
        log = await sincronizar_processo(p, db)
        results.append({
            "processo_id": pid,
            "numero_cnj": p.numero_cnj,
            "tribunal": log.tribunal,
            "status": log.status,
            "novos_andamentos": log.novos_andamentos,
            "mensagem": log.mensagem,
        })
    return results
