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
