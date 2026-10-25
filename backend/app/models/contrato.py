import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Contrato(Base):
    __tablename__ = "contratos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False
    )
    processo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("processos.id"), nullable=True
    )

    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    # "contrato" (padrão) ou "procuracao" — mesma infra (ClickSign, e-mails,
    # leitura por IA), só muda o gerador de PDF e a pasta do Drive.
    tipo_documento: Mapped[str] = mapped_column(String(20), nullable=False, default="contrato", server_default="contrato")
    arquivo_path: Mapped[str | None] = mapped_column(String(500))  # path local do PDF original (legado)
    arquivo_assinado_path: Mapped[str | None] = mapped_column(String(500))  # PDF assinado
    # Lista de arquivos: [{"filename": str, "path": str, "clicksign_key": str|null, "drive_link": str|null, "docs_link": str|null}]
    arquivos: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    # Nome do arquivo atualmente "gerado pelo sistema" (Gerar contrato/procuração) — ao
    # regerar, esse é o entry removido/substituído em vez de duplicado.
    doc_gerado_filename: Mapped[str | None] = mapped_column(String(500))
    # Último payload usado para gerar a procuração (GerarProcuracaoRequest), para
    # pré-preencher o formulário ao reabrir/editar.
    procuracao_dados: Mapped[dict | None] = mapped_column(JSONB)
    # Auditoria de quem gerou o PDF (e quando) — atualiza a cada geração/edição.
    doc_gerado_por: Mapped[str | None] = mapped_column(String(255))
    doc_gerado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Equipe interna responsável pelo contrato/cliente (ids de Responsavel, como
    # texto — JSONB em vez de tabela de junção, mesmo padrão de `arquivos`) e o
    # escopo/recomendações que vão no aviso a eles. Nada financeiro entra aqui.
    responsaveis_ids: Mapped[list] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    escopo_recomendacoes: Mapped[str | None] = mapped_column(Text)
    responsaveis_notificados_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(
        Enum(
            "rascunho",
            "aguardando_assinatura",
            "parcialmente_assinado",
            "assinado",
            "cancelado",
            name="status_contrato",
        ),
        nullable=False,
        default="rascunho",
    )

    # Assinatura manual (fora do ClickSign)
    assinatura_manual: Mapped[bool] = mapped_column(default=False, server_default="false")

    # Links do Drive do documento final assinado (pasta do cliente + pasta mestra /Contratos)
    drive_link_cliente: Mapped[str | None] = mapped_column(String(1000))
    drive_link_master: Mapped[str | None] = mapped_column(String(1000))

    # ClickSign
    clicksign_document_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    clicksign_request_signature_key: Mapped[str | None] = mapped_column(String(255))
    # Quando foi enviado ao ClickSign — base dos lembretes automáticos de assinatura.
    assinatura_enviada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Última vez que o sistema confirmou o status no ClickSign (antes de um lembrete) — evita consultar à toa.
    ultima_validacao_clicksign_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="contratos")  # noqa: F821
    processo: Mapped["Processo | None"] = relationship("Processo")  # noqa: F821
    signatarios: Mapped[list["Signatario"]] = relationship(
        "Signatario", back_populates="contrato", cascade="all, delete-orphan"
    )


class Signatario(Base):
    __tablename__ = "signatarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contrato_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contratos.id"), nullable=False
    )

    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    papel: Mapped[str] = mapped_column(
        Enum("contratante", "contratado", "testemunha", "outro", name="papel_signatario"),
        nullable=False,
        default="outro",
    )
    # Opcionais — ajudam o ClickSign a pré-preencher os dados na hora de assinar.
    cpf: Mapped[str | None] = mapped_column(String(18))
    data_nascimento: Mapped[date | None] = mapped_column(Date)
    # Preenchido = opt-in pro aviso de assinatura por WhatsApp (template
    # `assinatura_pendente`), além do e-mail do ClickSign. Vazio = só e-mail.
    whatsapp: Mapped[str | None] = mapped_column(String(30))
    # Com número preenchido, o PADRÃO é avisar por WhatsApp (nossa mensagem com o
    # link, além do e-mail do ClickSign). Desmarcar = só e-mail.
    # Lembretes automáticos por WhatsApp já enviados (estágio 0..4) e quando; aviso de cancelamento.
    lembretes_whatsapp: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    ultimo_lembrete_whatsapp_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelamento_avisado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Cópia do contrato assinado (PDF) já enviada a este signatário por WhatsApp.
    contrato_assinado_enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    avisar_whatsapp: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    # Opcional: o próprio ClickSign convida e autentica por WhatsApp (communicate_by
    # + auths=whatsapp). Exige o recurso habilitado na conta/plano e cobra por
    # mensagem do ClickSign — por isso nunca é padrão. Exclui o nosso aviso (duplicaria).
    assinar_via_whatsapp: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    # ClickSign
    clicksign_signer_key: Mapped[str | None] = mapped_column(String(255))
    clicksign_request_key: Mapped[str | None] = mapped_column(String(255))
    # Preenchido quando a criação/vinculação desse signatário no ClickSign falha —
    # nesse caso ele NUNCA existe lá e não recebe convite nenhum, mesmo que o envio
    # geral do contrato "dê certo" pros outros signatários.
    clicksign_erro: Mapped[str | None] = mapped_column(Text)
    status_assinatura: Mapped[str] = mapped_column(
        Enum("pendente", "assinado", "recusado", name="status_assinatura"),
        nullable=False,
        default="pendente",
    )
    assinado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    contrato: Mapped["Contrato"] = relationship("Contrato", back_populates="signatarios")


class PoderesTemplate(Base):
    """Texto salvo (com nome) para substituir a cláusula padrão "ad judicia et
    extra" na seção DOS PODERES da procuração. Reutilizável entre procurações —
    ver app/services/procuracao_pdf.py e o endpoint /contratos/poderes-templates."""
    __tablename__ = "poderes_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class EscopoTemplate(Base):
    """Texto salvo (com nome) de escopo/recomendações — pré-formatado pra reaproveitar
    em vários contratos. Mesmo molde de PoderesTemplate."""
    __tablename__ = "escopo_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
