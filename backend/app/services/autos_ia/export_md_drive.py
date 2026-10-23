"""Exporta o resumo + inteiro teor de cada peça do Autos IA, em .md, para o Drive.

Espelha a pasta de PDFs dos andamentos, na mesma lógica e nomenclatura:

    PDFs:  {raiz}/{cliente}/{número CNJ}/Andamentos/NNN - AAAA-MM-DD - Tipo - trecho.pdf
    .md:   {raiz}/{cliente}/{número CNJ}/Andamentos (MD)/NNN - AAAA-MM-DD - Tipo - trecho.md

Cada peça do Autos IA nasce de um andamento (relação 1:1), então o nome do .md é o do arquivo
do andamento, sem a extensão. Módulo independente: não altera nada da consulta jus.br/DataJud
(arquivos travados) nem o `google_drive.py` — só reaproveita os helpers de pasta dele.

Idempotente: guarda em `autos_ia_pecas` o id do arquivo no Drive e o hash do que foi enviado;
um novo envio só acontece quando nome ou conteúdo mudam (e então o arquivo é ATUALIZADO, não
duplicado).
"""
import hashlib
import json
import logging
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import func, update

from app.database import SessionLocal
from app.models.andamento import AndamentoProcesso
from app.models.autos_ia import AutosIACaso, AutosIAPeca
from app.models.cliente import Cliente
from app.models.processo import Processo
from app.services import google_drive as gd

logger = logging.getLogger(__name__)

PASTA_MD = "Andamentos (MD)"
_EXTENSOES = (".pdf", ".html", ".htm", ".doc", ".docx", ".xml", ".txt", ".rtf", ".odt")
_BRT = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019
_LOTE = 24            # peças lidas do banco / enviadas por rodada
_PARALELO = 4         # envios simultâneos ao Drive
_TEXTO_MIN = 50       # abaixo disso o texto da peça é só a descrição do andamento
_MAX_FALHAS_SEGUIDAS = 8

_LOCK = threading.Lock()          # uma exportação por vez (a máquina é pequena)
_PROGRESSO: dict[str, dict] = {}  # caso_id -> andamento da última/atual execução


# ── Nome e conteúdo ──────────────────────────────────────────────────────────

def nome_md(arquivo_nome: str | None, data: date | None, tipo: str | None, titulo: str | None) -> str:
    """Mesmo nome do arquivo do andamento, trocando a extensão por .md. Aceita extensão
    repetida (`….pdf.pdf`, `….html.html`), que existe nos andamentos antigos."""
    base = (arquivo_nome or "").strip()
    mudou = True
    while mudou and base:
        mudou = False
        for ext in _EXTENSOES:
            if base.lower().endswith(ext):
                base = base[: -len(ext)].rstrip()
                mudou = True
    if not base:
        base = f"{data.isoformat() if data else 'sem-data'} - {tipo or 'Peça'} - {titulo or 'sem título'}"
    base = re.sub(r'[\\/:*?"<>|]+', "_", base)
    base = re.sub(r"\s+", " ", base).strip(" .,-")[:180].strip(" .,-")
    return f"{base or 'peca'}.md"


def _nomes_unicos(linhas: list[tuple]) -> dict[uuid.UUID, str]:
    """linhas: (peca_id, arquivo_nome, data, tipo, titulo), em ordem estável. Nomes iguais
    na mesma pasta ganham " (2)", " (3)"… — o Drive aceitaria duplicados, mas o espelho
    precisa de um .md por arquivo, identificável."""
    usados: dict[str, int] = {}
    saida: dict[uuid.UUID, str] = {}
    for peca_id, arquivo, data, tipo, titulo in linhas:
        nome = nome_md(arquivo, data, tipo, titulo)
        chave = nome.lower()
        n = usados.get(chave, 0) + 1
        usados[chave] = n
        if n > 1:
            nome = f"{nome[:-3]} ({n}).md"
        saida[peca_id] = nome
    return saida


def _data_br(d: date | datetime | None) -> str:
    if d is None:
        return ""
    if isinstance(d, datetime):
        d = d.astimezone(_BRT)
        return d.strftime("%d/%m/%Y %H:%M") + " (BRT)"
    return d.strftime("%d/%m/%Y")


def _sem_html(texto: str | None, limite: int = 400) -> str:
    t = re.sub(r"<[^>]+>", " ", texto or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limite] + ("…" if len(t) > limite else "")


