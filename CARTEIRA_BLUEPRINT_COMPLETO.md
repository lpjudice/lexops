# 📊 BLUEPRINT COMPLETO - MÓDULO CARTEIRA/PATRIMÔNIO

**Status**: Proposta para validação  
**Data**: 2026-09-30  
**Versão**: 1.0 (Layout + Tabela)

---

## SUMÁRIO EXECUTIVO

### O que você quer fazer?
Um módulo único de gestão de **PATRIMÔNIO DE CLIENTES** que organize:
- **Debêntures** (Rhino + outras securitizadoras)
- **Imobiliário** (Empreendimentos via SPE/ABMPARSE)
- **Fundos** (Carbyne, Apex, etc.)
- **Subcategorias**: Direito de Recompra, Ações Apex

### Princípios de design
✅ **Uma única tabela/interface** por tipo de ativo (não 3 menus separados)  
✅ **Dados pré-preenchidos** de referência (Emissões, Empreendimentos, Gestoras)  
✅ **Upload IA** para auto-completar documentos  
✅ **Reutilização de dados** (uma emissão = múltiplos clientes com mesmo dado)  
✅ **Links dinâmicos** com Clientes, Contratos, Processos, Drive  
✅ **Estratégias reutilizáveis** (salva 1, aplica a N clientes)  

---

## PARTE 1: DEBÊNTURES/SECURITIZADAS

### 1.1 Visão Geral
**Tipo de Ativo**: Renda Fixa com fluxo periódico  
**Gestor Principal**: Rhino Securitizadora (e outros)  
**Dados Base**: Planilha "Matriz Cautelas x Emissões"  

### 1.2 Estrutura de Dados — EMISSÃO (Referência, Reutilizável)

Tabela: `carteira_debenture_emissao`

```
id_emissao [PK]
├─ nome_serie                  "BRMAPEX110", "BRMAPEX115", "BRMAPEX120"
├─ numero_emissao              1, 2, 3...
├─ emissor                      "Rhino Securitizadora S/A"
├─ cnpj_emissor                 "XX.XXX.XXX/0001-XX"
├─ indexador                    "CDI", "IPCA"
├─ taxa_adicional               11.5% a.a. (IPCA+11,5%), "140% CDI"
├─ data_inicio_emissao          date
├─ data_vencimento_previsto     date
├─ prazo_carencia_meses         integer (3, 6, 12, "Sem carência")
├─ prazo_pgto_pos_resgate       "D+1", "D+30", "D+90", "1 dia útil"
├─ resgate_antecipado_contrato  boolean (sim/não - conforme contrato)
├─ resgate_antecipado_securit   boolean (sim/não - conforme termo de securitização)
├─ promessa_recompra_contrario  string ("CDI", "CDI+2%", null)
├─ tipos_garantia              [ARRAY] "Fluxo Imobiliário", "Aval Sócios", "FIDC", etc.
└─ observacoes_gerais          text (limitações, especificidades)
```

**Exemplo real**:
```
Serie: BRMAPEX120
Numero: 1
Emissor: Rhino Securitizadora
Indexador: CDI + 40%
Data Vencimento: 2028-05-02
Carência: 12 meses
Resgate Antecipado (Contrato): SIM (30 dias + D+1)
Resgate Antecipado (Securitização): SIM (mesmos termos)
Garantias: Fluxo Imobiliário Showa, Aval Lucas Judice + Sócios APEX
```

### 1.3 Estrutura de Dados — POSIÇÃO DO CLIENTE (Específica, 1:1 por Cliente+Cautela)

Tabela: `carteira_debenture_posicao`

```
id_posicao [PK]
├─ cliente_id [FK → carteira_cliente]
├─ emissao_id [FK → carteira_debenture_emissao]  # PRÉ-PREENCHIDA quando seleciona série
├─ numero_cautela              "1816", "1562", "2108"  [OBRIGATÓRIO]
├─ numero_debentures           integer (quantidade de debêntures, ex: 200, 500)
├─ valor_aplicado              R$ (calculado: qtd × valor_nominal)
├─ data_aquisicao              date [OBRIGATÓRIO]
├─ data_base_valor_atual       date
├─ valor_atual_estimado        R$ (informado manualmente ou via integração)
├─ variacao_percentual         % (automático: (valor_atual - valor_aplicado) / valor_aplicado)
├─ status_resgate              "Ativo", "Solicitado", "Negado", "Processando", "Liquidado"
├─ data_pedido_resgate         date (se status ≠ Ativo)
├─ resposta_rhino              text ("Negado em 09/09/26 (liminar cautelar)", etc.)
├─ foi_pago                    boolean
├─ valor_pago                  R$ (se foi_pago = true)
├─ data_pagamento              date
├─ aval_socios                 [ARRAY FK → carteira_socio_aval] (múltiplos)
├─ processos_judiciais         [ARRAY FK → processo] (linker com Processos)
├─ estrategia_id               [FK → carteira_estrategia] (opcional, reutilizável)
├─ honorarios_aplica           boolean (se faz parte dos honorários)
├─ observacoes                 text
├─ notificado                  boolean
├─ folder_drive_id             string (Google Drive folder ID)
└─ data_criacao                timestamp
```

### 1.4 Tabelas Auxiliares

#### A) `carteira_socio_aval` (Referência de Avalistas)
```
id [PK]
├─ nome_socio                  "Lucas Judice", "Outro Sócio APEX"
├─ percentual_aval             % (em relação ao patrimônio da debenture)
└─ ativo                       boolean
```

