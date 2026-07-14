const colors = { BTCUSDT: '#f59e0b', BNBUSDT: '#a78bfa', ETHUSDT: '#60a5fa', SOLUSDT: '#2dd4bf' };
const fmtUsd = value => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: value >= 1000 ? 0 : 2 }).format(value);
const fmtPct = value => `${value.toFixed(1)}%`;
const layout = (extra = {}) => ({ paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', font: { color: '#dce6ff' }, margin: { l: 60, r: 25, t: 25, b: 45 }, xaxis: { gridcolor: '#25304d', zerolinecolor: '#25304d' }, yaxis: { gridcolor: '#25304d', zerolinecolor: '#25304d' }, legend: { orientation: 'h', y: 1.1 }, ...extra });

function metrics(data) {
  const records = data.records;
  const values = records.map(row => row.portfolio_value);
  const returns = values.slice(1).map((value, i) => (value / values[i] - 1) * 100);
  let peak = values[0], maxDd = 0;
  const drawdowns = values.map(value => { peak = Math.max(peak, value); const dd = (value / peak - 1) * 100; maxDd = Math.min(maxDd, dd); return dd; });
  const last = records.at(-1);
  const returnPct = (last.portfolio_value / last.injected - 1) * 100;
  const months = records.length;
  const annual = (Math.pow(last.portfolio_value / last.injected, 12 / months) - 1) * 100;
  const avg = returns.reduce((a, b) => a + b, 0) / returns.length;
  const variance = returns.reduce((a, value) => a + (value - avg) ** 2, 0) / returns.length;
  const sharpe = variance ? avg / Math.sqrt(variance) * Math.sqrt(12) : 0;
  const positives = returns.filter(value => value > 0).reduce((a, b) => a + b, 0);
  const negatives = returns.filter(value => value < 0).reduce((a, b) => a + Math.abs(b), 0);
  return { last, values, returns, drawdowns, maxDd, returnPct, annual, sharpe, profitFactor: negatives ? positives / negatives : 0, winRate: returns.filter(value => value > 0).length / returns.length * 100 };
}

function render(data) {
  const { records, events, config } = data;
  const stat = metrics(data);
  const pairs = config.pairs.map(pair => pair.symbol);
  const dates = records.map(row => row.date);
  const select = document.querySelector('#pair-select');
  const tabs = document.querySelector('#pair-tabs');
  select.replaceChildren(...pairs.map(symbol => new Option(symbol, symbol)));
  select.value = pairs[0];
  tabs.replaceChildren(...pairs.map(symbol => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = symbol;
    button.dataset.symbol = symbol;
    button.addEventListener('click', () => choosePair(symbol));
    return button;
  }));
  const choosePair = symbol => {
    select.value = symbol;
    tabs.querySelectorAll('button').forEach(button => button.classList.toggle('active', button.dataset.symbol === symbol));
    renderPrice(data, symbol);
  };
  select.onchange = event => choosePair(event.currentTarget.value);
  document.querySelector('#report-meta').textContent = `${records[0].date} to ${records.at(-1).date} | ${records.length} monthly candles | generated ${new Date(data.generated_at).toLocaleString()}`;
  document.querySelector('#notice').className = 'notice success';
  document.querySelector('#notice').textContent = `Loaded ${records.length} monthly records and ${events.length} trade events.`;
  document.querySelector('#metrics').innerHTML = [
    ['Portfolio', fmtUsd(stat.last.portfolio_value)], ['External investment', fmtUsd(stat.last.injected)], ['Total return', fmtPct(stat.returnPct)], ['Annualized', fmtPct(stat.annual)], ['Max drawdown', fmtPct(stat.maxDd)], ['Sharpe', stat.sharpe.toFixed(2)], ['Profit factor', stat.profitFactor.toFixed(2)], ['Idle reserve', fmtUsd(stat.last.usdt)],
  ].map(([label, value]) => `<div class="metric"><span>${label}</span><strong>${value}</strong></div>`).join('');
  const tiers = (config.drawdown_tiers || []).map(tier => `${tier.minimum_drawdown_pct}% DD -> ${tier.reserve_percentage}% reserve`).join(' | ');
  const minimums = config.min_order_usdt || {};
  document.querySelector('#strategy').innerHTML = `<b>Monthly investment:</b> ${fmtUsd(config.monthly_total)}. <b>Minimum orders:</b> ${pairs.map(symbol => `${symbol} ${fmtUsd(minimums[symbol] || 0)}`).join(', ')}. Orders below the minimum are skipped. <b>Take profit:</b> sell ${(config.tp_percentage * 100).toFixed(0)}% when price reaches ${config.tp_multiplier}x the prior sell ATH. <b>Drawdown reinvestment:</b> ${tiers || 'legacy progressive settings'}. <b>Pairs:</b> ${config.pairs.map(pair => `${pair.symbol} (${fmtUsd(pair.monthly_invest)}/mo)`).join(' | ')}.`;

  Plotly.react('equity-chart', [
    { x: dates, y: records.map(row => row.injected), name: 'Cost basis', mode: 'lines', line: { color: '#94a3b8', dash: 'dot' } },
    { x: dates, y: stat.values, name: 'Portfolio', mode: 'lines', line: { color: '#f8fafc', width: 3 } },
    ...pairs.map(symbol => ({
      x: dates,
      y: records.map(row => row.positions[symbol].value),
      name: symbol,
      mode: 'lines',
      line: { color: colors[symbol] || '#60a5fa', width: 2 },
    })),
  ], layout({ yaxis: { gridcolor: '#25304d', tickprefix: '$' }, legend: { orientation: 'h', y: 1.12, itemclick: 'toggle', itemdoubleclick: 'toggleothers' } }), { responsive: true });
  const pairFlows = Object.fromEntries(pairs.map(symbol => [symbol, { buys: 0, sells: 0 }]));
  const pairProfit = Object.fromEntries(pairs.map(symbol => [symbol, []]));
  const eventsByDate = Object.groupBy ? Object.groupBy(events, event => event.date) : events.reduce((groups, event) => { (groups[event.date] ||= []).push(event); return groups; }, {});
  for (const date of dates) {
    for (const event of eventsByDate[date] || []) {
      if (!pairFlows[event.symbol]) continue;
      if (event.type === 'sell') pairFlows[event.symbol].sells += event.amount;
      else pairFlows[event.symbol].buys += event.amount;
    }
    const record = records.find(row => row.date === date);
    for (const symbol of pairs) pairProfit[symbol].push(record.positions[symbol].value + pairFlows[symbol].sells - pairFlows[symbol].buys);
  }
  const pairProfitTraces = [];
  for (const pair of config.pairs) {
    const symbol = pair.symbol;
    const color = colors[symbol] || '#60a5fa';
    pairProfitTraces.push({
      x: dates,
      y: pairProfit[symbol],
      name: `${symbol} P&L`,
      mode: 'lines',
      line: { color, width: 2 },
      fill: 'tozeroy',
      hovertemplate: '%{x}<br>' + symbol + ' P&L: $%{y:,.2f}<extra></extra>',
    });
    pairProfitTraces.push({
      x: dates,
      y: dates.map((_, index) => (index + 1) * pair.monthly_invest),
      name: `${symbol} cost basis`,
      mode: 'lines',
      line: { color, width: 1.5, dash: 'dash' },
      hovertemplate: '%{x}<br>' + symbol + ' cost basis: $%{y:,.2f}<extra></extra>',
    });
  }
  Plotly.react('pair-profit-chart', pairProfitTraces, layout({ yaxis: { tickprefix: '$' }, shapes: [{ type: 'line', x0: dates[0], x1: dates.at(-1), y0: 0, y1: 0, line: { color: '#94a3b8', dash: 'dot' } }], legend: { orientation: 'h', y: 1.12, itemclick: 'toggle', itemdoubleclick: 'toggleothers' } }), { responsive: true });
  Plotly.react('drawdown-chart', [{ x: dates, y: stat.drawdowns, type: 'scatter', mode: 'lines', fill: 'tozeroy', line: { color: '#ff6b7a' }, fillcolor: 'rgba(255,107,122,.22)' }], layout({ yaxis: { ticksuffix: '%' } }), { responsive: true });
  Plotly.react('allocation-chart', [
    ...pairs.map(symbol => ({ x: dates, y: records.map(row => row.positions[symbol].value), stackgroup: 'one', name: symbol, mode: 'lines', line: { color: colors[symbol] || '#60a5fa' } })),
    { x: dates, y: records.map(row => row.usdt), stackgroup: 'one', name: 'USDT reserve', mode: 'lines', line: { color: '#42d392' } },
  ], layout({ yaxis: { tickprefix: '$' } }), { responsive: true });
  Plotly.react('returns-chart', [{ x: dates.slice(1), y: stat.returns, type: 'bar', marker: { color: stat.returns.map(value => value >= 0 ? '#42d392' : '#ff6b7a') } }], layout({ yaxis: { ticksuffix: '%' } }), { responsive: true });
  const eventTypes = ['buy', 'dip', 'sell'];
  const eventLabels = { buy: 'Monthly DCA', dip: 'Dip reinvestment', sell: 'Sell proceeds' };
  const eventColors = { buy: '#42d392', dip: '#60a5fa', sell: '#ff6b7a' };
  const monthlyFlow = type => dates.map(date => events.filter(event => event.date === date && event.type === type).reduce((sum, event) => sum + event.amount, 0));
  Plotly.react('events-chart', [
    ...eventTypes.map(type => ({ x: dates, y: monthlyFlow(type), name: eventLabels[type], type: 'bar', marker: { color: eventColors[type] }, hovertemplate: '%{x}<br>' + eventLabels[type] + ': $%{y:,.2f}<extra></extra>' })),
    { x: dates, y: records.map(row => row.usdt), name: 'USDT reserve', mode: 'lines', yaxis: 'y2', line: { color: '#f8fafc', width: 2 }, hovertemplate: '%{x}<br>Reserve: $%{y:,.2f}<extra></extra>' },
  ], layout({ barmode: 'group', yaxis: { tickprefix: '$' }, yaxis2: { title: 'Reserve', tickprefix: '$', overlaying: 'y', side: 'right', gridcolor: 'transparent' } }), { responsive: true });
  choosePair(select.value);
  const recordByDate = Object.fromEntries(records.map(record => [record.date, record]));
  document.querySelector('#events-table').innerHTML = [...events].reverse().map(event => {
    const record = recordByDate[event.date];
    const portfolioValue = record?.portfolio_value;
    const externalInvestment = record?.injected;
    return `<tr><td>${event.date}</td><td>${event.symbol}</td><td class="${event.type}">${event.type}</td><td>${fmtUsd(event.price)}</td><td>${fmtUsd(event.amount)}</td><td>${event.drawdown_pct == null ? '-' : `${event.drawdown_pct.toFixed(1)}%`}</td><td>${event.reinvest_pct == null ? '-' : `${event.reinvest_pct.toFixed(0)}%`}</td><td>${externalInvestment == null ? '-' : fmtUsd(externalInvestment)}</td><td>${portfolioValue == null ? '-' : fmtUsd(portfolioValue)}</td></tr>`;
  }).join('');
}

function renderPrice(data, symbol) {
  const eventTrace = type => data.events.filter(event => event.symbol === symbol && event.type === type);
  const markers = { buy: { name: 'DCA buy', color: '#42d392', symbol: 'triangle-up', size: 8 }, dip: { name: 'Dip buy', color: '#60a5fa', symbol: 'triangle-up', size: 10 }, sell: { name: 'Sell', color: '#ff6b7a', symbol: 'triangle-down', size: 11 } };
  const traces = [{ x: data.records.map(row => row.date), y: data.records.map(row => row.positions[symbol].close), name: symbol, mode: 'lines', line: { color: colors[symbol] || '#60a5fa', width: 2 } }];
  for (const type of Object.keys(markers)) { const points = eventTrace(type), style = markers[type]; traces.push({ x: points.map(point => point.date), y: points.map(point => point.price), customdata: points.map(point => [point.amount, point.drawdown_pct, point.reinvest_pct]), name: style.name, mode: 'markers', marker: { color: style.color, symbol: style.symbol, size: points.map(point => Math.max(style.size, Math.min(32, Math.sqrt(point.amount) * 2.2))), sizemode: 'diameter' }, hovertemplate: '%{x}<br>Price: $%{y:,.2f}<br>USDT amount: $%{customdata[0]:,.2f}<br>ATH drawdown: %{customdata[1]:.1f}%<br>Reserve rate: %{customdata[2]:.0f}%<extra>' + style.name + '</extra>' }); }
  const chart = document.querySelector('#price-chart');
  if (chart.data) Plotly.purge(chart);
  Plotly.newPlot(chart, traces, layout({ title: { text: `${symbol}: marker size represents USDT invested or sold`, font: { size: 12, color: '#93a4c7' } }, yaxis: { tickprefix: '$' } }), { responsive: true });
}

async function loadDefault() {
  try { const response = await fetch('backtest-results.json'); if (!response.ok) throw new Error('No result file yet'); render(await response.json()); } catch { document.querySelector('#notice').className = 'notice'; document.querySelector('#notice').innerHTML = 'Run <code>python3 run_backtest.py</code>, then refresh. If you opened this file directly, use <b>Load JSON</b> or start <code>python3 -m http.server 8000</code>.'; }
}
document.querySelector('#file-input').addEventListener('change', event => { const file = event.target.files[0]; if (!file) return; const reader = new FileReader(); reader.onload = () => render(JSON.parse(reader.result)); reader.readAsText(file); });
loadDefault();
