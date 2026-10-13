import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ComentarioPrazo(Base):
    """Anotação livre do usuário sobre um prazo.

    Não é dado de tribunal (isso vive em AndamentoProcesso, sincronizado do
    DataJud/jus.br) — é contexto humano: por que um recurso foi ou não
    interposto, o que o cliente decidiu, etc. Pensado pra ser lido meses depois,
    ao revisitar o processo. Mesmo padrão de PatrimonioComentario.

    Sem relationship() de volta pra Prazo — ver o comentário em
    app/models/prazo.py sobre por que a lista é montada como atributo
    transiente no router, não via ORM relationship.
    """
    __tablename__ = "comentarios_prazo"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prazo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prazos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Qual andamento real do processo este comentário explica — ex.: "por que
    # não recorremos desta sentença". Nullable: o usuário pode marcar
    # explicitamente "Não vinculado a andamento" (quando o sistema ainda não
    # importou o andamento correspondente, ou quando não há um 1:1 claro).
    # SET NULL (não CASCADE): se o andamento sumir num re-sync, o comentário
    # não é apagado — só volta a aparecer como não vinculado.
    andamento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("andamentos_processo.id", ondelete="SET NULL"), nullable=True, index=True
    )
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    autor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    autor_nome: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
