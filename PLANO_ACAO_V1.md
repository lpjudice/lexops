# 🚀 PLANO DE AÇÃO - CARTEIRA V1 (TODAY)

**Status**: Iniciando Desenvolvimento  
**Data**: 30/09/2026  
**Escopo**: Backend + Frontend + Seed de Dados  

---

## RESUMO EXECUTIVO

**O QUE VAMOS FAZER HOJE**:
- ✅ Menu atualizado (Carteira em AUTOS IA)
- 🔄 **Backend**: SQLAlchemy models (Cliente, Debentures, Imobiliário, Fundos)
- 🔄 **API Endpoints**: CRUD para cada ativo
- 🔄 **Frontend**: Tabelas + Formulários (Opção 2 do blueprint)
- 🔄 **Seed**: Importar dados da planilha XLSX
- 🔄 **Drive Integration**: Linker com Google Drive
- 🔄 **IA Upload**: Claude Vision para leitura de documentos

**Prioridade**: Debêntures → Imobiliário → Fundos (nessa ordem)

---

## FASE 1: BACKEND (Models + Endpoints)

### 1.1 Criar Models SQLAlchemy

**Arquivo**: `backend/app/models/carteira.py`

```python
from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, ForeignKey, Text, JSON, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()

# ─────────────────────────────────────────────────────────────────
# 1. CLIENTE (Vinculação Principal)
# ─────────────────────────────────────────────────────────────────

class CarteiraCliente(Base):
    __tablename__ = 'carteira_cliente'
    
    id = Column(Integer, primary_key=True)
    usuario_cliente_id = Column(Integer, nullable=False)  # FK para usuario_cliente
    cpf = Column(String(20), unique=True, nullable=True)
    tipo_pessoa = Column(String(2), default='PF')  # PF or PJ
    
    # Contatos
    email = Column(String(255), nullable=True)
    telefone = Column(String(20), nullable=True)
    qualificacao_id = Column(Integer, nullable=True)  # FK para cliente_qualificacao
    
    # Vinculações Legais
    contrato_principal_id = Column(Integer, nullable=True)
    procuracao_id = Column(Integer, nullable=True)
    
    # Honorários (Separado da Lógica Financeira)
    pro_labore_tipo = Column(String(50), default='fixo')  # 'fixo' ou '%_ativo' ou '%_imobiliario' ou '%_financeiro' ou '%_total'
    pro_labore_valor = Column(Float, nullable=True)  # R$ (se fixo) ou % (se variável)
    percentual_sucesso_geral = Column(Float, default=0.0)  # % padrão
    observacao_honorarios = Column(Text, nullable=True)
    fonte_captacao = Column(String(255), nullable=True)  # "Indicação XYZ", "Contato Direto", etc.
    
    # Drive
    folder_drive_principal_id = Column(String(255), nullable=True)  # Google Drive folder ID
    folder_drive_url = Column(String(500), nullable=True)
    
    # Administrativo
    data_cadastro = Column(DateTime, default=datetime.now)
    ativo = Column(Boolean, default=True)
    observacoes = Column(Text, nullable=True)
    
    # Relacionamentos
    debentures = relationship("CarteiradebenturePosicao", back_populates="cliente")
    imobiliarios = relationship("CarteiraImobiliarioPosicao", back_populates="cliente")
    fundos = relationship("CarteiraFundoPosicao", back_populates="cliente")


# ─────────────────────────────────────────────────────────────────
# 2. DEBÊNTURES
# ─────────────────────────────────────────────────────────────────

class CarteiraDebentureadotEmissao(Base):
    """Referência reutilizável (uma emissão = múltiplos clientes)"""
    __tablename__ = 'carteira_debenture_emissao'
    
    id = Column(Integer, primary_key=True)
    nome_serie = Column(String(100), nullable=False)  # "BRMAPEX110", "BRMAPEX115"
    numero_emissao = Column(Integer, nullable=False)  # 1, 2, 3...
    emissor = Column(String(255), nullable=False)
    cnpj_emissor = Column(String(20), nullable=True)
    indexador = Column(String(100))  # "CDI", "IPCA", etc.
    taxa_adicional = Column(String(100))  # "11,5% a.a.", "140% CDI", etc.
    data_inicio_emissao = Column(Date, nullable=True)
    data_vencimento_previsto = Column(Date, nullable=True)
    prazo_carencia_meses = Column(Integer, nullable=True)  # 3, 6, 12, NULL = sem
    prazo_pgto_pos_resgate = Column(String(100))  # "D+1", "D+30", "D+90"
    
    # Direito de Resgate Antecipado (2 flags: diferença entre Emissão e Termo)
    resgate_antecipado_emissao = Column(Boolean, default=False)  # Contrato Público
    resgate_antecipado_termo = Column(Boolean, default=False)  # Termo Securitização
    
    # Notas sobre contradições
    notas_resgate = Column(Text, nullable=True)  # "Emissão diz não, Termo diz sim" etc.
    
    tipos_garantia = Column(JSON, default=list)  # ["Fluxo Imobiliário", "Aval Sócios", ...]
    observacoes_gerais = Column(Text, nullable=True)
    data_criacao = Column(DateTime, default=datetime.now)
    ativo = Column(Boolean, default=True)
    
    # Relacionamentos
    posicoes = relationship("CarteiraDebenturePosicao", back_populates="emissao")


class CarteiraDebenturePosicao(Base):
    """Posição específica de um cliente (1 cliente + 1 cautela = 1 posição)"""
    __tablename__ = 'carteira_debenture_posicao'
    
    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey('carteira_cliente.id'), nullable=False)
    emissao_id = Column(Integer, ForeignKey('carteira_debenture_emissao.id'), nullable=False)
    
    numero_cautela = Column(String(100), nullable=False)  # "1816", "1954"
    numero_debentures = Column(Integer, nullable=True)  # Quantidade
    valor_aplicado = Column(Float, nullable=False)  # R$
    data_aquisicao = Column(Date, nullable=False)
    
    # Valor Atual
    data_base_valor_atual = Column(Date, nullable=True)
    valor_atual_estimado = Column(Float, nullable=True)
    variacao_percentual = Column(Float, nullable=True)  # Calculado automático
    
    # Projeção de Retorno
    projecao_retorno_percentual = Column(Float, default=0.0)  # -x% a +x%
    
    # Resgate
    status_resgate = Column(String(50), default='Ativo')  # Ativo, Solicitado, Negado, Processando, Liquidado
    data_pedido_resgate = Column(Date, nullable=True)
    resposta_rhino = Column(Text, nullable=True)
    foi_pago = Column(Boolean, default=False)
    valor_pago = Column(Float, nullable=True)
    data_pagamento = Column(Date, nullable=True)
    
    # Aval de Sócios
    aval_socios = Column(JSON, default=list)  # [{"nome": "Lucas", "percentual": 50}, ...]
    
    # Administrativo
    estrategia_id = Column(Integer, ForeignKey('carteira_estrategia.id'), nullable=True)
    faz_parte_honorarios = Column(Boolean, default=False)
    percentual_sucesso_honor = Column(Float, nullable=True)
    processos_judiciais = Column(JSON, default=list)  # [processo_id, ...]
    notificado = Column(Boolean, default=False)
    folder_drive_id = Column(String(255), nullable=True)
    observacoes = Column(Text, nullable=True)
    data_criacao = Column(DateTime, default=datetime.now)
    data_atualizacao = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    cliente = relationship("CarteiraCliente", back_populates="debentures")
    emissao = relationship("CarteiraDebentureadotEmissao", back_populates="posicoes")
    estrategia = relationship("CarteiraEstrategia", back_populates="posicoes_debentures")


# ─────────────────────────────────────────────────────────────────
# 3. IMOBILIÁRIO
# ─────────────────────────────────────────────────────────────────

class CarteiraImobiliarioEmpreendimento(Base):
    """Referência reutilizável (um empreendimento = múltiplos clientes)"""
    __tablename__ = 'carteira_imobiliario_empreendimento'
    
    id = Column(Integer, primary_key=True)
    nome_venda = Column(String(255), unique=True, nullable=False)  # "Showa", "Fazenda Atalaia"
    nome_razao_social = Column(String(255), nullable=True)
    cnpj_empreendimento = Column(String(20), nullable=True)
    tipo_desenvolvimento = Column(String(100))  # "Residencial", "Logístico", "Escritórios"
    localizacao = Column(String(255), nullable=True)
    abmparse_veiculo = Column(String(100), nullable=True)  # "ABMPARSE 01", "ABMPARSE 02"
    data_inicio_previsto = Column(Date, nullable=True)
    data_conclusao_prevista = Column(Date, nullable=True)
    valor_total_empreendimento = Column(Float, nullable=True)  # R$ orçamento
    descricao = Column(Text, nullable=True)
    data_criacao = Column(DateTime, default=datetime.now)
    ativo = Column(Boolean, default=True)
    
    # Relacionamentos
    posicoes = relationship("CarteiraImobiliarioPosicao", back_populates="empreendimento")


class CarteiraImobiliarioSpe(Base):
    """SPE vinculada ao veículo ABM-PARSE"""
    __tablename__ = 'carteira_imobiliario_spe'
    
    id = Column(Integer, primary_key=True)
    nome = Column(String(255), nullable=False)
    cnpj = Column(String(20), nullable=True)
    abmparse_vinculado = Column(String(100), nullable=True)  # "ABMPARSE 01"
    empreendimento_id = Column(Integer, ForeignKey('carteira_imobiliario_empreendimento.id'), nullable=True)
    data_criacao = Column(DateTime, default=datetime.now)
    ativo = Column(Boolean, default=True)


class CarteiraImobiliarioPosicao(Base):
    """Posição específica de um cliente em um empreendimento (multi-layer)"""
    __tablename__ = 'carteira_imobiliario_posicao'
    
    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey('carteira_cliente.id'), nullable=False)
    empreendimento_id = Column(Integer, ForeignKey('carteira_imobiliario_empreendimento.id'), nullable=False)
    
    # Partes Interessadas
    partes_interessadas = Column(JSON, default=list)  # ["Lucas Judice", "Cônjuge", ...]
    percentual_participacao = Column(Float, default=100.0)  # %
    
    # Valores
    valor_total_compromissado = Column(Float, nullable=False)  # R$ prometido
    valor_efetivamente_investido = Column(Float, nullable=False)  # R$ aportado
    data_base_valores = Column(Date, nullable=True)
    valor_esperado_retorno = Column(Float, nullable=True)  # R$ projeção
    percentual_esperado_retorno = Column(Float, nullable=True)  # % a.a. ou período
    
    # Estrutura de Investimento (Multi-Layer ABM-PARSE)
    veiculo_abmparse_primario = Column(String(100), nullable=True)
    veiculo_abmparse_secundario = Column(String(100), nullable=True)
    veiculo_abmparse_terciario = Column(String(100), nullable=True)
    spe_principal_id = Column(Integer, ForeignKey('carteira_imobiliario_spe.id'), nullable=True)
    percentual_na_spe = Column(Float, nullable=True)  # %
    
    # SCP (Sociedade em Conta de Participação)
    scp_numero = Column(String(100), nullable=True)  # "SCP 001/2024"
    scp_contrato_link = Column(Integer, nullable=True)  # FK para contrato
    scp_data_constituicao = Column(Date, nullable=True)
    partes_na_scp = Column(JSON, default=list)  # [{"nome": "Lucas", "%": 50, "data": "2024-01-15"}, ...]
    representante_scp = Column(String(255), nullable=True)
    
    # Camada Superior (Prestadora de Serviços)
    prestadora_servicos = Column(String(255), default="Apex Realty")
    cnpj_prestadora = Column(String(20), nullable=True)
    percentual_servico_prestadora = Column(Float, nullable=True)  # % sobre retorno
    taxa_performance = Column(Float, nullable=True)  # % se meta atingida
    
    # Aportes
    data_primeiro_aporte = Column(Date, nullable=True)
    data_ultimo_aporte = Column(Date, nullable=True)
    quantidade_aportes = Column(Integer, nullable=True)
    historico_aportes = Column(JSON, default=list)  # [{"data": "2024-01-15", "valor": 100000}, ...]
    
    # Honorários
    faz_parte_honorarios = Column(Boolean, default=False)
    percentual_sucesso_honorario = Column(Float, nullable=True)  # % do ganho
    observacao_honorarios = Column(Text, nullable=True)
    
    # Administrativo
    estrategia_id = Column(Integer, ForeignKey('carteira_estrategia.id'), nullable=True)
    folder_drive_id = Column(String(255), nullable=True)
    processos_judiciais = Column(JSON, default=list)  # [processo_id, ...]
    notificado = Column(Boolean, default=False)
    observacoes = Column(Text, nullable=True)
    data_criacao = Column(DateTime, default=datetime.now)
    data_atualizacao = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relacionamentos
    cliente = relationship("CarteiraCliente", back_populates="imobiliarios")
    empreendimento = relationship("CarteiraImobiliarioEmpreendimento", back_populates="posicoes")
    estrategia = relationship("CarteiraEstrategia", back_populates="posicoes_imobiliarios")


# ─────────────────────────────────────────────────────────────────
# 4. FUNDOS
# ─────────────────────────────────────────────────────────────────

class CarteiraFundoReferencia(Base):
    """Referência reutilizável (um fundo = múltiplos clientes)"""
    __tablename__ = 'carteira_fundo_referencia'
    
    id = Column(Integer, primary_key=True)
    nome_fundo = Column(String(255), unique=True, nullable=False)
    cnpj_fundo = Column(String(20), nullable=True)  # IMPORTANTE: Filtro
    gestora = Column(String(255), nullable=True)
    administradora = Column(String(255), nullable=True)
    tipo_fundo = Column(String(50))  # "FIDC", "FIA", "FII", "Multimercado"
    indexador = Column(String(100))  # "CDI", "IPCA", "Renda Variável", "Misto"
    percentual_esperado = Column(Float, nullable=True)  # % a.a.
    data_constituicao = Column(Date, nullable=True)
    data_criacao = Column(DateTime, default=datetime.now)
    ativo = Column(Boolean, default=True)
    observacoes = Column(Text, nullable=True)
    
    # Relacionamentos
    posicoes = relationship("CarteiraFundoPosicao", back_populates="fundo")


class CarteiraFundoPosicao(Base):
    """Posição específica de um cliente em um fundo"""
    __tablename__ = 'carteira_fundo_posicao'
    
    id = Column(Integer, primary_key=True)
    cliente_id = Column(Integer, ForeignKey('carteira_cliente.id'), nullable=False)
    fundo_id = Column(Integer, ForeignKey('carteira_fundo_referencia.id'), nullable=False)
    
    numero_conta = Column(String(100), nullable=True)  # ID bancária/custodia
    
    # Aplicação
    data_aplicacao = Column(Date, nullable=False)
    valor_aplicado = Column(Float, nullable=False)
    quantidade_cotas = Column(Float, nullable=True)
    valor_cota_inicial = Column(Float, nullable=True)
    
    # Posição Atual
    data_base_valor_atual = Column(Date, nullable=True)
    valor_cota_atual = Column(Float, nullable=True)
    valor_atual_estimado = Column(Float, nullable=True)
    variacao_percentual = Column(Float, nullable=True)  # Automático
    variacao_valor_absoluto = Column(Float, nullable=True)  # Automático
    
    # Projeção de Retorno
    projecao_retorno_percentual = Column(Float, default=0.0)  # -x% a +x%
    
    # Direito de Recompra
    tem_direito_recompra = Column(Boolean, default=False)
    promessa_recompra = Column(String(100), nullable=True)  # "CDI", "CDI+2%", etc.
    data_vencimento_recompra = Column(Date, nullable=True)
    valor_base_recompra = Column(Float, nullable=True)
    status_recompra = Column(String(50), default='Aguardando')  # Aguardando, Exercido, Expirado
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


# ─────────────────────────────────────────────────────────────────
# 5. ESTRATÉGIA (Reutilizável)
# ─────────────────────────────────────────────────────────────────

class CarteiraEstrategia(Base):
    """Estratégia reutilizável entre clientes"""
    __tablename__ = 'carteira_estrategia'
    
    id = Column(Integer, primary_key=True)
    nome = Column(String(255), nullable=False, unique=True)  # "Debentures RH + Resgate Solicitado"
    descricao = Column(Text, nullable=True)  # Descrição longa
    criada_por = Column(Integer, nullable=True)  # FK para usuario
    data_criacao = Column(DateTime, default=datetime.now)
    publico = Column(Boolean, default=True)  # Aparece no combobox
    alocacao_recomendada = Column(JSON, default=dict)  # { "debentures": {...}, "fundos": {...}, "imobiliario": {...} }
    usuarios_count = Column(Integer, default=0)  # Quantos clientes usam
    ativo = Column(Boolean, default=True)
    
    # Relacionamentos
    posicoes_debentures = relationship("CarteiraDebenturePosicao", back_populates="estrategia")
    posicoes_imobiliarios = relationship("CarteiraImobiliarioPosicao", back_populates="estrategia")
    posicoes_fundos = relationship("CarteiraFundoPosicao", back_populates="estrategia")


# ─────────────────────────────────────────────────────────────────
# 6. AUXILIARES
# ─────────────────────────────────────────────────────────────────

class CarteiraSocioAval(Base):
    """Avalistas de Sócios (para Debêntures)"""
    __tablename__ = 'carteira_socio_aval'
    
    id = Column(Integer, primary_key=True)
    nome_socio = Column(String(255), nullable=False)
    percentual_participacao = Column(Float, nullable=True)
    ativo = Column(Boolean, default=True)
    observacoes = Column(Text, nullable=True)


class CarteiraUploadDocumento(Base):
    """Rastreamento de uploads de documentos"""
    __tablename__ = 'carteira_upload_documento'
    
    id = Column(Integer, primary_key=True)
    tipo_ativo = Column(String(50))  # "debenture", "imobiliario", "fundo"
    posicao_id = Column(Integer, nullable=True)  # FK flexível (pode ser de qualquer tabela)
    nome_arquivo = Column(String(500), nullable=False)
    tipo_documento = Column(String(100))  # "Emissão", "Termo Securitização", "Contrato", etc.
    url_gd = Column(String(500), nullable=True)  # Google Drive URL
    ia_processada = Column(Boolean, default=False)
    dados_extraidos = Column(JSON, default=dict)  # {"cautela": "1954", "serie": "BRMAPEX120", ...}
    data_upload = Column(DateTime, default=datetime.now)
    data_processamento_ia = Column(DateTime, nullable=True)
```

