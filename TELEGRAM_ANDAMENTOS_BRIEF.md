# Brief — Bot Telegram de Andamentos (jus.br) dentro do lexops

> Cole o bloco abaixo numa NOVA sessão do Claude para iniciar este projeto.
> Este arquivo é só o ponto de partida; a arquitetura final será validada na sessão.

---

```
Vou iniciar um novo módulo DENTRO do repositório lexops
(/Users/lucasjudice/ClaudeCode/GestorJuridico): um bot de Telegram que dispara a
busca de andamentos de um processo no jus.br/PDPJ e me devolve o resultado.

== REGRA Nº 1 (INEGOCIÁVEL): NÃO MEXER NA LÓGICA DE COLETA DO JUS.BR ==
A lógica de busca (andamentos + documentos) já existe, está PERFEITA e funcionando,
e está protegida por uma semi-trava (git pre-commit). É PROIBIDO alterar estes
arquivos — eles devem ser apenas REUTILIZADOS como estão:
  - backend/app/services/consulta_processual/orchestrator.py
  - backend/app/services/consulta_processual/pdpj.py
  - backend/app/services/consulta_processual/jusbr_session.py
  - backend/app/services/consulta_processual/datajud.py
  - backend/app/services/consulta_processual/cnj.py
  - backend/app/services/consulta_processual/base.py
  - frontend/src/utils/jusbrToken.ts
Detalhes da trava e como ela funciona estão no CLAUDE.md (Notas operacionais) e na
memória do projeto (memory/project_jusbr_lock.md). Override só com minha ordem
expressa: ALLOW_JUSBR_CHANGES=1 git commit. NÃO desative o hook.

== O QUE QUERO QUE O BOT FAÇA ==
1. Eu mando no Telegram: "pesquisar processo <número CNJ>".
2. O bot inicia um login gov.br/PDPJ via Playwright e me ABRE no celular a tela de
   login (login + senha + 2FA) para eu completar manualmente o gov.br.
3. Após o login, o Playwright RETOMA o controle automaticamente.
4. A coleta de andamentos + documentos é feita pela LÓGICA JÁ EXISTENTE do lexops
   (não reimplementar scraping).
5. O bot me devolve no Telegram os X andamentos novos (e documentos).
6. Opcional / menos importante: atualizar também no lexops (gravar os andamentos
   no banco como já é feito hoje).

== ORDEM DE ATAQUE QUE QUERO QUE VOCÊ SIGA ==
O Telegram e a coleta NÃO são o problema difícil — a coleta já está pronta e a infra
de Telegram já existe no lexops. O ponto que DECIDE a viabilidade de tudo, sem custo,
é: "como faço a tela do gov.br aparecer no meu CELULAR para eu logar (login/senha/2FA)
e o Playwright retomar depois?". Então ataque NESTA ordem:

  FASE 0 — PROVA DE CONCEITO DO LOGIN REMOTO (faça isto ANTES de qualquer outra coisa):
    - Demonstre, de ponta a ponta, que eu consigo: receber um link/acesso no celular,
      ver a tela real do gov.br controlada pelo Playwright, digitar login/senha/2FA, e
      o Playwright detectar que loguei e seguir em frente.
    - Avalie opções concretas (ex.: Cloudflare Tunnel + viewer de browser remoto/noVNC,
      Playwright em modo remoto, ou alternativa) e me recomende UMA, com prós/contras,
      custo (quero ZERO custo novo) e onde o navegador roda.
    - Só seguir para as próximas fases depois que esta PoC funcionar e eu aprovar.

  FASE 1 — EXTRAÇÃO DO TOKEN: após o login, extrair o access_token da sessão logada
    do portal (localStorage / requisições de rede) e validar que ele serve de entrada
    para a lógica de coleta existente.

  FASE 2 — COLETA REUSADA: alimentar o token na lógica de coleta JÁ EXISTENTE
    (jusbr_session/pdpj/orchestrator) e obter andamentos + documentos. Sem tocar nela.

  FASE 3 — CAMADA TELEGRAM: conversa do bot ("pesquisar processo X"), orquestração do
    pending/retomada pós-login, e entrega dos X andamentos novos + documentos.

  FASE 4 — PERSISTÊNCIA DE SESSÃO: reusar a sessão enquanto válida (não me pedir login
    gov.br toda vez), pedindo novo login só quando expirar.

  FASE 5 (opcional, menos importante): gravar os andamentos no banco do lexops.

== ARQUITETURA A VALIDAR COMIGO ANTES DE CODAR ==
A lógica de coleta atual NÃO usa Playwright — ela recebe um TOKEN e chama a API do
PDPJ. Proposta: o Playwright serve SÓ para autenticação (FASE 0/1). Depois do meu
login gov.br, ele extrai o access_token e entrega para a lógica de coleta existente,
que faz andamentos + documentos como sempre. Assim o Playwright só substitui o passo
de "colar o token manual"; a coleta fica intocada. Confirme se é a melhor abordagem
antes de implementar — se houver caminho melhor que respeite a Regra nº 1, proponha.

== CONTEXTO: PROTÓTIPO EXTERNO NO CODEX (referência, NÃO é o destino) ==
Em /Users/lucasjudice/Documents/Codex/2026-06-04/crie-um-projeto-completo-para-um
há um protótipo standalone (aiogram + FastAPI + Playwright) que:
  - já abre o Chromium e chega no portal (https://portaldeservicos.pdpj.jus.br/home);
  - tenta reusar sessão persistente (data/home, data/ms-playwright);
  - tenta clicar em "Entrar com gov.br" (instável — geralmente clico manual);
  - mantém pending request para retomar via /continue (retomada pós-login instável);
  - preenche número do processo, busca, tenta abrir o resultado e a aba "Movimentos".
Problemas: clique em "Entrar com gov.br" instável; detecção de sessão válida instável;
fluxo pós-login não continua sozinho; clique na linha do resultado instável.
IMPORTANTE: NÃO quero bot standalone externo. Quero dentro do lexops, reaproveitando
a lógica de coleta que já funciona — por isso o scraping da aba "Movimentos" do
protótipo provavelmente nem é necessário (a coleta vem da lógica existente via token).
Use o protótipo só como referência do que já foi aprendido sobre o portal.

== INFRA / TELEGRAM JÁ EXISTENTE NO LEXOPS ==
O lexops já tem um bot de Telegram (@sui_lexops_bot) para reembolsos, com infra em
backend/app/routers/telegram.py, backend/app/services/telegram_api.py, etc. Estude
esse código para reaproveitar webhook/conversa e credenciais em vez de criar do zero.
Meu user_id do Telegram autorizado é 5152275140. O lexops roda no Fly.io (app
"lexops", região gru).

== QUESTÕES TÉCNICAS EM ABERTO (levante e me ajude a decidir na FASE 0) ==
- Como surgir a tela do gov.br no meu CELULAR para eu logar e o Playwright retomar?
  (Cloudflare Tunnel + viewer remoto/noVNC, ou outra abordagem). Celular + ZERO custo.
- Onde o Playwright roda? Dentro do app no Fly pode ser pesado/custoso; avalie se deve
  ser um processo/serviço separado dentro do mesmo repo. Sem aumentar custo.
- Como persistir a sessão para não me pedir login gov.br toda vez.
- Confirmar que dá para extrair o access_token da sessão logada e alimentar a lógica
  de coleta existente.

== COMO QUERO QUE VOCÊ TRABALHE ==
- ESTUDE o código existente (lógica de coleta travada + infra Telegram de reembolsos +
  protótipo Codex) e me faça PERGUNTAS antes de solucionar. Alinhe a direção comigo
  antes de editar qualquer coisa.
- A cada atualização, suba a versão (padrão do projeto).
- Higiene de git; nada de perder arquivos no deploy; nada de custo novo sem me avisar.
- Primeiro entregue o PLANO (incluindo a recomendação da FASE 0) e os pontos de
  decisão; só depois implemente, por fases.

Comece pela FASE 0: estude o terreno e me traga (a) o plano de arquitetura, (b) a
recomendação concreta de como fazer o login gov.br no meu celular com retomada do
Playwright e ZERO custo, (c) confirmação de como a Regra nº 1 será respeitada,
(d) suas perguntas em aberto. NÃO implemente antes do meu aval do plano.
```
