# ANÁLISE COMPLETA - PLANILHA CARTEIRA APEX 📊

**Data**: 2026-09-30  
**Fonte**: `Distribuicao Carteira_Investidores_APEX.xlsx`  
**Objetivo**: Mapear estrutura de dados + definir parâmetros para novo módulo de Carteira no GestorJuridico

---

## 1. VISÃO GERAL DA PLANILHA

### 1.1 Estrutura de Dados
- **10 abas** cobrindo diferentes dimensões da carteira
- **1.051 registros** de posições individuais (aba Consolidado)
- **67 investidores únicos**
- **Período de análise**: Julho/Agosto/2026 (com histórico desde 2020)

### 1.2 Abas Disponíveis

| Aba | Linhas | Propósito |
|-----|--------|----------|
| **Consolidado** | 1.051 | Visão mestrada: todas as posições + dados de contrato, resgate, observações |
| **Carbyne - Apex** | 1.000 | Investimentos em fundos Carbyne, segmentado por investidor |
| **Rhino, Ações e Sem Extrato** | 1.000 | Debêntures Rhino (securitizadas) + Ações + registros sem extrato |
| **CARBYNE-APEX** | 1.002 | Versão simplificada Carbyne/Apex com percentuais de rentabilidade |
| **RhinoAções e Sem Extrato** | 1.002 | Detalhes de debêntures Rhino com datas de vencimento |
| **Imobiliario** | 1.000 | Investimentos imobiliários por cliente |
| **Relacao ABM -- Empreendimento** | 31 | Lookup: ABM ↔ Tipo de Empreendimento (referência cruzada) |
| **Aportes — Debêntures** | 1.000 | Histórico de aportes em debêntures Rhino |
| **Clientes Únicos** | 56 | Lista mestrada de investidores |
| **Matriz Cautelas x Emissões** | 100 | Cruzamento cautelas ↔ emissões de títulos |

---

## 2. MAPEAMENTO DE ATIVOS

### 2.1 ATIVOS FINANCEIROS vs. IMOBILIÁRIOS

#### 🏦 ATIVOS FINANCEIROS (Fund-based + Renda Fixa)

**Característica principal**: Liquidez variável, rentabilidade periódica, gestão por terceiros

##### **CARBYNE** (5 tipos de fundos)
- **BRM Carbyne Crédito Estruturado FIC FIDC**
  - Tipo: Fundo de Investimento em Direitos Creditórios
  - Risco: ALTO (quedas 33-71% mês a mês)
  - Exemplo: Cliente A aplicou R$ 69.735,01 em maio/26, valor caiu para R$ 21.200,47 em ago/26 (-70%)
  
- **Carbyne Mercados Privados FC FI Mult CP**
  - Tipo: Fundo de Investimento Multimercado
  - Risco: MÉDIO (variações -2% a +5%)
  - Rentabilidade: Mais estável que FIDC, com histórico desde 2023
  
- **Carbyne Cred Priv FI Mult**
  - Crédito privado diversificado
  - Risco: ALTO (quedas até 33%)
  
- **BRM Carbyne Voyage FIA**
  - Tipo: Fundo de Investimento em Ações
  - Risco: MÉDIO (variações -30% a +7%)
  - Rentabilidade anual: +30% (em alguns períodos)

##### **RHINO** (Debêntures Securitizadas)
- **Séries BRMAPEX (110%, 115%, 120%, 140%)**
  - Tipo: Debêntures com garantia de securitização de fluxo imobiliário
  - Indexação: CDI, IPCA+juros fixos (11,5% a.a.)
  - Vencimento: 2027-2030 (conforme série)
  - Resgate: D+1 a D+90 pós-vencimento
  - Carência: 3-12 meses
  - Rentabilidade: Mais previsível, com rendimentos mensais (juros)

##### **APEX** (FII - Fundos Imobiliários Líquidos)
- **FII Apex MS CI ER (APXM11)**
  - Tipo: Fundo Imobiliário de Investimento (ações)
  - Cotação: ~R$ 41,99/cota
  - Volatilidade: Alta (perdas até -32% ao mês)
  - Exemplo: Cliente investiu R$ 317.000, posição caiu para R$ 210.500 (-33%)

##### **AÇÕES**
- Posições avulsas em ações ordinárias/preferenciais
- Exemplo: Apex Partners Gestão (4.484 ações ordinárias)

---

#### 🏢 ATIVOS IMOBILIÁRIOS (Propriedade Real)

