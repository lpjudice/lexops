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

    @property
    def database_url(self) -> str:
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
