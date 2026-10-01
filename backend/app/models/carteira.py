from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, ForeignKey, Text, JSON, Index
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


# ─────────────────────────────────────────────────────────────────
# 1. CLIENTE (Vinculação Principal)
# ─────────────────────────────────────────────────────────────────

class CarteiraCliente(Base):
    __tablename__ = 'carteira_cliente'

    id = Column(Integer, primary_key=True)
    usuario_cliente_id = Column(Integer, nullable=False, unique=True)
    cpf = Column(String(20), unique=True, nullable=True)
    tipo_pessoa = Column(String(2), default='PF')

    # Contatos
    email = Column(String(255), nullable=True)
    telefone = Column(String(20), nullable=True)
    qualificacao_id = Column(Integer, nullable=True)

    # Vinculações Legais
    contrato_principal_id = Column(Integer, nullable=True)
    procuracao_id = Column(Integer, nullable=True)

    # Honorários
    pro_labore_tipo = Column(String(50), default='fixo')
    pro_labore_valor = Column(Float, nullable=True)
    percentual_sucesso_geral = Column(Float, default=0.0)
    observacao_honorarios = Column(Text, nullable=True)
    fonte_captacao = Column(String(255), nullable=True)

    # Drive
    folder_drive_principal_id = Column(String(255), nullable=True)
    folder_drive_url = Column(String(500), nullable=True)

    # Administrativo
    data_cadastro = Column(DateTime, default=datetime.now)
    ativo = Column(Boolean, default=True)
    observacoes = Column(Text, nullable=True)

    # Relacionamentos
    debentures = relationship("CarteiraDebenturePosicao", back_populates="cliente", cascade="all, delete-orphan")
    imobiliarios = relationship("CarteiraImobiliarioPosicao", back_populates="cliente", cascade="all, delete-orphan")
    fundos = relationship("CarteiraFundoPosicao", back_populates="cliente", cascade="all, delete-orphan")

    __table_args__ = (Index('idx_usuario_cliente_id', 'usuario_cliente_id'),)


# ─────────────────────────────────────────────────────────────────
# 2. DEBÊNTURES
# ─────────────────────────────────────────────────────────────────

class CarteiraDebentureadotEmissao(Base):
    __tablename__ = 'carteira_debenture_emissao'

    id = Column(Integer, primary_key=True)
    nome_serie = Column(String(100), nullable=False)
    numero_emissao = Column(Integer, nullable=False)
    emissor = Column(String(255), nullable=False)
    cnpj_emissor = Column(String(20), nullable=True)
    indexador = Column(String(100), nullable=True)
    taxa_adicional = Column(String(100), nullable=True)
    data_inicio_emissao = Column(Date, nullable=True)
    data_vencimento_previsto = Column(Date, nullable=True)
    prazo_carencia_meses = Column(Integer, nullable=True)
    prazo_pgto_pos_resgate = Column(String(100), nullable=True)

    # Resgate Antecipado (2 flags)
    resgate_antecipado_emissao = Column(Boolean, default=False)
    resgate_antecipado_termo = Column(Boolean, default=False)
    notas_resgate = Column(Text, nullable=True)

    # Garantias e Observações
    tipos_garantia = Column(JSON, default=list)
    observacoes_gerais = Column(Text, nullable=True)
    data_criacao = Column(DateTime, default=datetime.now)
    ativo = Column(Boolean, default=True)

    # Relacionamentos
    posicoes = relationship("CarteiraDebenturePosicao", back_populates="emissao", cascade="all, delete-orphan")

    __table_args__ = (Index('idx_nome_serie', 'nome_serie'), Index('idx_emissor', 'emissor'))


