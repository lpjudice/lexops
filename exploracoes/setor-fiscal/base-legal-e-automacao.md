# Base legal e automação futura

## Referência legal principal

Para esta exploração, a base jurídica principal dos créditos de IBS/CBS deve partir da **Lei Complementar nº 214, de 16 de janeiro de 2025**, que institui IBS, CBS e Imposto Seletivo e traz a lógica geral de neutralidade, apuração e créditos. Fonte oficial: [Planalto](https://www.planalto.gov.br/ccivil_03/leis/lcp/quadro_lcp.htm) e [LC 214/2025](https://planalto.gov.br/ccivil_03/Leis/LCP/Lcp214.htm).

Pontos que impactam diretamente a modelagem:

- a LC 214/2025 institui IBS e CBS e adota a lógica de neutralidade do sistema;
- o desenho de créditos e ressarcimento precisa ser tratado como parte estrutural do regime regular;
- a própria regulamentação já conversa com a hipótese de optantes do Simples no regime regular de IBS/CBS, inclusive em resultados de busca do texto compilado da lei no Planalto;
- como a legislação vem recebendo ajustes e atos complementares, o sistema não deve hardcodar teses jurídicas por categoria de despesa sem trilha de revisão.

Observação de modelagem:

O sistema não deve prometer "crédito garantido" apenas por categoria. O que ele deve produzir é:

- `potencial de crédito estimado`;
- `fundamento legal associado`;
- `status de validação humana`;
- `data da última conferência`.

## Modelo recomendado para cada despesa

Cada despesa cadastrada deve carregar, além do valor:

- categoria interna;
- descrição livre;
- fornecedor;
- documento fiscal vinculado, quando houver;
- regra jurídica aplicada;
- fundamento legal principal;
- fundamento complementar, se existir;
- status da análise;
- data da última conferência;
- data prevista da próxima revalidação.

## Fluxo futuro de consulta legal

### 1. Primeiro cadastro de uma despesa nova

Quando uma categoria ou combinação de categoria + tipo de documento + natureza do gasto aparecer pela primeira vez:

- o sistema consulta a base legal e/ou motor de pesquisa jurídica configurado;
- monta uma sugestão de enquadramento;
- sugere se há:
  - potencial de crédito;
  - potencial de não crédito;
  - zona cinzenta;
- guarda os fundamentos encontrados;
- marca o item como `pendente de conferência`.

### 2. Validação humana

Depois da sua revisão:

- você confirma, ajusta ou rejeita a tese;
- o sistema grava essa decisão como regra validada;
- a despesa passa a poder usar essa regra nas próximas ocorrências.

### 3. Revalidação semestral

Se a mesma despesa voltar a ser cadastrada:

- o sistema reutiliza a regra validada;
- se a última conferência tiver mais de 6 meses, ele deve reconsultar;
- a nova consulta não precisa bloquear o uso, mas deve levantar alerta de revisão.

## Estados visuais sugeridos

Para a UI, cada despesa deveria ter um selo simples:

- `Validado`: regra confirmada por você;
- `Pendente`: primeira análise aguardando conferência;
- `Revalidar`: regra antiga, com mais de 6 meses;
- `Exceção`: item com divergência ou dúvida jurídica.

## Arquitetura preparada para automação posterior

Mesmo sem implementar agora, vale estruturar a experiência já pensando em:

- leitura automática de documento fiscal de entrada;
- vinculação futura de DANFe/NFS-e tomada;
- classificação assistida da despesa;
- busca de fundamento jurídico;
- reaproveitamento de regra validada;
- rechecagem semestral automatizada.

## Recomendação de produto

Na prática, isso sugere separar o módulo em duas camadas:

- `camada fiscal-operacional`: lança, vincula documento, classifica e soma;
- `camada jurídico-tributária`: sugere fundamento, marca confiança, pede validação e agenda revalidação.

Essa separação deixa o produto pronto para automação futura sem obrigar a interface atual a fingir que tudo já é automático.
