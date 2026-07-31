"""Manutenção do Drive: encontra e mescla PASTAS DUPLICADAS (mesmo nome, mesmo
pai) mantendo a mais antiga e movendo o conteúdo das extras para dentro dela.

- Conta única (master) — ver google_drive._load_tokens.
- Merge é RECURSIVO: se a duplicada tem subpasta com nome que já existe na
  principal, as duas são mescladas também (e assim por diante).
- Arquivos são MOVIDOS (addParents/removeParents); pastas extras vazias são
  enviadas à lixeira. Nada é apagado de forma definitiva.
- `dry_run=True` (padrão) só registra as ações, sem tocar no Drive.
"""

import json
import logging

import httpx

from app.services.google_drive import (
    DRIVE_META,
    _auth_headers,
    _load_tokens,
    _refresh,
    registry_set,
    root_folder_id,
)

logger = logging.getLogger(__name__)
FOLDER_MIME = "application/vnd.google-apps.folder"


def _listar_conteudo(folder_id: str, headers: dict) -> list[dict]:
    """Filhos diretos (pastas e arquivos) de uma pasta."""
    itens: list[dict] = []
    page_token = None
    while True:
        params = {
            "q": f"'{folder_id}' in parents and trashed=false",
            "fields": "nextPageToken, files(id,name,mimeType,createdTime)",
            "orderBy": "createdTime",
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
            "pageSize": 1000,
        }
        if page_token:
            params["pageToken"] = page_token
        r = httpx.get(f"{DRIVE_META}/files", headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        itens.extend(data.get("files", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return itens


def _mover(item_id: str, novo_pai: str, antigo_pai: str, headers: dict) -> None:
    httpx.patch(
        f"{DRIVE_META}/files/{item_id}",
        headers=headers,
        params={"addParents": novo_pai, "removeParents": antigo_pai, "supportsAllDrives": True},
        timeout=30,
    ).raise_for_status()


def _trash(folder_id: str, headers: dict) -> None:
    httpx.patch(
        f"{DRIVE_META}/files/{folder_id}",
        headers={**headers, "Content-Type": "application/json"},
        params={"supportsAllDrives": True},
        content=json.dumps({"trashed": True}),
        timeout=30,
    ).raise_for_status()


def _merge_pasta(origem: dict, destino: dict, headers: dict, dry_run: bool, acoes: list[str], stats: dict) -> None:
    """Move todo o conteúdo de `origem` para `destino` (mesmo nome). Recursivo
    para subpastas de nome coincidente. Ao final, descarta `origem` se vazia.
    NENHUM arquivo é apagado — arquivos são MOVIDOS; só cascas vazias vão à lixeira."""
    filhos = _listar_conteudo(origem["id"], headers)
    destino_pastas = {
        f["name"]: f for f in _listar_conteudo(destino["id"], headers) if f["mimeType"] == FOLDER_MIME
    }
    for filho in filhos:
        eh_pasta = filho["mimeType"] == FOLDER_MIME
        if eh_pasta and filho["name"] in destino_pastas:
            acoes.append(f"MERGE pasta '{filho['name']}' ({filho['id']}) → {destino_pastas[filho['name']]['id']}")
            if not dry_run:
                _merge_pasta(filho, destino_pastas[filho["name"]], headers, dry_run, acoes, stats)
        else:
            acoes.append(f"MOVER {'📁' if eh_pasta else '📄'} '{filho['name']}' ({filho['id']}) → {destino['id']}")
            if not eh_pasta:
                stats["arquivos_movidos"] += 1
            if not dry_run:
                _mover(filho["id"], destino["id"], origem["id"], headers)
    # origem deve estar vazia agora
    acoes.append(f"TRASH pasta vazia '{origem['name']}' ({origem['id']})")
    if not dry_run:
        restantes = _listar_conteudo(origem["id"], headers)
        if not restantes:
            _trash(origem["id"], headers)
            stats["pastas_lixeira"].append({"name": origem["name"], "id": origem["id"]})
        else:
            acoes.append(f"  ⚠️ '{origem['name']}' ({origem['id']}) NÃO ficou vazia — mantida")


def consolidar(root_id: str | None = None, max_depth: int = 2, dry_run: bool = True) -> dict:
    """Varre a árvore (até max_depth) achando pastas-irmãs de mesmo nome e as
    mescla na mais antiga. Retorna resumo + lista de ações."""
    tokens = _load_tokens()
    if not tokens:
        return {"erro": "Google Drive não conectado", "grupos": 0, "acoes": []}

    def _run(tkns: dict) -> dict:
        from app.services.google_drive import registry_forget, registry_set
        headers = _auth_headers(tkns)
        acoes: list[str] = []
        stats = {"arquivos_movidos": 0, "pastas_lixeira": []}
        grupos_dup = 0
        pastas_mescladas = 0

        def _processar(pai_id: str, depth: int) -> None:
            nonlocal grupos_dup, pastas_mescladas
            pastas = [f for f in _listar_conteudo(pai_id, headers) if f["mimeType"] == FOLDER_MIME]
            por_nome: dict[str, list[dict]] = {}
            for p in pastas:
                por_nome.setdefault(p["name"], []).append(p)

            principais: list[dict] = []
            for nome, lst in por_nome.items():
                lst.sort(key=lambda f: f.get("createdTime") or "")
                principal = lst[0]
                principais.append(principal)
                if len(lst) > 1:
                    grupos_dup += 1
                    acoes.append(f"=== '{nome}' sob {pai_id}: {len(lst)} cópias → manter {principal['id']} (mais antiga) ===")
                    for extra in lst[1:]:
                        pastas_mescladas += 1
                        _merge_pasta(extra, principal, headers, dry_run, acoes, stats)
                    # Aponta o registro anti-duplicação para a pasta sobrevivente
                    if not dry_run:
                        registry_set(pai_id, nome, principal["id"])

            if depth < max_depth:
                for p in principais:
                    _processar(p["id"], depth + 1)

        _processar(root_id or root_folder_id(), 0)
        return {
            "dry_run": dry_run,
            "grupos_duplicados": grupos_dup,
            "pastas_mescladas": pastas_mescladas,
            "arquivos_movidos": stats["arquivos_movidos"],
            "arquivos_apagados": 0,  # esta rotina NUNCA apaga arquivos
            "pastas_lixeira": stats["pastas_lixeira"],
            "acoes": acoes,
        }

    try:
        return _run(tokens)
    except httpx.HTTPStatusError as exc:
        if exc.response is not None and exc.response.status_code == 401:
            return _run(_refresh(tokens))
        raise

