"""Sincronização local do Informativo STF — roda no Mac do usuário, não no servidor.

O site do STF (stf.jus.br) bloqueia o IP de datacenter do servidor (Fly.io)
com 403, mas não bloqueia rede residencial/doméstica. Este script conecta
DIRETO no Postgres de produção (mesmo padrão dos outros scripts em
backend/scripts/) e roda a sincronização a partir desta máquina.

Uso:
    cd backend
    DATABASE_URL="postgresql://..." .venv/bin/python scripts/sync_informativo_stf_local.py

Agendado via launchd (~/Library/LaunchAgents/com.lexops.informativostf.plist),
que dispara este script a cada 30 min. A cada execução, o script decide se
"está na hora" de rodar:
  - pedido manual pendente (sync_local_solicitado_em mais recente que
    sync_local_ultimo_em) — o botão "Rodar sincronização agora" no site grava
    esse campo;
  - ou agenda semanal: segunda-feira a partir das 13h, se ainda não rodou
    esta semana.
Se o Mac estiver desligado na hora agendada, a próxima execução (quando o
Mac ligar e o launchd disparar de novo) resolve sozinha.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env.production"))

from app.database import SessionLocal  # noqa: E402
from app.models.informativo_stf import InformativoStfConfig  # noqa: E402
from app.services import scraping_informativo_stf  # noqa: E402


def _deve_rodar(config: InformativoStfConfig, agora: datetime) -> bool:
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


def main() -> None:
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
            resultado = scraping_informativo_stf.sincronizar_processar_e_notificar(db)
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


if __name__ == "__main__":
    main()