**Característica principal**: Iliquidez, rendimento diferido (aluguel), valorização patrimonial, gestão ativa

##### **Tipos de Empreendimento** (conforme abra Imobiliário)

1. **Desenvolvimento Residencial**
   - Exemplo: Showa (R$ 417.496 a R$ 2.050.933)
   - Status: Ativo, sem extrato mensal (fluxo por milestones)
   - Perspectiva: Retorno ao fim da obra

2. **Aquisição de Terrenos**
   - Exemplo: Fazenda Atalaia (R$ 300.000)
   - Estágio: Adquisição, não gera fluxo até desenvolvimento

3. **Desenvolvimento de Condomínios Logísticos**
   - Similar a residencial, mas para uso comercial

4. **Desenvolvimento de Escritórios**
   - Empreendimento de renda comercial

5. **Satelização** (passthrough structures)
   - Exemplo: Satélite Showa x Realty ES (R$ 6.088,48)
   - Tipo: Condomínio satélite que recebe automaticamente do principal

---

### 2.2 DIFERENÇAS ESTRUTURAIS

| Aspecto | Financeiro (Fundos/Debêntures) | Imobiliário |
|---------|--------------------------------|------------|
| **Entrada de Recurso** | Aportes diretos ao fundo | Investimento em desenvolvimento |
| **Fluxo de Retorno** | Mensal/trimestral (cotas, juros) | Diferido (ao término da obra) |
| **Liquidez** | ALTA (resgate D+1 a D+30) | MUITO BAIXA (venda de quota rara) |
| **Rentabilidade** | Periódica, com relatório mensal | Ao final (ganho de capital + aluguel) |
| **Risco** | Volatilidade de mercado | Risco operacional/atraso de obra |
| **Tributação** | IR sobre ganho de capital + IRRF | IR diferido até saída |
| **Monitoramento** | Extrato mensal + comunicados | Relatórios de andamento |

---

## 3. CATEGORIAS DINÂMICAS (para filtros + busca)

### 3.1 Dimensão 1: TIPO DE ATIVO
```
├── Fundo de Investimento
│   ├── FIDC (Crédito Estruturado)
│   ├── Fundo Multimercado
│   ├── FIA (Ações)
│   └── FII (Imobiliário Líquido)
├── Renda Fixa
│   ├── Debênture Securitizada
│   ├── Debênture Simples
│   └── Títulos Privados
├── Ações
│   ├── Ordinária
│   ├── Preferencial
│   └── Cota de Fundo
└── Imóvel/Empreendimento
    ├── Desenvolvimento Residencial
    ├── Escritórios Comerciais
    ├── Condomínios Logísticos
    └── Terreno
```

### 3.2 Dimensão 2: GESTOR/ESTRUTURADOR
```
├── CARBYNE (gestora)
├── RHINO (securitizadora)
├── APEX (gestora / FII)
└── OUTROS (diretos/parcerias)
```

### 3.3 Dimensão 3: PERFORMANCE/RISCO
```
├── Performance (período)
│   ├── Alta Volatilidade (-70% a +30%)
│   ├── Média Volatilidade (-5% a +10%)
│   └── Baixa Volatilidade (-2% a +3%)
└── Risco Embutido
    ├── Estruturado (com garantia)
    ├── Crédito (dependente de fluxo)
    └── Mercado (cotação aberta)
```

### 3.4 Dimensão 4: STATUS DE CONTRATO
```
├── Ativo
├── Em Resgate
│   ├── Resgate Solicitado (data)
│   ├── Resgate Negado (com liminar)
│   └── Em Processamento
├── Vencido (mas com resgate pendente)
└── Liquidado
```

### 3.5 Dimensão 5: PERÍODO DE REFERÊNCIA
```
Mês/Ano: Julho/2026, Agosto/2026, etc.
(dinâmico: últimos 25 meses na planilha original)
```

---

## 4. ESTRUTURA DE DADOS PARA CADASTRO

### 4.1 Entidade: INVESTIDOR

```python
{
    "investidor_id": "PK",
    "nome_completo": str,
    "tipo": "PF | PJ",  # Pessoa Física ou Jurídica
    "cpf_cnpj": str,
    "contato_email": str,
    "observacoes": str,  # p.ex., "conta conjunta com X", "cliente nova"
    "ativo": bool,
    "data_cadastro": date,
}
```

### 4.2 Entidade: POSIÇÃO DE ATIVO

