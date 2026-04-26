# Notas de Continuidade: DataJud e jus.br

Escopo desta intervencao:

- somente `Processos/Andamentos`;
- foco em `DataJud` e `jus.br/PDPJ`;
- sem mudanca de banco;
- sem mexer em deduplicacao, scheduler ou outras areas do app.

## O que mudou

### DataJud

- a consulta deixou de depender apenas do `tribunal` digitado manualmente;
- o backend agora tenta:
  - tribunal informado no processo;
  - tribunal inferido a partir do numero CNJ;
  - mais de uma estrategia de query no indice do DataJud.

Arquivos:

- `backend/app/services/consulta_processual/cnj.py`
- `backend/app/services/consulta_processual/datajud.py`

### Cadastro / Atualizacao de processo

- o backend normaliza a sigla do tribunal ao criar/editar processo;
- se o tribunal vier vazio e o CNJ permitir inferencia segura, o backend preenche automaticamente.

Arquivo:

- `backend/app/routers/processos.py`

### jus.br / PDPJ

- o backend passou a:
  - tentar bases adicionais do `cabecalho-processual`;
  - usar parametros extras de busca por processo;
  - aproveitar movimentos inline quando a resposta ja vier completa;
  - filtrar melhor o processo pelo tribunal esperado;
  - informar expiracao do token quando isso puder ser lido do JWT.

Arquivo:

- `backend/app/services/consulta_processual/pdpj.py`

### UX do token jus.br

- o token agora fica salvo no `localStorage` do navegador enquanto ainda estiver valido;
- a tela mostra expiracao detectada e permite limpar/renovar o token;
- o modal de sincronizacao em lote nao esconde mais processos apenas por falta de tribunal preenchido, se o CNJ ja permitir inferencia.

Arquivos:

- `frontend/src/utils/jusbrToken.ts`
- `frontend/src/utils/cnj.ts`
- `frontend/src/components/AndamentosSection.tsx`
- `frontend/src/components/InstrucoesJusBRModal.tsx`
- `frontend/src/components/SincronizarModal.tsx`

## O que ficou de fora de proposito

- nao alteramos a estrategia de deduplicacao dos andamentos;
- nao automatizamos login completo do `jus.br` no Fly.io;
- nao mudamos o scheduler diario para depender de token do `jus.br`.

Motivo:

- isso aumentaria bastante o risco operacional e de regressao;
- token do `jus.br` continua sendo sessao curta;
- login automatizado com `gov.br`/certificado no servidor exige outro desenho.

## Proximo passo natural

Se for continuar depois:

1. criar um diagnostico persistente por sync, registrando quais indices/queries do DataJud foram tentados;
2. revisar a deduplicacao com um identificador de movimento por fonte;
3. decidir se o `jus.br` vai seguir com token humano assistido ou se vai ganhar um conector autenticado de verdade.
