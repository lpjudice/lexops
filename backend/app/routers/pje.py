"""
PJe Comunica — credenciais e sincronização de comunicações processuais.
Credenciais armazenadas em /app/uploads/pje_config.json (persistente via volume).
"""
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_current_user

router = APIRouter(prefix="/pje", tags=["pje"],
                   dependencies=[Depends(get_current_user)])
CONFIG_PATH = Path("/app/uploads/pje_config.json")


def _ler_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def _salvar_config(config: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2))


class PjeCredenciais(BaseModel):
    login_cpf: str
    senha: str


@router.get("/config")
def obter_config():
    cfg = _ler_config()
    return {"configurado": bool(cfg.get("login_cpf")), "login_cpf": cfg.get("login_cpf", "")}


@router.post("/config")
def salvar_credenciais(body: PjeCredenciais):
    _salvar_config({"login_cpf": body.login_cpf, "senha": body.senha})
    return {"ok": True}


@router.post("/sync")
def sync_pje():
    """Autentica no PJe Comunica e importa comunicações processuais como publicações."""
    cfg = _ler_config()
    if not cfg.get("login_cpf") or not cfg.get("senha"):
        raise HTTPException(status_code=400, detail="Credenciais PJe não configuradas. Acesse /configuracoes.")

    from app.services.pje_comunica import login, listar_comunicacoes, comunicacoes_para_publicacoes

    token = login(cfg["login_cpf"], cfg["senha"])
    if not token:
        raise HTTPException(status_code=401, detail="Login PJe falhou. Verifique CPF e senha em /configuracoes.")

    itens = listar_comunicacoes(token, page=0, size=50)
    publicacoes_data = comunicacoes_para_publicacoes(itens)

    # Import into DB (same dedup logic as diario scraping)
    from app.database import SessionLocal
    from app.models.publicacao import Publicacao
    from sqlalchemy.orm import Session

    db: Session = SessionLocal()
    try:
        inseridas = 0
        duplicatas = 0
        for pub_data in publicacoes_data:
            # Dedup by numero_cnj + fonte + data
            exists = db.query(Publicacao).filter(
                Publicacao.fonte == pub_data["fonte"],
                Publicacao.data_publicacao == pub_data["data_publicacao"],
                Publicacao.numero_cnj == pub_data.get("numero_cnj"),
            ).first()
            if exists:
                duplicatas += 1
                continue
            pub = Publicacao(**{k: v for k, v in pub_data.items() if k != "email_message_id"})
            db.add(pub)
            inseridas += 1
        db.commit()
    finally:
        db.close()

    return {"inseridas": inseridas, "duplicatas": duplicatas, "total_pje": len(itens)}