```python
{
    "posicao_id": "PK",
    "investidor_id": "FK",
    "tipo_ativo": "Fundo | Debênture | Ação | Imóvel",
    
    # Identificação do Ativo
    "ativo_nome": str,  # "BRM Carbyne Crédito Estruturado FIC FIDC"
    "ativo_ticker": str,  # "APXM11" ou "-" se não aplicável
    "numero_conta_cautela": str,  # "001605364" ou "Cautela 1816"
    
    # Categorização
    "categoria": "Carbyne | Rhino | Apex | Ações | Imobiliário | Sem Extrato",
    "fundo_ou_estrutura": str,  # Referência ao fundo específico
    "tipo_empreendimento": str,  # Se imobiliário: "Desenvolvimento Residencial", etc.
    "gestor": str,  # "CARBYNE", "RHINO", "APEX", "OUTRO"
    
    # Financeiro da Aplicação
    "data_aplicacao": date,
    "valor_aplicado": decimal,  # R$ original
    
    # Termos de Contrato (se aplicável)
    "data_contratacao": date,
    "meses_carencia": int,
    "prazo_pgto_pos_resgate": str,  # "D+1", "D+30", "30 dias", etc.
    "data_vencimento": date,
    
    # Rentabilidade (período atual)
    "mes_referencia": date,
    "percentual_rentabilidade": decimal,  # % do período
    "valor_liquido": decimal,  # Saldo atual em R$
    
    # Status de Resgate
    "resgate_status": "Ativo | Solicitado | Negado | Processando | Liquidado",
    "data_pedido_resgate": date,  # Se solicitado
    "resposta_resgate": str,  # Documento/observação
    
    # Observações e Ações
    "observacoes": str,
    "notificar": bool,
    "acoes_pendentes": str,  # "Ajuizar direito de recompra"
}
```

### 4.3 Entidade: EVENTO DE POSIÇÃO (time-series)

```python
{
    "evento_id": "PK",
    "posicao_id": "FK",
    "mes_referencia": date,
    "percentual_variacao": decimal,  # % no período
    "valor_liquido": decimal,
    "rentabilidade_absoluta": decimal,  # R$ ganho/perdido
    "data_relatorio": date,
}
```

---

## 5. PARÂMETROS PARA O NOVO MENU CARTEIRA

### 5.1 Permissões de Entrada (Cadastro Manual)

- ✅ **Nome do Investidor** (obrigatório)
- ✅ **Tipo de Ativo** (dropdown: Fundo, Debênture, Ação, Imóvel)
- ✅ **Categoria** (dropdown: Carbyne, Rhino, Apex, Ações, Imobiliário, Outro)
- ✅ **Número de Conta / Cautela** (texto, admite "-" se sem número)
- ✅ **Data de Aplicação** (date picker)
- ✅ **Valor Aplicado** (currency)
- ✅ **Gestor/Estruturador** (dropdown + livre)
- ✅ **Fundo/Estrutura** (combobox com referência a lista de fundos conhecidos)
- ✅ **Tipo de Empreendimento** (se Imobiliário: dropdown de tipos)
- ✅ **Data de Vencimento** (date picker, opcional)
- ✅ **Observações** (textarea)

### 5.2 Campos Calculados / Automáticos

- 📊 **Valor Líquido Atual** (origem: extrato mais recente)
- 📊 **Rentabilidade %** (cálculo: (valor_líquido - valor_aplicado) / valor_aplicado)
- 📊 **Dias em Aplicação** (data hoje - data aplicação)
- 📊 **Rentabilidade Anualizada** (extrapolação)
- 📊 **Status de Carência** (se hoje < data_aplicacao + meses_carência)

### 5.3 Filtros Essenciais

1. **Por Investidor** (seleção única ou múltipla)
2. **Por Tipo de Ativo** (checkboxes: Fundo, Debênture, Ação, Imóvel)
3. **Por Categoria** (checkboxes: Carbyne, Rhino, Apex, Imobiliário)
4. **Por Status de Resgate** (Ativo, Solicitado, Negado, Liquidado)
5. **Por Período** (data início - data fim)
6. **Por Performance** (Perdas > 10%, Estável, Ganhos > 10%)
7. **Por Gestor** (dropdown: CARBYNE, RHINO, APEX, OUTRO)
8. **Por Vencimento** (próximos 3/6/12 meses, vencido)

### 5.4 Agregações e Visualizações