class CarteiraDebenturePosicao(Base):
    __tablename__ = 'carteira_debenture_posicao'

    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey('carteira_cliente.id'), nullable=False)
    emissao_id = Column(Integer, ForeignKey('carteira_debenture_emissao.id'), nullable=False)

    numero_cautela = Column(String(100), nullable=False)
    numero_debentures = Column(Integer, nullable=True)
    valor_aplicado = Column(Float, nullable=False)
    data_aquisicao = Column(Date, nullable=False)

    # Valor Atual
    data_base_valor_atual = Column(Date, nullable=True)
    valor_atual_estimado = Column(Float, nullable=True)
    variacao_percentual = Column(Float, nullable=True)

    # Projeção de Retorno
    projecao_retorno_percentual = Column(Float, default=0.0)

    # Resgate
    status_resgate = Column(String(50), default='Ativo')
    data_pedido_resgate = Column(Date, nullable=True)
    resposta_rhino = Column(Text, nullable=True)
    foi_pago = Column(Boolean, default=False)
    valor_pago = Column(Float, nullable=True)
    data_pagamento = Column(Date, nullable=True)

    # Aval de Sócios
    aval_socios = Column(JSON, default=list)

    # Administrativo
    estrategia_id = Column(Integer, ForeignKey('carteira_estrategia.id'), nullable=True)
    faz_parte_honorarios = Column(Boolean, default=False)
    percentual_sucesso_honor = Column(Float, nullable=True)
    processos_judiciais = Column(JSON, default=list)
    notificado = Column(Boolean, default=False)
    folder_drive_id = Column(String(255), nullable=True)
    observacoes = Column(Text, nullable=True)
    data_criacao = Column(DateTime, default=datetime.now)
    data_atualizacao = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relacionamentos
    cliente = relationship("CarteiraCliente", back_populates="debentures")
    emissao = relationship("CarteiraDebentureadotEmissao", back_populates="posicoes")
    estrategia = relationship("CarteiraEstrategia", back_populates="posicoes_debentures")

    __table_args__ = (Index('idx_cliente_debenture', 'cliente_id'), Index('idx_numero_cautela', 'numero_cautela'))


# ─────────────────────────────────────────────────────────────────
# 3. IMOBILIÁRIO
# ─────────────────────────────────────────────────────────────────

class CarteiraImobiliarioEmpreendimento(Base):
    __tablename__ = 'carteira_imobiliario_empreendimento'

    id = Column(Integer, primary_key=True)
    nome_venda = Column(String(255), unique=True, nullable=False)
    nome_razao_social = Column(String(255), nullable=True)
    cnpj_empreendimento = Column(String(20), nullable=True)
    tipo_desenvolvimento = Column(String(100), nullable=True)
    localizacao = Column(String(255), nullable=True)
    abmparse_veiculo = Column(String(100), nullable=True)
    data_inicio_previsto = Column(Date, nullable=True)
    data_conclusao_prevista = Column(Date, nullable=True)
    valor_total_empreendimento = Column(Float, nullable=True)
    descricao = Column(Text, nullable=True)
    data_criacao = Column(DateTime, default=datetime.now)
    ativo = Column(Boolean, default=True)

    # Relacionamentos
    posicoes = relationship("CarteiraImobiliarioPosicao", back_populates="empreendimento", cascade="all, delete-orphan")

    __table_args__ = (Index('idx_nome_venda', 'nome_venda'), Index('idx_abmparse', 'abmparse_veiculo'))


class CarteiraImobiliarioSpe(Base):
    __tablename__ = 'carteira_imobiliario_spe'

    id = Column(Integer, primary_key=True)
    nome = Column(String(255), nullable=False)
    cnpj = Column(String(20), nullable=True)
    abmparse_vinculado = Column(String(100), nullable=True)
    empreendimento_id = Column(Integer, ForeignKey('carteira_imobiliario_empreendimento.id'), nullable=True)
    data_criacao = Column(DateTime, default=datetime.now)
    ativo = Column(Boolean, default=True)


