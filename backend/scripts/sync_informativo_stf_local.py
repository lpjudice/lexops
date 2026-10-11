"""Sincronização local do Informativo STF — roda no Mac do usuário, não no servidor.

O site do STF (stf.jus.br) bloqueia o IP de datacenter do servidor (Fly.io)
com 403, mas não bloqueia rede residencial/doméstica. Este script roda a
sincronização a partir desta máquina e grava direto no Postgres de produção.

O Postgres de produção só é alcançável pela rede interna do Fly
(`lexops-db.flycast`) — por isso o script abre um túnel local com
`flyctl proxy` antes de conectar (equivalente ao que `flyctl postgres
connect` faz por baixo dos panos), usando a DATABASE_URL "crua" (a mesma
que `flyctl ssh console -a lexops -C "printenv DATABASE_URL"` devolve) só
pra extrair usuário/senha/banco — o host:porta usados na conexão real são
os do túnel local.

Uso:
    cd backend
    cp .env.production.example .env.production   # cole a DATABASE_URL crua
    .venv/bin/python scripts/sync_informativo_stf_local.py

Este script faz SÓ o scraping (inserir edições/itens novos) — não gera
resumo de IA nem manda e-mail. Isso roda no servidor (tem a chave do
Gemini), num job frequente (a cada hora) que pega o que este script
inserir, sem precisar dos dois rodarem no mesmo instante — ver
app.scheduler._processar_pendentes_informativo_stf.

Agendado via launchd (~/Library/LaunchAgents/com.lexops.informativostf.plist),
que dispara este script a cada 30 min. A cada execução, o script decide se
"está na hora" de rodar:
  - pedido manual pendente (sync_local_solicitado_em mais recente que
    sync_local_ultimo_em) — o botão "Rodar sincronização agora" no site grava
    esse campo;
  - ou agenda semanal: segunda-feira a partir das 13h, se ainda não rodou
    esta semana.
Se o Mac estiver desligado na hora agendada, a próxima execução (quando o
Mac ligar e o launchd disparar de novo) resolve sozinha. Dentro de 1h depois
disso, o resumo de IA e o e-mail de destaques saem sozinhos pelo servidor.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(BACKEND_DIR, ".env.production"))

FLYCTL_PATHS = [
    os.path.expanduser("~/.fly/bin/flyctl"),
    "/usr/local/bin/flyctl",
    "flyctl",
]
PG_APP = "lexops-db"
PORTA_LOCAL = 15432


def _flyctl_bin() -> str:
    for p in FLYCTL_PATHS:
        if p == "flyctl" or os.path.exists(p):
            return p
    return "flyctl"


def _abrir_tunel() -> subprocess.Popen:
    """Abre `flyctl proxy` pra rede privada do Postgres (lexops-db.flycast)."""
    proc = subprocess.Popen(
        [_flyctl_bin(), "proxy", f"{PORTA_LOCAL}:5432", "-a", PG_APP],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    for _ in range(30):
        try:
            with socket.create_connection(("localhost", PORTA_LOCAL), timeout=1):
                return proc
        except OSError:
            time.sleep(1)
    proc.terminate()
    raise RuntimeError("Túnel flyctl proxy não abriu em 30s — veja se `flyctl` está logado (flyctl auth whoami).")


def _database_url_via_tunel() -> str:
    cru = os.environ.get("DATABASE_URL", "")
    if not cru:
        raise RuntimeError("DATABASE_URL não encontrada em backend/.env.production")
    partes = urlparse(cru.replace("postgres://", "postgresql://", 1))
    netloc = f"{partes.username}:{partes.password}@localhost:{PORTA_LOCAL}"
    return urlunparse(partes._replace(netloc=netloc))


def _importar_todos_os_models() -> None:
    """O grafo de relacionamentos do SQLAlchemy é compartilhado entre TODOS os
    models (ex: Processo -> AndamentoProcesso) — importar só o model do STF
    não basta, o mapper falha ao resolver nomes de classe não carregados
    neste processo. Importa cada arquivo de app/models/ (não os routers, que
    têm efeitos colaterais tipo criar /app/uploads — caminho só existe dentro
    do container Docker)."""
    import importlib
    import pkgutil

    import app.models as models_pkg

    for info in pkgutil.iter_modules(models_pkg.__path__):
        importlib.import_module(f"app.models.{info.name}")


def main() -> None:
    tunel = _abrir_tunel()
    try:
        os.environ["DATABASE_URL"] = _database_url_via_tunel()

        _importar_todos_os_models()

        from app.database import SessionLocal
        from app.models.informativo_stf import InformativoStfConfig
        from app.services import scraping_informativo_stf

        db = SessionLocal()
        try:
            config = db.get(InformativoStfConfig, 1)
            if not config:
                config = InformativoStfConfig(id=1, areas_selecionadas=[], keywords_livres=[])
                db.add(config)
                db.commit()

            agora = datetime.now(timezone.utc)
            if not _deve_rodar(config, agora):
                print(f"[{agora.isoformat()}] Nada a fazer agora.")
                return

            print(f"[{agora.isoformat()}] Rodando sincronização do Informativo STF...")
            try:
                resultado = scraping_informativo_stf.sincronizar_novas_edicoes(db)
                erro = resultado.get("erro")
                if erro:
                    config.sync_local_ultimo_status = "erro"
                    config.sync_local_ultima_mensagem = str(erro)[:2000]
                    print("ERRO:", erro)
                else:
                    config.sync_local_ultimo_status = "ok"
                    config.sync_local_ultima_mensagem = f"{resultado.get('edicoes_processadas', 0)} edição(ões) processada(s)."
                    print("OK:", resultado)
            except Exception as exc:  # noqa: BLE001
                config.sync_local_ultimo_status = "erro"
                config.sync_local_ultima_mensagem = str(exc)[:2000]
                print("EXCEÇÃO:", exc)

            config.sync_local_ultimo_em = datetime.now(timezone.utc)
            db.commit()
        finally:
            db.close()
    finally:
        tunel.terminate()
        try:
            tunel.wait(timeout=5)
        except subprocess.TimeoutExpired:
            tunel.kill()


def _deve_rodar(config, agora: datetime) -> bool:
    if config.sync_local_solicitado_em and (
        not config.sync_local_ultimo_em or config.sync_local_solicitado_em > config.sync_local_ultimo_em
    ):
        return True  # pedido manual pendente ("Rodar sincronização agora")

    # Agenda semanal: segunda a partir das 13h, só 1x por semana.
    e_segunda_tarde = agora.weekday() == 0 and agora.hour >= 13
    if not e_segunda_tarde:
        return False
    if not config.sync_local_ultimo_em:
        return True
    return (agora - config.sync_local_ultimo_em) > timedelta(days=6)


if __name__ == "__main__":
    main()