#### B) `carteira_debenture_garantia` (Tipos de Garantia - Reutilizável por Emissão)
```
id [PK]
├─ emissao_id [FK]
├─ tipo_garantia               "Fluxo Imobiliário Showa", "Aval Sócios", "Securitização FIDC", etc.
├─ descricao                   text
└─ valor_ou_percentual         $ ou %
```

### 1.5 Campos de Upload & IA

**Upload de Arquivos por Cliente**:
- Contrato de emissão
- Termo de securitização
- Demonstrativo de saldo mensal
- Pedido de resgate (se aplicável)
- Resposta da Rhino
- Comprovante de pagamento

**IA Auto-preenchimento**:
Quando usuário faz upload, IA lê e extrai:
- Número da cautela
- Série/emissão
- Número de emissão
- Valor nominal
- Datas (aquisição, vencimento, carência)
- Termos de resgate
- Garantias

**Fluxo**:
1. Usuário seleciona "Upload de Documentação"
2. Faz upload de 1+ arquivos (PDF/imagens)
3. IA processa e preenche campos automaticamente
4. Usuário valida e salva

---

## PARTE 2: IMOBILIÁRIO

### 2.1 Visão Geral
**Tipo de Ativo**: Investimento em desenvolvimento imobiliário  
**Estrutura Complexa**: Cliente → SCP → ABM-PARSE/SPE → Empreendimento → Obra  
**Dados Base**: Planilha "Relacao ABM -- Empreendimento"  

### 2.2 Estrutura de Dados — EMPREENDIMENTO (Referência, Reutilizável)

Tabela: `carteira_imobiliario_empreendimento`

```
id_empreendimento [PK]
├─ nome_venda                  "Showa", "Fazenda Atalaia", "Apex Log Pitanga"
├─ nome_razao_social           "Empreendimento XYZ SPE S/A"
├─ cnpj_empreendimento         "XX.XXX.XXX/0001-XX"
├─ tipo_desenvolvimento        "Desenvolvimento Residencial", "Condomínio Logístico", "Escritórios"
├─ localizacao                 "Espírito Santo", "Minas Gerais"
├─ abmparse_veiculo            "ABMPARSE 01", "ABMPARSE 02", "ABMPARSE 20"  [MATCH com planilha]
├─ data_inicio_previsto        date
├─ data_conclusao_prevista     date
├─ valor_total_empreendimento  R$ (orçamento da obra)
├─ descricao                   text
└─ ativo                       boolean
```

**Exemplo real do matching**:
```
Nome Venda: Showa
Nome Razão Social: Showa Participações SPE S/A
CNPJ: XX.XXX.XXX/0001-XX
ABM-PARSE Veículo: ABMPARSE 01
Tipo: Desenvolvimento Residencial
Localização: Espírito Santo
```

### 2.3 Estrutura de Dados — POSIÇÃO DO CLIENTE (Específica, Multi-Layer)

Tabela: `carteira_imobiliario_posicao`

```
id_posicao [PK]
├─ cliente_id [FK → carteira_cliente]
├─ empreendimento_id [FK → carteira_imobiliario_empreendimento]
│
├─ INFORMAÇÕES DE PARTES
├─ partes_interessadas         [ARRAY text] (ex: "Lucas Judice", "Cônjuge", "PJ XYZ")
├─ percentual_participacao     % (ex: 50%, 100%)
│
├─ VALORES
├─ valor_total_compromissado   R$ (quanto foi prometido investir no total)
├─ valor_efetivamente_investido R$ (quanto já foi aportado)
├─ data_base_valores           date
├─ valor_esperado_retorno      R$ (projeção de ganho final)
├─ percentual_esperado_retorno % a.a. (ou no período)
│
├─ ESTRUTURA DE INVESTIMENTO (Multi-Layer)
├─ veiculo_abmparse_primario   "ABMPARSE 01"  [da tabela de Empreendimento]
├─ veiculo_abmparse_secundario "ABMPARSE 02"  (opcional, se houver 2 camadas)
├─ veiculo_abmparse_terciario  "ABMPARSE 03"  (opcional, se houver 3 camadas)
├─ spe_principal_id            [FK → carteira_imobiliario_spe]
├─ percentual_na_spe           % (ex: Lucas participa de 50% da ABMPARSE 01)
│
├─ SCP (Sociedade em Conta de Participação)
├─ scp_numero                  "SCP 001/2024", "SCP 002/2024"
├─ scp_contrato_link           [FK → contrato] (opcional, linker com Contratos)
├─ scp_data_constituicao       date
├─ partes_na_scp               [ARRAY] {nome, %, data_adesao}
├─ representante_scp           "Lucas Judice" (quem assina)
│
├─ CAMADA SUPERIOR
├─ prestadora_servicos         "Apex Realty"  (pré-preenchido, alterável)
├─ cnpj_prestadora             "XX.XXX.XXX/0001-XX"
├─ %_servico_prestadora        % (ex: 5% sobre valor retorno)
├─ taxa_performance            % (ex: 2% se meta atingida)
│
├─ APORTES
├─ data_primeiro_aporte        date
├─ data_ultimo_aporte          date
├─ quantidade_aportes          integer
├─ historico_aportes           [ARRAY] {data, valor}  (opcional, para tracking)
│
├─ HONORÁRIOS
├─ faz_parte_honorarios        boolean (flag com confirmação de desmarcação)
├─ percentual_sucesso_honorario % (ex: 15% se obra lucrar)
├─ observacao_honorarios       text
│
├─ DOCUMENTAÇÃO
├─ estrategia_id               [FK → carteira_estrategia]
├─ folder_drive_id             string
├─ processos_judiciais         [ARRAY FK → processo]
└─ observacoes                 text
```

