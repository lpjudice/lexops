from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.models import email_cliente  # noqa: F401 — ensures EmailCliente table is registered
from app.models import reuniao  # noqa: F401 — ensures Reuniao table is registered
from app.models import jusbr_session as _jusbr_session_model  # noqa: F401 — ensures JusbrSession table is registered
from app.models import telegram_conversa as _telegram_conversa_model  # noqa: F401 — ensures TelegramConversa table is registered
from app.models import processo_telegram_extra as _processo_telegram_extra_model  # noqa: F401
from app.models import processo_parte as _processo_parte_model  # noqa: F401
from app.models import andamento_telegram_extra as _andamento_telegram_extra_model  # noqa: F401
from app.models import nota_fiscal as _nota_fiscal_model  # noqa: F401
from app.models import config_fiscal as _config_fiscal_model  # noqa: F401
from app.models import relatorio_fiscal_log as _relatorio_fiscal_log_model  # noqa: F401
from app.models import telegram_task as _telegram_task_model  # noqa: F401 — TelegramTaskBatch/Item/Session
from app.models import backoffice as _backoffice_model  # noqa: F401
from app.models import precedentcheck as _precedentcheck_model  # noqa: F401
from app.models import tarefa_projeto as _tarefa_projeto_model  # noqa: F401
from app.models import pagante as _pagante_model  # noqa: F401 — ensures Pagante table is registered
from app.models import conselho as _conselho_model  # noqa: F401 — ensures Conselho tables are registered
from app.models import tarefa_card as _tarefa_card_model  # noqa: F401 — ensures TarefaCard tables are registered
from app.models import memoria_estrategica as _memoria_estrategica_model  # noqa: F401 — ensures MemoriaEstrategica table is registered
from app.models import responsavel as _responsavel_model  # noqa: F401 — ensures Responsavel table is registered
from app.models import patrimonio as _patrimonio_model  # noqa: F401 — ensures Patrimonio tables are registered
from app.models import cadastro_link as _cadastro_link_model  # noqa: F401 — ensures ClienteCadastroLink/Submissao tables are registered
from app.models import instagram as _instagram_model  # noqa: F401 — ensures InstagramSugestao table is registered
from app.models import informativo as _informativo_model  # noqa: F401 — ensures Informativo table is registered
from app.routers import andamentos, anotacoes, auth, clientes, contratos, conversas_ia, diario, diario2, feriados, financeiro, fiscal, pagantes, config_fiscal, jurisprudencia, organizador, pje, prazos, processos, publico, reembolsos, reunioes, system, tarefas, telegram, telegram_andamentos, telegram_tasks, teses, usuarios, webhooks
from app.routers import backoffice, precedentcheck, conselho, tarefa_projetos, tarefa_cards, memoria_estrategica, despacho, conselho_juridico, responsaveis, patrimonio, instagram
from app.routers import cadastro_links, cadastro_publico, cadastro_submissoes
from app.routers import informativos

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
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS rejeitada BOOLEAN NOT NULL DEFAULT false"
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
            "ALTER TABLE reembolsos ADD COLUMN IF NOT EXISTS email_destinatario VARCHAR(255)"
        ))
        conn.execute(text(
            "ALTER TABLE reembolsos ADD COLUMN IF NOT EXISTS ultimo_lembrete_em TIMESTAMPTZ"
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
        # Identificador único do documento (anti-colisão de dedup quando dois
        # documentos do mesmo movimento têm descrição idêntica).
        conn.execute(text(
            "ALTER TABLE andamentos_processo ADD COLUMN IF NOT EXISTS documento_id VARCHAR(500)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_andamentos_documento_id ON andamentos_processo(processo_id, documento_id)"
        ))
        # Indicador visual da última sincronização (ok | incompleto | erro).
        conn.execute(text(
            "ALTER TABLE processos ADD COLUMN IF NOT EXISTS ultimo_sync_status VARCHAR(20)"
        ))
        # Vínculo estável da pasta-raiz do cliente no Drive (imune a renome do cliente).
        conn.execute(text(
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS drive_folder_id VARCHAR(255)"
        ))
        # Conta Gmail extra por usuário (3ª fonte de busca de emails).
        conn.execute(text(
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS google_tokens_extra JSONB"
        ))
        # Privacidade dos emails de cliente (padrão público; privado restringe).
        conn.execute(text(
            "ALTER TABLE emails_cliente ADD COLUMN IF NOT EXISTS privado BOOLEAN NOT NULL DEFAULT false"
        ))
        conn.execute(text(
            "ALTER TABLE emails_cliente ADD COLUMN IF NOT EXISTS privado_por UUID"
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
        # Sessão jus.br/PDPJ compartilhada — persistida no Postgres (sobrevive a deploys)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS jusbr_sessions (
                id INTEGER PRIMARY KEY DEFAULT 1,
                data JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
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
        # Diário Oficial: dedup por id estável da Comunica + match por OAB
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS comunica_id VARCHAR(64)"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_publicacoes_comunica_id ON publicacoes (comunica_id)"
        ))
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS match_oab VARCHAR(20)"
        ))
        # Cliente: opt-in de monitoramento por nome no Diário Oficial
        conn.execute(text(
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS monitorar_diario BOOLEAN NOT NULL DEFAULT false"
        ))
        # Reembolsos: múltiplos comprovantes por despesa (bot do Telegram)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS comprovantes_item (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                item_id UUID NOT NULL REFERENCES itens_reembolso(id) ON DELETE CASCADE,
                filename VARCHAR(500),
                file_path VARCHAR(1000),
                drive_link VARCHAR(1000),
                mime VARCHAR(100),
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        # Estado da conversa do bot do Telegram
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_conversas (
                chat_id BIGINT PRIMARY KEY,
                state VARCHAR(50) NOT NULL DEFAULT 'idle',
                data JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        # Comprovantes recebidos pelo bot (reconciliação /pendentes)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_docs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                chat_id BIGINT NOT NULL,
                file_id VARCHAR(400) NOT NULL,
                file_unique_id VARCHAR(200),
                filename VARCHAR(500),
                mime VARCHAR(100),
                valor_detectado NUMERIC(12,2),
                status VARCHAR(20) NOT NULL DEFAULT 'pendente',
                item_id UUID,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """))

        # ── Bot @jusbr_andamentos_bot — push diário e CNJs avulsos ──────────
        # Flag por processo para ligar/desligar o push diário do Telegram.
        conn.execute(text(
            "ALTER TABLE processos ADD COLUMN IF NOT EXISTS notificar_telegram BOOLEAN NOT NULL DEFAULT TRUE"
        ))
        # Parte contrária — texto livre, editável na mão ou sugerido após sync jus.br.
        conn.execute(text(
            "ALTER TABLE processos ADD COLUMN IF NOT EXISTS parte_contraria VARCHAR(500)"
        ))
        # CNJs adicionados via /add no bot que não estão na carteira do escritório.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS processos_telegram_extras (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                cnj VARCHAR(25) UNIQUE NOT NULL,
                nome_cliente VARCHAR(255),
                apelido VARCHAR(255),
                descricao TEXT,
                info_adicional VARCHAR(120),
                tribunal VARCHAR(20),
                vara VARCHAR(255),
                comarca VARCHAR(255),
                notificar BOOLEAN NOT NULL DEFAULT TRUE,
                criado_por_chat_id BIGINT,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        # Partes coletadas via PDPJ (polo ativo / passivo / etc).
        # Vincula a processos (escritório) OU a processos_telegram_extras (avulsos),
        # exatamente UM dos dois. Polo: ATIVO / PASSIVO / OUTROS.
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS processo_partes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                processo_id UUID REFERENCES processos(id) ON DELETE CASCADE,
                extra_id UUID REFERENCES processos_telegram_extras(id) ON DELETE CASCADE,
                polo VARCHAR(20) NOT NULL,
                nome VARCHAR(500) NOT NULL,
                tipo_pessoa VARCHAR(20),
                documento VARCHAR(50),
                ordem INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT now(),
                CHECK ((processo_id IS NOT NULL) <> (extra_id IS NOT NULL))
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_processo_partes_processo ON processo_partes(processo_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_processo_partes_extra ON processo_partes(extra_id)"
        ))
        # Andamentos dos CNJs avulsos (não estão em processos do escritório).
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS andamentos_telegram_extras (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                extra_id UUID NOT NULL REFERENCES processos_telegram_extras(id) ON DELETE CASCADE,
                data_andamento DATE,
                descricao TEXT NOT NULL,
                tipo VARCHAR(255),
                arquivo_nome VARCHAR(500),
                arquivo_url TEXT,
                hash_unico VARCHAR(64) UNIQUE NOT NULL,
                notificado BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_andamentos_telegram_extra ON andamentos_telegram_extras(extra_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_andamentos_telegram_extra_notif "
            "ON andamentos_telegram_extras(notificado) WHERE notificado = FALSE"
        ))

        # ── NFS-e Nacional ───────────────────────────────────────────────────
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS notas_fiscais (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                numero_nfse VARCHAR(50),
                chave_acesso VARCHAR(200) UNIQUE,
                serie VARCHAR(10) NOT NULL DEFAULT '1',
                numero_dps INTEGER,
                competencia VARCHAR(7) NOT NULL,
                data_emissao DATE,
                prestador_cnpj VARCHAR(14) NOT NULL DEFAULT '10901611000164',
                tomador_cpf_cnpj VARCHAR(14) NOT NULL,
                tomador_nome VARCHAR(200) NOT NULL,
                tomador_email VARCHAR(100),
                tomador_telefone VARCHAR(11),
                tomador_logradouro VARCHAR(200),
                tomador_numero VARCHAR(10),
                tomador_complemento VARCHAR(60),
                tomador_bairro VARCHAR(100),
                tomador_cod_municipio VARCHAR(7),
                tomador_cep VARCHAR(8),
                cod_tributacao_nacional VARCHAR(20) NOT NULL,
                descricao_servico TEXT NOT NULL,
                valor_servicos NUMERIC(14,2) NOT NULL,
                retencao_ir NUMERIC(14,2),
                retencao_inss NUMERIC(14,2),
                retencao_csll NUMERIC(14,2),
                retencao_cofins NUMERIC(14,2),
                retencao_pis NUMERIC(14,2),
                ibs_valor NUMERIC(14,2),
                cbs_valor NUMERIC(14,2),
                status VARCHAR(20) NOT NULL DEFAULT 'rascunho',
                erro_mensagem TEXT,
                xml_nfse TEXT,
                honorario_id UUID REFERENCES honorarios(id) ON DELETE SET NULL,
                recebimento_id UUID REFERENCES recebimentos(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_notas_fiscais_competencia ON notas_fiscais(competencia)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_notas_fiscais_status ON notas_fiscais(status)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_notas_fiscais_honorario ON notas_fiscais(honorario_id)"
        ))
        # Colunas adicionadas na v2 do módulo fiscal
        for _col in [
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS natureza_operacao VARCHAR(2) NOT NULL DEFAULT '1'",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS regime_tributario VARCHAR(2) NOT NULL DEFAULT '1'",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS iss_retido BOOLEAN NOT NULL DEFAULT false",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS contrato_id UUID",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS cliente_id UUID",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS processo_id UUID",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS pdf_path VARCHAR(1000)",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS drive_link VARCHAR(1000)",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS ambiente INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS retroativa BOOLEAN NOT NULL DEFAULT false",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS processos_ids JSONB DEFAULT '[]'::jsonb",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS pago BOOLEAN NOT NULL DEFAULT false",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS data_pagamento DATE",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS origem VARCHAR(20) NOT NULL DEFAULT 'sistema'",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS cliente_compensacao_id UUID",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS contrato_compensacao_id UUID",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS valor_compensacao NUMERIC(14,2)",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS substituida_por VARCHAR(200)",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS substitui_chave VARCHAR(200)",
            "ALTER TABLE pagantes ADD COLUMN IF NOT EXISTS cidade VARCHAR(100)",
            "ALTER TABLE pagantes ADD COLUMN IF NOT EXISTS estado VARCHAR(2)",
            "ALTER TABLE reembolsos ADD COLUMN IF NOT EXISTS descricao VARCHAR(1000)",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS honorario_compensacao_id UUID",
            "ALTER TABLE notas_fiscais ADD COLUMN IF NOT EXISTS email_enviado_em TIMESTAMPTZ",
            "ALTER TABLE config_fiscal ADD COLUMN IF NOT EXISTS nbs_codigo VARCHAR(9)",
        ]:
            conn.execute(text(_col))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS relatorio_fiscal_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                competencia VARCHAR(7) NOT NULL,
                enviado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
                destinatarios JSONB DEFAULT '[]'::jsonb,
                cc VARCHAR(255),
                nf_qtd INTEGER DEFAULT 0,
                anexos INTEGER DEFAULT 0,
                gmail_message_id VARCHAR(120),
                drive_pasta_link VARCHAR(1000),
                status VARCHAR(20) DEFAULT 'enviado',
                erro TEXT
            )
        """))

        # ── Config Fiscal (singleton) ────────────────────────────────────────
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS config_fiscal (
                id INTEGER PRIMARY KEY DEFAULT 1,
                razao_social VARCHAR(200) DEFAULT 'PIMENTA JUDICE SOCIEDADE INDIVIDUAL DE ADVOCACIA',
                cnpj VARCHAR(14) DEFAULT '10901611000164',
                inscricao_municipal VARCHAR(20),
                cnae VARCHAR(20) DEFAULT '6911-7/01',
                endereco TEXT,
                municipio_ibge VARCHAR(7) DEFAULT '3205309',
                municipio_nome VARCHAR(100) DEFAULT 'Vitória',
                uf VARCHAR(2) DEFAULT 'ES',
                email_fiscal VARCHAR(255),
                telefone_fiscal VARCHAR(20),
                regime_tributario VARCHAR(30) DEFAULT 'simples',
                aliquota_iss NUMERIC(5,2) DEFAULT 2.00,
                regime_especial VARCHAR(2) DEFAULT '0',
                anexo_simples VARCHAR(5) DEFAULT 'IV',
                rbt12 NUMERIC(14,2),
                aliquota_efetiva_simples NUMERIC(5,2) DEFAULT 6.00,
                ret_ir_pct NUMERIC(5,2) DEFAULT 0,
                ret_inss_pct NUMERIC(5,2) DEFAULT 0,
                ret_csll_pct NUMERIC(5,2) DEFAULT 0,
                ret_pis_pct NUMERIC(5,2) DEFAULT 0,
                ret_cofins_pct NUMERIC(5,2) DEFAULT 0,
                iss_retido_padrao BOOLEAN DEFAULT false,
                ibs_pct NUMERIC(5,2) DEFAULT 0,
                cbs_pct NUMERIC(5,2) DEFAULT 0,
                piloto_ibscbs BOOLEAN DEFAULT false,
                emails_contador JSONB DEFAULT '[]'::jsonb,
                email_master VARCHAR(255) DEFAULT 'pj@pimentajudice.com.br',
                dia_envio_relatorio INTEGER DEFAULT 1,
                enviar_relatorio_auto BOOLEAN DEFAULT true,
                serie_padrao VARCHAR(10) DEFAULT '1',
                codigos_favoritos JSONB DEFAULT '[]'::jsonb,
                templates_descricao JSONB DEFAULT '[]'::jsonb,
                rodape_danfse TEXT,
                danfse_prefixo_numero VARCHAR(20) DEFAULT '',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text(
            "ALTER TABLE config_fiscal ADD COLUMN IF NOT EXISTS danfse_prefixo_numero VARCHAR(20) DEFAULT ''"
        ))
        conn.execute(text(
            "ALTER TABLE config_fiscal ADD COLUMN IF NOT EXISTS dfe_ultimo_nsu INTEGER DEFAULT 0"
        ))
        conn.execute(text(
            "ALTER TABLE config_fiscal ADD COLUMN IF NOT EXISTS carga_media_pct NUMERIC(5,2) DEFAULT 16.33"
        ))
        conn.execute(text(
            "ALTER TABLE config_fiscal ADD COLUMN IF NOT EXISTS link_publico_token VARCHAR(64)"
        ))

        # Tarefas: campos de período e email do responsável
        conn.execute(text(
            "ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS data_inicio DATE"
        ))
        conn.execute(text(
            "ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS data_fim DATE"
        ))
        conn.execute(text(
            "ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS responsavel_email VARCHAR(255)"
        ))

        # Bot de Tarefas — lotes e sessões
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_task_batches (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                chat_id VARCHAR(100) NOT NULL,
                source_message_id VARCHAR(100),
                raw_text TEXT NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'ativo',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_telegram_task_batches_chat ON telegram_task_batches(chat_id)"
        ))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_task_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                batch_id UUID NOT NULL REFERENCES telegram_task_batches(id) ON DELETE CASCADE,
                tarefa_id UUID NOT NULL REFERENCES tarefas(id) ON DELETE CASCADE,
                titulo_original VARCHAR(500) NOT NULL,
                titulo_normalizado VARCHAR(500) NOT NULL,
                cliente_inferido_id UUID REFERENCES clientes(id) ON DELETE SET NULL,
                cliente_inferido_nome VARCHAR(255),
                cliente_inferencia_score FLOAT,
                duplicada_de_tarefa_id UUID REFERENCES tarefas(id) ON DELETE SET NULL,
                duplicada_score FLOAT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_telegram_task_items_batch ON telegram_task_items(batch_id)"
        ))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS telegram_task_sessions (
                chat_id VARCHAR(100) PRIMARY KEY,
                current_batch_id UUID REFERENCES telegram_task_batches(id) ON DELETE SET NULL,
                pending_action VARCHAR(100),
                payload JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))

        # ── Backoffice Fiscal ─────────────────────────────────────────────
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fiscal_mes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                mes VARCHAR(7) NOT NULL UNIQUE,
                ibs_full_pct NUMERIC(6,3),
                cbs_full_pct NUMERIC(6,3),
                reducao_setorial_pct NUMERIC(5,2),
                credito_modo VARCHAR(10) NOT NULL DEFAULT 'integral',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fiscal_folha (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                mes VARCHAR(7) NOT NULL UNIQUE REFERENCES fiscal_mes(mes) ON DELETE CASCADE,
                salarios NUMERIC(14,2) NOT NULL DEFAULT 0,
                prolabore NUMERIC(14,2) NOT NULL DEFAULT 0,
                inss_patronal NUMERIC(14,2) NOT NULL DEFAULT 0,
                rat NUMERIC(14,2) NOT NULL DEFAULT 0,
                fgts NUMERIC(14,2) NOT NULL DEFAULT 0,
                beneficios NUMERIC(14,2) NOT NULL DEFAULT 0,
                outros NUMERIC(14,2) NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS regra_credito (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                categoria VARCHAR(100) NOT NULL UNIQUE,
                descricao TEXT,
                base_legal VARCHAR(200) NOT NULL DEFAULT 'LC 214/2025',
                fundamento_complementar TEXT,
                status VARCHAR(20) NOT NULL DEFAULT 'pendente',
                elegivel BOOLEAN NOT NULL DEFAULT false,
                last_check VARCHAR(7),
                next_check VARCHAR(7),
                notas TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fiscal_despesa (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                mes VARCHAR(7) NOT NULL REFERENCES fiscal_mes(mes) ON DELETE CASCADE,
                categoria VARCHAR(100) NOT NULL,
                fornecedor VARCHAR(200) NOT NULL,
                descricao TEXT,
                valor NUMERIC(14,2) NOT NULL,
                tem_nota BOOLEAN NOT NULL DEFAULT true,
                elegivel BOOLEAN NOT NULL DEFAULT false,
                base_legal VARCHAR(200),
                status VARCHAR(20) NOT NULL DEFAULT 'novo',
                last_check VARCHAR(7),
                regra_id UUID REFERENCES regra_credito(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fiscal_receita (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                mes VARCHAR(7) NOT NULL REFERENCES fiscal_mes(mes) ON DELETE CASCADE,
                nota_fiscal_id UUID UNIQUE REFERENCES notas_fiscais(id),
                cliente_nome VARCHAR(200) NOT NULL,
                tipo_cliente VARCHAR(20) NOT NULL DEFAULT 'pj_regular',
                valor NUMERIC(14,2) NOT NULL,
                retencoes NUMERIC(14,2) NOT NULL DEFAULT 0,
                credito_interesse BOOLEAN NOT NULL DEFAULT false,
                modo_tributacao VARCHAR(10) NOT NULL DEFAULT 'embutido',
                is_manual BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))

        conn.execute(text(
            "ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS acessos_backoffice JSONB"
        ))
        conn.execute(text("ALTER TABLE fiscal_despesa ADD COLUMN IF NOT EXISTS data DATE"))
        conn.execute(text("ALTER TABLE fiscal_despesa ADD COLUMN IF NOT EXISTS criado_por_id UUID"))
        conn.execute(text("ALTER TABLE fiscal_despesa ADD COLUMN IF NOT EXISTS drive_link VARCHAR(1000)"))
        conn.execute(text("ALTER TABLE fiscal_despesa ADD COLUMN IF NOT EXISTS reembolso_ids JSONB"))
        conn.execute(text("ALTER TABLE config_fiscal ADD COLUMN IF NOT EXISTS estagio_reforma VARCHAR(20) NOT NULL DEFAULT 'pre_reforma'"))
        conn.execute(text("ALTER TABLE reembolsos ADD COLUMN IF NOT EXISTS tratar_como_perda BOOLEAN NOT NULL DEFAULT false"))
        conn.execute(text("ALTER TABLE fiscal_despesa ADD COLUMN IF NOT EXISTS perda_valor NUMERIC(14,2)"))
        conn.execute(text("ALTER TABLE nf_sugestoes ADD COLUMN IF NOT EXISTS reembolso_ids JSONB"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS adiantamento_alocacao (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                despesa_id UUID NOT NULL REFERENCES fiscal_despesa(id) ON DELETE CASCADE,
                reembolso_id UUID NOT NULL,
                item_reembolso_id UUID,
                valor NUMERIC(14,2) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS nf_sugestoes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                data DATE,
                competencia VARCHAR(7),
                pagador VARCHAR(200) NOT NULL,
                valor NUMERIC(14,2) NOT NULL,
                descricao TEXT,
                tipo_sugerido VARCHAR(30) NOT NULL DEFAULT 'receita',
                status VARCHAR(20) NOT NULL DEFAULT 'pendente',
                nota_fiscal_id UUID,
                cliente_id UUID,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fiscal_fornecedor (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                nome VARCHAR(200) NOT NULL UNIQUE,
                cnpj VARCHAR(18),
                categoria_padrao VARCHAR(100),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS despesa_recorrente (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                categoria VARCHAR(100) NOT NULL,
                fornecedor VARCHAR(200) NOT NULL,
                descricao TEXT,
                valor_padrao NUMERIC(14,2) NOT NULL DEFAULT 0,
                tem_nota BOOLEAN NOT NULL DEFAULT true,
                elegivel BOOLEAN NOT NULL DEFAULT false,
                ativa BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS precedentcheck_analises (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                cliente_id UUID REFERENCES clientes(id) ON DELETE SET NULL,
                processo_id UUID,
                titulo VARCHAR(500),
                texto_peca TEXT NOT NULL,
                citacoes JSONB NOT NULL DEFAULT '[]'::jsonb,
                total_citacoes INTEGER NOT NULL DEFAULT 0,
                total_ok INTEGER NOT NULL DEFAULT 0,
                total_divergencia INTEGER NOT NULL DEFAULT 0,
                total_nao_encontrado INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_precedentcheck_created ON precedentcheck_analises(created_at DESC)"
        ))
        conn.execute(text(
            "ALTER TABLE precedentcheck_analises ADD COLUMN IF NOT EXISTS arquivado BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        conn.execute(text(
            "ALTER TABLE precedentcheck_analises ADD COLUMN IF NOT EXISTS custo_usd DOUBLE PRECISION NOT NULL DEFAULT 0"
        ))

        # Instagram — sugestões de post do Agente master (@dr.lucasjudice)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS instagram_sugestoes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                titulo VARCHAR(255) NOT NULL,
                tema VARCHAR(255) NOT NULL DEFAULT '',
                formato VARCHAR(20) NOT NULL DEFAULT 'carrossel',
                tema_capa VARCHAR(1) NOT NULL DEFAULT 'A',
                slides JSONB NOT NULL DEFAULT '[]'::jsonb,
                legenda TEXT NOT NULL DEFAULT '',
                hashtags TEXT NOT NULL DEFAULT '',
                fonte_tipo VARCHAR(20) NOT NULL DEFAULT 'evergreen',
                fonte_ref VARCHAR(500),
                motivo_ia TEXT NOT NULL DEFAULT '',
                status VARCHAR(20) NOT NULL DEFAULT 'sugerido',
                data_sugerida DATE,
                enviado_assessoria_em TIMESTAMPTZ,
                data_geracao TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_instagram_sugestoes_status ON instagram_sugestoes(status, data_geracao DESC)"
        ))
        conn.execute(text("ALTER TABLE instagram_sugestoes ADD COLUMN IF NOT EXISTS aprovado_em TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE instagram_sugestoes ADD COLUMN IF NOT EXISTS drive_link TEXT"))
        conn.execute(text("ALTER TABLE instagram_sugestoes ADD COLUMN IF NOT EXISTS custo_usd DOUBLE PRECISION NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE instagram_sugestoes ADD COLUMN IF NOT EXISTS ajustes JSONB NOT NULL DEFAULT '[]'::jsonb"))
        conn.execute(text("ALTER TABLE instagram_sugestoes ADD COLUMN IF NOT EXISTS ajustes_count INTEGER NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE instagram_sugestoes ADD COLUMN IF NOT EXISTS brinde_palavra_chave VARCHAR(60)"))
        conn.execute(text("ALTER TABLE instagram_sugestoes ADD COLUMN IF NOT EXISTS brinde_titulo VARCHAR(255)"))
        conn.execute(text("ALTER TABLE instagram_sugestoes ADD COLUMN IF NOT EXISTS brinde_formato VARCHAR(20)"))
        conn.execute(text("ALTER TABLE instagram_sugestoes ADD COLUMN IF NOT EXISTS brinde_html TEXT"))
        conn.execute(text("ALTER TABLE instagram_sugestoes ADD COLUMN IF NOT EXISTS brinde_drive_link TEXT"))
        conn.execute(text("ALTER TABLE instagram_sugestoes ADD COLUMN IF NOT EXISTS video_drive_link TEXT"))
        conn.execute(text("ALTER TABLE instagram_sugestoes ADD COLUMN IF NOT EXISTS brinde_conteudo JSONB"))
        conn.execute(text("ALTER TABLE instagram_sugestoes ADD COLUMN IF NOT EXISTS brinde_site_conteudo JSONB"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS instagram_config (
                id INTEGER PRIMARY KEY DEFAULT 1,
                assessoria_emails TEXT NOT NULL DEFAULT 'moni@pimentajudice.com.br',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text(
            "INSERT INTO instagram_config (id, assessoria_emails) VALUES (1, 'moni@pimentajudice.com.br') ON CONFLICT (id) DO NOTHING"
        ))

        # Conselho/Expansão: dias_lembrete adicionado a conselho_eventos depois da tabela já existir em produção
        # (Base.metadata.create_all só cria tabelas novas, não adiciona colunas a tabelas existentes)
        conn.execute(text(
            "ALTER TABLE conselho_eventos ADD COLUMN IF NOT EXISTS dias_lembrete INTEGER NOT NULL DEFAULT 2"
        ))
        conn.execute(text(
            "ALTER TABLE conselho_contatos ADD COLUMN IF NOT EXISTS empresa VARCHAR(300)"
        ))
        conn.execute(text(
            "ALTER TABLE conselho_evento_convidados ADD COLUMN IF NOT EXISTS recusou BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        conn.execute(text(
            "ALTER TABLE conselho_evento_convidados ADD COLUMN IF NOT EXISTS pendente BOOLEAN NOT NULL DEFAULT FALSE"
        ))
        conn.execute(text(
            "ALTER TABLE conselho_evento_convidados ADD COLUMN IF NOT EXISTS pendente_obs TEXT"
        ))
        conn.execute(text(
            "ALTER TABLE conselho_evento_convidados ADD COLUMN IF NOT EXISTS followup_data DATE"
        ))

        # TelegramTaskItem: vínculo com TarefaCard
        conn.execute(text(
            "ALTER TABLE telegram_task_items ADD COLUMN IF NOT EXISTS card_id UUID REFERENCES tarefa_cards(id) ON DELETE SET NULL"
        ))

        # TarefaCardSubtask: responsável, email e prazo
        for _col in [
            "ALTER TABLE tarefa_card_subtasks ADD COLUMN IF NOT EXISTS responsavel VARCHAR(255)",
            "ALTER TABLE tarefa_card_subtasks ADD COLUMN IF NOT EXISTS responsavel_email VARCHAR(255)",
            "ALTER TABLE tarefa_card_subtasks ADD COLUMN IF NOT EXISTS data_limite DATE",
        ]:
            conn.execute(text(_col))

        # Tarefas: campo de ordenação manual
        conn.execute(text(
            "ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS ordem INTEGER"
        ))

        # Projetos de tarefas
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tarefa_projetos (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                nome VARCHAR(200) NOT NULL,
                cor VARCHAR(7) NOT NULL DEFAULT '#6366f1',
                oculto BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text(
            "ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS projeto_id UUID REFERENCES tarefa_projetos(id) ON DELETE SET NULL"
        ))
        # Inicializa ordem = row_number por created_at para tarefas existentes sem valor
        conn.execute(text("""
            UPDATE tarefas SET ordem = sub.rn
            FROM (
                SELECT id, ROW_NUMBER() OVER (ORDER BY created_at ASC) AS rn
                FROM tarefas WHERE ordem IS NULL
            ) sub
            WHERE tarefas.id = sub.id
        """))

        # Tarefas Cards (teste): card macro + subtarefas, tabelas próprias
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tarefa_cards (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                projeto_id UUID REFERENCES tarefa_projetos(id) ON DELETE SET NULL,
                cliente_id UUID REFERENCES clientes(id) ON DELETE SET NULL,
                processo_id UUID REFERENCES processos(id) ON DELETE SET NULL,
                criado_por_id UUID REFERENCES usuarios(id) ON DELETE SET NULL,
                titulo VARCHAR(500) NOT NULL,
                descricao TEXT,
                notas TEXT,
                responsavel VARCHAR(255),
                responsavel_email VARCHAR(255),
                status VARCHAR(50) NOT NULL DEFAULT 'pendente',
                data_limite DATE,
                google_event_id VARCHAR(500),
                ordem INTEGER,
                confidencial BOOLEAN NOT NULL DEFAULT false,
                usuarios_com_acesso JSONB DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tarefa_card_subtasks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                card_id UUID NOT NULL REFERENCES tarefa_cards(id) ON DELETE CASCADE,
                texto VARCHAR(500) NOT NULL,
                concluida BOOLEAN NOT NULL DEFAULT false,
                ordem INTEGER NOT NULL DEFAULT 0
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_tarefa_card_subtasks_card ON tarefa_card_subtasks(card_id)"
        ))
        # Arquivamento de tarefas (menu original e cards)
        conn.execute(text("ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS arquivada BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS arquivada_em TIMESTAMPTZ"))
        conn.execute(text("ALTER TABLE tarefa_cards ADD COLUMN IF NOT EXISTS arquivada BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE tarefa_cards ADD COLUMN IF NOT EXISTS arquivada_em TIMESTAMPTZ"))
        # Código único por entidade + anexos no Drive
        conn.execute(text("ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS codigo VARCHAR(12)"))
        conn.execute(text("ALTER TABLE tarefa_cards ADD COLUMN IF NOT EXISTS codigo VARCHAR(12)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tarefa_anexos (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tarefa_id UUID NOT NULL REFERENCES tarefas(id) ON DELETE CASCADE,
                nome_arquivo VARCHAR(500) NOT NULL,
                drive_link VARCHAR(1000),
                drive_file_id VARCHAR(200),
                content_type VARCHAR(150),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tarefa_anexos_tarefa ON tarefa_anexos(tarefa_id)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tarefa_card_anexos (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                card_id UUID NOT NULL REFERENCES tarefa_cards(id) ON DELETE CASCADE,
                subtask_id UUID REFERENCES tarefa_card_subtasks(id) ON DELETE CASCADE,
                nome_arquivo VARCHAR(500) NOT NULL,
                drive_link VARCHAR(1000),
                drive_file_id VARCHAR(200),
                content_type VARCHAR(150),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tarefa_card_anexos_card ON tarefa_card_anexos(card_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tarefa_card_anexos_subtask ON tarefa_card_anexos(subtask_id)"))
        conn.execute(text("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS codigo VARCHAR(12)"))
        # Registro de pastas do Drive (trava anti-duplicação cross-process/restart)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS drive_pasta_registry (
                parent_id VARCHAR(200) NOT NULL,
                name VARCHAR(500) NOT NULL,
                folder_id VARCHAR(200) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (parent_id, name)
            )
        """))
        # Links do Drive para o contrato finalizado (pasta do cliente + pasta mestra /Contratos)
        conn.execute(text(
            "ALTER TABLE contratos ADD COLUMN IF NOT EXISTS drive_link_cliente VARCHAR(1000)"
        ))
        conn.execute(text(
            "ALTER TABLE contratos ADD COLUMN IF NOT EXISTS drive_link_master VARCHAR(1000)"
        ))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS memorias_estrategicas (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                cliente_id UUID REFERENCES clientes(id) ON DELETE CASCADE,
                processo_id UUID REFERENCES processos(id) ON DELETE CASCADE,
                texto TEXT NOT NULL,
                autor_id UUID REFERENCES usuarios(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_memorias_estrategicas_cliente ON memorias_estrategicas(cliente_id, created_at DESC)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_memorias_estrategicas_processo ON memorias_estrategicas(processo_id, created_at DESC)"
        ))

        conn.execute(text(
            "ALTER TABLE emails_cliente ADD COLUMN IF NOT EXISTS categoria VARCHAR(20)"
        ))

        conn.execute(text(
            "ALTER TABLE andamentos_processo ADD COLUMN IF NOT EXISTS texto_extraido TEXT"
        ))

        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS vinculo_confirmado BOOLEAN NOT NULL DEFAULT false"
        ))
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS sugestao_acao TEXT"
        ))

        conn.execute(text(
            "ALTER TABLE prazos ADD COLUMN IF NOT EXISTS criado_automaticamente BOOLEAN NOT NULL DEFAULT false"
        ))
        conn.execute(text(
            "ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS criado_automaticamente BOOLEAN NOT NULL DEFAULT false"
        ))

        # Deletar um prazo não pode falhar por causa da publicação que o gerou.
        conn.execute(text(
            "ALTER TABLE publicacoes DROP CONSTRAINT IF EXISTS publicacoes_prazo_id_fkey"
        ))
        conn.execute(text(
            "ALTER TABLE publicacoes ADD CONSTRAINT publicacoes_prazo_id_fkey "
            "FOREIGN KEY (prazo_id) REFERENCES prazos(id) ON DELETE SET NULL"
        ))

        conn.execute(text(
            "ALTER TYPE status_prazo ADD VALUE IF NOT EXISTS 'ignorado'"
        ))

        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS peca_gerada TEXT"
        ))
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS peca_doc_url TEXT"
        ))
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS tarefas_criadas TEXT"
        ))

        conn.execute(text(
            "ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS prazo_id UUID REFERENCES prazos(id) ON DELETE SET NULL"
        ))

        # despacho_tratada é separado do `lida` do menu Diário Oficial (ver
        # comentário no model). Backfill só roda na primeira vez que a coluna
        # é criada — depois disso cada fluxo cuida do próprio campo.
        conn.execute(text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='publicacoes' AND column_name='despacho_tratada'
                ) THEN
                    ALTER TABLE publicacoes ADD COLUMN despacho_tratada BOOLEAN NOT NULL DEFAULT false;
                    UPDATE publicacoes SET despacho_tratada = true WHERE lida = true OR rejeitada = true;
                END IF;
            END $$;
            """
        ))

        conn.execute(text(
            "ALTER TABLE tarefas ADD COLUMN IF NOT EXISTS responsavel_id UUID REFERENCES responsaveis(id) ON DELETE SET NULL"
        ))
        conn.execute(text(
            "ALTER TABLE prazos ADD COLUMN IF NOT EXISTS responsavel_id UUID REFERENCES responsaveis(id) ON DELETE SET NULL"
        ))
        conn.execute(text(
            "ALTER TABLE tarefa_cards ADD COLUMN IF NOT EXISTS responsavel_id UUID REFERENCES responsaveis(id) ON DELETE SET NULL"
        ))
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS disposicao VARCHAR(20)"
        ))
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS tarefa_card_id UUID REFERENCES tarefa_cards(id) ON DELETE SET NULL"
        ))
        # Cliente: cadastro enriquecido (autocadastro via link público — Fase 1)
        for col_sql in [
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS whatsapp VARCHAR(30)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS cep VARCHAR(9)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS logradouro VARCHAR(255)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS numero VARCHAR(20)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS complemento VARCHAR(120)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS bairro VARCHAR(120)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS cidade VARCHAR(120)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS uf VARCHAR(2)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS data_nascimento DATE",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS rg VARCHAR(30)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS estado_civil VARCHAR(40)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS profissao VARCHAR(150)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS empresas_vinculadas TEXT",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS nome_fantasia VARCHAR(255)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS responsavel_nome VARCHAR(255)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS responsavel_cpf VARCHAR(18)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS responsavel_email VARCHAR(255)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS responsavel_telefone VARCHAR(30)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS origem_cadastro VARCHAR(30) DEFAULT 'manual'",
        ]:
            conn.execute(text(col_sql))
        # estado_civil pode vir com regime de bens (ex.: "casado em regime de
        # comunhão parcial de bens") — alarga de 40 para 120. Idempotente.
        conn.execute(text("ALTER TABLE clientes ALTER COLUMN estado_civil TYPE VARCHAR(120)"))

        # Patrimônio: inventário de bens do cliente (diagnóstico de holding)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS patrimonio_bens (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                cliente_id UUID NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
                tipo_bem VARCHAR(20) NOT NULL DEFAULT 'imovel',
                nome VARCHAR(255) NOT NULL,
                descricao TEXT,
                valor_compra NUMERIC(15,2),
                valor_mercado NUMERIC(15,2),
                valor_ir NUMERIC(15,2),
                data_compra DATE,
                objetivo VARCHAR(20),
                descricao_matricula TEXT,
                numero_matricula VARCHAR(100),
                cartorio VARCHAR(255),
                status VARCHAR(20) NOT NULL DEFAULT 'em_validacao',
                integralizar_holding BOOLEAN NOT NULL DEFAULT false,
                proprietario_real VARCHAR(255),
                proprietario_matricula VARCHAR(255),
                tem_gravame BOOLEAN NOT NULL DEFAULT false,
                gravame_descricao TEXT,
                observacoes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_patrimonio_bens_cliente ON patrimonio_bens(cliente_id)"
        ))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS patrimonio_anexos (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                bem_id UUID NOT NULL REFERENCES patrimonio_bens(id) ON DELETE CASCADE,
                filename VARCHAR(500) NOT NULL,
                drive_link VARCHAR(1000),
                mime VARCHAR(100),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS patrimonio_cadeia_elos (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                bem_id UUID NOT NULL REFERENCES patrimonio_bens(id) ON DELETE CASCADE,
                ordem INTEGER NOT NULL DEFAULT 0,
                tipo_documento VARCHAR(50) NOT NULL DEFAULT 'outro',
                de_quem VARCHAR(255),
                para_quem VARCHAR(255),
                data DATE,
                descricao TEXT,
                arquivo_nome VARCHAR(500),
                drive_link VARCHAR(1000),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        # Patrimônio: bem móvel do tipo cota social (empresa + quadro de sócios)
        for _col in [
            "ALTER TABLE patrimonio_bens ADD COLUMN IF NOT EXISTS empresa_nome VARCHAR(255)",
            "ALTER TABLE patrimonio_bens ADD COLUMN IF NOT EXISTS empresa_cnpj VARCHAR(18)",
            "ALTER TABLE patrimonio_bens ADD COLUMN IF NOT EXISTS capital_social NUMERIC(15,2)",
            "ALTER TABLE patrimonio_bens ADD COLUMN IF NOT EXISTS valor_balanco NUMERIC(15,2)",
            "ALTER TABLE patrimonio_bens ADD COLUMN IF NOT EXISTS data_balanco DATE",
        ]:
            conn.execute(text(_col))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS patrimonio_socios (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                bem_id UUID NOT NULL REFERENCES patrimonio_bens(id) ON DELETE CASCADE,
                ordem INTEGER NOT NULL DEFAULT 0,
                nome VARCHAR(255) NOT NULL,
                cpf VARCHAR(18),
                percentual NUMERIC(6,3),
                integralizar BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        # Patrimônio: origem/título, referência de escritura pública, % do cliente na cota
        for _col in [
            "ALTER TABLE patrimonio_bens ADD COLUMN IF NOT EXISTS origem_titulo VARCHAR(30)",
            "ALTER TABLE patrimonio_bens ADD COLUMN IF NOT EXISTS escritura_numero VARCHAR(50)",
            "ALTER TABLE patrimonio_bens ADD COLUMN IF NOT EXISTS escritura_livro VARCHAR(50)",
            "ALTER TABLE patrimonio_bens ADD COLUMN IF NOT EXISTS escritura_folha VARCHAR(50)",
            "ALTER TABLE patrimonio_bens ADD COLUMN IF NOT EXISTS participacao_cliente_pct NUMERIC(6,3)",
            "ALTER TABLE patrimonio_bens ADD COLUMN IF NOT EXISTS ordem INTEGER",
        ]:
            conn.execute(text(_col))
        # Objetivo: renomeia 'segurar' -> 'uso_proprio'
        conn.execute(text("UPDATE patrimonio_bens SET objetivo='uso_proprio' WHERE objetivo='segurar'"))
        # Comentários por bem (autor + data/hora)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS patrimonio_comentarios (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                bem_id UUID NOT NULL REFERENCES patrimonio_bens(id) ON DELETE CASCADE,
                titulo VARCHAR(255),
                texto TEXT NOT NULL,
                autor_id UUID,
                autor_nome VARCHAR(255),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        # Ordena bens existentes sem 'ordem' (por cliente, mais recente primeiro = mesma ordem da UI)
        conn.execute(text("""
            UPDATE patrimonio_bens SET ordem = sub.rn FROM (
                SELECT id, ROW_NUMBER() OVER (PARTITION BY cliente_id ORDER BY created_at DESC) AS rn
                FROM patrimonio_bens WHERE ordem IS NULL
            ) sub WHERE patrimonio_bens.id = sub.id
        """))

        # Prazos: tratamento "Nada a fazer" + controle do lembrete diário
        conn.execute(text(
            "ALTER TYPE status_prazo ADD VALUE IF NOT EXISTS 'nada_a_fazer'"
        ))
        conn.execute(text(
            "ALTER TABLE prazos ADD COLUMN IF NOT EXISTS ultimo_lembrete_em TIMESTAMPTZ"
        ))

        # Data de disponibilização no diário — guardada à parte da publicação
        # (art. 224, §2º CPC). Só para conferência; não entra no cálculo.
        conn.execute(text(
            "ALTER TABLE publicacoes ADD COLUMN IF NOT EXISTS data_disponibilizacao DATE"
        ))
        # Backfill do histórico do DJEN: até aqui, data_publicacao guardava a
        # DISPONIBILIZAÇÃO. Copia para a coluna certa, sem alterar
        # data_publicacao — mexer nela mudaria prazos já calculados, e a decisão
        # do Lucas foi não reescrever histórico (só os 3 pendentes, à parte).
        conn.execute(text("""
            UPDATE publicacoes SET data_disponibilizacao = data_publicacao
            WHERE data_disponibilizacao IS NULL
              AND fonte::text LIKE 'scraping%'
        """))

        # ── Financeiro: parcelamento de recebíveis + cobrança automática ──────
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS parcelas (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                honorario_id UUID NOT NULL REFERENCES honorarios(id) ON DELETE CASCADE,
                numero INTEGER NOT NULL DEFAULT 1,
                valor NUMERIC(14,2) NOT NULL,
                data_vencimento DATE NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pendente',
                data_pagamento DATE,
                observacao VARCHAR(500),
                ultimo_lembrete_em TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            )
        """))
        conn.execute(text("ALTER TABLE recebimentos ADD COLUMN IF NOT EXISTS parcela_id UUID"))
        conn.execute(text("ALTER TABLE honorarios ADD COLUMN IF NOT EXISTS cobranca_ativa BOOLEAN NOT NULL DEFAULT false"))
        conn.execute(text("ALTER TABLE honorarios ADD COLUMN IF NOT EXISTS cobranca_email VARCHAR(255)"))
        conn.execute(text("ALTER TABLE parcelas ADD COLUMN IF NOT EXISTS cobranca_estagio INTEGER NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE honorarios ADD COLUMN IF NOT EXISTS cobranca_estagio INTEGER NOT NULL DEFAULT 0"))
        conn.execute(text("ALTER TABLE honorarios ADD COLUMN IF NOT EXISTS cobranca_emails JSONB DEFAULT '[]'::jsonb"))
        conn.execute(text("ALTER TABLE recebimentos ADD COLUMN IF NOT EXISTS comprovante_filename VARCHAR(500)"))
        conn.execute(text("ALTER TABLE recebimentos ADD COLUMN IF NOT EXISTS comprovante_path VARCHAR(1000)"))
        conn.execute(text("ALTER TABLE recebimentos ADD COLUMN IF NOT EXISTS comprovante_drive_link VARCHAR(1000)"))
        conn.execute(text("ALTER TABLE informativos ADD COLUMN IF NOT EXISTS numero INTEGER"))

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


def _seed_conselho_data() -> None:
    """Popula diretrizes/pipeline/parceiros de exemplo (idempotente — só roda se vazio)."""
    from datetime import date as _date

    from app.database import SessionLocal
    from app.models.conselho import (
        ConselhoDiretriz,
        ConselhoDiretrizSubtask,
        ConselhoParceiro,
        ConselhoPipeline,
    )

    db = SessionLocal()
    try:
        if db.query(ConselhoDiretriz).count() > 0:
            return

        diretrizes = [
            dict(
                categoria="operacional",
                titulo="Reativar pipeline de oportunidades",
                descricao="Criar e preencher a planilha de pipeline retroativamente (últimos 30 dias) e a partir de 30/06 registrar todo lead novo no mesmo dia. Revisão obrigatória toda sexta-feira.",
                prazo=_date(2026, 7, 10),
                status="Em andamento",
                subtasks=[
                    ("Criar estrutura da planilha de pipeline", True),
                    ("Registrar retroativamente oportunidades dos últimos 30 dias", False),
                    ("Definir rotina fixa de revisão de sexta-feira", False),
                ],
            ),
            dict(
                categoria="comercial",
                titulo="Estruturar os 3 cafés como funil profissional",
                descricao="Holding+ITCMD, Reforma Tributária (holding imobiliária) e Conflitos Societários. Pré-evento, durante (conteúdo técnico, zero pitch) e pós-evento (follow-up 48h).",
                prazo=_date(2026, 7, 31),
                status="Não iniciado",
                subtasks=[
                    ("Definir co-host para o café de Conflitos Societários", False),
                    ("Montar lista de convidados (15-18 por evento)", False),
                    ("Preparar e-mail de follow-up pós-evento (48h)", False),
                ],
            ),
            dict(
                categoria="parcerias",
                titulo="Reativar as 4 parcerias frias",
                descricao="Ligação (não mensagem) reconhecendo o desequilíbrio e oferecendo contrapartida concreta: co-host em café, palestra exclusiva para a base do parceiro, ou estrutura de indicação.",
                prazo=_date(2026, 7, 15),
                status="Não iniciado",
                subtasks=[
                    ("Ligar para os 4 parceiros esfriados", False),
                    ("Definir plano de retribuição individual por parceiro", False),
                ],
            ),
            dict(
                categoria="operacional",
                titulo="Métrica diária + rotina de decisão",
                descricao="Escolher uma métrica diária única (follow-ups, reuniões qualificadas ou horas em atividade comercial) e registrar por 60 dias contínuos.",
                prazo=_date(2026, 6, 30),
                status="Em andamento",
                subtasks=[
                    ("Escolher a métrica diária única", True),
                    ("Registrar diariamente por 60 dias", False),
                ],
            ),
            dict(
                categoria="juridico",
                titulo="Blindagem ética dos cafés e parcerias",
                descricao="Convite institucional sempre via parceiro/co-host (nunca lista própria de empresas desconhecidas) — Art. 39 do Código de Ética. Com não-advogados: vedada comissão; retribuição apenas não-monetária.",
                prazo=_date(2026, 7, 31),
                status="Não iniciado",
                subtasks=[
                    ("Confirmar que todo convite institucional sai do parceiro/co-host", False),
                    ("Revisar roteiro de divulgação dos cafés sob ótica do Provimento 205/2021", False),
                ],
            ),
        ]

        for d in diretrizes:
            subtasks = d.pop("subtasks")
            diretriz = ConselhoDiretriz(**d)
            db.add(diretriz)
            db.flush()
            for i, (texto, concluida) in enumerate(subtasks):
                db.add(ConselhoDiretrizSubtask(diretriz_id=diretriz.id, texto=texto, concluida=concluida, ordem=i))

        db.add(ConselhoPipeline(
            nome="Empresa X",
            origem="Palestra",
            tema="Holding",
            estagio="Proposta enviada",
            ultimo_contato=_date(2026, 6, 20),
            proxima_acao="Follow-up",
            proxima_data=_date(2026, 6, 28),
            ticket=100000,
            probabilidade=60,
        ))

        parceiros = [
            ("Parceiro quente atual", "Advogado", "Quente", "Manter cadência mensal", None),
            ("Parceiro esfriado 1", "Assessor de investimentos", "Frio", "Convidar como co-host do café societário + palestra para a base", _date(2026, 7, 15)),
            ("Parceiro esfriado 2", "Advogado", "Frio", "Propor contrato de colaboração profissional (art. 50 CED)", _date(2026, 7, 15)),
            ("Parceiro esfriado 3", "Assessor de investimentos", "Frio", "Oferecer consultoria preventiva gratuita para estrutura própria", _date(2026, 7, 15)),
            ("Parceiro esfriado 4", "Advogado", "Frio", "A definir no contato", _date(2026, 7, 15)),
        ]
        for nome, tipo, status_p, plano, proximo in parceiros:
            db.add(ConselhoParceiro(nome=nome, tipo=tipo, status=status_p, plano=plano, proximo_contato=proximo))

        db.commit()
    finally:
        db.close()


def _backfill_responsaveis() -> None:
    """Cria a tabela de Responsáveis a partir do que já existe: um por
    Usuário (sincronizado por usuario_id) e um "manual" pra cada nome livre
    já usado em tarefas/prazos/cards que não bate com um usuário. Só roda
    a parte de nomes livres se a tabela estiver vazia — depois disso quem
    cria responsável novo é o combobox ou o cadastro de usuário."""
    from app.database import SessionLocal
    from app.models.prazo import Prazo
    from app.models.responsavel import Responsavel
    from app.models.tarefa import Tarefa
    from app.models.tarefa_card import TarefaCard
    from app.models.usuario import Usuario

    db = SessionLocal()
    try:
        vazio = db.query(Responsavel).count() == 0

        # Sincroniza um Responsavel por Usuario (idempotente sempre).
        for u in db.query(Usuario).all():
            resp = db.query(Responsavel).filter(Responsavel.usuario_id == u.id).first()
            if not resp:
                db.add(Responsavel(nome=u.nome, email=u.email, usuario_id=u.id, categoria="colaborador", ativo=u.ativo))
        db.commit()

        if not vazio:
            return

        nomes_usuario = {r.nome.strip().lower() for r in db.query(Responsavel).filter(Responsavel.usuario_id.isnot(None)).all()}

        candidatos: dict[str, str | None] = {}
        for nome, email in db.query(Tarefa.responsavel, Tarefa.responsavel_email).filter(Tarefa.responsavel.isnot(None)).all():
            if nome and nome.strip():
                candidatos.setdefault(nome.strip(), email)
        for (nome,) in db.query(Prazo.responsavel).filter(Prazo.responsavel.isnot(None)).all():
            if nome and nome.strip():
                candidatos.setdefault(nome.strip(), candidatos.get(nome.strip()))
        for nome, email in db.query(TarefaCard.responsavel, TarefaCard.responsavel_email).filter(TarefaCard.responsavel.isnot(None)).all():
            if nome and nome.strip():
                candidatos.setdefault(nome.strip(), email)

        for nome, email in candidatos.items():
            if nome.lower() in nomes_usuario:
                continue
            db.add(Responsavel(nome=nome, email=email, categoria="terceiro", ativo=True))
        db.commit()

        # Liga o que dá pra ligar por nome (case-insensitive) — só preenche
        # o que ainda está null, nunca sobrescreve um vínculo já feito.
        todos = {r.nome.strip().lower(): r.id for r in db.query(Responsavel).all()}
        for tarefa in db.query(Tarefa).filter(Tarefa.responsavel.isnot(None), Tarefa.responsavel_id.is_(None)).all():
            rid = todos.get(tarefa.responsavel.strip().lower())
            if rid:
                tarefa.responsavel_id = rid
        for prazo in db.query(Prazo).filter(Prazo.responsavel.isnot(None), Prazo.responsavel_id.is_(None)).all():
            rid = todos.get(prazo.responsavel.strip().lower())
            if rid:
                prazo.responsavel_id = rid
        for card in db.query(TarefaCard).filter(TarefaCard.responsavel.isnot(None), TarefaCard.responsavel_id.is_(None)).all():
            rid = todos.get(card.responsavel.strip().lower())
            if rid:
                card.responsavel_id = rid
        db.commit()
    finally:
        db.close()


_run_migrations()
_seed_super_admin()
_seed_conselho_data()
_backfill_responsaveis()

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


# Handler de validação à prova de bytes — o handler default do FastAPI tenta serializar
# o `input` dos erros, que para uploads é o body binário (PDF), e estoura UnicodeDecodeError
# virando 500. Aqui sanitizamos qualquer valor não-serializável antes de devolver 422.
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402


@app.exception_handler(RequestValidationError)
async def _validation_handler(request, exc: RequestValidationError):
    import logging as _lg
    safe_errors = []
    for err in exc.errors():
        e = dict(err)
        inp = e.get("input")
        if isinstance(inp, (bytes, bytearray)):
            e["input"] = f"<{len(inp)} bytes binários>"
        # ctx pode conter exceções não serializáveis
        if "ctx" in e and not isinstance(e["ctx"], (str, int, float, bool, type(None))):
            e["ctx"] = str(e.get("ctx"))
        safe_errors.append(e)
    _lg.getLogger("validation").warning(
        "422 em %s — content-type=%s — erros=%s",
        request.url.path, request.headers.get("content-type"), safe_errors,
    )
    # Mensagem amigável quando o campo de arquivo não chegou (multipart malformado)
    faltou_arquivo = any(
        e.get("type") == "missing" and "file" in (e.get("loc") or [])
        for e in safe_errors
    )
    detail = (
        "Arquivo não recebido pelo servidor (multipart inválido). "
        "Tente reenviar — se persistir, recarregue a página (Cmd+Shift+R)."
        if faltou_arquivo else safe_errors
    )
    return JSONResponse(status_code=422, content={"detail": detail})

app.include_router(auth.router)
app.include_router(clientes.router)
app.include_router(anotacoes.router)
app.include_router(contratos.router)
app.include_router(processos.router)
app.include_router(prazos.router)
app.include_router(feriados.router)
app.include_router(diario.router)
app.include_router(diario2.router)
app.include_router(teses.router)
app.include_router(reembolsos.router)
app.include_router(financeiro.router)
app.include_router(fiscal.router)
app.include_router(pagantes.router)
app.include_router(backoffice.router)
app.include_router(config_fiscal.router)
app.include_router(publico.router)
app.include_router(cadastro_publico.router)
app.include_router(cadastro_links.router)
app.include_router(cadastro_submissoes.router)
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
app.include_router(telegram.router)
app.include_router(telegram_andamentos.router)
app.include_router(telegram_tasks.router)
app.include_router(precedentcheck.router)
app.include_router(conselho.router)
app.include_router(tarefa_projetos.router)
app.include_router(tarefa_cards.router)
app.include_router(memoria_estrategica.router)
app.include_router(despacho.router)
app.include_router(conselho_juridico.router)
app.include_router(responsaveis.router)
app.include_router(patrimonio.router)
app.include_router(instagram.router)
app.include_router(informativos.router)


@app.on_event("startup")
async def _startup_andamentos_bot():
    """Start aiogram polling for @jusbr_andamentos_bot (login via user's browser)."""
    import asyncio
    import logging
    log = logging.getLogger(__name__)

    token = settings.andamentos_bot_token
    if not token:
        log.warning("andamentos_bot_token não configurado — bot desativado.")
        return

    from app.routers.telegram_andamentos import create_dispatcher, run_polling

    dispatcher = create_dispatcher()
    asyncio.create_task(run_polling(token, dispatcher))
    log.info("@jusbr_andamentos_bot polling iniciado (login PKCE no navegador do usuário).")


@app.on_event("startup")
def _startup():
    try:
        from app.scheduler import start_scheduler
        start_scheduler()
    except ModuleNotFoundError:
        import logging
        logging.getLogger(__name__).warning("apscheduler não instalado — scheduler desativado")

    # Registra comandos do bot de Reembolsos no menu sanduíche do Telegram
    try:
        from app.services.telegram_api import set_my_commands
        set_my_commands([
            ("manual",    "Catalogar despesa só por texto (sem foto)"),
            ("resumo",    "Ver pastas em aberto e comprovantes pendentes"),
            ("pendentes", "Listar comprovantes recebidos não catalogados"),
            ("cancelar",  "Cancelar o lote em andamento"),
            ("ajuda",     "Mostrar todos os comandos disponíveis"),
        ])
    except Exception:
        pass

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