class CarteiraImobiliarioPosicao(Base):
    __tablename__ = 'carteira_imobiliario_posicao'

    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey('carteira_cliente.id'), nullable=False)
    empreendimento_id = Column(Integer, ForeignKey('carteira_imobiliario_empreendimento.id'), nullable=False)

    # Partes Interessadas
    partes_interessadas = Column(JSON, default=list)
    percentual_participacao = Column(Float, default=100.0)

    # Valores
    valor_total_compromissado = Column(Float, nullable=False)
    valor_efetivamente_investido = Column(Float, nullable=False)
    data_base_valores = Column(Date, nullable=True)
    valor_esperado_retorno = Column(Float, nullable=True)
    percentual_esperado_retorno = Column(Float, nullable=True)

    # Estrutura de Investimento (Multi-Layer ABM-PARSE)
    veiculo_abmparse_primario = Column(String(100), nullable=True)
    veiculo_abmparse_secundario = Column(String(100), nullable=True)
    veiculo_abmparse_terciario = Column(String(100), nullable=True)
    spe_principal_id = Column(Integer, ForeignKey('carteira_imobiliario_spe.id'), nullable=True)
    percentual_na_spe = Column(Float, nullable=True)

    # SCP (Sociedade em Conta de Participação)
    scp_numero = Column(String(100), nullable=True)
    scp_contrato_link = Column(Integer, nullable=True)
    scp_data_constituicao = Column(Date, nullable=True)
    partes_na_scp = Column(JSON, default=list)
    representante_scp = Column(String(255), nullable=True)

    # Camada Superior (Prestadora de Serviços)
    prestadora_servicos = Column(String(255), default="Apex Realty")
    cnpj_prestadora = Column(String(20), nullable=True)
    percentual_servico_prestadora = Column(Float, nullable=True)
    taxa_performance = Column(Float, nullable=True)

    # Aportes
    data_primeiro_aporte = Column(Date, nullable=True)
    data_ultimo_aporte = Column(Date, nullable=True)
    quantidade_aportes = Column(Integer, nullable=True)
    historico_aportes = Column(JSON, default=list)

    # Honorários
    faz_parte_honorarios = Column(Boolean, default=False)
    percentual_sucesso_honorario = Column(Float, nullable=True)
    observacao_honorarios = Column(Text, nullable=True)

    # Administrativo
    estrategia_id = Column(Integer, ForeignKey('carteira_estrategia.id'), nullable=True)
    folder_drive_id = Column(String(255), nullable=True)
    processos_judiciais = Column(JSON, default=list)
    notificado = Column(Boolean, default=False)
    observacoes = Column(Text, nullable=True)
    data_criacao = Column(DateTime, default=datetime.now)
    data_atualizacao = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relacionamentos
    cliente = relationship("CarteiraCliente", back_populates="imobiliarios")
    empreendimento = relationship("CarteiraImobiliarioEmpreendimento", back_populates="posicoes")
    estrategia = relationship("CarteiraEstrategia", back_populates="posicoes_imobiliarios")

    __table_args__ = (Index('idx_cliente_imobiliario', 'cliente_id'),)


# ─────────────────────────────────────────────────────────────────
# 4. FUNDOS
# ─────────────────────────────────────────────────────────────────

class CarteiraFundoReferencia(Base):
    __tablename__ = 'carteira_fundo_referencia'

    id = Column(Integer, primary_key=True)
    nome_fundo = Column(String(255), unique=True, nullable=False)
    cnpj_fundo = Column(String(20), nullable=True, index=True)
    gestora = Column(String(255), nullable=True)
    administradora = Column(String(255), nullable=True)
    tipo_fundo = Column(String(50), nullable=True)
    indexador = Column(String(100), nullable=True)
    percentual_esperado = Column(Float, nullable=True)
    data_constituicao = Column(Date, nullable=True)
    data_criacao = Column(DateTime, default=datetime.now)
    ativo = Column(Boolean, default=True)
    observacoes = Column(Text, nullable=True)

    # Relacionamentos
    posicoes = relationship("CarteiraFundoPosicao", back_populates="fundo", cascade="all, delete-orphan")

    __table_args__ = (Index('idx_nome_fundo', 'nome_fundo'), Index('idx_gestora', 'gestora'))


