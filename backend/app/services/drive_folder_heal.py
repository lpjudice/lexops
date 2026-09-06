"""Auto-cura de pasta-raiz órfã + detecção de pastas duplicadas na raiz do Drive.

Duas classes de problema na pasta-raiz do cliente (`clientes.drive_folder_id`):

1. ID ÓRFÃO: a pasta salva foi apagada/movida por fora do app (limpeza manual
   no Drive). O app passa a falhar silenciosamente ("Drive não conectado") pra
   sempre, nada se autocura. `escanear_orfaos` detecta; `curar_orfao` resolve
   pelo nome (tolerante a espaço/maiúscula, via `_listar_pastas` já ajustado em
   google_drive.py) e corrige o registro — só quando há UM candidato claro.

2. DUPLICATA JÁ EXISTENTE: dois clientes (linhas diferentes na tabela, nome
   igual ou quase igual) cada um com sua PRÓPRIA pasta-raiz válida no Drive —
   duas pastas reais para a mesma pessoa. `escanear_duplicatas_raiz` só
   DETECTA (não mescla sozinho — juntar pastas de pessoas com nome parecido
   sem revisão humana é arriscado). `mesclar_cluster` faz a mesclagem quando
   acionado manualmente: move todo o conteúdo pras pastas extras para a
   canônica (nunca apaga pasta com conteúdo sem antes esvaziá-la) e atualiza
   todos os clientes que apontavam pra pasta extra.

Não altera nenhuma lógica travada (jus.br). Usa helpers de google_drive.py.
"""
from __future__ import annotations

import logging

import httpx
from sqlalchemy import text

from app.database import SessionLocal
from app.services.google_drive import (
    DRIVE_FOLDER_ID,
    DRIVE_META,
    _auth_headers,
    _consolidar_pastas,
    _listar_pastas,
    _load_tokens,
    _normalizar_nome_busca,
    _refresh,
)

logger = logging.getLogger(__name__)


def _get_com_refresh(url: str, tokens: dict, params: dict) -> tuple[httpx.Response, dict]:
    """GET com retry-on-401 (refresh de token), devolve (response, tokens_atuais)."""
    h = _auth_headers(tokens)
    r = httpx.get(url, headers=h, params=params, timeout=30)
    if r.status_code == 401:
        tokens = _refresh(tokens)
        h = _auth_headers(tokens)
        r = httpx.get(url, headers=h, params=params, timeout=30)
    return r, tokens


# ── 1) ID órfão ────────────────────────────────────────────────────────────

def escanear_orfaos() -> list[dict]:
    """Valida o drive_folder_id de todos os clientes. Retorna os que apontam
    para pasta inexistente/lixeira: [{cliente_id, nome, folder_id_antigo}]."""
    tokens = _load_tokens()
    if not tokens:
        return []
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT id::text, nome, drive_folder_id FROM clientes WHERE drive_folder_id IS NOT NULL"
        )).fetchall()
    finally:
        db.close()

    stale = []
    for cid, nome, fid in rows:
        r, tokens = _get_com_refresh(
            f"{DRIVE_META}/files/{fid}", tokens,
            {"fields": "id,trashed", "supportsAllDrives": True},
        )
        if r.status_code != 200 or r.json().get("trashed"):
            stale.append({"cliente_id": cid, "nome": nome, "folder_id_antigo": fid})
    return stale


def curar_orfao(nome_cliente: str) -> dict:
    """Resolve a pasta correta do cliente pelo nome (tolerante) e corrige TODOS
    os registros com esse nome (normalizado) que estejam apontando errado.
    Só corrige quando há exatamente 1 candidato claro — caso contrário, retorna
    ambíguo/sem-candidato pra revisão manual (não inventa pasta)."""
    tokens = _load_tokens()
    if not tokens:
        return {"ok": False, "erro": "sem_sessao_drive"}
    h = _auth_headers(tokens)

    candidatos = _listar_pastas(nome_cliente, DRIVE_FOLDER_ID, h)
    if not candidatos:
        return {"ok": False, "erro": "sem_candidato", "nome": nome_cliente}
    if len(candidatos) > 1:
        fid = _consolidar_pastas(candidatos, h)  # mescla se as extras estiverem vazias
        # Reconfirma: se ainda sobrar mais de uma NÃO-vazia, é ambíguo de verdade.
        restantes = _listar_pastas(nome_cliente, DRIVE_FOLDER_ID, h)
        if len(restantes) > 1:
            return {
                "ok": False, "erro": "ambiguo", "nome": nome_cliente,
                "candidatos": [{"id": c["id"], "createdTime": c.get("createdTime")} for c in restantes],
            }
    else:
        fid = candidatos[0]["id"]

    nome_norm = _normalizar_nome_busca(nome_cliente)
    db = SessionLocal()
    try:
        res = db.execute(text(
            "UPDATE clientes SET drive_folder_id = :f "
            "WHERE lower(regexp_replace(trim(nome), '\\s+', ' ', 'g')) = :n"
        ), {"f": fid, "n": nome_norm})
        db.commit()
        n_atualizados = res.rowcount
    finally:
        db.close()

    return {"ok": True, "nome": nome_cliente, "folder_id_novo": fid, "clientes_atualizados": n_atualizados}


# ── 2) Duplicatas na raiz ────────────────────────────────────────────────────

