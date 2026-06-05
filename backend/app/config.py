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
    # IDs de usuários autorizados a operar o bot em DM (separados por vírgula).
    telegram_allowed_user_ids: str = ""
    # IDs de grupos cujos membros são automaticamente autorizados (separados por vírgula).
    # Qualquer pessoa adicionada ao grupo pode usar o bot — sem precisar cadastrar ID individual.
    telegram_allowed_group_ids: str = ""
    # Segredo do webhook: o Telegram envia no header X-Telegram-Bot-Api-Secret-Token.
    telegram_webhook_secret: str = ""

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
