"""Detecção e reparo de documentos salvos com o erro do repositório PDPJ ("Codex").

Quando o binário de um documento não pôde ser baixado do jus.br (circuit breaker
do "Codex" aberto / indisponibilidade), o portal devolve um texto de erro que a
coleta acaba salvando no lugar do PDF (arquivo minúsculo de ~120–170 bytes). Este
módulo detecta esses "stubs", marca a flag `codex_erro` no andamento (para o
indicador na tela) e re-baixa o documento correto pela MESMA coleta do escritório
(`sincronizar_processo_jusbr`).

IMPORTANTE: não altera nenhuma lógica travada — apenas CHAMA `sincronizar_processo_jusbr`
e usa helpers existentes de `google_drive`. Toda a lógica de coleta jus.br continua
intocada.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import text

from app.database import SessionLocal
from app.models.andamento import AndamentoProcesso
from app.models.processo import Processo
from app.services.google_drive import (
    DRIVE_META,
    _auth_headers,
    _load_tokens,
    baixar_arquivo_por_id,
    deletar_arquivo_por_id,
    extrair_file_id,
)

logger = logging.getLogger(__name__)

# Os stubs de erro têm ~120–170 bytes; documentos reais (PDF/HTML) são bem maiores.
_STUB_MAX_BYTES = 500


def _e_erro_codex(content: bytes) -> bool:
    prefix = (content or b"")[:800].decode("utf-8", errors="ignore").lower()
    return (
        ("circuitbreaker" in prefix and "does not permit" in prefix)
        or "codex indispon" in prefix
        or ("codex" in prefix and "stream" in prefix)
    )


def _meta_size(fid: str, headers: dict) -> int | None:
    try:
        r = httpx.get(
            f"{DRIVE_META}/files/{fid}", headers=headers,
            params={"fields": "id,size", "supportsAllDrives": True}, timeout=30,
        )
        if r.status_code != 200:
            return None
        j = r.json()
        return int(j["size"]) if j.get("size") else None
    except Exception:
        return None


def obter_sessao() -> dict | None:
    """Sessão jus.br para re-baixar: bot (id=2, perene) com fallback lexops (id=1)."""
    try:
        from app.services.andamentos_auth import load_session as load_bot
        s = load_bot()
        if s and s.get("token"):
            return s
    except Exception:
        logger.exception("codex_repair: falha ao carregar sessão do bot")
    try:
        from app.services.consulta_processual.jusbr_session import load_session as load_lexops
        s = load_lexops()
        if s and s.get("token"):
            return s
    except Exception:
        logger.exception("codex_repair: falha ao carregar sessão lexops")
    return None


def detectar_stubs(processo_id, desde: datetime | None = None) -> list[dict]:
    """Varre os documentos do processo no Drive e devolve os que são stub de erro
    Codex. Atualiza a flag `codex_erro` (marca os achados, limpa os que não são
    mais). Retorna [{id, nome, documento_id, data, bytes}]. `desde` limita a
    andamentos criados a partir dessa data (varredura barata na faxina)."""
    db = SessionLocal()
    try:
        q = (
            "SELECT id::text, arquivo_nome, documento_id, data_andamento, arquivo_drive_link "
            "FROM andamentos_processo WHERE processo_id = :p AND arquivo_drive_link IS NOT NULL"
        )
        params: dict = {"p": str(processo_id)}
        if desde is not None:
            q += " AND created_at >= :desde"
            params["desde"] = desde
        rows = db.execute(text(q), params).fetchall()

        tokens = _load_tokens()
        headers = _auth_headers(tokens) if tokens else None
        corrompidos: list[dict] = []
        if headers:
            for aid, nome, docid, dt, link in rows:
                fid = extrair_file_id(link)
                if not fid:
                    continue
                size = _meta_size(fid, headers)
                if size is None or size >= _STUB_MAX_BYTES:
                    continue
                content = baixar_arquivo_por_id(fid) or b""
                if _e_erro_codex(content):
                    corrompidos.append({
                        "id": aid, "nome": nome, "documento_id": docid,
                        "data": str(dt) if dt else None, "bytes": len(content),
                    })

        ids = [c["id"] for c in corrompidos]
        # Limpa flags antigas do processo que não estão mais corrompidas.
        limpar = db.query(AndamentoProcesso).filter(
            AndamentoProcesso.processo_id == processo_id,
            AndamentoProcesso.codex_erro.is_(True),
        )
        if ids:
            limpar = limpar.filter(~AndamentoProcesso.id.in_(ids))
        limpar.update({"codex_erro": False}, synchronize_session=False)
        # Marca os corrompidos.
        if ids:
            db.query(AndamentoProcesso).filter(AndamentoProcesso.id.in_(ids)).update(
                {"codex_erro": True}, synchronize_session=False
            )
        db.commit()
        return corrompidos
    finally:
        db.close()


def reparar_processo(processo_id, session: dict | None = None) -> dict:
    """Detecta os stubs do processo, joga os arquivos-erro na lixeira, limpa o
    vínculo e re-sincroniza (rebaixa os faltantes). Retorna o relatório."""
    session = session or obter_sessao()
    if not session or not session.get("token"):
        return {"ok": False, "erro": "sessao_indisponivel",
                "msg": "Sessão jus.br indisponível — reconecte/cole um token e tente de novo."}

    from app.services.consulta_processual.orchestrator import sincronizar_processo_jusbr

    corrompidos = detectar_stubs(processo_id)
    if not corrompidos:
        return {"ok": True, "detectados": 0, "reparados": 0, "pendentes": 0, "itens": []}

    db = SessionLocal()
    try:
        proc = db.query(Processo).filter(Processo.id == processo_id).first()
        if not proc:
            return {"ok": False, "erro": "processo_nao_encontrado"}
        for c in corrompidos:
            row = db.query(AndamentoProcesso).filter(AndamentoProcesso.id == c["id"]).first()
            if row and row.arquivo_drive_link:
                fid = extrair_file_id(row.arquivo_drive_link)
                if fid:
                    try:
                        deletar_arquivo_por_id(fid)
                    except Exception:
                        logger.warning("codex_repair: falha ao lixeira %s", fid)
                row.arquivo_drive_link = None
                row.arquivo_path = None
                row.texto_extraido = None
        db.commit()
        try:
            asyncio.run(sincronizar_processo_jusbr(
                proc, db, token=session["token"], session_data=session))
        except Exception as exc:
            logger.exception("codex_repair: re-sync falhou para %s", proc.numero_cnj)
            return {"ok": False, "erro": "resync_falhou", "msg": str(exc),
                    "detectados": len(corrompidos)}
    finally:
        db.close()

    restantes = detectar_stubs(processo_id)
    reparados = len(corrompidos) - len(restantes)
    return {
        "ok": True,
        "detectados": len(corrompidos),
        "reparados": reparados,
        "pendentes": len(restantes),
        "itens": corrompidos,
        "pendentes_itens": restantes,
    }


def faxina(dias: int = 3) -> dict:
    """Roda periodicamente (após o push). Varre os processos com documentos
    RECENTES, detecta stubs de erro Codex e tenta reparar. Retorna um resumo por
    processo (para o alerta)."""
    session = obter_sessao()
    desde = datetime.now(timezone.utc) - timedelta(days=dias)

    db = SessionLocal()
    try:
        pids = db.execute(text(
            "SELECT DISTINCT processo_id::text FROM andamentos_processo "
            "WHERE arquivo_drive_link IS NOT NULL AND created_at >= :desde"
        ), {"desde": desde}).fetchall()
        candidatos = [r[0] for r in pids]
    finally:
        db.close()

    resultado = {"processos_verificados": len(candidatos), "afetados": []}
    for pid in candidatos:
        try:
            achados = detectar_stubs(pid, desde=desde)
        except Exception:
            logger.exception("codex_repair.faxina: detectar falhou p/ %s", pid)
            continue
        if not achados:
            continue
        rep = reparar_processo(pid, session=session) if session else {
            "ok": False, "detectados": len(achados), "reparados": 0,
            "pendentes": len(achados), "itens": achados,
        }
        db2 = SessionLocal()
        try:
            proc = db2.query(Processo).filter(Processo.id == pid).first()
            cnj = proc.numero_cnj if proc else str(pid)
        finally:
            db2.close()
        resultado["afetados"].append({
            "cnj": cnj,
            "detectados": rep.get("detectados", len(achados)),
            "reparados": rep.get("reparados", 0),
            "pendentes": rep.get("pendentes", len(achados)),
            "itens": [i.get("nome") for i in achados],
        })
    return resultado