---

## SEGUINTE: API Endpoints (FastAPI)

Estrutura que será criada em `backend/app/routers/carteira.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

router = APIRouter(prefix="/api/carteira", tags=["carteira"])

# ─ CLIENTES ─
@router.get("/clientes")
def listar_clientes(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    pass

@router.post("/clientes")
def criar_cliente(data: dict, db: Session = Depends(get_db)):
    pass

@router.get("/clientes/{id}")
def obter_cliente(id: int, db: Session = Depends(get_db)):
    pass

# ─ DEBÊNTURES ─
@router.get("/debentures")
def listar_debentures(
    cliente_id: Optional[int] = None,
    serie: Optional[str] = None,
    status_resgate: Optional[str] = None,
    db: Session = Depends(get_db)
):
    pass

@router.post("/debentures")
def criar_debenture(data: dict, db: Session = Depends(get_db)):
    pass

@router.get("/debentures/{id}")
def obter_debenture(id: int, db: Session = Depends(get_db)):
    pass

@router.put("/debentures/{id}")
def atualizar_debenture(id: int, data: dict, db: Session = Depends(get_db)):
    pass

# ─ EMISSÕES (Referência) ─
@router.get("/emissoes")
def listar_emissoes(db: Session = Depends(get_db)):
    pass

@router.post("/emissoes")
def criar_emissao(data: dict, db: Session = Depends(get_db)):
    pass

# ─ IMOBILIÁRIO ─
@router.get("/imobiliario")
def listar_imobiliario(
    cliente_id: Optional[int] = None,
    tipo_desenvolvimento: Optional[str] = None,
    db: Session = Depends(get_db)
):
    pass

@router.post("/imobiliario")
def criar_imobiliario(data: dict, db: Session = Depends(get_db)):
    pass

# ─ EMPREENDIMENTOS (Referência) ─
@router.get("/empreendimentos")
def listar_empreendimentos(db: Session = Depends(get_db)):
    pass

# ─ FUNDOS ─
@router.get("/fundos")
def listar_fundos(
    cliente_id: Optional[int] = None,
    gestora: Optional[str] = None,
    cnpj_fundo: Optional[str] = None,
    db: Session = Depends(get_db)
):
    pass

@router.post("/fundos")
def criar_fundo(data: dict, db: Session = Depends(get_db)):
    pass

# ─ ESTRATÉGIAS ─
@router.get("/estrategias")
def listar_estrategias(publico: bool = True, db: Session = Depends(get_db)):
    pass

@router.post("/estrategias")
def criar_estrategia(data: dict, db: Session = Depends(get_db)):
    pass

@router.get("/estrategias/busca")
def buscar_estrategia(termo: str, db: Session = Depends(get_db)):
    pass

# ─ UPLOAD DE DOCUMENTOS COM IA ─
@router.post("/upload-documento")
async def upload_documento(
    tipo_ativo: str,
    posicao_id: int,
    file: UploadFile,
    db: Session = Depends(get_db)
):
    pass  # Será processado por IA (Claude Vision)

# ─ DASHBOARD ─
@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    # Retorna KPIs: # clientes, pro-labore total, carteira $, expectativa honorários
    pass

# ─ RELATÓRIOS ─
@router.get("/cliente/{id}/pdf")
def gerar_pdf_cliente(id: int, db: Session = Depends(get_db)):
    # Gera PDF consolidado do cliente
    pass

@router.post("/exportar-qualificacao")
def exportar_qualificacao(
    cliente_ids: List[int],
    formato: str = "xlsx",  # xlsx ou pdf
    db: Session = Depends(get_db)
):
    pass
```

