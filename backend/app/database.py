from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# pool_pre_ping: testa a conexão antes de usar e reconecta de forma transparente.
# Sem isso, jobs do scheduler (que rodam horas depois, após o Postgres do Fly
# fechar conexões ociosas) falham com "server closed the connection unexpectedly".
# pool_recycle: descarta conexões com mais de 30 min antes que o servidor as feche.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
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