def _listar_filhas_raiz() -> list[dict]:
    """Todas as pastas diretas (não-lixeira) sob a raiz LexOps."""
    tokens = _load_tokens()
    if not tokens:
        return []
    out: list[dict] = []
    page_token = None
    while True:
        params = {
            "q": f"mimeType='application/vnd.google-apps.folder' and '{DRIVE_FOLDER_ID}' in parents and trashed=false",
            "fields": "nextPageToken,files(id,name,createdTime)",
            "pageSize": 200,
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        }
        if page_token:
            params["pageToken"] = page_token
        r, tokens = _get_com_refresh(f"{DRIVE_META}/files", tokens, params)
        if r.status_code != 200:
            break
        data = r.json()
        out.extend(data.get("files", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return out


def _contar_itens_diretos(folder_id: str, tokens: dict) -> int:
    r, _ = _get_com_refresh(f"{DRIVE_META}/files", tokens, {
        "q": f"'{folder_id}' in parents and trashed=false",
        "fields": "files(id)", "pageSize": 100,
        "supportsAllDrives": True, "includeItemsFromAllDrives": True,
    })
    return len(r.json().get("files", [])) if r.status_code == 200 else -1


def escanear_duplicatas_raiz() -> list[dict]:
    """Agrupa as pastas da raiz por nome normalizado; retorna só os grupos com
    2+ pastas E que correspondem a um nome de cliente cadastrado (evita marcar
    pastas de sistema — Contratos, Backoffice, etc. — como duplicata).
    [{nome_normalizado, membros: [{id, createdTime, n_itens, clientes: [...]}]}]"""
    tokens = _load_tokens()
    if not tokens:
        return []

    db = SessionLocal()
    try:
        clientes = db.execute(text(
            "SELECT id::text, nome, drive_folder_id FROM clientes"
        )).fetchall()
    finally:
        db.close()

    nomes_cliente = {_normalizar_nome_busca(c[1]) for c in clientes}
    por_folder_id: dict[str, list[tuple]] = {}
    for cid, nome, fid in clientes:
        if fid:
            por_folder_id.setdefault(fid, []).append((cid, nome))

    filhas = _listar_filhas_raiz()
    grupos: dict[str, list[dict]] = {}
    for f in filhas:
        norm = _normalizar_nome_busca(f.get("name", ""))
        if norm not in nomes_cliente:
            continue  # pasta de sistema (Contratos, Backoffice, etc.) — ignora
        grupos.setdefault(norm, []).append(f)

    resultado = []
    for norm, membros in grupos.items():
        if len(membros) < 2:
            continue
        detalhado = []
        for m in membros:
            detalhado.append({
                "id": m["id"],
                "createdTime": m.get("createdTime"),
                "n_itens": _contar_itens_diretos(m["id"], tokens),
                "clientes": [{"cliente_id": cid, "nome": nome} for cid, nome in por_folder_id.get(m["id"], [])],
            })
        resultado.append({"nome_normalizado": norm, "membros": detalhado})
    return resultado


def mesclar_cluster(folder_ids: list[str], canonical_id: str | None = None) -> dict:
    """Move todo o conteúdo das pastas extras para a canônica e joga as extras
    (agora vazias) na lixeira. NUNCA apaga pasta que ainda tiver conteúdo após
    a tentativa de mover (falha fica reportada, não é silenciosa). Atualiza
    todos os clientes que apontavam para uma pasta extra."""
    tokens = _load_tokens()
    if not tokens:
        return {"ok": False, "erro": "sem_sessao_drive"}
    if len(folder_ids) < 2:
        return {"ok": False, "erro": "precisa_de_2_ou_mais_pastas"}

    if not canonical_id:
        # Prefere a pasta com mais itens diretos; empate → mais antiga (1ª da lista).
        contagens = [(fid, _contar_itens_diretos(fid, tokens)) for fid in folder_ids]
        canonical_id = max(contagens, key=lambda x: x[1])[0]

    extras = [f for f in folder_ids if f != canonical_id]
    h = _auth_headers(tokens)
    mesclados, falhas = [], []

    for extra_id in extras:
        r, tokens = _get_com_refresh(f"{DRIVE_META}/files", tokens, {
            "q": f"'{extra_id}' in parents and trashed=false",
            "fields": "files(id,name)", "pageSize": 200,
            "supportsAllDrives": True, "includeItemsFromAllDrives": True,
        })
        filhos = r.json().get("files", []) if r.status_code == 200 else []
        h = _auth_headers(tokens)
        erro_mover = False
        for filho in filhos:
            resp = httpx.patch(
                f"{DRIVE_META}/files/{filho['id']}", headers=h,
                params={"supportsAllDrives": True, "addParents": canonical_id,
                        "removeParents": extra_id, "fields": "id,parents"},
                timeout=30,
            )
            if not resp.is_success:
                erro_mover = True
                logger.warning("mesclar_cluster: falha ao mover %s de %s p/ %s: %s",
                                filho.get("name"), extra_id, canonical_id, resp.text[:200])

        restante = _contar_itens_diretos(extra_id, tokens)
        if restante == 0:
            resp = httpx.patch(
                f"{DRIVE_META}/files/{extra_id}", headers=h,
                params={"supportsAllDrives": True},
                content=b'{"trashed": true}',
                timeout=30,
            )
            resp.raise_for_status()
            mesclados.append(extra_id)
        else:
            falhas.append({"folder_id": extra_id, "itens_restantes": restante, "erro_mover": erro_mover})

    # Atualiza todo cliente que apontava pra uma pasta extra (mesclada ou não —
    # se a extra não pôde ser esvaziada, ainda assim o cliente deve apontar pra
    # canônica, que já recebeu o que pôde ser movido).
    db = SessionLocal()
    try:
        for extra_id in extras:
            db.execute(text(
                "UPDATE clientes SET drive_folder_id = :canon WHERE drive_folder_id = :extra"
            ), {"canon": canonical_id, "extra": extra_id})
        db.commit()
    finally:
        db.close()

    return {"ok": True, "canonical_id": canonical_id, "mesclados": mesclados, "falhas": falhas}
