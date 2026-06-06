from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_user: str = "gestor"
    db_password: str = "gestor123"
    db_name: str = "gestor_juridico"
    db_host: str = "db"
    db_port: int = 5432

    secret_key: str = "dev-secret"
    cors_origins: str = "http://localhost:5173"

    # IA
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_ai_api_key: str = ""  # Gemini

    # DataJud — CNJ public API for process movements
    datajud_api_key: str = ""

    # Email (Option A: Resend; Option B: Gmail SMTP; fallback: console log)
    resend_api_key: str = ""
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_from: str = ""

    # Frontend base URL (for magic links)
    frontend_url: str = "http://localhost:5174"

    # Telegram — bot de Reembolsos
    telegram_bot_token: str = ""

    # Andamentos bot (@jusbr_andamentos_bot) — separate token, long polling
    andamentos_bot_token: str = ""
    andamentos_allowed_user_ids: str = "5152275140"
    # Grupo dedicado pro push diário (cron 19h BRT). Crie o grupo, adicione o
    # bot, mande qualquer mensagem e pegue o chat_id do log.
    andamentos_push_chat_id: str = ""
    # IDs de usuários autorizados a operar o bot em DM (separados por vírgula).
    telegram_allowed_user_ids: str = ""
    # IDs de grupos cujos membros são automaticamente autorizados (separados por vírgula).
    # Qualquer pessoa adicionada ao grupo pode usar o bot — sem precisar cadastrar ID individual.
    telegram_allowed_group_ids: str = ""
    # Segredo do webhook: o Telegram envia no header X-Telegram-Bot-Api-Secret-Token.
    telegram_webhook_secret: str = ""

    # Telegram — bot de Tarefas (Tarefas_sui_bot)
    # Token separado do bot de Reembolsos.
    telegram_tarefas_bot_token: str = ""
    telegram_tarefas_webhook_secret: str = ""
    # Email ou UUID do usuário LexOps que será `criado_por` nas tarefas criadas pelo bot.
    telegram_tarefas_default_user: str = ""

    # NFS-e Nacional — e-CNPJ A1 (mTLS)
    nfse_cert_path: str = ""       # caminho local do .pfx (dev)
    nfse_cert_password: str = ""   # senha do .pfx
    nfse_cert_b64: str = ""        # conteúdo do .pfx em base64 (Fly.io)
    # SEFIN Nacional — emissão (POST /nfse), consulta, eventos
    nfse_api_url: str = "https://sefin.nfse.gov.br/SefinNacional/"
    # ADN Contribuinte — distribuição (DFe), parâmetros municipais
    nfse_adn_url: str = "https://adn.nfse.gov.br/contribuintes/"
    nfse_ambiente: int = 1         # 1=Produção, 2=Homologação

    @property
    def telegram_allowed_ids(self) -> set[int]:
        out: set[int] = set()
        for part in self.telegram_allowed_user_ids.split(","):
            part = part.strip()
            if part:
                try:
                    out.add(int(part))
                except ValueError:
                    pass
        return out

    @property
    def telegram_allowed_group_ids_set(self) -> set[int]:
        out: set[int] = set()
        for part in self.telegram_allowed_group_ids.split(","):
            part = part.strip()
            if part:
                try:
                    out.add(int(part))
                except ValueError:
                    pass
        return out

    @property
    def database_url(self) -> str:
        import os
        # Fly.io sets DATABASE_URL; normalize postgres:// → postgresql://
        raw = os.environ.get("DATABASE_URL", "")
        if raw:
            return raw.replace("postgres://", "postgresql://", 1)
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"


settings = Settings()