#### **Dashboard Principal**
```
┌─────────────────────────────────────────────────────┐
│ CARTEIRA - RESUMO POR INVESTIDOR                    │
├─────────────────────────────────────────────────────┤
│ Investidor: [seleção]                               │
│                                                     │
│ Total Investido:     R$ 2.589.735,00                │
│ Valor Atual:         R$ 1.892.450,00  (-27%)        │
│ Rentabilidade:       R$ -697.285,00   (período)     │
│                                                     │
│ Distribuição:                                       │
│   ├─ Carbyne:        R$ 892.450    [████░░ 47%]    │
│   ├─ Rhino:          R$ 600.000    [███░░░ 32%]    │
│   ├─ Apex:           R$ 250.000    [██░░░░ 13%]    │
│   └─ Imobiliário:    R$ 150.000    [█░░░░░  8%]    │
└─────────────────────────────────────────────────────┘
```

#### **Tabela de Posições**
```
| Ativo | Conta | Aplicado | Atual | Variação | Vencimento | Status |
|-------|-------|----------|-------|----------|------------|--------|
| BRM Carbyne FIDC | 001605364 | 69.735 | 21.200 | -70% | -- | ⚠️ Monitorar |
| Rhino BRMAPEX120 | Cautela 1954 | 200.000 | 205.815 | +2,9% | 28/04/28 | ✓ Ativo |
| Showa | -- | 417.496 | -- | -- | -- | 📋 Desenvolvimento |
```

#### **Estratégias Sugeridas**
```
Agrupamento por Objetivo:
├─ Renda (Fundos + Debêntures com fluxo periódico)
│  └─ Rhino: R$ 600.000 (juros mensais/trimestrais)
├─ Crescimento (Ações + Imobiliário)
│  └─ Apex: R$ 250.000
│  └─ Imobiliário: R$ 150.000
└─ Crédito Estruturado (risco específico)
   └─ Carbyne FIDC: R$ 892.450 (-70% ⚠️)
```

---

## 6. PONTOS DE INTEGRAÇÃO DINÂMICOS

### 6.1 Referências Cruzadas

- **Investidor ↔ Posições**: 1:N (um cliente, múltiplas posições)
- **Fundo ↔ Gestor**: N:1 (vários fundos, um gestor)
- **Empreendimento ↔ Tipo**: N:1 (vários clientes em uma obra, um tipo)
- **Cautela ↔ Emissão**: 1:1 (cada cautela é uma série específica)

### 6.2 Campos de Auditoria

- `data_cadastro` (quando a posição foi registrada no sistema)
- `data_ultima_atualizacao` (última sincronização com extrato)
- `usuario_cadastro` (responsável pelo lançamento)
- `fonte_dados` (Manual / Integração API / Upload Planilha)

### 6.3 Histórico de Rentabilidade

Manter tabela separada de eventos mensais:
```
posicao_id | mes | valor_liquido | rentabilidade_% | data_relatorio
001 | 2026-07 | 71.787,71 | 0.043 | 31/07/26
001 | 2026-08 | 21.200,47 | 0.0136 | 31/08/26
```

---

## 7. FUNCIONALIDADES DO NOVO MENU

### **Aba: CARTEIRA**

#### 📍 Seção 1: Nova Posição (Cadastro)
- Botão "+ Nova Posição"
- Formulário inline com validação
- Auto-complete para investidor + fundo
- Preview: "Adicionando R$ 100.000 em [Fundo] para [Investidor]"

#### 📍 Seção 2: Minhas Posições (Listagem)
- Tabela com filtros sticky (top)
- Colunas: Investidor, Ativo, Valor Aplicado, Valor Atual, Variação %, Vencimento, Ações
- Ações por linha: Editar, Ver Detalhes, Atualizar Extrato, Solicitar Resgate

#### 📍 Seção 3: Dashboard de Carteira
- Gráfico de pizza: Distribuição por categoria
- Gráfico de linha: Evolução mensal (últimos 12 meses)
- Cards: Total Investido, Valor Atual, Rentabilidade Acumulada, Rentabilidade Anualizada
- KPIs de risco: Posições em vermelho (perdas > 10%)

#### 📍 Seção 4: Estratégias & Alertas
- Sugestões automáticas: "Rebalancear: Carbyne acumula -70%"
- Alertas de vencimento: "3 posições vencem nos próximos 90 dias"
- Notificações de resgate: "Seu resgate foi processado em [ativo]"

