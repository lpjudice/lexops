"""Orchestrates process consultation via DataJud (primary) and saves andamentos."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.andamento import AndamentoProcesso, SincronizacaoLog
from app.models.cliente import Cliente
from app.models.processo import Processo
from app.services.google_drive import upload_arquivo
from app.services.pasta_cliente import pasta_processo as pasta_cliente_processo, salvar_arquivo

from .datajud import buscar_via_datajud
from .pdpj import buscar_via_pdpj

logger = logging.getLogger(__name__)

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
) -> tuple[str | None, str | None, str | None]:
    if not nome_arquivo or not conteudo:
        return None, None, None

    nome_limpo = _sanitizar_nome_arquivo(nome_arquivo)
    if (mimetype or "").lower() == "application/pdf" and not nome_limpo.lower().endswith(".pdf"):
        nome_limpo = f"{nome_limpo}.pdf"

    destino = _caminho_documento_unico(processo.id, nome_limpo)
    destino.write_bytes(conteudo)

    drive_link = None
    cliente = db.query(Cliente).filter(Cliente.id == processo.cliente_id).first()
    if cliente and processo.numero_cnj:
        try:
            salvar_arquivo(pasta_cliente_processo(cliente.nome, processo.numero_cnj), destino.name, conteudo)
        except Exception:
            pass
        try:
            drive_link = upload_arquivo(
                conteudo,
                destino.name,
                cliente.nome,
                processo.numero_cnj,
                mimetype or "application/pdf",
            )
        except Exception:
            drive_link = None

    return destino.name, str(destino), drive_link


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
) -> SincronizacaoLog:
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

    novos = 0
    for a in raw_andamentos:
        h = AndamentoProcesso.calcular_hash(
            str(processo.id),
            str(a.data_andamento) if a.data_andamento else None,
            a.descricao,
        )
        if db.query(AndamentoProcesso).filter(AndamentoProcesso.hash_unico == h).first():
            continue
        arquivo_nome, arquivo_path, arquivo_drive_link = _persistir_documento_jusbr(
            processo,
            db,
            a.arquivo_nome,
            a.arquivo_bytes,
            a.arquivo_mimetype,
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
    log.finalizado_em = datetime.now(timezone.utc)
    db.commit()
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