class CarteiraFundoPosicao(Base):
    __tablename__ = 'carteira_fundo_posicao'

    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey('carteira_cliente.id'), nullable=False)
    fundo_id = Column(Integer, ForeignKey('carteira_fundo_referencia.id'), nullable=False)

    numero_conta = Column(String(100), nullable=True)

    # Aplicação
    data_aplicacao = Column(Date, nullable=False)
    valor_aplicado = Column(Float, nullable=False)
    quantidade_cotas = Column(Float, nullable=True)
    valor_cota_inicial = Column(Float, nullable=True)

    # Posição Atual
    data_base_valor_atual = Column(Date, nullable=True)
    valor_cota_atual = Column(Float, nullable=True)
    valor_atual_estimado = Column(Float, nullable=True)
    variacao_percentual = Column(Float, nullable=True)
    variacao_valor_absoluto = Column(Float, nullable=True)

    # Projeção de Retorno
    projecao_retorno_percentual = Column(Float, default=0.0)

    # Direito de Recompra
    tem_direito_recompra = Column(Boolean, default=False)
    promessa_recompra = Column(String(100), nullable=True)
    data_vencimento_recompra = Column(Date, nullable=True)
    valor_base_recompra = Column(Float, nullable=True)
    status_recompra = Column(String(50), default='Aguardando')
    data_exercicio_recompra = Column(Date, nullable=True)

    # Administrativo
    faz_parte_honorarios = Column(Boolean, default=False)
    percentual_sucesso_honor = Column(Float, nullable=True)
    estrategia_id = Column(Integer, ForeignKey('carteira_estrategia.id'), nullable=True)
    folder_drive_id = Column(String(255), nullable=True)
    processos_judiciais = Column(JSON, default=list)
    notificado = Column(Boolean, default=False)
    observacoes = Column(Text, nullable=True)
    data_criacao = Column(DateTime, default=datetime.now)
    data_atualizacao = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relacionamentos
    cliente = relationship("CarteiraCliente", back_populates="fundos")
    fundo = relationship("CarteiraFundoReferencia", back_populates="posicoes")
    estrategia = relationship("CarteiraEstrategia", back_populates="posicoes_fundos")

    __table_args__ = (Index('idx_cliente_fundo', 'cliente_id'),)


# ─────────────────────────────────────────────────────────────────
# 5. ESTRATÉGIA (Reutilizável)
# ─────────────────────────────────────────────────────────────────

class CarteiraEstrategia(Base):
    __tablename__ = 'carteira_estrategia'

    id = Column(Integer, primary_key=True)
    nome = Column(String(255), nullable=False, unique=True)
    descricao = Column(Text, nullable=True)
    criada_por = Column(Integer, nullable=True)
    data_criacao = Column(DateTime, default=datetime.now)
    publico = Column(Boolean, default=True)
    alocacao_recomendada = Column(JSON, default=dict)
    usuarios_count = Column(Integer, default=0)
    ativo = Column(Boolean, default=True)

    # Relacionamentos
    posicoes_debentures = relationship("CarteiraDebenturePosicao", back_populates="estrategia")
    posicoes_imobiliarios = relationship("CarteiraImobiliarioPosicao", back_populates="estrategia")
    posicoes_fundos = relationship("CarteiraFundoPosicao", back_populates="estrategia")

    __table_args__ = (Index('idx_nome_estrategia', 'nome'),)


# ─────────────────────────────────────────────────────────────────
# 6. AUXILIARES
# ─────────────────────────────────────────────────────────────────

class CarteiraSocioAval(Base):
    __tablename__ = 'carteira_socio_aval'

    id = Column(Integer, primary_key=True)
    nome_socio = Column(String(255), nullable=False, unique=True)
    percentual_participacao = Column(Float, nullable=True)
    ativo = Column(Boolean, default=True)
    observacoes = Column(Text, nullable=True)


class CarteiraUploadDocumento(Base):
    __tablename__ = 'carteira_upload_documento'

    id = Column(Integer, primary_key=True)
    tipo_ativo = Column(String(50))
    posicao_id = Column(Integer, nullable=True)
    nome_arquivo = Column(String(500), nullable=False)
    tipo_documento = Column(String(100), nullable=True)
    url_gd = Column(String(500), nullable=True)
    ia_processada = Column(Boolean, default=False)
    dados_extraidos = Column(JSON, default=dict)
    data_upload = Column(DateTime, default=datetime.now)
    data_processamento_ia = Column(DateTime, nullable=True)

    __table_args__ = (Index('idx_posicao_tipo', 'posicao_id', 'tipo_ativo'),)
