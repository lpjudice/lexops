# Setor Fiscal do Escritório

## Norte do módulo

O módulo não deve parecer apenas uma tela de emissão fiscal ou configuração contábil. Ele precisa transmitir uma sensação de **mesa de decisão tributária**, porque o objetivo real não é lançar nota, e sim responder:

- qual regime pesa menos no caixa;
- qual regime gera mais crédito para o cliente PJ;
- qual diferença comercial isso cria;
- qual mudança passa a valer a pena com a Reforma.

## Tese principal de UX

Para este módulo, a comparação entre regimes precisa vir **antes** do detalhe operacional.

Se a interface começar por cadastro, filtros e tabelas longas, o usuário sente que está em uma tela burocrática. Se começar por comparação, ranking e impacto financeiro, ele entende que está em uma ferramenta de decisão.

## Conceito recomendado

### Conceito A: Mesa de Decisão Tributária

Melhor opção para a primeira versão visual.

#### Ideia central

Uma tela com cara de painel executivo, organizada para responder em poucos segundos:

- quanto o escritório pagaria em cada regime;
- qual regime vence no mês;
- quanto crédito cada regime entrega ao cliente;
- onde existe risco comercial por gerar pouco crédito.

#### Estrutura sugerida

1. Cabeçalho com competência, filtros e botão "Simular cenário".
2. Faixa de resumo com quatro leituras:
   - regime mais barato;
   - economia potencial;
   - crédito ao cliente PJ;
   - alerta comercial.
3. Tabela comparativa principal com quatro colunas fixas:
   - Simples por dentro;
   - Simples por fora;
   - Lucro Presumido;
   - Lucro Real.
4. Bloco visual de composição do tributo:
   - DAS;
   - IBS;
   - CBS;
   - IRPJ;
   - CSLL;
   - INSS patronal;
   - créditos abatidos.
5. Bloco "caixa x comercial":
   - melhor para o escritório;
   - melhor para clientes PJ;
   - melhor equilíbrio.
6. Linha do tempo mensal com tendência anual.

#### Forças

- leitura imediata;
- boa para decisão de diretoria;
- favorece comparações objetivas;
- comunica bem a tensão entre carga e crédito.

#### Risco

Se exagerar nos números sem hierarquia, vira uma planilha disfarçada de dashboard.

## Conceito alternativo

### Conceito B: Radar Comercial e Tributário

Opção mais consultiva, útil se o escritório quiser usar isso também para conversa com clientes no futuro.

#### Ideia central

A tela divide a análise em dois eixos:

- eixo 1: custo efetivo do escritório;
- eixo 2: atratividade comercial do crédito para o cliente.

Cada regime aparece como um posicionamento estratégico, não apenas como total de imposto.

#### Estrutura sugerida

1. Matriz 2x2:
   - menor carga / maior crédito;
   - menor carga / menor crédito;
   - maior carga / maior crédito;
   - maior carga / menor crédito.
2. Cards por regime com:
   - total pago;
   - carga efetiva;
   - crédito transferível;
   - pressão comercial estimada.
3. Lista de alertas interpretativos:
   - "regime barato, mas fraco para cliente PJ";
   - "regime mais caro, porém defensável em clientes corporativos".
4. Histórico mensal mostrando se a vantagem muda ao longo do ano.

#### Forças

- muito forte para estratégia;
- excelente para consultoria;
- deixa claro que "mais barato" não significa "melhor".

#### Risco

É menos direto para quem quer apuração mensal antes de análise estratégica.

## Conceito alternativo

### Conceito C: Laboratório de Cenários

Opção mais analítica, boa para fase de testes internos.

#### Ideia central

A tela funciona como um simulador vivo. O usuário altera premissas e enxerga o reflexo instantâneo nos quatro regimes.

#### Estrutura sugerida

1. Painel lateral de premissas:
   - IBS;
   - CBS;
   - redução de 30%;
   - crédito permitido;
   - folha;
   - despesas elegíveis.
2. Área central com comparação entre regimes.
3. Rodapé analítico com sensibilidades:
   - se a folha subir;
   - se as despesas com crédito aumentarem;
   - se o faturamento migrar para clientes PJ que exigem crédito.

#### Forças

- muito útil para calibração;
- ideal para validar premissas tributárias.

#### Risco

Pode parecer ferramenta técnica demais para uso recorrente da operação.

## Recomendação de arquitetura visual

Minha recomendação é combinar os conceitos assim:

- tela principal baseada no **Conceito A**;
- bloco comercial inspirado no **Conceito B**;
- drawer ou painel lateral de simulação inspirado no **Conceito C**.

Isso cria uma experiência que começa executiva e continua analítica apenas quando necessário.

## O que a tela principal deve mostrar primeiro

Ordem ideal de leitura:

1. qual regime venceu no mês;
2. quanto se economiza em reais;
3. quanto crédito o cliente pode aproveitar;
4. qual a diferença entre "melhor para o caixa" e "melhor para vender";
5. só depois a composição técnica dos tributos.

## Proposta de blocos visuais

### 1. Barra de decisão

Uma faixa larga no topo com:

- competência analisada;
- regime recomendado no mês;
- economia potencial anualizada;
- status da Reforma nas premissas usadas.

### 2. Placar comparativo

Em vez de quatro cards isolados, usar um placar horizontal.

Cada regime deve mostrar:

- total tributário;
- carga efetiva;
- crédito ao cliente;
- selo de posição no ranking.

### 3. Tabela analítica

A tabela comparativa é o centro do módulo.

Linhas sugeridas:

- faturamento;
- folha total;
- despesas com crédito;
- DAS;
- IBS bruto;
- CBS bruto;
- créditos IBS;
- créditos CBS;
- IRPJ;
- CSLL;
- INSS patronal;
- total a pagar;
- carga efetiva;
- crédito do cliente.

### 4. Tabela mensal de custos com crédito potencial

Essa nova tabela passa a ser estrutural no módulo, não acessória.

Ela precisa registrar o gasto mensal e estimar automaticamente o potencial de crédito com base nas premissas configuradas para IBS/CBS.

#### Colunas sugeridas

- categoria;
- fornecedor;
- valor da despesa;
- possui nota;
- elegível para crédito;
- alíquota IBS aplicável;
- alíquota CBS aplicável;
- crédito estimado IBS;
- crédito estimado CBS;
- crédito total;
- observação.

#### Regras de UX

- a categoria pode sugerir uma alíquota padrão de mercado, mas o usuário deve poder editar;
- itens sem nota ou sem elegibilidade devem continuar visíveis, apenas sem gerar crédito;
- o rodapé da tabela deve somar:
  - total das despesas;
  - total elegível;
  - total de crédito estimado;
  - impacto do crédito na decisão do regime.

#### Papel na decisão do regime

Esse bloco precisa conversar diretamente com a recomendação do topo.

Exemplo de leitura:

"O Simples por fora sobe no ranking porque as despesas elegíveis do mês geraram R$ X de crédito potencial."

### 5. Painel de premissas dinâmicas

Como IBS, CBS e até a redução de 30% ainda podem variar, a interface deve tratar esses números como insumos vivos.

#### Campos mínimos

- IBS cheio;
- CBS cheio;
- IVA total;
- redução setorial;
- IBS reduzido resultante;
- CBS reduzido resultante;
- crédito integral ou parcial;
- trava para editar por mês ou manter padrão anual.

#### Comportamento esperado

- qualquer ajuste recalcula a tela comparativa;
- a interface mostra claramente qual premissa foi usada no mês;
- se houver premissa customizada para um mês, isso aparece com um selo visual.

### 6. Faixa "escritório x cliente"

Bloco interpretativo com três etiquetas:

- melhor para caixa;
- melhor para cliente PJ;
- melhor equilíbrio.

Esse bloco é importante porque traduz a lógica tributária para decisão comercial.

### 7. Tendência mensal

Gráfico de linha com:

- carga efetiva de cada regime;
- possibilidade de alternar para valor nominal;
- destaque dos meses em que a liderança muda.

## Linguagem visual sugerida

### Direção

Clínica, analítica e segura, mas sem aparência de sistema contábil velho.

### Sensação

- alta confiança;
- leitura executiva;
- clareza numérica;
- foco em comparação, não em burocracia.

### Paleta sugerida

- base clara e levemente aquecida;
- verde-petróleo para regime atual ou recomendado;
- âmbar para atenção comercial;
- azul profundo para crédito ao cliente;
- vermelho controlado apenas para risco ou aumento de carga.

### Tipografia

- títulos compactos e firmes;
- números com bastante destaque;
- textos explicativos curtos, quase de sala de reunião.

## Padrões que eu evitaria

- quatro cards idênticos com números grandes e sem contexto;
- tabela enorme logo na primeira dobra;
- excesso de filtros antes da resposta principal;
- interface com cara de "configuração fiscal";
- linguagem centrada em tributos sem traduzir impacto comercial.

## Proposta de menu interno do módulo

Se esse menu Fiscal evoluir, eu separaria em:

- `Decisão`: visão principal comparativa;
- `Lançamentos`: faturamento, folha e despesas;
- `Premissas`: regras tributárias e alíquotas;
- `Relatórios`: mensal, anual, PDF e Excel;
- `Crédito ao Cliente`: impacto comercial por perfil de tomador.

## Estrutura de navegação recomendada

Como o produto já trabalha com menu lateral à esquerda, a tela principal não deve tentar condensar tudo em uma única página longa e densa.

Minha sugestão é:

- `Decisão Tributária`: resumo, ranking e comparativo;
- `Custos & Créditos`: tabela mensal de despesas e cálculo de crédito potencial;
- `Premissas Tributárias`: IBS, CBS, redução setorial e regras dinâmicas;
- `Visão Anual`: tendência, ranking e consolidação;
- `Relatórios`: exportações e parecer executivo.

## Estratégia de responsividade

### Desktop com sidebar aberta

- conteúdo central com largura mais contida;
- usar duas colunas apenas nos blocos realmente comparativos;
- evitar tabelas gigantes acima da dobra;
- preferir seções colapsáveis para folha, despesas e premissas.

### Tablet com sidebar estreita

- manter cards de resumo em 2 colunas;
- tabela comparativa com rolagem horizontal controlada;
- custos mensais em lista compacta ou tabela simplificada.

### Mobile

- leitura em fluxo vertical;
- placar comparativo vira cards empilhados;
- custos mensais devem poder recolher detalhes por item;
- premissas tributárias ficam em bloco próprio, recolhível.

## Primeira hipótese para validar

Se formos validar só uma direção agora, eu seguiria esta:

- uma tela principal chamada **Decisão Tributária**;
- topo com recomendação do mês;
- centro com tabela comparativa dos quatro regimes;
- faixa lateral ou inferior mostrando crédito ao cliente e pressão comercial;
- histórico mensal logo abaixo.

Essa hipótese é a mais forte para transformar uma área fiscal em ferramenta de decisão, e não apenas em centro de cadastro.