def montar_markdown(peca: AutosIAPeca, andamento: AndamentoProcesso | None, caso: AutosIACaso, cnj: str | None) -> str:
    titulo = (peca.titulo_customizado or peca.titulo or "Peça").strip()
    linhas = [f"# {titulo}", ""]

    def campo(rotulo: str, valor) -> None:
        if valor not in (None, "", []):
            linhas.append(f"- **{rotulo}:** {valor}")

    campo("Processo", cnj or caso.numero_processo)
    campo("Caso (Autos IA)", caso.nome)
    campo("Tipo", peca.tipo)
    campo("Data do andamento", _data_br(andamento.data_andamento) if andamento else _data_br(peca.data_peca))
    campo("Protocolado em", _data_br(andamento.protocolado_em) if andamento and andamento.protocolado_em else "")
    campo("Autor", peca.autor)
    campo("ID processual", peca.id_processual)
    if peca.pagina_inicio and peca.pagina_fim and peca.pagina_fim > peca.pagina_inicio:
        campo("Páginas", f"{peca.pagina_inicio}–{peca.pagina_fim}")
    campo("Advogado responsável", peca.advogado_responsavel)
    kws = list(peca.keywords or []) + list(peca.keywords_usuario or [])
    campo("Palavras-chave", ", ".join(dict.fromkeys(kws)))
    campo("IDs mencionados", ", ".join(peca.ids_mencionados or []))
    if andamento and andamento.arquivo_drive_link:
        campo("PDF/arquivo original", f"[abrir no Drive]({andamento.arquivo_drive_link})")
    if andamento and andamento.descricao:
        campo("Andamento", _sem_html(andamento.descricao))

    linhas += ["", "## Resumo", "", (peca.resumo or "_Resumo ainda não gerado._").strip()]
    if peca.nota_usuario and peca.nota_usuario.strip():
        linhas += ["", "## Anotação", "", peca.nota_usuario.strip()]

    texto = (peca.texto_md or "").strip()
    linhas += ["", "## Inteiro teor", ""]
    if len(texto) >= _TEXTO_MIN:
        linhas.append(texto)
    else:
        linhas.append("_Texto do documento não extraído (download ou OCR falhou) — veja o arquivo original._")
        if texto:
            linhas += ["", texto]
    return "\n".join(linhas).rstrip() + "\n"


def _hash(nome: str, conteudo: str) -> str:
    return hashlib.sha256(f"{nome}\n{conteudo}".encode("utf-8")).hexdigest()


# ── Drive ────────────────────────────────────────────────────────────────────

class DriveIndisponivel(Exception):
    pass


class _Auth:
    """Tokens do Drive compartilhados entre as threads de envio; o refresh é serializado."""

    def __init__(self, tokens: dict):
        self.tokens = tokens
        self._lock = threading.Lock()

    def headers(self) -> dict:
        return gd._auth_headers(self.tokens)

    def renovar(self, headers_usados: dict) -> None:
        with self._lock:
            if gd._auth_headers(self.tokens) == headers_usados:  # outra thread já renovou?
                self.tokens = gd._refresh(self.tokens)


def _resolver_pasta(auth: _Auth, nome_cliente: str, cnj: str) -> str:
    """cliente / número CNJ / "Andamentos (MD)" — mesma árvore de upload_arquivo()."""
    for tentativa in range(2):
        h = auth.headers()
        try:
            cliente_id = gd._resolver_pasta_cliente(nome_cliente, h)
            processo_id = gd._get_or_create_subfolder(cnj, cliente_id, h)
            return gd._get_or_create_subfolder(PASTA_MD, processo_id, h)
        except Exception as exc:
            if tentativa == 0 and gd._is_unauthorized(exc):
                auth.renovar(h)
                continue
            raise DriveIndisponivel(f"não consegui preparar a pasta no Drive: {exc}") from exc
    raise DriveIndisponivel("não consegui preparar a pasta no Drive")


