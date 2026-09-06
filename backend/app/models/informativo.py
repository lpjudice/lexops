import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Nome do responsável default (busca em `responsaveis` por nome, best-effort —
# se não achar, o informativo nasce sem responsável e o usuário define na tela).
RESPONSAVEL_PADRAO_NOME = "Jamyle"

# 'rascunho' → Doc criado, sem conteúdo revisado ainda
# 'primeiro_draft' → 1º rascunho pronto (marcado manualmente ou pelo sync do Doc)
# 'revisado' → revisado pelo Lucas, pronto para virar PDF
# 'publicado' → PDF gerado, salvo no Drive e disponível no site
STATUS_INFORMATIVO = ("rascunho", "primeiro_draft", "revisado", "publicado")


class Informativo(Base):
    """Informativo jurídico mensal (Expansão → Informativos).

    Fluxo: cria-se um Google Doc a partir de um template em branco (pasta
    /Informativos/{AAAA-MM} no Drive); o responsável escreve/edita no Doc;
    "sincronizar" traz o texto pro sistema; citações de lei/julgado passam
    por validação (PrecedentCheck) antes de liberar; ao publicar, o HTML no
    layout padrão é renderizado, convertido em PDF e salvo no Drive, e fica
    disponível na rota pública (site, seção Informativos).
    """

    __tablename__ = "informativos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Primeiro dia do mês a que o informativo se refere (ex.: informativo de
    # janeiro/2026 → 2026-01-01). Usado para calcular os prazos internos.
    mes_referencia: Mapped[date] = mapped_column(Date, nullable=False)

    titulo: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # Título resumido puxado de uma sugestão do Instagram (opcional, só referência)
    tema_resumido: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tema_sugestao_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="rascunho")

    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("responsaveis.id", ondelete="SET NULL"), nullable=True
    )

    # Google Doc vinculado (edição do texto acontece lá)
    google_doc_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_doc_link: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Snapshot do texto/HTML após a última sincronização/geração
    conteudo_texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    conteudo_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    paginas_estimadas: Mapped[float | None] = mapped_column(nullable=True)

    # [{"tribunal","numero","trecho_citado","status_geral","custo_usd",...}]
    citacoes_validadas: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    # Arquivos de estudo enviados pelo usuário (imagem/vídeo/PDF), base para o
    # informativo do mês. [{"nome","link_drive","tipo"}]
    arquivos_referencia: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    drive_folder_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    drive_pdf_link: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Prazos internos (calculados ao criar): 1º draft 15 dias antes do fim do
    # mês anterior; versão revisada 7 dias antes do início do mês de referência.
    data_prazo_draft: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_prazo_final: Mapped[date | None] = mapped_column(Date, nullable=True)

    lembrete_draft_enviado: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    lembrete_final_enviado: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")

    publicado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