---

## FRONTEND (Opção 2: Tabela)

**Arquivos a criar**:
- `frontend/src/pages/Carteira/index.tsx` (Dashboard)
- `frontend/src/pages/Carteira/Debentures.tsx` (Tabela + Formulário)
- `frontend/src/pages/Carteira/Imobiliario.tsx` (Tabela + Formulário)
- `frontend/src/pages/Carteira/Fundos.tsx` (Tabela + Formulário)
- `frontend/src/components/CarteiraTabela.tsx` (Componente reutilizável)
- `frontend/src/api/carteira.ts` (Cliente API)

---

## SEED DE DADOS

**Arquivo**: `backend/app/scripts/seed_carteira.py`

```python
import pandas as pd
from sqlalchemy.orm import Session

def seed_planilha_apex(db: Session):
    """Importa dados da planilha APEX"""
    
    # 1. Ler Consolidado → criar CarteiraCiente + posições
    df_consolidado = pd.read_excel("path/to/Distribuicao Carteira_Investidores_APEX .xlsx", sheet_name="Consolidado")
    
    for _, row in df_consolidado.iterrows():
        # Criar cliente se não existir
        # Criar posição (debenture, imobiliário ou fundo)
        pass
    
    # 2. Ler Matriz Cautelas x Emissões → criar CarteiraDebentureadotEmissao
    df_matriz = pd.read_excel(..., sheet_name="Matriz Cautelas x Emissões")
    
    # 3. Ler Relacao ABM -- Empreendimento → criar CarteiraImobiliarioEmpreendimento
    df_abm = pd.read_excel(..., sheet_name="Relacao ABM -- Empreendimento")
    
    db.commit()
    print("✅ Seed concluído!")
```

