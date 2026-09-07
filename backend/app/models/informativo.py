import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
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

    # Número sequencial do informativo (ex.: "Informativo nº 12"), atribuído
    # na criação a partir de InformativoConfig.proximo_numero.
    numero: Mapped[int | None] = mapped_column(Integer, nullable=True)

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

    # Snapshot de resumo/perguntas lido do Doc no momento da publicação — evita
    # ler o Google Docs a cada request da listagem pública (era o motivo da
    # página /informativos do site demorar 5-10s pra carregar).
    resumo_publicado: Mapped[str | None] = mapped_column(Text, nullable=True)
    perguntas_publicadas: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    # [{"tribunal","numero","trecho_citado","status_geral","custo_usd",...}]
    citacoes_validadas: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    # Arquivos de estudo enviados pelo usuário (imagem/vídeo/PDF), base para o
    # informativo do mês. [{"nome","link_drive","tipo"}]
    arquivos_referencia: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")

    # Direcionamento livre do usuário pro rascunho da IA (ex.: "foque no
    # impacto pra holdings imobiliárias, cite o julgado X").
    instrucoes_ia: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Quando o rascunho (corpo) foi gerado/regenerado pela IA pela última vez.
    rascunho_gerado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    drive_folder_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    drive_pdf_link: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Prazos internos (calculados ao criar): 1º draft 15 dias antes do fim do
    # mês anterior; versão revisada 7 dias antes do início do mês de referência.
    data_prazo_draft: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_prazo_final: Mapped[date | None] = mapped_column(Date, nullable=True)

    lembrete_draft_enviado: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    lembrete_final_enviado: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")

    # Confirmação manual do Lucas de que o informativo está revisado e pode
    # ser publicado/distribuído. Não trava nada no sistema — é só um sinal
    # pro fluxo de lembretes por e-mail saber que já pode parar de cobrar.
    autorizado: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    autorizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Throttle dos lembretes de "confirme e autorize" (a cada 2 dias).
    ultimo_lembrete_autorizacao_em: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Dedup do lembrete de véspera do mês (publicação, se autorizado; aviso
    # de atraso, se não).
    lembrete_vespera_enviado: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")

    publicado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class InformativoConfig(Base):
    """Configuração única do módulo (linha id=1): o modelo (Google Doc) usado
    como base de cada informativo novo, e o contador do número sequencial.

    O modelo é criado automaticamente na primeira vez (cópia do timbrado do
    escritório + esqueleto: número/mês, tema/subtema, resumo estruturado,
    separador, corpo). É só um Google Doc — pode ser aberto e ajustado
    livremente (fonte, cores, logo) a qualquer momento; os próximos
    informativos vão copiar a versão mais recente dele.
    """

    __tablename__ = "informativo_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    template_doc_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    template_doc_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    proximo_numero: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # Responsável padrão pra todo informativo NOVO — editável na tela
    # principal; muda o default só pra informativos futuros (os já criados
    # mantêm o responsável que tinham). Semeado com RESPONSAVEL_PADRAO_NOME
    # (busca por nome) na primeira vez que for resolvido, se ainda não setado.
    responsavel_padrao_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("responsaveis.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class InformativoAssinante(Base):
    """Inscrição pública pra newsletter dos Informativos (formulário na
    página pública do site) — independente de ser Cliente cadastrado.
    A lista de envio da newsletter soma isso com Cliente.email e
    ConselhoContato.email (ver `listar_destinatarios_newsletter`)."""

    __tablename__ = "informativo_assinantes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ativo: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InformativoOptOut(Base):
    """Lista de supressão da newsletter — e-mail aqui NUNCA recebe, mesmo que
    seja Cliente, Contato do Conselho ou InformativoAssinante. Alimentada
    pelo link de descadastro no rodapé do e-mail, ou manualmente pelo Lucas
    na tela de E-mails.

    `oculto` distingue as duas ações que a tela de E-mails oferece: opt-out
    (email continua listado, só marcado como descadastrado — reversível) e
    "excluir completamente" (email some da listagem inteira, além de nunca
    receber — para quando o cadastro é lixo/errado)."""

    __tablename__ = "informativo_opt_out"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    oculto: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InformativoEnvioStatus(Base):
    """Resumo compacto de envio da newsletter por e-mail — 1 linha por
    destinatário, não 1 linha por envio, pra não crescer sem limite conforme
    mais informativos forem saindo. Usado só pra mostrar "já recebeu X
    informativos, último em tal data" na tela de E-mails."""

    __tablename__ = "informativo_envio_status"

    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    total_enviados: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    ultimo_numero: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ultimo_titulo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ultimo_enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
