from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.models import email_cliente  # noqa: F401 — ensures EmailCliente table is registered
from app.models import reuniao  # noqa: F401 — ensures Reuniao table is registered
from app.routers import andamentos, anotacoes, auth, clientes, contratos, conversas_ia, diario, feriados, financeiro, jurisprudencia, organizador, pje, prazos, processos, reembolsos, reunioes, system, tarefas, teses, usuarios, webhooks

# Cria as tabelas (Alembic gerencia em produção; aqui facilita o dev)
Base.metadata.create_all(bind=engine)

# Migrations manuais para colunas novas em tabelas existentes
def _run_migrations() -> None:
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS analise_ia TEXT"
        ))
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS cliente_nome_pub VARCHAR(500)"
        ))
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS url_fonte TEXT"
        ))
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS match_tipo VARCHAR(30)"
        ))
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS match_nome VARCHAR(500)"
        ))
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS match_categoria VARCHAR(50)"
        ))
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS match_processo_id UUID"
        ))
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS match_detalhes TEXT"
        ))
        conn.execute(text(
            "ALTER TYPE fonte_publicacao ADD VALUE IF NOT EXISTS 'scraping_djen'"
        ))
        conn.execute(text(
            "ALTER TYPE fonte_publicacao ADD VALUE IF NOT EXISTS 'pje_comunica'"
        ))
        conn.execute(text(
            "ALTER TABLE contratos ADD COLUMN IF NOT EXISTS arquivos JSONB DEFAULT '[]'::jsonb"
        ))
        conn.execute(text(
            "ALTER TABLE conversas_ia ADD COLUMN IF NOT EXISTS parent_conversa_id UUID"
        ))
        conn.execute(text(
            "ALTER TABLE itens_reembolso ADD COLUMN IF NOT EXISTS comprovante_path VARCHAR(1000)"
        ))
        # Add "aguardando_pagamento" to the reembolso status enum (idempotent)
        conn.execute(text(
            "ALTER TYPE status_reembolso ADD VALUE IF NOT EXISTS 'aguardando_pagamento'"
        ))
        # Campos extras para honorários de êxito
        conn.execute(text(
            "ALTER TABLE honorarios ADD COLUMN IF NOT EXISTS valor_causa NUMERIC(14,2)"
        ))
        conn.execute(text(
            "ALTER TABLE honorarios ADD COLUMN IF NOT EXISTS percentual_exito NUMERIC(5,2)"
        ))
        conn.execute(text(
            "ALTER TABLE honorarios ADD COLUMN IF NOT EXISTS data_estimada_sentenca DATE"
        ))
        conn.execute(text(
            "ALTER TABLE reembolsos ADD COLUMN IF NOT EXISTS drive_link VARCHAR(1000)"
        ))
        conn.execute(text(
            "ALTER TABLE signatarios ADD COLUMN IF NOT EXISTS clicksign_request_key VARCHAR(255)"
        ))
        conn.execute(text(
            "ALTER TABLE conversas_ia ADD COLUMN IF NOT EXISTS processo_id UUID"
        ))
        conn.execute(text(
            "ALTER TABLE honorarios ADD COLUMN IF NOT EXISTS contrato_id UUID"
        ))
        conn.execute(text(
            "ALTER TABLE honorarios ADD COLUMN IF NOT EXISTS pendente_assinatura BOOLEAN NOT NULL DEFAULT false"
        ))
        conn.execute(text(
            "ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS cliente_id UUID"
        ))
        conn.execute(text(
            "ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS processo_id UUID"
        ))
        conn.execute(text(
            "ALTER TYPE status_reembolso ADD VALUE IF NOT EXISTS 'cancelado'"
        ))
        conn.execute(text(
            "ALTER TABLE contratos ADD COLUMN IF NOT EXISTS assinatura_manual BOOLEAN NOT NULL DEFAULT false"
        ))
        conn.execute(text(
            "ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS google_event_id VARCHAR(500)"
        ))
        # Andamentos sync fields on processos
        conn.execute(text(
            "ALTER TABLE processos ADD COLUMN IF NOT EXISTS ultimo_andamento_data DATE"
        ))
        conn.execute(text(
            "ALTER TABLE processos ADD COLUMN IF NOT EXISTS ultimo_andamento_desc VARCHAR(500)"
        ))
        conn.execute(text(
            "ALTER TABLE processos ADD COLUMN IF NOT EXISTS ultimo_check TIMESTAMPTZ"
        ))
        conn.execute(text(
            "ALTER TABLE processos ADD COLUMN IF NOT EXISTS tentativas_falha INTEGER NOT NULL DEFAULT 0"
        ))
        conn.execute(text(
            "ALTER TABLE processos ADD COLUMN IF NOT EXISTS andamentos_nao_lidos INTEGER NOT NULL DEFAULT 0"
        ))
        conn.execute(text(
            "ALTER TABLE processos ADD COLUMN IF NOT EXISTS orgao_julgador_tipo VARCHAR(30)"
        ))
        # Andamentos tables
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS andamentos_processo (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                processo_id UUID NOT NULL REFERENCES processos(id) ON DELETE CASCADE,
                data_andamento DATE,
                descricao TEXT NOT NULL,
                tipo VARCHAR(255),
                fonte VARCHAR(100),
                grau VARCHAR(10),
                hash_unico VARCHAR(64) NOT NULL,
                lido BOOLEAN NOT NULL DEFAULT true,
                notificado BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_andamentos_processo_id ON andamentos_processo(processo_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_andamentos_hash ON andamentos_processo(hash_unico)"
        ))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sincronizacao_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                processo_id UUID NOT NULL REFERENCES processos(id) ON DELETE CASCADE,
                tribunal VARCHAR(20),
                status VARCHAR(20) NOT NULL DEFAULT 'ok',
                novos_andamentos INTEGER DEFAULT 0,
                mensagem TEXT,
                iniciado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
                finalizado_em TIMESTAMPTZ
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_sincronizacao_processo_id ON sincronizacao_logs(processo_id)"
        ))
        # Controle de acesso — usuários
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) UNIQUE NOT NULL,
                nome VARCHAR(150) NOT NULL,
                senha_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'membro',
                ativo BOOLEAN NOT NULL DEFAULT true,
                pode_ver_financeiro BOOLEAN NOT NULL DEFAULT true,
                pode_ver_contratos BOOLEAN NOT NULL DEFAULT true,
                pode_ver_tarefas_outros BOOLEAN NOT NULL DEFAULT true,
                clientes_restritos BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_usuarios_email ON usuarios(email)"
        ))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_clientes (
                usuario_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
                PRIMARY KEY (usuario_id, cliente_id)
            )
        """))
        # Magic link + first-access fields on usuarios
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS invite_token VARCHAR(128)"))
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS invite_token_expires TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS primeiro_acesso BOOLEAN NOT NULL DEFAULT false"))
        # senha_hash is now nullable (set on invite acceptance)
        conn.execute(text("ALTER TABLE usuarios ALTER COLUMN senha_hash DROP NOT NULL"))
        # Per-user Google OAuth tokens (JSONB)
        conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS google_tokens JSONB"))
        # Emails per client — synced from Gmail accounts
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS emails_cliente (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
                gmail_message_id VARCHAR(255) NOT NULL UNIQUE,
                conta_google VARCHAR(36) NOT NULL,
                conta_email VARCHAR(255),
                remetente VARCHAR(500),
                destinatarios TEXT,
                assunto VARCHAR(1000),
                snippet TEXT,
                thread_id VARCHAR(255),
                data TIMESTAMPTZ,
                lido BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_emails_cliente_id ON emails_cliente(cliente_id)"
        ))
        # Reuniões Google Meet / Gemini
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS reunioes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                cliente_id UUID REFERENCES clientes(id) ON DELETE CASCADE,
                processo_id UUID REFERENCES processos(id) ON DELETE SET NULL,
                titulo VARCHAR(500) NOT NULL,
                data_reuniao TIMESTAMPTZ,
                duracao_minutos INTEGER,
                google_meet_url VARCHAR(1000),
                drive_transcricao_file_id VARCHAR(500),
                drive_notas_file_id VARCHAR(500),
                drive_tldr_file_id VARCHAR(500),
                transcricao_texto TEXT,
                resumo_ia TEXT,
                acoes_sugeridas JSONB DEFAULT '[]'::jsonb,
                status VARCHAR(50) NOT NULL DEFAULT 'pendente',
                fonte VARCHAR(50) NOT NULL DEFAULT 'manual',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_reunioes_cliente_id ON reunioes(cliente_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_reunioes_status ON reunioes(status)"
        ))
        # Confidentiality + creator fields (additive migration)
        for col_sql in [
            "ALTER TABLE reunioes ADD COLUMN IF NOT EXISTS criado_por_id UUID REFERENCES usuarios(id) ON DELETE SET NULL",
            "ALTER TABLE reunioes ADD COLUMN IF NOT EXISTS confidencial BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE reunioes ADD COLUMN IF NOT EXISTS usuarios_com_acesso JSONB DEFAULT '[]'::jsonb",
            # Anotacao: source meeting link + confidential flag
            "ALTER TABLE anotacoes ADD COLUMN IF NOT EXISTS reuniao_id UUID REFERENCES reunioes(id) ON DELETE SET NULL",
            "ALTER TABLE anotacoes ADD COLUMN IF NOT EXISTS confidencial BOOLEAN NOT NULL DEFAULT FALSE",
            # Tarefa: creator + confidentiality
            "ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS criado_por_id UUID REFERENCES usuarios(id) ON DELETE SET NULL",
            "ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS confidencial BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS usuarios_com_acesso JSONB DEFAULT '[]'::jsonb",
        ]:
            conn.execute(text(col_sql))

        # Retroactive: link existing 'reuniao'-type annotations to their confidential source meeting
        # by matching cliente_id + closest date. Sets reuniao_id + confidencial=TRUE.
        conn.execute(text("""
            UPDATE anotacoes a
            SET
                reuniao_id = sub.reuniao_id,
                confidencial = TRUE
            FROM (
                SELECT DISTINCT ON (a2.id)
                    a2.id AS anotacao_id,
                    r.id  AS reuniao_id
                FROM anotacoes a2
                JOIN reunioes r ON r.cliente_id = a2.cliente_id AND r.confidencial = TRUE
                WHERE a2.tipo = 'reuniao'
                  AND a2.reuniao_id IS NULL
                ORDER BY a2.id, ABS(EXTRACT(EPOCH FROM (r.data_reuniao - a2.data_evento::timestamp)))
            ) sub
            WHERE a.id = sub.anotacao_id
        """))

        conn.commit()


def _seed_super_admin() -> None:
    """Ensure Super Admin exists (idempotent)."""
    from app.database import SessionLocal
    from app.models.usuario import Usuario
    from app.services.auth_service import hash_senha

    SUPER_ADMIN_EMAIL = "pj@pimentajudice.com.br"
    SUPER_ADMIN_NOME = "Pimenta Judice"
    SUPER_ADMIN_SENHA = "admin2024"  # change after first login

    db = SessionLocal()
    try:
        existing = db.query(Usuario).filter(Usuario.email == SUPER_ADMIN_EMAIL).first()
        if not existing:
            admin = Usuario(
                email=SUPER_ADMIN_EMAIL,
                nome=SUPER_ADMIN_NOME,
                senha_hash=hash_senha(SUPER_ADMIN_SENHA),
                role="super_admin",
                ativo=True,
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()


_run_migrations()
_seed_super_admin()

app = FastAPI(
    title="Sui",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(clientes.router)
app.include_router(anotacoes.router)
app.include_router(contratos.router)
app.include_router(processos.router)
app.include_router(prazos.router)
app.include_router(feriados.router)
app.include_router(diario.router)
app.include_router(teses.router)
app.include_router(reembolsos.router)
app.include_router(financeiro.router)
app.include_router(tarefas.router)
app.include_router(conversas_ia.router)
app.include_router(organizador.router)
app.include_router(jurisprudencia.router)
app.include_router(pje.router)
app.include_router(system.router)
app.include_router(andamentos.router)
app.include_router(usuarios.router)
app.include_router(reunioes.router)
app.include_router(webhooks.router)


@app.on_event("startup")
def _startup():
    try:
        from app.scheduler import start_scheduler
        start_scheduler()
    except ModuleNotFoundError:
        import logging
        logging.getLogger(__name__).warning("apscheduler não instalado — scheduler desativado")

    # Auto-registra Drive webhook se ainda não estiver ativo
    try:
        import os
        from app.services.drive_watch import channel_ativo, registrar_watch
        if not channel_ativo():
            base_url = os.getenv("WEBHOOK_BASE_URL", "https://lexops.fly.dev")
            result = registrar_watch(base_url)
            import logging
            log = logging.getLogger(__name__)
            if "erro" in result:
                log.warning("Drive webhook não registrado no startup: %s", result["erro"])
            else:
                log.info("Drive webhook registrado automaticamente no startup: %s", result.get("channel_id"))
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Erro ao registrar Drive webhook no startup: %s", exc)


@app.on_event("shutdown")
def _shutdown():
    try:
        from app.scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass


@app.get("/health")
def health():
    return {"status": "ok"}
