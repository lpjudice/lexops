"""
Gestão de pastas de clientes no filesystem local (Dropbox/LexOps).
Volume Docker: /host/clientes → /Users/lucasjudice/Dropbox/Clientes/LexOps

Estrutura de pastas por cliente:
  {nome_cliente}/
    Contratos/
    Reembolsos/
    IA/
    Publicações/
    Teses/
    Uploads/
    {numero_cnj}/   ← subpasta por processo
"""
import re
import os
from datetime import datetime
from pathlib import Path

_DOCKER_HOST_DIR = Path("/host/clientes")
_MAC_HOST_DIR = Path("/Users/lucasjudice/Dropbox/Clientes/LexOps")


def _base_dir() -> Path:
    configured = os.getenv("CLIENTES_HOST_DIR")
    if configured:
        return Path(configured)
    if _DOCKER_HOST_DIR.exists():
        return _DOCKER_HOST_DIR
    if _MAC_HOST_DIR.exists():
        return _MAC_HOST_DIR
    return _DOCKER_HOST_DIR


HOST_DIR = _base_dir()

# Mapeamento tipo → nome da pasta
SUBPASTAS: dict[str, str] = {
    "contratos":       "Contratos",
    "reembolsos":      "Reembolsos",
    "anotacoes":       "Anotações",
    "ia":              "IA",
    "publicacoes":     "Publicações",
    "teses":           "Teses",
    "uploads":         "Uploads",
    "jurisprudencia":  "Jurisprudência",
    "patrimonio":      "Patrimônio",
}


def _host_disponivel() -> bool:
    return HOST_DIR.exists()


def _safe_name(nome: str) -> str:
    """Remove only truly invalid filesystem chars, preserves accents and spaces."""
    return re.sub(r'[/\\:*?"<>|]', '', nome).strip()


def pasta_cliente(nome: str) -> Path:
    p = HOST_DIR / _safe_name(nome)
    if _host_disponivel():
        p.mkdir(parents=True, exist_ok=True)
    return p


def pasta_tipo(nome_cliente: str, tipo: str) -> Path:
    """Returns (and creates) the subfolder for a document type under the client folder."""
    nome_pasta = SUBPASTAS.get(tipo, tipo)
    p = pasta_cliente(nome_cliente) / nome_pasta
    if _host_disponivel():
        p.mkdir(parents=True, exist_ok=True)
    return p


def pasta_processo(nome_cliente: str, numero_cnj: str) -> Path:
    cnj_safe = re.sub(r'[/\\:*?"<>|]', '-', numero_cnj).strip()
    p = pasta_cliente(nome_cliente) / cnj_safe
    if _host_disponivel():
        p.mkdir(parents=True, exist_ok=True)
    return p


def salvar_arquivo(pasta: Path, nome_arquivo: str, conteudo: bytes) -> Path:
    dest = pasta / nome_arquivo
    dest.write_bytes(conteudo)
    return dest


def salvar_md(pasta: Path, nome_arquivo: str, conteudo: str) -> Path:
    dest = pasta / nome_arquivo
    dest.write_text(conteudo, encoding="utf-8")
    return dest


def listar_subpastas(nome_cliente: str) -> list[dict]:
    """Lists all subfolders inside the client folder (processes + type folders)."""
    if not _host_disponivel():
        return []
    pasta = HOST_DIR / _safe_name(nome_cliente)
    if not pasta.exists():
        return []
    result = []
    for item in sorted(pasta.iterdir()):
        if item.is_dir():
            num_arquivos = sum(1 for f in item.iterdir() if f.is_file())
            result.append({
                "nome": item.name,
                "caminho_host": str(item).replace("/host/clientes", "/Users/lucasjudice/Dropbox/Clientes/LexOps"),
                "num_arquivos": num_arquivos,
            })
    return result


def listar_arquivos(nome_cliente: str) -> list[dict]:
    """Lists all files recursively in the client folder (root + subfolders)."""
    if not _host_disponivel():
        return []
    pasta = HOST_DIR / _safe_name(nome_cliente)
    if not pasta.exists():
        return []
    result = []
    for item in sorted(pasta.iterdir()):
        if item.is_file():
            result.append({
                "nome": item.name,
                "tamanho": item.stat().st_size,
                "modificado": datetime.fromtimestamp(item.stat().st_mtime).isoformat(),
                "tipo": item.suffix.lower().lstrip(".") or "file",
                "subpasta": None,
                "caminho": str(item),
            })
        elif item.is_dir():
            for sub in sorted(item.iterdir()):
                if sub.is_file():
                    result.append({
                        "nome": sub.name,
                        "tamanho": sub.stat().st_size,
                        "modificado": datetime.fromtimestamp(sub.stat().st_mtime).isoformat(),
                        "tipo": sub.suffix.lower().lstrip(".") or "file",
                        "subpasta": item.name,
                        "caminho": str(sub),
                    })
    return result


def renomear_pasta_cliente(nome_antigo: str, nome_novo: str) -> bool:
    if not _host_disponivel():
        return False
    p_antigo = HOST_DIR / _safe_name(nome_antigo)
    p_novo = HOST_DIR / _safe_name(nome_novo)
    if p_antigo.exists() and not p_novo.exists():
        p_antigo.rename(p_novo)
        return True
    return False


def caminho_host(nome_cliente: str, subfolder: str | None = None) -> str:
    """Returns the macOS host path (for display / clipboard)."""
    base_dir = _base_dir()
    if str(base_dir) == "/host/clientes":
        base = f"/Users/lucasjudice/Dropbox/Clientes/LexOps/{_safe_name(nome_cliente)}"
    else:
        base = str(base_dir / _safe_name(nome_cliente))
    if subfolder:
        return f"{base}/{subfolder}"
    return base


def carregar_contexto_gemini(nome_cliente: str) -> list[dict]:
    """
    Loads ALL files from client folder (recursively) for Gemini AI context.
    Returns list of {tipo: 'pdf'|'texto', nome, conteudo/texto}
    Skips files > 5MB. Stops if total payload exceeds 50MB.
    """
    if not _host_disponivel():
        return []
    pasta = HOST_DIR / _safe_name(nome_cliente)
    if not pasta.exists():
        return []
    arquivos = []
    total_bytes = 0
    MAX_FILE = 5 * 1024 * 1024    # 5MB
    MAX_TOTAL = 50 * 1024 * 1024  # 50MB
    for item in sorted(pasta.rglob("*")):
        if not item.is_file():
            continue
        if total_bytes >= MAX_TOTAL:
            break
        file_size = item.stat().st_size
        if file_size > MAX_FILE:
            continue
        ext = item.suffix.lower()
        try:
            if ext == ".pdf":
                conteudo = item.read_bytes()
                arquivos.append({"tipo": "pdf", "nome": item.name, "conteudo": conteudo})
                total_bytes += len(conteudo)
            elif ext in (".md", ".txt"):
                texto = item.read_text(encoding="utf-8")
                arquivos.append({"tipo": "texto", "nome": item.name, "texto": texto})
                total_bytes += len(texto.encode("utf-8"))
        except Exception:
            pass
    return arquivos
