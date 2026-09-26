from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# pool_pre_ping: testa a conexão antes de usar e reconecta de forma transparente.
# Sem isso, jobs do scheduler (que rodam horas depois, após o Postgres do Fly
# fechar conexões ociosas) falham com "server closed the connection unexpectedly".
# pool_recycle: descarta conexões com mais de 30 min antes que o servidor as feche.
# pool_size/max_overflow: o default (5+10=15) já foi visto esgotado em produção
# (erro de checkout do pool) com uma sincronização do Autos IA rodando ao mesmo
# tempo que o polling normal da tela (caso/documentos/peças/grafo a cada poucos
# segundos) — subir a capacidade reduz o risco de uma request comum falhar por
# não conseguir conexão enquanto um job de fundo está em andamento.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=10,
    max_overflow=20,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
