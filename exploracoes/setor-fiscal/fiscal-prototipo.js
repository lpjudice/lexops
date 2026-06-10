const STORAGE_KEY = 'setor-fiscal-prototipo-v1';

const DEFAULT_STATE = {
  currentMonth: '2026-05',
  months: {
    '2026-04': {
      premises: {
        ibsFull: 17.5,
        cbsFull: 8.8,
        reductionPct: 30,
        creditMode: 'integral',
      },
      revenues: [
        {
          id: 'r1',
          client: 'Grupo Atlas Participações',
          kind: 'PJ regime regular',
          amount: 118000,
          creditInterest: true,
          taxationMode: 'por fora',
          withheld: 4200,
        },
        {
          id: 'r2',
          client: 'Marina Azevedo',
          kind: 'Pessoa física',
          amount: 24000,
          creditInterest: false,
          taxationMode: 'embutido',
          withheld: 0,
        },
        {
          id: 'r3',
          client: 'Techmar Soluções Ltda.',
          kind: 'PJ Simples',
          amount: 51000,
          creditInterest: false,
          taxationMode: 'embutido',
          withheld: 1800,
        },
      ],
      payroll: {
        salaries: 54000,
        prolabore: 16000,
        inssEmployer: 14000,
        rat: 1800,
        fgts: 5100,
        benefits: 6900,
      },
      expenses: [
        {
          id: 'e1',
          category: 'Software jurídico',
          vendor: 'Legal Tech One',
          amount: 8400,
          hasInvoice: true,
          eligible: true,
          legalBase: 'LC 214/2025',
          status: 'validado',
          lastCheck: '2026-02',
        },
        {
          id: 'e2',
          category: 'Marketing/publicidade',
          vendor: 'Studio Trinta',
          amount: 12000,
          hasInvoice: true,
          eligible: true,
          legalBase: 'LC 214/2025',
          status: 'revalidar',
          lastCheck: '2025-10',
        },
        {
          id: 'e3',
          category: 'Correspondentes jurídicos',
          vendor: 'Rede Processual',
          amount: 18600,
          hasInvoice: true,
          eligible: true,
          legalBase: 'LC 214/2025',
          status: 'validado',
          lastCheck: '2026-01',
        },
        {
          id: 'e4',
          category: 'Aluguel',
          vendor: 'Imobiliária Centro',
          amount: 9800,
          hasInvoice: true,
          eligible: false,
          legalBase: 'Tese sensível',
          status: 'pendente',
          lastCheck: '',
        },
        {
          id: 'e5',
          category: 'Energia elétrica',
          vendor: 'Concessionária',
          amount: 3600,
          hasInvoice: true,
          eligible: true,
          legalBase: 'LC 214/2025',
          status: 'validado',
          lastCheck: '2026-03',
        },
      ],
    },
    '2026-05': {
      premises: {
        ibsFull: 17.5,
        cbsFull: 8.8,
        reductionPct: 30,
        creditMode: 'integral',
      },
      revenues: [
        {
          id: 'r4',
          client: 'Holding Vale Verde S.A.',
          kind: 'PJ regime regular',
          amount: 143000,
          creditInterest: true,
          taxationMode: 'por fora',
          withheld: 5100,
        },
        {
          id: 'r5',
          client: 'Clínica Monteiro',
          kind: 'PJ regime regular',
          amount: 72000,
          creditInterest: true,
          taxationMode: 'embutido',
          withheld: 2600,
        },
        {
          id: 'r6',
          client: 'Juliana Prado',
          kind: 'Pessoa física',
          amount: 28000,
          creditInterest: false,
          taxationMode: 'embutido',
          withheld: 0,
        },
        {
          id: 'r7',
          client: 'Construtora Horizonte',
          kind: 'PJ Simples',
          amount: 64000,
          creditInterest: false,
          taxationMode: 'embutido',
          withheld: 2100,
        },
      ],
      payroll: {
        salaries: 61000,
        prolabore: 18000,
        inssEmployer: 15500,
        rat: 2100,
        fgts: 5800,
        benefits: 7900,
      },
      expenses: [
        {
          id: 'e6',
          category: 'Software jurídico',
          vendor: 'Legal Tech One',
          amount: 8400,
          hasInvoice: true,
          eligible: true,
          legalBase: 'LC 214/2025',
          status: 'validado',
          lastCheck: '2026-02',
        },
        {
          id: 'e7',
          category: 'Marketing/publicidade',
          vendor: 'Studio Trinta',
          amount: 14000,
          hasInvoice: true,
          eligible: true,
          legalBase: 'LC 214/2025',
          status: 'revalidar',
          lastCheck: '2025-11',
        },
        {
          id: 'e8',
          category: 'Correspondentes jurídicos',
          vendor: 'Rede Processual',
          amount: 22400,
          hasInvoice: true,
          eligible: true,
          legalBase: 'LC 214/2025',
          status: 'validado',
          lastCheck: '2026-01',
        },
        {
          id: 'e9',
          category: 'Energia elétrica',
          vendor: 'Concessionária',
          amount: 3900,
          hasInvoice: true,
          eligible: true,
          legalBase: 'LC 214/2025',
          status: 'validado',
          lastCheck: '2026-03',
        },
        {
          id: 'e10',
          category: 'Internet',
          vendor: 'Fibra Empresas',
          amount: 980,
          hasInvoice: true,
          eligible: true,
          legalBase: 'LC 214/2025',
          status: 'novo',
          lastCheck: '',
        },
        {
          id: 'e11',
          category: 'Aluguel',
          vendor: 'Imobiliária Centro',
          amount: 9800,
          hasInvoice: true,
          eligible: false,
          legalBase: 'Tese sensível',
          status: 'pendente',
          lastCheck: '',
        },
        {
          id: 'e12',
          category: 'Despesas com clientes',
          vendor: 'Diversos',
          amount: 4200,
          hasInvoice: false,
          eligible: false,
          legalBase: 'Sem documento hábil',
          status: 'pendente',
          lastCheck: '',
        },
      ],
    },
  },
};