def _enviar(cli: httpx.Client, auth: _Auth, pasta_id: str, nome: str, conteudo: str, file_id: str | None) -> str:
    """Cria (POST) ou atualiza (PATCH) o .md; devolve o id do arquivo. Repete em 401/429/5xx."""
    corpo_md = conteudo.encode("utf-8")
    ultimo = "sem resposta"
    for tentativa in range(5):
        h = auth.headers()
        meta = {"name": nome}
        if not file_id:
            meta["parents"] = [pasta_id]
            meta["mimeType"] = "text/markdown"
        fronteira = "lexops_md_" + uuid.uuid4().hex
        corpo = (
            f"--{fronteira}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
            + json.dumps(meta).encode()
            + f"\r\n--{fronteira}\r\nContent-Type: text/markdown; charset=UTF-8\r\n\r\n".encode()
            + corpo_md
            + f"\r\n--{fronteira}--".encode()
        )
        url = f"{gd.DRIVE_API}/files/{file_id}" if file_id else f"{gd.DRIVE_API}/files"
        try:
            r = cli.request(
                "PATCH" if file_id else "POST",
                url,
                headers={**h, "Content-Type": f"multipart/related; boundary={fronteira}"},
                params={"uploadType": "multipart", "supportsAllDrives": True, "fields": "id"},
                content=corpo,
                timeout=60,
            )
        except httpx.HTTPError as exc:
            ultimo = f"rede: {exc}"
            time.sleep(2 * (tentativa + 1))
            continue
        if r.status_code == 401:
            auth.renovar(h)
            ultimo = "401"
            continue
        if r.status_code == 404 and file_id:  # arquivo apagado no Drive → recria
            file_id = None
            ultimo = "404 (recriando)"
            continue
        limite_taxa = r.status_code == 429 or (
            r.status_code == 403 and any(k in r.text.lower() for k in ("ratelimit", "quota"))
        )
        if limite_taxa or r.status_code >= 500:
            ultimo = f"{r.status_code} {r.text[:120]}"
            time.sleep(2 ** (tentativa + 1))
            continue
        r.raise_for_status()
        return r.json()["id"]
    raise RuntimeError(f"Drive recusou o envio de '{nome}': {ultimo}")