### 2.4 Tabela Auxiliar: SPE

Tabela: `carteira_imobiliario_spe`

```
id_spe [PK]
├─ nome                        "SPE Showa Participações"
├─ cnpj                        "XX.XXX.XXX/0001-XX"
├─ abmparse_vinculado          "ABMPARSE 01"  (relação 1:1)
├─ empreendimento_id           [FK]
└─ ativo                       boolean
```

### 2.5 Campos de Upload & IA

**Upload de Contrato Imobiliário**:
- Contrato de participação
- Aditivos
- Demonstrativo de obra (fotos, relatório)
- Comprovante de aporte

**IA Auto-preenchimento do Contrato**:
- Contratantes (partes)
- Valor investido
- Valor esperado de retorno
- % de serviço da prestadora
- Taxa de performance
- Datas chaves (assinatura, first/last aporte)

---

## PARTE 3: FUNDOS (Financeiros)

### 3.1 Visão Geral
**Tipo de Ativo**: Renda Variável + Renda Fixa (Fundos de Investimento)  
**Gestoras**: Carbyne, Apex, Rhino (para debêntures), BTG, etc.  
**Dados Base**: Planilha "Carbyne - Apex" + "Rhino, Ações e Sem Extrato"  

### 3.2 Estrutura de Dados — FUNDO (Referência, Reutilizável)

Tabela: `carteira_fundo_referencia`

```
id_fundo [PK]
├─ nome_fundo                  "BRM Carbyne Crédito Estruturado FIC FIDC"
├─ cnpj_fundo                  "XX.XXX.XXX/0001-XX"  [FILTRO]
├─ gestora                      "BRM Gestão de Recursos"
├─ administradora               "Banco XYZ"
├─ tipo_fundo                   "FIDC", "FIA", "FII", "Multimercado"
├─ indexador                    "CDI", "IPCA", "Renda Variável", "Misto"
├─ percentual_esperado          % a.a. (rentabilidade histórica)
├─ data_constituicao           date
├─ ativo                       boolean
└─ observacoes                 text
```

### 3.3 Estrutura de Dados — POSIÇÃO DO CLIENTE

Tabela: `carteira_fundo_posicao`

```
id_posicao [PK]
├─ cliente_id [FK → carteira_cliente]
├─ fundo_id [FK → carteira_fundo_referencia]
├─ numero_conta                "001605364", "005750140"  (ID bancária/custodia)
│
├─ APLICAÇÃO
├─ data_aplicacao              date
├─ valor_aplicado              R$
├─ quantidade_cotas            integer (se FII: cotas; se Fundo: cotas)
├─ valor_cota_inicial          R$ (valor/cota no momento da aplicação)
│
├─ POSIÇÃO ATUAL
├─ data_base_valor_atual       date
├─ valor_cota_atual            R$ (cotação atual)
├─ valor_atual_estimado        R$ (cotas × cota_atual)
├─ variacao_percentual         % (automático)
├─ variacao_valor_absoluto     R$ (automático)
│
├─ DIREITO DE RECOMPRA
├─ tem_direito_recompra        boolean
├─ promessa_recompra           "CDI", "CDI+2%", "CDI+3%", string (se tem_direito = true)
├─ data_vencimento_recompra    date
├─ valor_base_recompra         R$ (se aplicável)
├─ status_recompra             "Aguardando", "Exercido", "Expirado"
├─ data_exercicio_recompra     date (se status = Exercido)
│
├─ ADMINISTRATIVO
├─ faz_parte_honorarios        boolean (flag com confirmação)
├─ percentual_sucesso_honor    % (da recompra ou ganho)
├─ estrategia_id               [FK → carteira_estrategia]
├─ folder_drive_id             string
├─ processos_judiciais         [ARRAY FK → processo]
├─ notificado                  boolean
│
└─ observacoes                 text
```

### 3.4 Subcategoria: DIREITO DE RECOMPRA (Ativo Financeiro Separado)

**Contexto**: Um direito de recompra é uma opção de compra de um fundo em data futura, com preço pré-determinado. Pode ser:
- Cadastrado junto com o Fundo
- Ou cadastrado isoladamente como "Ativo Financeiro Especial"

Tabela: `carteira_recompra_direito` (Alternativa: registrar como fundo com `tipo = "Direito Recompra"`)

```
id_recompra [PK]
├─ cliente_id [FK]
├─ fundo_origem_id             [FK → carteira_fundo_referencia]  (qual fundo originou)
├─ promessa                    "CDI", "CDI+2%"
├─ data_vencimento            date
├─ valor_investido_orig       R$ (valor da aplicação original)
├─ valor_base_recompra        R$ (base para cálculo)
├─ data_ultimo_calculo        date
├─ valor_estimado_recompra    R$ (automático: valor_base × indexador)
├─ status                      "Aguardando", "Exercido", "Expirado"
├─ estrategia_id              [FK]
└─ observacoes                text
```

### 3.5 Subcategoria: AÇÕES APEX (Ativo Financeiro)

Tabela: `carteira_acao_apex`

```
id_acao [PK]
├─ cliente_id [FK]
├─ tipo_acao                   "Ordinária (ON)", "Preferencial (PN)"
├─ classe_acao                 "A", "B", "C"  (se houver)
├─ empresa_acao                "Apex Partners Gestão de Ativos S.A."
├─ cnpj_empresa                "XX.XXX.XXX/0001-XX"
│
├─ POSIÇÃO
├─ quantidade_on               integer (ações ordinárias)
├─ quantidade_pn               integer (ações preferenciais)
├─ valor_unitario_on           R$ (preço/ação ON)
├─ valor_unitario_pn           R$ (preço/ação PN)
├─ data_base_valor            date
├─ valor_total_investido      R$ (automático)
│
├─ ADMINISTRATIVO
├─ faz_parte_honorarios       boolean
├─ estrategia_id              [FK]
├─ folder_drive_id            string
└─ observacoes                text
```

