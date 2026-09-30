# Gestor Jurídico

Sistema pessoal de gestão jurídica para Lucas Judice.

## Visão geral

Plataforma integrada para gestão da rotina jurídica: leitura de diários oficiais, calendário de publicações, gestão de processos, resumo de teses, integração com Gmail e Google Calendar.

## Stack (a definir)

- Backend: Python (FastAPI ou Flask)
- Frontend: a definir
- DB: a definir
- Integrações: Gmail API, Google Calendar API, Diário Oficial

## Status

Projeto em fase de planejamento. Aguardando coordenadas do usuário.

## Notas operacionais

- Para a intervencao em `Processos/Andamentos` com foco em `DataJud` e `jus.br`, ver `PROCESSOS_ANDAMENTOS_NOTAS.md`.

- jus.br: o fluxo preferido agora e colar o JSON de token do portal; a sessao compartilhada tenta refresh automatico quando houver `refresh_token`.

- ⚠️ SEMI-TRAVA jus.br (NÃO DESATIVAR sem ordem expressa do Lucas): a LÓGICA da consulta jus.br/DataJud (andamentos + documentos) e do fluxo de colar token está congelada e funcionando. Um hook `pre-commit` (`.githooks/pre-commit`, ativado via `core.hooksPath`) bloqueia commits que alterem estes arquivos: `backend/app/services/consulta_processual/{orchestrator,pdpj,jusbr_session,datajud,cnj,base}.py` e `frontend/src/utils/jusbrToken.ts`. Mudanças VISUAIS/layout da tela de Processos (ProcessosPage, AndamentosSection, SincronizarModal, ImportarJusBRModal) são livres — não estão travadas. Para alterar a lógica de forma intencional e revisada, e SÓ com aval do Lucas: `ALLOW_JUSBR_CHANGES=1 git commit ...`. Não burle a trava removendo o hook. Reativar em novo clone: `bash scripts/setup-hooks.sh`.

- ⚠️ DEPLOY com vários chats/clones em paralelo: ANTES de qualquer `flyctl deploy`, rode `bash scripts/pre-deploy-check.sh`. Ele barra deploy de uma linhagem que não contém o `origin/main` (senão o deploy apaga do ar o que outros chats já entregaram), de tree sujo e de cadeia do Alembic com mais de 1 head. Fluxo: `git fetch origin && git merge origin/main`, commitar, checar, deployar e dar push no `main` (fast-forward). Nova migração do Alembic: o `down_revision` deve ser o head atual do `main`. Em sessões na nuvem use `flyctl deploy --remote-only --depot=false -a lexops` (o builder Depot não é alcançável).
