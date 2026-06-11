---
name: project-backoffice-fiscal
description: Módulo Backoffice Fiscal — motor comparativo de regimes tributários com crédito IBS/CBS da Reforma
metadata:
  type: project
---

Módulo de decisão tributária implementado em Jun/2026.

**Por que:** Pós-Reforma (LC 214/2025), despesas elegíveis geram crédito IBS/CBS que influencia qual regime é melhor para caixa e para o cliente PJ — isso precisa ser monitorado mensalmente.

**Why:** Merged FINANCEIRO + FISCAL into BACKOFFICE group in sidebar (Option C). Fiscal is a collapsible sub-group that auto-expands on /fiscal/* routes.

**Arquivos criados:**
- `backend/app/models/backoffice.py` — 5 modelos: FiscalMes, FiscalFolha, FiscalDespesa, FiscalReceita, RegraCredito
- `backend/app/services/fiscal_engine.py` — motor de cálculo (Simples Anexo IV, LP, LR) com fórmulas reais
- `backend/app/routers/backoffice.py` — endpoints em /backoffice/*
- `frontend/src/api/backoffice.ts` — API client
- `frontend/src/pages/BackofficeDecisaoPage.tsx` — página com 4 tabs: Comparativo, Lançamentos, Crédito IBS/CBS, Visão Anual

**Rota:** `/fiscal/decisao`

**Motor de cálculo:**
- Simples: faixas reais do Anexo IV (LC/2006), alíquota efetiva = (RBT12 × aliq_nominal - deducao) / RBT12
- LP: base presumida 32%, IRPJ 15%+10% adicional, CSLL 9%, PIS 0.65%, COFINS 3%, ISS municipal
- LR: lucro contábil real (receita - folha - despesas), PIS 1.65%/COFINS 7.6% não-cumulativos com crédito sobre entradas
- Todos + IBS/CBS da Reforma com redução setorial de 30% p/ advocacia

**Lógica de crédito:**
- `ibs_entrada_pct = ibs_saida_pct / (1 - reducao/100)` — crédito na alíquota cheia dos fornecedores
- Despesas: precisa `tem_nota=true` e `elegivel=true` para gerar crédito
- Status das regras: validado | pendente | revalidar | novo (revalidação semestral)

**Integração com NFs:**
- `_sync_receitas_nf()` no endpoint `/backoffice/decisao/{mes}` — importa automaticamente NFs com status `emitida|autorizada` da `notas_fiscais` que ainda não estão em `fiscal_receita`
- Tipo cliente inferido pelo tamanho do CPF/CNPJ (14 dígitos = PJ)

**How to apply:** Ao trabalhar no módulo fiscal/backoffice, checar estes arquivos primeiro. O engine não tem deps de ORM — testável em isolamento.