---

## PARTE 4: ENTIDADES TRANSVERSAIS

### 4.1 Cliente (Vinculação Principal)

Tabela: `carteira_cliente` (estende `usuario_cliente` existente)

```
id_cliente [PK]
├─ usuario_cliente_id          [FK → usuario_cliente]  (reusa cadastro existente)
├─ cpf                         "XXX.XXX.XXX-XX"
├─ tipo_pessoa                 "PF" ou "PJ"
│
├─ CONTATOS E QUALIFICAÇÃO
├─ email                       string
├─ telefone                    string
├─ qualificacao_id            [FK → cliente_qualificacao]  (aba da planilha)
│
├─ VINCULAÇÕES LEGAIS
├─ contrato_principal_id      [FK → contrato]  (opcional, linker)
├─ procuracao_id              [FK → procuracao]  (opcional, linker)
├─ processos_vinculados       [ARRAY FK → processo]
│
├─ HONORÁRIOS (Separado da Lógica Financeira)
├─ pro_labore_mensal          R$ (honorário fixo)
├─ percentual_sucesso_geral   %  (padrão, pode variar por ativo)
├─ observacao_honorarios      text
├─ fonte_captacao             "Indicação XYZ", "Contato Direto", "APEX Partners", etc.
│
├─ DRIVE
├─ folder_drive_principal_id  string (Google Drive folder ID para CARTEIRA deste cliente)
├─ folder_drive_url           string (URL acessível)
│
├─ ADMINISTRATIVO
├─ data_cadastro              timestamp
├─ ativo                       boolean
└─ observacoes                text
```

### 4.2 Estratégia (Reutilizável, Dinâmica)

Tabela: `carteira_estrategia`

```
id_estrategia [PK]
├─ nome                        "Segurança + Renda", "Crescimento Imobiliário", "Mix Rhino", etc.
├─ descricao                   text (justificativa)
├─ criada_por                  [FK → usuario]
├─ data_criacao                timestamp
├─ publico                     boolean (se sim, aparece no combobox de sugestões)
│
├─ RECOMENDAÇÕES EMBUTIDAS
├─ alocacao_recomendada       JSON {
│     "debentures": {
│       "percentual": 50,
│       "series": ["BRMAPEX110", "BRMAPEX120"],
│       "observacao": "Foco renda segura"
│     },
│     "fundos": {
│       "percentual": 30,
│       "gestoras": ["Carbyne", "BTG"],
│       "observacao": "Diversificação"
│     },
│     "imobiliario": {
│       "percentual": 20,
│       "tipos": ["Residencial", "Logístico"],
│       "observacao": "Longo prazo"
│     }
│   }
├─ usuarios_count              integer (quantos clientes usam)
└─ ativo                       boolean
```

**Exemplo real**:
```
Nome: Preservação + Renda Estruturada
Descrição: Estratégia conservadora para clientes em fase de aposentadoria
Alocação:
  - Debêntures Rhino: 60% (renda previsível)
  - Fundos Carbyne: 20% (renda variável baixa)
  - Imobiliário: 20% (longo prazo)
```

### 4.3 Aval de Sócios (Apenas para Debêntures)

Tabela: `carteira_socio_aval`

```
id [PK]
├─ nome_socio                  "Lucas Judice", "Sócio 2"
├─ percentual_participacao     %
├─ ativo                       boolean
└─ observacoes                 text
```

---

## PARTE 5: DASHBOARD CENTRAL (Resumo Executivo)

**Rota**: `/carteira` ou `/patrimonio` (sugestão: `/carteira`)

**Cards Principais**:

```
┌─────────────────────────────────────────────────────────────┐
│ # Clientes: 67                                              │
│ Pro-Labore Total (Mensal): R$ XX.XXX,XX                    │
│ Carteira $ Total: R$ 2.589.735,00                          │
│                                                             │
│ Expectativa Honorários Futuros: R$ X.XXX.XXX               │
│ ├─ Imobiliário: R$ X.XXX.XXX (por sucesso/conclusão)       │
│ └─ Financeiro: R$ X.XXX.XXX (por resgate/recompra)         │
└─────────────────────────────────────────────────────────────┘

📋 LISTA GERAL DE CLIENTES
├─ Nome | CPF | Valor Carteira | Expectativa | Ações
├─ [Filtro por Estratégia]
└─ [Exportar: Qualificação Individual / Lista Total / Selecionados]

🎯 ATALHOS RÁPIDOS
├─ [+ Novo Cliente]
├─ [+ Novo Ativo]
├─ [Importar de Planilha]
└─ [Upload de Documentação IA]
```

---

## PARTE 6: INTERFACE — TABELA PRINCIPAL (Opção 2)

### 6.1 Navegação

```
CARTEIRA
├─ Dashboard (KPIs + Lista)
├─ Debêntures
│  ├─ Minhas Posições (Tabela filtrada)
│  └─ Emissões (Referência)
├─ Imobiliário
│  ├─ Minhas Posições (Tabela filtrada)
│  └─ Empreendimentos (Referência)
├─ Fundos
│  ├─ Minhas Posições (Tabela filtrada)
│  ├─ Direito de Recompra (Submenu ou Tabela)
│  ├─ Ações Apex (Submenu ou Tabela)
│  └─ Fundos (Referência)
├─ Estratégias (Criar/Editar reutilizáveis)
├─ Configurações (Honorários, Drive, etc.)
└─ Relatórios (PDF por Cliente, Exportação)
```