#### 📍 Seção 5: Relatórios & Exportação
- Botões: Exportar XLS, Gerar PDF, Enviar por Email
- Filtros avançados para relatórios customizados

---

## 8. BANCO DE DADOS - SCHEMA INICIAL

### **Tabelas SQL**

```sql
-- Investidores (Clientes)
CREATE TABLE carteira_investidor (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(255) NOT NULL,
    tipo VARCHAR(2) CHECK (tipo IN ('PF', 'PJ')),
    cpf_cnpj VARCHAR(20) UNIQUE,
    email VARCHAR(255),
    observacoes TEXT,
    ativo BOOLEAN DEFAULT true,
    data_cadastro TIMESTAMP DEFAULT NOW(),
    usuario_id INTEGER -- FK para usuario
);

-- Ativos Base (Referência)
CREATE TABLE carteira_ativo_referencia (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(255) UNIQUE NOT NULL,
    tipo VARCHAR(50) -- "Fundo", "Debênture", "Ação", "Empreendimento"
    categoria VARCHAR(50), -- "Carbyne", "Rhino", "Apex", etc.
    gestor VARCHAR(100),
    ticker VARCHAR(20),
    descricao TEXT
);

-- Posições (Investimentos)
CREATE TABLE carteira_posicao (
    id SERIAL PRIMARY KEY,
    investidor_id INTEGER NOT NULL REFERENCES carteira_investidor(id),
    ativo_id INTEGER REFERENCES carteira_ativo_referencia(id),
    
    -- Identificação
    numero_conta_cautela VARCHAR(50),
    
    -- Aplicação
    data_aplicacao DATE,
    valor_aplicado DECIMAL(15,2),
    
    -- Contrato
    data_contratacao DATE,
    meses_carencia INTEGER,
    prazo_pgto_pos_resgate VARCHAR(100),
    data_vencimento DATE,
    
    -- Status
    status VARCHAR(50) CHECK (status IN ('Ativa', 'Resgate Solicitado', 'Negado', 'Liquidada')),
    
    -- Resgate
    data_pedido_resgate DATE,
    resposta_resgate TEXT,
    
    -- Auditoria
    observacoes TEXT,
    notificar BOOLEAN DEFAULT false,
    data_criacao TIMESTAMP DEFAULT NOW(),
    data_atualizacao TIMESTAMP DEFAULT NOW()
);

-- Histórico de Rentabilidade (Time-Series)
CREATE TABLE carteira_rentabilidade_mensal (
    id SERIAL PRIMARY KEY,
    posicao_id INTEGER NOT NULL REFERENCES carteira_posicao(id),
    mes_referencia DATE,
    valor_liquido DECIMAL(15,2),
    percentual_variacao DECIMAL(6,2), -- %
    rentabilidade_absoluta DECIMAL(15,2), -- R$
    data_relatorio DATE,
    UNIQUE(posicao_id, mes_referencia)
);

-- Matriz de Empreendimentos (para imobiliário)
CREATE TABLE carteira_empreendimento (
    id SERIAL PRIMARY KEY,
    nome VARCHAR(255) UNIQUE NOT NULL,
    tipo_desenvolvimento VARCHAR(100), -- "Residencial", "Comercial", etc.
    descricao TEXT,
    localizacao VARCHAR(255),
    status VARCHAR(50), -- "Planejamento", "Construção", "Finalizado"
);
```

---

## 9. PRÓXIMOS PASSOS

### **Fase 1: Estrutura Base** (semana 1)
1. ✅ Mapear schema SQL (já feito aqui)
2. ⏳ Criar models SQLAlchemy
3. ⏳ Criar endpoints FastAPI (CRUD)
4. ⏳ Criar componentes React básicos

### **Fase 2: Cadastro Manual** (semana 2)
1. Formulário de nova posição
2. Validações
3. Upload em batch (planilha → DB)
4. Auto-complete de investidores + fundos

### **Fase 3: Visualizações** (semana 3)
1. Dashboard com gráficos
2. Tabela com filtros avançados
3. Relatórios

### **Fase 4: Inteligência** (semana 4)
1. Alertas automáticos
2. Sugestões de rebalanceamento
3. Análise de performance vs. benchmark

---

## 10. ARQUIVO PARA REFERÊNCIA

Todos os dados estão na planilha original. **Manter sincronizado**: quando novos fundos/empreendimentos aparecerem na planilha, atualizar a tabela `carteira_ativo_referencia`.

