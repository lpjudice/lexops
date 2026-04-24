"""
System utilities: abrir pasta no Finder, info da máquina.
"""
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/abrir-pasta")
def abrir_pasta(path: str = Query(..., description="Caminho da pasta a abrir no Finder")):
    """
    Abre uma pasta no Finder do macOS.
    Funciona apenas quando o backend roda no host (não em Docker).
    """
    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Pasta não encontrada: {path}")
    try:
        subprocess.Popen(["open", str(p)])
        return {"ok": True, "path": str(p)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pasta-cliente-path")
def pasta_cliente_path(nome: str = Query(...)):
    """Retorna o caminho macOS da pasta de um cliente."""
    from app.services.pasta_cliente import caminho_host
    return {"path": caminho_host(nome)}