### 6.2 Layout da Tabela: DEBÊNTURES

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ CARTEIRA > DEBÊNTURES > MINHAS POSIÇÕES                                      │
├──────────────────────────────────────────────────────────────────────────────┤
│ FILTROS (à esquerda)                                                         │
├─ Investidor: [seleção]                                                      │
├─ Série: [checkboxes: BRMAPEX110, BRMAPEX115, BRMAPEX120...]                 │
├─ Status Resgate: [Ativo, Solicitado, Negado, Processando, Liquidado]       │
├─ Data Vencimento: [range picker]                                            │
├─ Tipo Garantia: [checkboxes: Fluxo Imobiliário, Aval Sócios, FIDC...]      │
├─ Notificado: [toggle]                                                       │
├─ Aval de Sócios: [seleção: Lucas, Sócio2, etc.]                             │
└─ Processo Vinculado: [seleção de processos]                                 │

TABELA
┌─────────────────────────────────────────────────────────────────────────────┐
│ Cliente | Cautela | Série | Emissão | Qtd | Val.Aplic. | Val.Atual | Var% │
├─────────────────────────────────────────────────────────────────────────────┤
│         |         |       |         |     |            |           |       │
│ Carmelita C. | 1954 | BRMAPEX120 | 1 | 200 | R$ 200.000 | R$ 205.815 | +2,9% │
│ [Detalhes] [Editar] [PDF] [Drive] [✓ Resgate Solicitado] [Processo: Showa] │
│         |         |       |         |     |            |           |       │
│ Barbara M. | 1562 | BRMAPEX115 | 1 | 150 | R$ 150.000 | R$ 168.135 | +12,1% │
│ [Detalhes] [Editar] [PDF] [Drive] [✗ Resgate Negado] [Processo: Liminar] │
└─────────────────────────────────────────────────────────────────────────────┘

Cada linha pode:
├─ [Detalhes] → Abre modal/página com campos completos (cautela, série, etc.)
├─ [Editar] → Formulário inline ou modal
├─ [PDF] → Gera relatório individual
├─ [Drive] → Link para pasta no Google Drive
├─ [Status Resgate] → Indica se foi solicitado, com date + resposta
└─ [Processo] → Link para processo judicial (se houver)
```

### 6.3 Formulário: Adicionar Debênture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ + NOVA DEBÊNTURE                                                             │
├──────────────────────────────────────────────────────────────────────────────┤
│ CLIENTE (obrigatório)                                                        │
├─ [Select Cliente] (autocomplete: "Carmelita Cominote Monequi")              │
│                                                                              │
│ EMISSÃO (obrigatório - com PRÉ-PREENCHIMENTO)                               │
├─ Série: [Dropdown: BRMAPEX110, BRMAPEX115, BRMAPEX120...]                  │
│   → Ao selecionar, pré-preenche automaticamente:                            │
│      - Número de Emissão: "1"                                              │
│      - Emissor: "Rhino Securitizadora"                                     │
│      - Indexador: "CDI + 40%"                                              │
│      - Carência: "12 meses"                                                │
│      - Resgate Antecipado (Contrato): SIM/NÃO                              │
│      - Resgate Antecipado (Securitização): SIM/NÃO                         │
│      - Tipos de Garantia: [checkboxes] "Fluxo Imobiliário", "Aval", etc.  │
│                                                                              │
│ ESPECÍFICO DO CLIENTE                                                       │
├─ Número Cautela: [text] (obrigatório)                                       │
├─ Quantidade de Debêntures: [number]                                         │
├─ Data de Aquisição: [date picker]                                          │
├─ Valor Aplicado: R$ [currency] (automático: qtd × valor_nominal)          │
│                                                                              │
│ VALOR ATUAL                                                                 │
├─ Data Base: [date picker]                                                   │
├─ Valor Atual: R$ [currency]                                                │
│   → Variação % (automático)                                                │
│                                                                              │
│ RESGATE                                                                     │
├─ Status: [radio] Ativo / Solicitado / Negado / Processando / Liquidado    │
├─ [Se Solicitado/Negado/Liquidado]                                          │
│   - Data do Pedido: [date picker]                                          │
│   - Resposta da Rhino: [textarea]                                          │
│   - [Se Liquidado] Valor Pago: R$ [currency]                              │
│                                                                              │
│ AVAL E GARANTIAS                                                            │
├─ Aval de Sócios: [Multi-select: Lucas Judice, Sócio 2, etc.]              │
├─ Tipos de Garantia: [Checkboxes, pré-preenchidas da série]                │
│                                                                              │
│ ADMINISTRATIVO                                                              │
├─ Estratégia: [Combobox de estratégias reutilizáveis + criar nova]          │
├─ Faz Parte dos Honorários: [toggle]                                        │
├─ Processo Judicial: [Multi-select de processos cadastrados]                │
├─ Observações: [textarea]                                                    │
│                                                                              │
│ DOCUMENTAÇÃO                                                                │
├─ [Upload Múltiplo com IA]                                                   │
│   └─ Contrato, Termo Securitização, Demonstrativos, etc.                  │
│                                                                              │
│ DRIVE                                                                       │
├─ Link Pasta Google Drive: [auto-linked com pasta do cliente]               │
│   └─ [ícone] "Abrir Folder"                                                │
│                                                                              │
│ [SALVAR] [CANCELAR]                                                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 6.4 Layout da Tabela: IMOBILIÁRIO

```
Coluna: Cliente | Empreendimento | Tipo | Valor Aplic. | Valor Esperado | % Retorno | Aporte | Status

