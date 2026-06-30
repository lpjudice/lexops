import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ConselhoDiretriz(Base):
    __tablename__ = "conselho_diretrizes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    categoria: Mapped[str] = mapped_column(String(30), nullable=False)  # operacional | juridico | comercial | parcerias
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    prazo: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="Não iniciado")
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    subtasks: Mapped[list["ConselhoDiretrizSubtask"]] = relationship(
        "ConselhoDiretrizSubtask", back_populates="diretriz", cascade="all, delete-orphan", order_by="ConselhoDiretrizSubtask.ordem"
    )
    anexos: Mapped[list["ConselhoDiretrizAnexo"]] = relationship(
        "ConselhoDiretrizAnexo", back_populates="diretriz", cascade="all, delete-orphan"
    )


class ConselhoDiretrizSubtask(Base):
    __tablename__ = "conselho_diretriz_subtasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    diretriz_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conselho_diretrizes.id", ondelete="CASCADE"), nullable=False)
    texto: Mapped[str] = mapped_column(String(500), nullable=False)
    concluida: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    diretriz: Mapped["ConselhoDiretriz"] = relationship("ConselhoDiretriz", back_populates="subtasks")


class ConselhoDiretrizAnexo(Base):
    __tablename__ = "conselho_diretriz_anexos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    diretriz_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conselho_diretrizes.id", ondelete="CASCADE"), nullable=False)
    nome_arquivo: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    diretriz: Mapped["ConselhoDiretriz"] = relationship("ConselhoDiretriz", back_populates="anexos")


class ConselhoPipeline(Base):
    __tablename__ = "conselho_pipeline"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(300), nullable=False)
    origem: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tema: Mapped[str | None] = mapped_column(String(300), nullable=True)
    estagio: Mapped[str] = mapped_column(String(50), nullable=False, default="Prospecção")
    ultimo_contato: Mapped[date | None] = mapped_column(Date, nullable=True)
    proxima_acao: Mapped[str | None] = mapped_column(String(500), nullable=True)
    proxima_data: Mapped[date | None] = mapped_column(Date, nullable=True)
    ticket: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    probabilidade: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConselhoContato(Base):
    __tablename__ = "conselho_contatos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    primeiro_nome: Mapped[str] = mapped_column(String(150), nullable=False)
    sobrenome: Mapped[str | None] = mapped_column(String(150), nullable=True)
    empresa: Mapped[str | None] = mapped_column(String(300), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mensagem_global: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    notas: Mapped[list["ConselhoContatoNota"]] = relationship(
        "ConselhoContatoNota", back_populates="contato", cascade="all, delete-orphan"
    )


class ConselhoContatoNota(Base):
    __tablename__ = "conselho_contato_notas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contato_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conselho_contatos.id", ondelete="CASCADE"), nullable=False)
    evento_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conselho_eventos.id", ondelete="SET NULL"), nullable=True)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    contato: Mapped["ConselhoContato"] = relationship("ConselhoContato", back_populates="notas")
    evento: Mapped["ConselhoEvento"] = relationship("ConselhoEvento")


class ConselhoEvento(Base):
    __tablename__ = "conselho_eventos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(300), nullable=False)
    data: Mapped[date | None] = mapped_column(Date, nullable=True)
    cohost: Mapped[str | None] = mapped_column(String(300), nullable=True)
    custo: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    receita: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    reunioes: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    propostas: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    fechados: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    mensagem_master: Mapped[str | None] = mapped_column(Text, nullable=True)
    dias_lembrete: Mapped[int] = mapped_column(Integer, nullable=False, default=2)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    convidados: Mapped[list["ConselhoEventoConvidado"]] = relationship(
        "ConselhoEventoConvidado", back_populates="evento", cascade="all, delete-orphan",
        order_by="ConselhoEventoConvidado.created_at",
    )


class ConselhoEventoConvidado(Base):
    __tablename__ = "conselho_evento_convidados"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evento_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conselho_eventos.id", ondelete="CASCADE"), nullable=False)
    contato_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conselho_contatos.id", ondelete="CASCADE"), nullable=False)
    presenca_confirmada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    participacao_confirmada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mensagem_pessoal: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    evento: Mapped["ConselhoEvento"] = relationship("ConselhoEvento", back_populates="convidados")
    contato: Mapped["ConselhoContato"] = relationship("ConselhoContato")


class ConselhoParceiro(Base):
    __tablename__ = "conselho_parceiros"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(300), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)  # Advogado | Contador | Assessor de investimentos | Outro
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Frio")  # Quente | Frio | Reativado
    ultimo_encaminhamento: Mapped[date | None] = mapped_column(Date, nullable=True)
    plano: Mapped[str | None] = mapped_column(Text, nullable=True)
    proximo_contato: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConselhoLog(Base):
    __tablename__ = "conselho_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    data: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    numero: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    nota: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConselhoAnexo(Base):
    """Biblioteca de anexos (PDFs) do módulo, reutilizável em qualquer disparo (evento ou Disparador)."""
    __tablename__ = "conselho_anexos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome_arquivo: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
