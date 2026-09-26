from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# pool_pre_ping: testa a conexão antes de usar e reconecta de forma transparente.
# Sem isso, jobs do scheduler (que rodam horas depois, após o Postgres do Fly
# fechar conexões ociosas) falham com "server closed the connection unexpectedly".
# pool_recycle: descarta conexões com mais de 30 min antes que o servidor as feche.
#
# pool_size/max_overflow: chegou a subir pra 10+20 numa tentativa de reduzir
# esgotamento sob uma sincronização do Autos IA — mas o Postgres do Fly passou
# a recusar conexão nova ("server closed the connection unexpectedly" na
# CRIAÇÃO da conexão, não no pool interno) com essa capacidade mais alta,
# piorando o problema (sistema lento, deslogando sozinho, sincronização travada
# de vez, cancelar sem efeito). Revertido pro default do SQLAlchemy (5+10=15),
# que é o que rodou estável antes disso — o teto de conexões concorrentes do
# lado do Postgres provavelmente é menor do que 30 pra este app.
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