Detalhes no Modal/Página:
├─ Empreendimento: "Showa" (com match de ABM-PARSE)
├─ Tipo: "Desenvolvimento Residencial"
├─ Partes: "Lucas Judice", "Cônjuge"
├─ Valor Compromissado: R$ 2.050.933
├─ Valor Efetivamente Investido: R$ 1.200.000
├─ Data Primeiro Aporte: 20/12/2021
├─ Data Último Aporte: 15/06/2022
├─ Quantidade Aportes: 3
├─ Valor Esperado Retorno: R$ 3.076.400 (+50%)
├─ Camada 1 (ABM-PARSE): "ABMPARSE 01" → % 50%
├─ Camada 2 (SCP): "SCP 001/2024" → Lucas 50%, Cônjuge 50%
├─ Prestadora: "Apex Realty" → 5% do retorno
├─ Taxa Performance: 2% (se meta atingida)
├─ Faz Parte dos Honorários: SIM (15% do sucesso)
├─ Observações: "Obra em andamento, prazo previsto 2027-Q2"
└─ [Drive] [PDF] [Detalhes Empreendimento]
```

### 6.5 Layout da Tabela: FUNDOS

```
Coluna: Cliente | Fundo | Gestora | Qtd Cotas | Val.Aplic. | Val.Atual | Var% | Recompra?

Detalhes:
├─ Fundo: "BRM Carbyne Crédito FIDC"
├─ CNPJ: "XX.XXX.XXX/0001-XX"
├─ Gestora: "BRM Gestão"
├─ Administradora: "Banco XYZ"
├─ Data Aplicação: 05/06/2026
├─ Valor Aplicado: R$ 100.000
├─ Quantidade de Cotas: 1.000
├─ Valor Cota Inicial: R$ 100
├─ Valor Cota Atual: R$ 95 (data: 30/09/26)
├─ Valor Atual: R$ 95.000
├─ Variação: -5%
├─ Tem Direito de Recompra: SIM
│  └─ Promessa: "CDI + 2%"
│  └─ Data Vencimento: 05/06/2028
│  └─ Status: "Aguardando"
├─ Faz Parte dos Honorários: SIM (10% do ganho de recompra)
├─ Estratégia: "Mix Renda + Crescimento"
└─ [Drive] [PDF]
```

---

## PARTE 7: INTEGRAÇÃO COM OUTROS MENUS

### 7.1 Linker com CLIENTES

**Fluxo**:
1. Usuário em `/carteira/debenturas` clica em "+ Nova Debênture"
2. Campo "Cliente" é **autocomplete** que busca de `usuario_cliente`
3. Se cliente não existe em `carteira_cliente`, criar automaticamente
4. **Sem mudar** o menu de Clientes (apenas ler)

**Implementação**:
- `GET /api/clientes/?search=termo` → lista clientes existentes
- `POST /api/carteira/cliente/` → cria `carteira_cliente` se novo
- **Qualificação**: Se for novo, copiar dados de `cliente_qualificacao` se existente

### 7.2 Linker com CONTRATOS & PROCURAÇÕES

**Fluxo**:
1. Em `/carteira/cliente/{id}`, há campo opcional "Contrato Principal"
2. Combobox busca de `contratos` existentes (apenas leitura)
3. Se selecionar, fica visual que está linkado
4. Sem mudar o menu de Contratos

**Campos**:
```
contrato_principal_id: [FK → contrato_id]  (opcional)
procuracao_id: [FK → procuracao_id]  (opcional)
```

**Visual**:
```
Contrato Vinculado: [⬤ Contrato de Patrimônio - Ref. CONT-2024-001] [desvincular]
Procuração: [⬤ Procuração Geral e Especial] [desvincular]
```

Se NÃO linkado:
```
Contrato Vinculado: [○ Nenhum] [+ Linkar]
```

### 7.3 Linker com PROCESSOS

**Fluxo**:
1. Em formulário de qualquer ativo (debenture, imobiliário, fundo), há campo multi-select "Processos Judiciais"
2. Busca de `processo` existentes (apenas leitura)
3. Sem mudar o menu de Processos

**Campo**:
```
processos_judiciais: [ARRAY FK → processo_id]  (opcional)
```

**Visual**:
```
Processos Vinculados:
├─ ✓ Proc. Rhino - Liminar Resgate (PROC-2024-001)
├─ ✓ Proc. Showa - Atraso de Obra (PROC-2024-015)
└─ [+ Adicionar Processo]
```

### 7.4 Drive (Integração Nativa)

**Fluxo**:
1. Cada cliente tem `folder_drive_principal_id` (pasta Google Drive específica desta aba CARTEIRA)
2. Cada ativo (debenture, imobiliário, fundo) pode ter subpasta (ou arquivo direto)
3. Upload de arquivo → vai direto para Google Drive
4. Link "Abrir Folder" → abre a pasta no Drive com acesso do cliente

**Implementação**:
```
cliente.folder_drive_id = "folder-id-xyz"  (pasta: Lucas Judice > Carteira)
carteira_debenture_posicao.folder_drive_id = "subfolder-id" (opcional, pasta: Debêntures)
```

---

## PARTE 8: FILTROS (Opção 2 - Tabela)

### 8.1 Filtros por Tipo de Ativo

| Tipo | Filtros |
|------|---------|
| **Debêntures** | Série, Status Resgate, Tipo Garantia, Aval Sócios, Processo, Vencimento, Notificado |
| **Imobiliário** | Tipo Empreendimento, Status Obra, Tipo ABM-PARSE, Faz Parte Honorários, Vencimento Aporte |
| **Fundos** | Gestora, Tem Recompra, Status Recompra, Tipo Fundo, Faz Parte Honorários, Vencimento |
| **Global** | Cliente, Data Aplicação, Valor Range, Estratégia, Notificado |

### 8.2 Filtro de Vencimento (Especial)

```
[ ] Próximos 30 dias
[ ] Próximos 90 dias
[ ] Próximos 180 dias
[ ] Próximos 1 ano
[ ] Vencidos
[ ] Sem vencimento