**Executar**: 
```bash
python backend/app/scripts/seed_carteira.py
```

---

## CHECKLIST DE HOJE

- [ ] 1. Models SQLAlchemy criados e migração executada
- [ ] 2. Endpoints FastAPI implementados (CRUD básico)
- [ ] 3. Seed de dados executado (planilha importada)
- [ ] 4. Frontend: Tabelas + Formulários para Debêntures
- [ ] 5. Frontend: Tabelas + Formulários para Imobiliário
- [ ] 6. Frontend: Tabelas + Formulários para Fundos
- [ ] 7. Filtros funcionando (série, tipo, gestora, vencimento, etc.)
- [ ] 8. Drive integration (criar pastas, linker)
- [ ] 9. IA Upload (Claude Vision para leitura de documentos)
- [ ] 10. Dashboard com KPIs
- [ ] 11. PDF por cliente + Exportação
- [ ] 12. Testes básicos

---

## COMEÇANDO AGORA

Vou iniciar no backend (Models + API), depois frontend. Ordem:

1. **Backend Models** → `carteira.py`
2. **Alembic Migration** → versionar DB
3. **Seed de Dados** → importar planilha
4. **API Endpoints** → CRUD básico
5. **Frontend** → Tabelas + Formulários
6. **IA + Drive** → Integrações
7. **Polimentos** → Dashboard, PDFs, Filtros

**ETA**: Tudo pronto hoje! 🚀