const STATUS_LABEL = {
  validado: 'Validado',
  revalidar: 'Revalidar',
  pendente: 'Pendente',
  novo: 'Novo',
};

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return clone(DEFAULT_STATE);
    return { ...clone(DEFAULT_STATE), ...JSON.parse(raw) };
  } catch {
    return clone(DEFAULT_STATE);
  }
}

function saveState(state) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function monthLabel(month) {
  const [year, mm] = month.split('-');
  const names = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
  return `${names[Number(mm) - 1]}/${year}`;
}

function fmtBRL(value) {
  return value.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function fmtPct(value) {
  return `${value.toFixed(2).replace('.', ',')}%`;
}

function num(value) {
  return Number(value) || 0;
}

function getCurrentMonthData(state) {
  return state.months[state.currentMonth];
}

function ensureMonth(state, month) {
  if (!state.months[month]) {
    state.months[month] = {
      premises: clone(DEFAULT_STATE.months['2026-05'].premises),
      revenues: [],
      payroll: {
        salaries: 0,
        prolabore: 0,
        inssEmployer: 0,
        rat: 0,
        fgts: 0,
        benefits: 0,
      },
      expenses: [],
    };
  }
}

function expenseCredit(expense, premises) {
  if (!expense.hasInvoice || !expense.eligible) return { ibs: 0, cbs: 0, total: 0 };
  const factor = premises.creditMode === 'parcial' ? 0.5 : 1;
  const ibs = expense.amount * (premises.ibsFull / 100) * factor;
  const cbs = expense.amount * (premises.cbsFull / 100) * factor;
  return { ibs, cbs, total: ibs + cbs };
}

function totalsForMonth(monthData) {
  const revenueTotal = monthData.revenues.reduce((sum, item) => sum + item.amount, 0);
  const withheldTotal = monthData.revenues.reduce((sum, item) => sum + item.withheld, 0);
  const payrollTotal = Object.values(monthData.payroll).reduce((sum, value) => sum + value, 0);
  const expenseTotal = monthData.expenses.reduce((sum, item) => sum + item.amount, 0);
  const eligibleExpenseTotal = monthData.expenses.reduce(
    (sum, item) => sum + (item.hasInvoice && item.eligible ? item.amount : 0),
    0,
  );
  const credit = monthData.expenses.reduce(
    (sum, item) => {
      const c = expenseCredit(item, monthData.premises);
      return { ibs: sum.ibs + c.ibs, cbs: sum.cbs + c.cbs, total: sum.total + c.total };
    },
    { ibs: 0, cbs: 0, total: 0 },
  );
  const creditInterestedRevenue = monthData.revenues
    .filter((item) => item.creditInterest)
    .reduce((sum, item) => sum + item.amount, 0);
  return {
    revenueTotal,
    withheldTotal,
    payrollTotal,
    expenseTotal,
    eligibleExpenseTotal,
    credit,
    creditInterestedRevenue,
  };
}

function effectiveIbs(premises) {
  return premises.ibsFull * (1 - premises.reductionPct / 100);
}

function effectiveCbs(premises) {
  return premises.cbsFull * (1 - premises.reductionPct / 100);
}

function calculateRegimes(monthData) {
  const totals = totalsForMonth(monthData);
  const revenue = totals.revenueTotal;
  const payroll = totals.payrollTotal;
  const ibsRed = effectiveIbs(monthData.premises);
  const cbsRed = effectiveCbs(monthData.premises);
  const grossOutputTax = revenue * ((ibsRed + cbsRed) / 100);
  const clientCredit = totals.creditInterestedRevenue * ((ibsRed + cbsRed) / 100);

  const simpleInside = {
    name: 'Simples por dentro',
    total: revenue * 0.133 + payroll * 0.2,
    clientCredit: clientCredit * 0.34,
  };

  const simpleOutsideDas = revenue * 0.045 + payroll * 0.2;
  const simpleOutside = {
    name: 'Simples por fora',
    total: simpleOutsideDas + Math.max(grossOutputTax - totals.credit.total, 0),
    clientCredit,
  };

  const presumed = {
    name: 'Lucro Presumido',
    total: revenue * 0.145 + payroll * 0.2 + Math.max(revenue * ((ibsRed + cbsRed) / 100) - totals.credit.total * 0.85, 0),
    clientCredit: revenue * ((ibsRed + cbsRed) / 100),
  };

  const accountingProfit = Math.max(revenue - payroll - totals.expenseTotal, 0);
  const real = {
    name: 'Lucro Real',
    total:
      accountingProfit * 0.24 +
      payroll * 0.2 +
      Math.max(revenue * ((ibsRed + cbsRed) / 100) - totals.credit.total, 0),
    clientCredit: revenue * ((ibsRed + cbsRed) / 100),
  };

  const regimes = [simpleInside, simpleOutside, presumed, real].map((item) => ({
    ...item,
    effectiveRate: revenue ? (item.total / revenue) * 100 : 0,
  }));
  const winner = regimes.reduce((best, current) => (current.total < best.total ? current : best), regimes[0]);
  return { regimes, winner, grossOutputTax, clientCredit };
}

function pageLayout(active, title, body) {
  return `
    <div class="app">
      <aside class="sidebar">
        <div class="logo-main">Pimenta Judice</div>
        <div class="logo-sub">Advogados</div>
        <div class="nav-group">
          <div class="nav-label">Fiscal</div>
          <a class="nav-link ${active === 'home' ? 'active' : ''}" href="./prototipo-dashboard-fiscal.html"><span>Visão Geral</span></a>
          <a class="nav-link ${active === 'decision' ? 'active' : ''}" href="./decisao-tributaria.html"><span>Decisão Tributária</span></a>
          <a class="nav-link ${active === 'costs' ? 'active' : ''}" href="./custos-creditos.html"><span>Custos & Créditos</span></a>
          <a class="nav-link ${active === 'premises' ? 'active' : ''}" href="./premissas-tributarias.html"><span>Premissas</span></a>
          <a class="nav-link ${active === 'annual' ? 'active' : ''}" href="./visao-anual.html"><span>Visão Anual</span></a>
          <a class="nav-link ${active === 'reports' ? 'active' : ''}" href="./relatorios.html"><span>Relatórios</span></a>
        </div>
      </aside>
      <div class="main-wrapper">
        <div class="topbar">
          <div class="topbar-title">${title}</div>
          <div class="user">LJ</div>
        </div>
        <main class="main">
          <div class="content">${body}</div>
        </main>
      </div>
    </div>
  `;
}

function monthSelector(state) {
  const options = Object.keys(state.months)
    .sort()
    .map((month) => `<option value="${month}" ${month === state.currentMonth ? 'selected' : ''}>${monthLabel(month)}</option>`)
    .join('');
  return `
    <div class="actions">
      <label class="inline-field">
        <span>Mês</span>
        <select id="month-select">${options}</select>
      </label>
      <button class="btn btn-secondary" id="reset-data">Restaurar mock</button>
    </div>
  `;
}

function renderHome(state) {
  const monthData = getCurrentMonthData(state);
  const totals = totalsForMonth(monthData);
  const calc = calculateRegimes(monthData);
  return pageLayout(
    'home',
    'Fiscal',
    `
      <div class="page-head">
        <div>
          <div class="eyebrow">Protótipo dinâmico</div>
          <h1>Base navegável das 5 telas com receitas e despesas testáveis.</h1>
          <div class="lead">Os dados abaixo já vêm com 2 meses mockados de um escritório de advocacia. Você pode editar receitas, despesas e premissas para ver o impacto no crédito e no regime vencedor.</div>
        </div>
        ${monthSelector(state)}
      </div>

      <div class="grid-3">
        <div class="card card-pad">
          <div class="section-title">Mês ativo</div>
          <div class="kpi-value">${monthLabel(state.currentMonth)}</div>
          <div class="section-sub">Receita ${fmtBRL(totals.revenueTotal)} · Crédito ${fmtBRL(totals.credit.total)}</div>
        </div>
        <div class="card card-pad">
          <div class="section-title">Regime sugerido</div>
          <div class="kpi-value">${calc.winner.name}</div>
          <div class="section-sub">Carga efetiva ${fmtPct(calc.winner.effectiveRate)}</div>
        </div>
        <div class="card card-pad">
          <div class="section-title">Base jurídica preparada</div>
          <div class="kpi-value">LC 214/2025</div>
          <div class="section-sub">com validação humana e rechecagem semestral</div>
        </div>
      </div>

      <div class="grid-3 section-block">
        <div class="card card-pad"><div class="section-title">1. Decisão Tributária</div><div class="section-sub">Ranking entre regimes e leitura comercial.</div><div class="section-block"><a class="btn btn-secondary" href="./decisao-tributaria.html">Abrir tela</a></div></div>
        <div class="card card-pad"><div class="section-title">2. Custos & Créditos</div><div class="section-sub">Cadastro de despesas e receitas do mês.</div><div class="section-block"><a class="btn btn-secondary" href="./custos-creditos.html">Abrir tela</a></div></div>
        <div class="card card-pad"><div class="section-title">3. Premissas Tributárias</div><div class="section-sub">IBS, CBS e redução setorial variáveis.</div><div class="section-block"><a class="btn btn-secondary" href="./premissas-tributarias.html">Abrir tela</a></div></div>
        <div class="card card-pad"><div class="section-title">4. Visão Anual</div><div class="section-sub">Comparação entre os dois meses mockados.</div><div class="section-block"><a class="btn btn-secondary" href="./visao-anual.html">Abrir tela</a></div></div>
        <div class="card card-pad"><div class="section-title">5. Relatórios</div><div class="section-sub">Resumo executivo com os números atuais.</div><div class="section-block"><a class="btn btn-secondary" href="./relatorios.html">Abrir tela</a></div></div>
        <div class="card card-pad"><div class="section-title">6. Nota de automação</div><div class="section-sub">Fundamento, validação e rechecagem em 6 meses.</div><div class="section-block"><a class="btn btn-secondary" href="./base-legal-e-automacao.md">Ver nota</a></div></div>
      </div>
    `,
  );
}

function renderDecision(state) {
  const monthData = getCurrentMonthData(state);
  const totals = totalsForMonth(monthData);
  const calc = calculateRegimes(monthData);
  const rows = calc.regimes
    .map((regime) => `
      <tr ${regime.name === calc.winner.name ? 'class="highlight"' : ''}>
        <td><strong>${regime.name}</strong></td>
        <td class="money">${fmtBRL(regime.total)}</td>
        <td>${fmtPct(regime.effectiveRate)}</td>
        <td class="money">${fmtBRL(regime.clientCredit)}</td>
        <td>${regime.name === calc.winner.name ? '<span class="chip green">vencedor</span>' : '<span class="chip amber">comparar</span>'}</td>
      </tr>
    `)
    .join('');

  return pageLayout(
    'decision',
    'Decisão Tributária',
    `
      <div class="page-head">
        <div>
          <div class="eyebrow">Tela 1</div>
          <h1>Regime vencedor do mês, agora recalculado pelos seus números.</h1>
          <div class="lead">Esta tela lê receitas, despesas, folha e premissas do mês ativo. Ao alterar dados nas telas de lançamentos ou premissas, o ranking abaixo muda automaticamente.</div>
        </div>
        ${monthSelector(state)}
      </div>

      <div class="grid-4">
        <div class="kpi"><div class="kpi-label">Receita do mês</div><div class="kpi-value">${fmtBRL(totals.revenueTotal)}</div><div class="kpi-sub">${monthData.revenues.length} notas mockadas</div></div>
        <div class="kpi"><div class="kpi-label">Folha total</div><div class="kpi-value">${fmtBRL(totals.payrollTotal)}</div><div class="kpi-sub">com encargos</div></div>
        <div class="kpi"><div class="kpi-label">Crédito das despesas</div><div class="kpi-value">${fmtBRL(totals.credit.total)}</div><div class="kpi-sub">IBS + CBS</div></div>
        <div class="kpi"><div class="kpi-label">Regime sugerido</div><div class="kpi-value">${calc.winner.name}</div><div class="kpi-sub">${fmtPct(calc.winner.effectiveRate)} efetiva</div></div>
      </div>

      <div class="grid-2 section-block">
        <div class="soft-box teal">
          Leitura executiva
          <strong>${calc.winner.name} está na frente em ${monthLabel(state.currentMonth)}.</strong>
          <div class="section-sub">O crédito acumulado nas despesas elegíveis foi de ${fmtBRL(totals.credit.total)} e já alterou a decisão comparativa.</div>
        </div>
        <div class="soft-box blue">
          Crédito ao cliente PJ
          <strong>${fmtBRL(calc.winner.clientCredit)}</strong>
          <div class="section-sub">Valor estimado de crédito percebido pelo tomador no regime vencedor.</div>
        </div>
      </div>

      <div class="card card-pad section-block">
        <div class="section-title">Comparativo entre regimes</div>
        <div class="table-wrap section-block">
          <table>
            <thead>
              <tr><th>Regime</th><th>Total tributário</th><th>Carga efetiva</th><th>Crédito ao cliente</th><th>Status</th></tr>
            </thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    `,
  );
}

function revenueRows(monthData) {
  return monthData.revenues
    .map(
      (item) => `
      <tr>
        <td>${item.client}</td>
        <td>${item.kind}</td>
        <td class="money">${fmtBRL(item.amount)}</td>
        <td>${item.creditInterest ? '<span class="chip blue">valoriza crédito</span>' : '<span class="chip amber">não prioritário</span>'}</td>
        <td>${item.taxationMode}</td>
      </tr>`,
    )
    .join('');
}

function expenseRows(monthData) {
  return monthData.expenses
    .map((item) => {
      const credit = expenseCredit(item, monthData.premises);
      return `
        <tr>
          <td>${item.category}</td>
          <td>${item.vendor}</td>
          <td class="money">${fmtBRL(item.amount)}</td>
          <td>${item.hasInvoice ? '<span class="chip green">com nota</span>' : '<span class="chip red">sem nota</span>'}</td>
          <td>${item.eligible ? '<span class="chip green">sim</span>' : '<span class="chip amber">não</span>'}</td>
          <td class="${credit.total ? 'good' : 'muted'}">${fmtBRL(credit.total)}</td>
          <td><span class="chip ${item.status === 'validado' ? 'green' : item.status === 'revalidar' ? 'amber' : 'red'}">${STATUS_LABEL[item.status]}</span></td>
          <td>${item.legalBase}</td>
        </tr>
      `;
    })
    .join('');
}

function renderCosts(state) {
  const monthData = getCurrentMonthData(state);
  const totals = totalsForMonth(monthData);
  return pageLayout(
    'costs',
    'Custos & Créditos',
    `
      <div class="page-head">
        <div>
          <div class="eyebrow">Tela 2</div>
          <h1>Lançamentos testáveis de receitas e despesas.</h1>
          <div class="lead">Aqui você consegue testar o protótipo de verdade. As receitas alimentam a decisão do regime, e as despesas elegíveis geram o crédito que pode mudar o vencedor do mês.</div>
        </div>
        ${monthSelector(state)}
      </div>

      <div class="grid-4">
        <div class="kpi"><div class="kpi-label">Receita total</div><div class="kpi-value">${fmtBRL(totals.revenueTotal)}</div><div class="kpi-sub">${monthData.revenues.length} itens</div></div>
        <div class="kpi"><div class="kpi-label">Despesa total</div><div class="kpi-value">${fmtBRL(totals.expenseTotal)}</div><div class="kpi-sub">${monthData.expenses.length} itens</div></div>
        <div class="kpi"><div class="kpi-label">Base elegível</div><div class="kpi-value">${fmtBRL(totals.eligibleExpenseTotal)}</div><div class="kpi-sub">com documento hábil</div></div>
        <div class="kpi"><div class="kpi-label">Crédito estimado</div><div class="kpi-value">${fmtBRL(totals.credit.total)}</div><div class="kpi-sub">IBS + CBS</div></div>
      </div>

      <div class="grid-2 section-block">
        <div class="card card-pad">
          <div class="section-title">Adicionar receita</div>
          <form id="revenue-form" class="form-stack section-block">
            <label class="input-group"><span>Cliente</span><input name="client" required placeholder="Ex.: Empresa Alfa S.A." /></label>
            <label class="input-group"><span>Tipo</span>
              <select name="kind">
                <option>PJ regime regular</option>
                <option>PJ Simples</option>
                <option>Pessoa física</option>
              </select>
            </label>
            <label class="input-group"><span>Valor</span><input name="amount" type="number" step="0.01" required /></label>
            <label class="input-group"><span>Tributação</span>
              <select name="taxationMode"><option>por fora</option><option>embutido</option></select>
            </label>
            <label class="check-row"><input type="checkbox" name="creditInterest" /> Cliente valoriza crédito</label>
            <button class="btn btn-primary" type="submit">Adicionar receita</button>
          </form>
        </div>

        <div class="card card-pad">
          <div class="section-title">Adicionar despesa</div>
          <form id="expense-form" class="form-stack section-block">
            <label class="input-group"><span>Categoria</span><input name="category" required placeholder="Ex.: Contabilidade" /></label>
            <label class="input-group"><span>Fornecedor</span><input name="vendor" required /></label>
            <label class="input-group"><span>Valor</span><input name="amount" type="number" step="0.01" required /></label>
            <label class="check-row"><input type="checkbox" name="hasInvoice" checked /> Possui nota fiscal</label>
            <label class="check-row"><input type="checkbox" name="eligible" checked /> Gera crédito estimado</label>
            <button class="btn btn-primary" type="submit">Adicionar despesa</button>
          </form>
        </div>
      </div>

      <div class="card card-pad section-block">
        <div class="section-title">Receitas do mês</div>
        <div class="table-wrap section-block">
          <table>
            <thead><tr><th>Cliente</th><th>Tipo</th><th>Valor</th><th>Crédito</th><th>Modo</th></tr></thead>
            <tbody>${revenueRows(monthData)}</tbody>
          </table>
        </div>
      </div>

      <div class="card card-pad section-block">
        <div class="section-title">Despesas e crédito potencial</div>
        <div class="table-wrap section-block">
          <table>
            <thead><tr><th>Categoria</th><th>Fornecedor</th><th>Valor</th><th>Documento</th><th>Elegível</th><th>Crédito</th><th>Status</th><th>Base legal</th></tr></thead>
            <tbody>${expenseRows(monthData)}</tbody>
          </table>
        </div>
      </div>
    `,
  );
}

function renderPremises(state) {
  const monthData = getCurrentMonthData(state);
  const p = monthData.premises;
  return pageLayout(
    'premises',
    'Premissas Tributárias',
    `
      <div class="page-head">
        <div>
          <div class="eyebrow">Tela 3</div>
          <h1>Premissas variáveis para IBS, CBS e redução setorial.</h1>
          <div class="lead">Esses campos recalculam crédito das despesas e comparação entre regimes. Eles ficam por mês para você testar cenários diferentes da Reforma.</div>
        </div>
        ${monthSelector(state)}
      </div>

      <div class="card card-pad">
        <div class="section-title">Editar premissas do mês</div>
        <form id="premises-form" class="grid-4 section-block">
          <label class="input-group"><span>IBS cheio</span><input name="ibsFull" type="number" step="0.01" value="${p.ibsFull}" /></label>
          <label class="input-group"><span>CBS cheia</span><input name="cbsFull" type="number" step="0.01" value="${p.cbsFull}" /></label>
          <label class="input-group"><span>Redução setorial</span><input name="reductionPct" type="number" step="0.01" value="${p.reductionPct}" /></label>
          <label class="input-group"><span>Crédito</span>
            <select name="creditMode">
              <option value="integral" ${p.creditMode === 'integral' ? 'selected' : ''}>Integral</option>
              <option value="parcial" ${p.creditMode === 'parcial' ? 'selected' : ''}>Parcial</option>
            </select>
          </label>
          <div class="field"><label>IBS reduzido</label><div class="value">${fmtPct(effectiveIbs(p))}</div><div class="hint">resultado</div></div>
          <div class="field"><label>CBS reduzida</label><div class="value">${fmtPct(effectiveCbs(p))}</div><div class="hint">resultado</div></div>
          <div class="field"><label>IVA total</label><div class="value">${fmtPct(p.ibsFull + p.cbsFull)}</div><div class="hint">sem redução</div></div>
          <div class="field"><label>IVA setorial</label><div class="value">${fmtPct(effectiveIbs(p) + effectiveCbs(p))}</div><div class="hint">com redução</div></div>
          <div><button class="btn btn-primary" type="submit">Salvar premissas</button></div>
        </form>
      </div>
    `,
  );
}

function renderAnnual(state) {
  const months = Object.keys(state.months).sort();
  const cards = months
    .map((month) => {
      const calc = calculateRegimes(state.months[month]);
      const totals = totalsForMonth(state.months[month]);
      return `
        <div class="month ${month === state.currentMonth ? 'current' : ''}">
          <div class="month-name">${monthLabel(month)}</div>
          <strong>${calc.winner.name}</strong>
          <p>Receita ${fmtBRL(totals.revenueTotal)}</p>
          <p>Crédito ${fmtBRL(totals.credit.total)}</p>
        </div>
      `;
    })
    .join('');
  return pageLayout(
    'annual',
    'Visão Anual',
    `
      <div class="page-head">
        <div>
          <div class="eyebrow">Tela 4</div>
          <h1>Comparação consolidada dos meses mockados.</h1>
          <div class="lead">Como você pediu um teste inicial, deixei dois meses compatíveis com rotina de escritório de advocacia. A ideia aqui é comparar rapidamente como a liderança pode mudar.</div>
        </div>
        ${monthSelector(state)}
      </div>

      <div class="card card-pad">
        <div class="section-title">Meses disponíveis</div>
        <div class="timeline section-block">${cards}</div>
      </div>
    `,
  );
}

function renderReports(state) {
  const monthData = getCurrentMonthData(state);
  const totals = totalsForMonth(monthData);
  const calc = calculateRegimes(monthData);
  return pageLayout(
    'reports',
    'Relatórios',
    `
      <div class="page-head">
        <div>
          <div class="eyebrow">Tela 5</div>
          <h1>Resumo executivo do mês em teste.</h1>
          <div class="lead">Essa leitura já reflete os dados dinâmicos do navegador. Ela serve como um embrião do relatório exportável.</div>
        </div>
        ${monthSelector(state)}
      </div>

      <div class="grid-3">
        <div class="soft-box teal">Regime sugerido<strong>${calc.winner.name}</strong><div class="section-sub">com carga de ${fmtPct(calc.winner.effectiveRate)}</div></div>
        <div class="soft-box blue">Crédito das despesas<strong>${fmtBRL(totals.credit.total)}</strong><div class="section-sub">base elegível ${fmtBRL(totals.eligibleExpenseTotal)}</div></div>
        <div class="soft-box amber">Receita do mês<strong>${fmtBRL(totals.revenueTotal)}</strong><div class="section-sub">retenções ${fmtBRL(totals.withheldTotal)}</div></div>
      </div>

      <div class="card card-pad section-block">
        <div class="section-title">Resumo para decisão</div>
        <div class="table-wrap section-block">
          <table>
            <thead><tr><th>Pergunta</th><th>Resposta atual</th></tr></thead>
            <tbody>
              <tr><td>Quanto o escritório fatura no mês?</td><td class="money">${fmtBRL(totals.revenueTotal)}</td></tr>
              <tr><td>Quanto as despesas elegíveis geram de crédito?</td><td class="money">${fmtBRL(totals.credit.total)}</td></tr>
              <tr><td>Qual regime está melhor no cenário atual?</td><td><strong>${calc.winner.name}</strong></td></tr>
              <tr><td>Qual crédito o cliente PJ percebe no regime vencedor?</td><td class="money">${fmtBRL(calc.winner.clientCredit)}</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    `,
  );
}

function attachSharedHandlers(state) {
  const monthSelect = document.getElementById('month-select');
  if (monthSelect) {
    monthSelect.addEventListener('change', (event) => {
      state.currentMonth = event.target.value;
      saveState(state);
      location.reload();
    });
  }

  const reset = document.getElementById('reset-data');
  if (reset) {
    reset.addEventListener('click', () => {
      localStorage.removeItem(STORAGE_KEY);
      location.reload();
    });
  }
}

function attachCostsHandlers(state) {
  const revenueForm = document.getElementById('revenue-form');
  if (revenueForm) {
    revenueForm.addEventListener('submit', (event) => {
      event.preventDefault();
      const form = new FormData(revenueForm);
      const monthData = getCurrentMonthData(state);
      monthData.revenues.push({
        id: `r${Date.now()}`,
        client: form.get('client'),
        kind: form.get('kind'),
        amount: num(form.get('amount')),
        creditInterest: form.get('creditInterest') === 'on',
        taxationMode: form.get('taxationMode'),
        withheld: 0,
      });
      saveState(state);
      location.reload();
    });
  }

  const expenseForm = document.getElementById('expense-form');
  if (expenseForm) {
    expenseForm.addEventListener('submit', (event) => {
      event.preventDefault();
      const form = new FormData(expenseForm);
      const monthData = getCurrentMonthData(state);
      monthData.expenses.push({
        id: `e${Date.now()}`,
        category: form.get('category'),
        vendor: form.get('vendor'),
        amount: num(form.get('amount')),
        hasInvoice: form.get('hasInvoice') === 'on',
        eligible: form.get('eligible') === 'on',
        legalBase: 'LC 214/2025',
        status: 'novo',
        lastCheck: '',
      });
      saveState(state);
      location.reload();
    });
  }
}

function attachPremisesHandlers(state) {
  const form = document.getElementById('premises-form');
  if (!form) return;
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const monthData = getCurrentMonthData(state);
    monthData.premises.ibsFull = num(data.get('ibsFull'));
    monthData.premises.cbsFull = num(data.get('cbsFull'));
    monthData.premises.reductionPct = num(data.get('reductionPct'));
    monthData.premises.creditMode = data.get('creditMode');
    saveState(state);
    location.reload();
  });
}

function init() {
  const state = loadState();
  ensureMonth(state, state.currentMonth);
  const page = document.body.dataset.page;
  const root = document.getElementById('app');
  const renderers = {
    home: renderHome,
    decision: renderDecision,
    costs: renderCosts,
    premises: renderPremises,
    annual: renderAnnual,
    reports: renderReports,
  };
  root.innerHTML = renderers[page](state);
  attachSharedHandlers(state);
  attachCostsHandlers(state);
  attachPremisesHandlers(state);
}

document.addEventListener('DOMContentLoaded', init);