Com subfiltro por tipo de ativo:
[ ] Debêntures
[ ] Imobiliário (data conclusão)
[ ] Fundos (recompra)
```

---

## PARTE 9: RELATÓRIOS & EXPORTAÇÃO

### 9.1 PDF por Cliente

**Conteúdo**:
```
┌─────────────────────────────────────────┐
│ PATRIMÔNIO CONSOLIDADO                  │
│ Cliente: Lucas Judice                   │
│ Data: 30/09/2026                        │
├─────────────────────────────────────────┤
│ DEBÊNTURES                              │
│ ├─ Cautela 1954 | Série BRMAPEX120     │
│ │  Valor Aplic.: R$ 200.000             │
│ │  Valor Atual: R$ 205.815 (+2,9%)      │
│ │  Vencimento: 28/04/2028               │
│ │  Observações: [...]                   │
│                                         │
│ IMOBILIÁRIO                             │
│ ├─ Showa Dev. Residencial               │
│ │  Valor Compromissado: R$ 2.050.933    │
│ │  Investido: R$ 1.200.000              │
│ │  Retorno Esperado: +50%               │
│                                         │
│ FUNDOS                                  │
│ ├─ BRM Carbyne FIDC                     │
│ │  Valor Aplic.: R$ 100.000             │
│ │  Valor Atual: R$ 95.000 (-5%)         │
│                                         │
│ RESUMO TOTAL                            │
│ Total Investido: R$ X.XXX.XXX           │
│ Valor Atual: R$ Y.YYY.YYY               │
│ Variação: +Z% / -Z%                     │
│                                         │
│ Links para Documentos:                  │
│ Pasta Google Drive: [link acessível]    │
└─────────────────────────────────────────┘
```

**Geração**: Botão [PDF] em cada cliente
- Usuário clica
- Sistema gera PDF com Playwright/Puppeteer
- Inclui link para pasta Google Drive (apenas para aquela subpasta do cliente)

### 9.2 Exportação de Qualificação

**O que é**: Dados cadastrais do cliente + honorários + estratégia

**Formatos**: XLSX, PDF

**Fluxo**:
1. Tabela de Clientes → seleção de 1, alguns ou todos
2. Botão [Exportar Qualificação]
3. Gera arquivo com:
   - CPF, Email, Telefone
   - Pro-Labore, % Sucesso
   - Fonte Captação
   - Estratégia Recomendada
   - Observações

---

## PARTE 10: MENU & INTEGRAÇÃO VISUAL

### 10.1 Mudança no Sidebar (Layout.tsx)

**Antes**:
```
BACKOFFICE & FINANCEIRO
├─ Financeiro
├─ Pagantes
├─ Reembolsos
├─ Notas Fiscais
└─ etc.
```

**Depois** (Opção A: Novo Grupo):
```
GESTÃO DA CARTEIRA
├─ Patrimônio de Clientes
├─ Estratégias
└─ Relatórios

BACKOFFICE & FINANCEIRO
├─ Financeiro
├─ Pagantes
├─ Reembolsos
├─ etc.
```

**Depois** (Opção B: Integrar com BACKOFFICE):
```
BACKOFFICE & FINANCEIRO
├─ Financeiro
├─ Patrimônio de Clientes  ← AQUI
├─ Pagantes
├─ Reembolsos
└─ etc.
```

**Recomendação**: **Opção A** (novo grupo "GESTÃO DA CARTEIRA") para deixar claro que é uma aba separada.

### 10.2 Estrutura de Rotas (React Router)

```
/carteira
├─ /             (Dashboard)
├─ /clientes     (Lista de clientes na carteira)
├─ /clientes/:id (Detalhe de cliente + todos seus ativos consolidados)
│
├─ /debentures
│  ├─ /          (Minhas Posições - tabela)
│  ├─ /emissoes  (Referência - CRUD de emissões)
│  └─ /new       (Adicionar nova debênture)
│
├─ /imobiliario
│  ├─ /          (Minhas Posições - tabela)
│  ├─ /empreendimentos (Referência - CRUD)
│  └─ /new       (Adicionar novo empreendimento)
│
├─ /fundos
│  ├─ /          (Minhas Posições - tabela)
│  ├─ /recompra  (Direitos de Recompra)
│  ├─ /acoes-apex (Ações Apex)
│  ├─ /fundos    (Referência - CRUD)
│  └─ /new       (Adicionar novo fundo)
│
├─ /estrategias  (Criar/editar estratégias reutilizáveis)
├─ /honorarios   (Gerenciar honorários por cliente)
└─ /relatorios   (Gerar PDFs, Exportar)
```

---

## PARTE 11: DADOS INICIAIS (Seed/Migração)

### 11.1 Importação da Planilha

**Fonte**: Abas do XLSX
- `Consolidado` → `carteira_cliente` + posições
- `Matriz Cautelas x Emissões` → `carteira_debenture_emissao`
- `Relacao ABM -- Empreendimento` → `carteira_imobiliario_empreendimento`
- `Clientes Únicos` → `carteira_cliente` (qualificação)

**Implementação (V1)**:
```python
# backend/app/scripts/seed_carteira.py
def seed_debentures():
    # Ler Matriz Cautelas x Emissões
    # Criar carteira_debenture_emissao para cada série única
    # Criar carteira_debenture_posicao para cada cliente+cautela