def _link_pasta(pasta_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{pasta_id}"


# ── Execução ─────────────────────────────────────────────────────────────────

def _progresso(caso_id: uuid.UUID, **kw) -> dict:
    p = _PROGRESSO.setdefault(str(caso_id), {})
    p.update(kw)
    return p


def _erro_inicial(caso_id: uuid.UUID, mensagem: str) -> dict:
    """Falha antes de começar: zera os contadores da rodada anterior."""
    _PROGRESSO[str(caso_id)] = {"estado": "erro", "mensagem": mensagem}
    return _PROGRESSO[str(caso_id)]


def status_exportacao(db, caso_id: uuid.UUID) -> dict:
    """Contagens do banco + andamento da execução em memória (some num restart — a execução
    é retomável, então o que importa fica no banco)."""
    total, exportadas = db.query(
        func.count(AutosIAPeca.id), func.count(AutosIAPeca.md_drive_file_id)
    ).filter(AutosIAPeca.caso_id == caso_id).one()
    p = dict(_PROGRESSO.get(str(caso_id)) or {})
    return {
        "estado": p.get("estado", "ocioso"),
        "total": total,
        "exportadas": exportadas,
        "feitos": p.get("feitos", 0),
        "enviados": p.get("enviados", 0),
        "ignorados": p.get("ignorados", 0),
        "erros": p.get("erros", 0),
        "mensagem": p.get("mensagem"),
        "pasta_nome": PASTA_MD,
        "pasta_link": p.get("pasta_link"),
    }


_CACHE_PASTAS: dict[str, tuple[float, dict]] = {}
_CACHE_PASTAS_SEGUNDOS = 600


def links_pastas(db, caso_id: uuid.UUID) -> dict:
    """Links das pastas do caso no Drive: do processo (raiz das duas), dos PDFs ("Andamentos")
    e dos .md ("Andamentos (MD)"). Só devolve pasta que JÁ existe (não cria nada) e guarda
    o resultado por alguns minutos — são 3 consultas ao Drive."""
    chave = str(caso_id)
    hit = _CACHE_PASTAS.get(chave)
    if hit and time.monotonic() - hit[0] < _CACHE_PASTAS_SEGUNDOS:
        return hit[1]
    vazio = {"processo": None, "pdfs": None, "md": None}
    caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
    processo = db.query(Processo).filter(Processo.id == caso.processo_id).first() if caso and caso.processo_id else None
    cliente = db.query(Cliente).filter(Cliente.id == processo.cliente_id).first() if processo else None
    if not processo or not cliente or not processo.numero_cnj:
        return vazio
    nome, cnj = cliente.nome, processo.numero_cnj
    out = {
        "processo": gd.find_folder_link(nome, cnj),
        "pdfs": gd.find_folder_link(nome, cnj, "Andamentos"),
        "md": gd.find_folder_link(nome, cnj, PASTA_MD),
    }
    if any(out.values()):  # não guarda falha total (Drive fora do ar) no cache
        _CACHE_PASTAS[chave] = (time.monotonic(), out)
    return out


def exportar_caso(
    caso_id: uuid.UUID, limite: int | None = None, forcar: bool = False,
    peca_ids: set | None = None, esperar: bool = False,
) -> dict:
    """Exporta as peças do caso que ainda não estão no Drive ou que mudaram. `limite` corta
    a quantidade de ENVIOS (para uma amostra); `forcar` reenvia mesmo sem mudança; `peca_ids`
    restringe a essas peças (ex.: uma peça relida); `esperar` aguarda outra exportação em
    andamento terminar em vez de desistir. Nunca lança."""
    if not _LOCK.acquire(blocking=esperar, timeout=3600 if esperar else -1):
        return {"estado": "rodando", "mensagem": "Já há uma exportação em andamento."}
    db = SessionLocal()
    try:
        caso = db.query(AutosIACaso).filter(AutosIACaso.id == caso_id).first()
        if not caso or not caso.processo_id:
            return _erro_inicial(caso_id, "Caso sem processo vinculado.")
        processo = db.query(Processo).filter(Processo.id == caso.processo_id).first()
        cliente = db.query(Cliente).filter(Cliente.id == processo.cliente_id).first() if processo else None
        if not processo or not cliente or not processo.numero_cnj:
            return _erro_inicial(caso_id, "Processo sem cliente ou número CNJ.")
        tokens = gd._load_tokens()
        if not tokens:
            return _erro_inicial(caso_id, "Google Drive não está conectado.")

        _PROGRESSO[str(caso_id)] = {
            "estado": "rodando", "feitos": 0, "enviados": 0, "ignorados": 0, "erros": 0,
            "mensagem": "Preparando a pasta no Drive…", "pasta_link": None,
        }
        auth = _Auth(tokens)
        cnj, nome_cliente, nome_caso = processo.numero_cnj, cliente.nome, caso.nome
        pasta_id = _resolver_pasta(auth, nome_cliente, cnj)
        _progresso(caso_id, pasta_link=_link_pasta(pasta_id))

        # Nomes de TODAS as peças (leve), em ordem estável, para o desempate "(2)" não variar.
        linhas = (
            db.query(
                AutosIAPeca.id, AndamentoProcesso.arquivo_nome, AndamentoProcesso.data_andamento,
                AndamentoProcesso.tipo, func.coalesce(AutosIAPeca.titulo_customizado, AutosIAPeca.titulo),
            )
            .outerjoin(AndamentoProcesso, AutosIAPeca.andamento_id == AndamentoProcesso.id)
            .filter(AutosIAPeca.caso_id == caso_id)
            .order_by(
                AndamentoProcesso.data_andamento.asc().nulls_last(), AndamentoProcesso.arquivo_nome,
                AutosIAPeca.criado_em, AutosIAPeca.id,
            )
            .all()
        )
        nomes = _nomes_unicos([tuple(r) for r in linhas])   # desempate "(2)" olha TODAS as peças
        ids = [r[0] for r in linhas if peca_ids is None or r[0] in peca_ids]
        _progresso(caso_id, total=len(ids), mensagem="Enviando…")

        enviados_total = falhas_seguidas = 0
        with httpx.Client() as cli, ThreadPoolExecutor(max_workers=_PARALELO) as pool:
            for ini in range(0, len(ids), _LOTE):
                if limite is not None and enviados_total >= limite:
                    break
                lote_ids = ids[ini: ini + _LOTE]
                pecas = {p.id: p for p in db.query(AutosIAPeca).filter(AutosIAPeca.id.in_(lote_ids)).all()}
                andamentos = {
                    a.id: a for a in db.query(AndamentoProcesso).filter(
                        AndamentoProcesso.id.in_([p.andamento_id for p in pecas.values() if p.andamento_id])
                    ).all()
                }
                trabalhos = []
                for pid in lote_ids:
                    peca = pecas.get(pid)
                    if peca is None:
                        continue
                    nome = nomes[pid]
                    conteudo = montar_markdown(peca, andamentos.get(peca.andamento_id), caso, cnj)
                    h = _hash(nome, conteudo)
                    if not forcar and peca.md_drive_file_id and peca.md_hash == h:
                        _PROGRESSO[str(caso_id)]["ignorados"] += 1
                        continue
                    if limite is not None and enviados_total + len(trabalhos) >= limite:
                        break
                    trabalhos.append((pid, nome, conteudo, h, peca.md_drive_file_id))

                def _um(t):
                    pid, nome, conteudo, h, fid = t
                    try:
                        return pid, h, _enviar(cli, auth, pasta_id, nome, conteudo, fid), None
                    except Exception as exc:  # noqa: BLE001 — cada peça falha isolada
                        return pid, h, None, str(exc)[:300]

                agora = datetime.now(timezone.utc)
                for pid, h, novo_id, erro in pool.map(_um, trabalhos):
                    if erro:
                        _PROGRESSO[str(caso_id)]["erros"] += 1
                        _PROGRESSO[str(caso_id)]["mensagem"] = f"Falha: {erro}"
                        falhas_seguidas += 1
                        logger.warning("Export MD: peça %s falhou: %s", pid, erro)
                        continue
                    falhas_seguidas = 0
                    enviados_total += 1
                    _PROGRESSO[str(caso_id)]["enviados"] += 1
                    # atualizado_em fixado nele mesmo: exportar não conta como "peça alterada".
                    db.execute(
                        update(AutosIAPeca).where(AutosIAPeca.id == pid).values(
                            md_drive_file_id=novo_id, md_hash=h, md_exportado_em=agora,
                            atualizado_em=AutosIAPeca.atualizado_em,
                        )
                    )
                db.commit()
                db.expire_all()
                _PROGRESSO[str(caso_id)]["feitos"] = min(ini + _LOTE, len(ids))
                if falhas_seguidas >= _MAX_FALHAS_SEGUIDAS:
                    raise RuntimeError("Muitas falhas seguidas no Drive — interrompido; rode de novo para retomar.")

        p = _PROGRESSO[str(caso_id)]
        p["estado"] = "concluido"
        p["mensagem"] = (
            f"Concluído: {p['enviados']} enviado(s), {p['ignorados']} já em dia"
            + (f", {p['erros']} com erro" if p["erros"] else "") + "."
        )
        logger.info("Export MD caso %s (%s): %s", caso_id, nome_caso, p["mensagem"])
        return p
    except Exception as exc:  # noqa: BLE001
        logger.exception("Export MD do caso %s falhou", caso_id)
        db.rollback()
        _progresso(caso_id, estado="erro", mensagem=str(exc)[:300])
        return _PROGRESSO[str(caso_id)]
    finally:
        db.close()
        _LOCK.release()


_FILA: dict[str, set | None] = {}   # caso_id → ids pendentes (None = o caso inteiro, incremental)
_FILA_LOCK = threading.Lock()
_TRABALHADOR_ATIVO = False


def _trabalhador() -> None:
    global _TRABALHADOR_ATIVO
    while True:
        with _FILA_LOCK:
            if not _FILA:
                _TRABALHADOR_ATIVO = False
                return
            chave = next(iter(_FILA))
            ids = _FILA.pop(chave)
        try:
            exportar_caso(uuid.UUID(chave), peca_ids=ids, esperar=True)
        except Exception:  # noqa: BLE001
            logger.exception("Export MD (fila) do caso %s falhou", chave)


def agendar_exportacao(caso_id: uuid.UUID, peca_ids=None) -> None:
    """Atualiza o .md no Drive depois de algo que mudou peças (sincronização, reler, resumir,
    reclassificar, editar anotação…). Só age em casos que JÁ tiveram a primeira exportação
    (feita de propósito pelo botão) — nunca escreve no Drive de surpresa. Junta pedidos
    seguidos numa fila e roda numa thread própria, sem segurar quem chamou. Nunca lança."""
    global _TRABALHADOR_ATIVO
    try:
        with SessionLocal() as db:
            ja_exportou = db.query(AutosIAPeca.id).filter(
                AutosIAPeca.caso_id == caso_id, AutosIAPeca.md_drive_file_id.isnot(None)
            ).first()
        if not ja_exportou:
            return
        chave = str(caso_id)
        with _FILA_LOCK:
            if peca_ids is None or (chave in _FILA and _FILA[chave] is None):
                _FILA[chave] = None
            else:
                _FILA[chave] = (_FILA.get(chave) or set()) | set(peca_ids)
            if not _TRABALHADOR_ATIVO:
                _TRABALHADOR_ATIVO = True
                threading.Thread(target=_trabalhador, daemon=True, name="export-md-fila").start()
    except Exception:  # noqa: BLE001
        logger.exception("Export MD: falha ao agendar o caso %s", caso_id)


def exportar_pos_sync(caso_id: uuid.UUID) -> None:
    """Compat: gancho do fim de cada sincronização (ver agendar_exportacao)."""
    agendar_exportacao(caso_id)