def seed_imobiliarios():
    # Ler Relacao ABM -- Empreendimento
    # Criar carteira_imobiliario_empreendimento
    # Criar carteira_imobiliario_posicao para cada cliente

def seed_fundos():
    # Ler Carbyne - Apex + Rhino
    # Criar carteira_fundo_referencia
    # Criar carteira_fundo_posicao

# Executar: python manage.py seed_carteira
```

**Status**: Marcado como "Importado de Planilha v1.0 (30/09/26)"

---

## PARTE 12: DÚVIDAS PARA VOCÊ VALIDAR

Antes de começar a codificação, preciso que você respeonda:

### ❓ Dúvidas Estruturais

1. **Menu**: Você quer **novo grupo "GESTÃO DA CARTEIRA"** no sidebar ou **integrar com "BACKOFFICE & FINANCEIRO"**?

2. **Pro-Labore vs. Honorários de Sucesso**: 
   - Pro-Labore é fixo mensal (R$ X por mês)?
   - % de Sucesso é só quando ativo é liquidado/resgatado?
   - Se debenture vence com rendimento, o % de sucesso incide sobre o ganho ou sobre o valor total retornado?

3. **Resgate Antecipado (2 flags)**:
   - "Resgate Antecipado (Contrato)" = o que o contrato de emissão permite?
   - "Resgate Antecipado (Securitização)" = o que o termo de securitização permite?
   - Quando são diferentes, qual prevalece?

4. **Imobiliário - Multi-layer de ABM-PARSE**:
   - Cliente pode ter 2 ou 3 ABM-PARSE diferentes para o MESMO empreendimento?
   - Ou cada empreendimento tem apenas 1 ABM-PARSE principal?
   - Se múltiplas, como calcula o total investido? (Soma de todos?)

5. **SCP - Partes**:
   - SCP sempre em nome do cliente, ou pode ter outros sócios dentro da SCP?
   - Exemplo: SCP Showa (Lucas 50%, Cônjuge 50%)?

6. **Honorários - Flag Destrutiva**:
   - Quando usuário marca "Faz Parte dos Honorários = true", você quer pop-up CONFIRMAÇÃO no desmarcação?
   - Msg: "Tem certeza? Desmarcar removerá este ativo dos cálculos de honorários"?

7. **Drive - Pastas por Ativo**:
   - Cada ativo (debenture, imobiliário, fundo) tem sua própria subpasta no Drive?
   - Ou todos os arquivos de um cliente ficam em uma pasta única?
   - Exemplo: `/Lucas Judice/Carteira/Debentures/Cautela-1954/` ou `/Lucas Judice/Carteira/` (tudo junto)?

8. **Processo Judicial - Combobox**:
   - O combobox de processos busca por **processo_id** existente?
   - Ou precisa criar novo processo ali mesmo?
   - Recomendação: apenas linkar com existentes (criar processo está em outro menu)

9. **Estratégia - Reutilizável**:
   - Usuário define estratégia 1x
   - Depois pode aplicar a múltiplos clientes
   - Cada cliente pode ter estratégia diferente?
   - Sim? Isso tudo faz sentido?

10. **IA - Upload de Contrato**:
    - Qual modelo de visão você quer usar? (Claude Vision via API, Google Docs OCR, Tesseract?)
    - Precisão esperada: >90%, >80%, >70%?

11. **Relação com Clientes Existente**:
    - Usuários de `/clientes` veem dados de carteira lá?
    - Ou a carteira é **totalmente separada** do menu de Clientes?
    - Recomendação: separada (este módulo é novo, não mexe em Clientes)

12. **V1 - Scope**:
    - V1 é **tabela com CRUD básico** (criar, editar, listar)?
    - **Sem IA** (upload IA = V2)?
    - **Sem dashboard de KPIs** (apenas listagem)?
    - **Sem relatórios PDF** (apenas exportação XLS = V2)?

---

## PARTE 13: CHECKLIST PRÉ-DESENVOLVIMENTO

- [ ] Validar respostas das 12 dúvidas acima
- [ ] Confirmar menu: novo grupo vs. integrado?
- [ ] Confirmar scope V1: tabela + CRUD vs. com IA + dashboards
- [ ] Confirmar dados iniciais: quer seed de planilha já na V1?
- [ ] Confirmar Drive: estrutura de pastas
- [ ] Confirmar honorários: fórmula pro-labore + % sucesso
- [ ] Listar cores/tipografia do Lexops (para match visual)
- [ ] Confirmar espaço de telas (mockups refletem?

)

---

## PRÓXIMOS PASSOS (Após Validação)

1. **Você responde as 12 dúvidas** (ou respostas curtas tipo "como está no blueprint tá bom")
2. **Eu fecho o blueprint visual** (mockups em HTML respeitando Lexops)
3. **Inicia desenvolvimento** (Models, Endpoints, Frontend)
   - Fase 1A: Debêntures (CRUD + Tabela)
   - Fase 1B: Imobiliário (CRUD + Tabela)
   - Fase 1C: Fundos (CRUD + Tabela)
   - Fase 2: IA + Upload
   - Fase 3: Dashboard + Relatórios

---

**Este blueprint está pronto para você.**  
Próximo passo: **suas validações + respostas**.

