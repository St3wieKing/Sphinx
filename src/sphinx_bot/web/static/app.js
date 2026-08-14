const state = { symbol: "NQ", overview: null, payload: null, pine: "" };
const $ = (id) => document.getElementById(id);
const money = (v) => v == null ? "—" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(v);
const price = (v) => v == null ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const percent = (v) => v == null ? "—" : `${(Number(v) * 100).toFixed(1)}%`;
const number = (v, digits = 2) => v == null ? "—" : Number(v).toFixed(digits);
const dateET = (v, full = false) => v ? new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", month: "short", day: "2-digit", ...(full ? { year: "numeric" } : {}), hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(v)) + " ET" : "—";

function setText(id, value) { const node = $(id); if (node) node.textContent = value; }
function svg(tag, attrs = {}) { const node = document.createElementNS("http://www.w3.org/2000/svg", tag); Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v)); return node; }

async function getJSON(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function showView(name) {
  document.querySelectorAll(".view").forEach((node) => node.classList.toggle("active", node.id === `${name}-view`));
  document.querySelectorAll(".nav-tab").forEach((node) => node.classList.toggle("active", node.dataset.view === name));
}

function updateClock() {
  const now = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(new Date());
  setText("clock", `${now} ET`);
}

function updateSignal(payload) {
  const plan = payload.latest_signal;
  const action = payload.action;
  const orb = $("signal-orb");
  orb.className = `signal-orb ${action === "LONG" ? "long" : action === "SHORT" ? "short" : "wait"}`;
  setText("action", action);
  setText("action-copy", action === "WAIT" ? (plan ? `Last ${plan.direction.toLowerCase()} · ${payload.signal_age_bars} bars ago` : "No completed trigger") : "Fresh completed-bar trigger");
  setText("freshness", payload.fresh ? "FRESH" : "REPLAY");
  setText("score", plan ? `${number(plan.setup_score, 0)}/100` : "—");
  $("score-fill").style.width = plan ? `${Math.max(0, Math.min(100, plan.setup_score))}%` : "0";
  setText("entry", plan ? price(plan.raw_entry) : "—");
  setText("stop", plan ? price(plan.raw_stop) : "—");
  setText("tp1", plan ? price(plan.raw_target_1) : "—");
  setText("tp2", plan ? price(plan.raw_target_2) : "—");
  setText("rr", plan ? `${number(plan.expected_rr)}R` : "—");
  setText("regime", plan ? String(plan.regime || "unknown").replaceAll("_", " ").toUpperCase() : "—");
  setText("signal-note", payload.fresh ? "Trigger is fresh relative to the final completed replay bar. Confirm paper-risk controls before acting." : "WAIT means no fresh model trigger. The last setup remains plotted for forensic review; it is not a current call.");

  const checklist = $("checklist"); checklist.replaceChildren();
  if (!plan) { const row = document.createElement("div"); row.className = "empty-row"; row.textContent = "No completed setup in this replay."; checklist.append(row); }
  else (plan.passed_conditions || []).forEach((item) => { const row = document.createElement("div"); row.className = "check-row"; row.textContent = item; checklist.append(row); });
}

function renderPriceChart(payload, selectedPlan = payload.latest_signal) {
  const root = $("price-chart"); root.replaceChildren();
  const bars = payload.candles || [];
  if (!bars.length) return;
  const W = 900, H = 390, pad = { l: 8, r: 69, t: 13, b: 23 };
  const levels = selectedPlan ? [selectedPlan.raw_entry, selectedPlan.raw_stop, selectedPlan.raw_target_1, selectedPlan.raw_target_2].filter(Number.isFinite) : [];
  const lows = bars.map(b => b.low).concat(levels), highs = bars.map(b => b.high).concat(levels);
  let min = Math.min(...lows), max = Math.max(...highs); const margin = Math.max((max - min) * .08, .5); min -= margin; max += margin;
  const x = (i) => pad.l + i * (W - pad.l - pad.r) / Math.max(1, bars.length - 1);
  const y = (v) => pad.t + (max - v) * (H - pad.t - pad.b) / Math.max(.0001, max - min);

  for (let i = 0; i <= 5; i++) {
    const yy = pad.t + i * (H - pad.t - pad.b) / 5;
    root.append(svg("line", { x1: pad.l, y1: yy, x2: W - pad.r, y2: yy, class: "chart-grid" }));
    const label = svg("text", { x: W - pad.r + 8, y: yy + 3 }); label.textContent = price(max - i * (max - min) / 5); root.append(label);
  }
  const width = Math.max(1.6, Math.min(6, (W - pad.l - pad.r) / bars.length * .58));
  bars.forEach((bar, i) => {
    const up = bar.close >= bar.open, klass = up ? "candle-up" : "candle-down";
    root.append(svg("line", { x1: x(i), y1: y(bar.high), x2: x(i), y2: y(bar.low), class: `${klass} candle-wick` }));
    root.append(svg("rect", { x: x(i) - width / 2, y: Math.min(y(bar.open), y(bar.close)), width, height: Math.max(1, Math.abs(y(bar.open) - y(bar.close))), class: klass, rx: .4 }));
  });
  if (selectedPlan) {
    [["ENTRY", selectedPlan.raw_entry, "entry-line"], ["STOP", selectedPlan.raw_stop, "stop-line"], ["TP1", selectedPlan.raw_target_1, "target-line"], ["TP2", selectedPlan.raw_target_2, "target-line"]].forEach(([name, value, klass]) => {
      if (!Number.isFinite(value)) return; const yy = y(value);
      root.append(svg("line", { x1: pad.l, y1: yy, x2: W - pad.r, y2: yy, class: `level-line ${klass}` }));
      const label = svg("text", { x: pad.l + 5, y: yy - 4 }); label.textContent = `${name}  ${price(value)}`; label.style.fill = name === "STOP" ? "#ff6577" : name.startsWith("TP") ? "#62f2b0" : "#8ab8ff"; root.append(label);
    });
  }
  (payload.chart_signals || []).forEach((signal) => {
    const target = new Date(signal.timestamp).getTime(); let index = 0, distance = Infinity;
    bars.forEach((bar, i) => { const d = Math.abs(new Date(bar.timestamp).getTime() - target); if (d < distance) { distance = d; index = i; } });
    const long = signal.direction === "LONG", yy = long ? y(bars[index].low) + 13 : y(bars[index].high) - 13;
    const points = long ? `${x(index)-5},${yy+5} ${x(index)+5},${yy+5} ${x(index)},${yy-5}` : `${x(index)-5},${yy-5} ${x(index)+5},${yy-5} ${x(index)},${yy+5}`;
    root.append(svg("polygon", { points, class: `signal-marker ${long ? "long" : "short"}` }));
  });
  setText("chart-range", `${dateET(bars[0].timestamp)} — ${dateET(bars.at(-1).timestamp)}`);
}

function renderEquity(payload) {
  const root = $("equity-chart"); root.replaceChildren(); const points = payload.equity || []; if (points.length < 2) return;
  const W = 900, H = 155, pad = 7; const values = points.map(p => p.value); let min = Math.min(...values), max = Math.max(...values); if (min === max) { min -= 1; max += 1; }
  const x = i => pad + i * (W - 2 * pad) / (points.length - 1); const y = v => pad + (max - v) * (H - 2 * pad) / (max - min);
  const defs = svg("defs"); const grad = svg("linearGradient", { id: "equityGradient", x1: "0", y1: "0", x2: "0", y2: "1" }); grad.append(svg("stop", { offset: "0", "stop-color": "#62f2b0", "stop-opacity": ".45" }), svg("stop", { offset: "1", "stop-color": "#62f2b0", "stop-opacity": "0" })); defs.append(grad); root.append(defs);
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.value)}`).join(" ");
  root.append(svg("path", { d: `${path} L${x(points.length - 1)},${H} L${x(0)},${H} Z`, class: "equity-fill" })); root.append(svg("path", { d: path, class: "equity-line" }));
}

function renderMetrics(payload) {
  const m = payload.metrics; setText("m-trades", m.trade_count ?? "—"); setText("m-win", percent(m.win_rate)); setText("m-pf", number(m.profit_factor)); setText("m-exp", money(m.expectancy_per_trade)); setText("m-dd", percent(m.maximum_drawdown)); setText("m-cost", money(m.total_costs));
  setText("metric-context", payload.data_mode.includes("SYNTHETIC") ? "Synthetic · not market evidence" : "User replay · validate provenance");
}

function renderSignals(payload) {
  const tbody = $("signals-table"); tbody.replaceChildren(); const signals = payload.recent_signals || [];
  if (!signals.length) { const row = document.createElement("tr"); row.innerHTML = '<td colspan="9">No completed signals.</td>'; tbody.append(row); return; }
  signals.forEach((signal) => {
    const row = document.createElement("tr");
    const values = [dateET(signal.timestamp), signal.direction, price(signal.raw_entry), price(signal.raw_stop), price(signal.raw_target_1), price(signal.raw_target_2), `${number(signal.expected_rr)}R`, number(signal.setup_score, 0), signal.liquidity_target_id ? "Confirmed liquidity" : "1.66 extension"];
    values.forEach((value, index) => { const cell = document.createElement("td"); if (index === 1) { const span = document.createElement("span"); span.className = `side-pill ${String(value).toLowerCase()}`; span.textContent = value; cell.append(span); } else cell.textContent = value; row.append(cell); });
    row.addEventListener("click", () => { renderPriceChart(payload, signal); updateSelectedLevels(signal); document.querySelector(".chart-panel").scrollIntoView({ behavior: "smooth", block: "center" }); });
    tbody.append(row);
  });
}

function updateSelectedLevels(plan) { setText("entry", price(plan.raw_entry)); setText("stop", price(plan.raw_stop)); setText("tp1", price(plan.raw_target_1)); setText("tp2", price(plan.raw_target_2)); setText("rr", `${number(plan.expected_rr)}R`); }

async function loadInstrument(symbol) {
  state.symbol = symbol; document.querySelectorAll(".instrument").forEach(n => n.classList.toggle("active", n.dataset.symbol === symbol));
  const payload = await getJSON(`/api/instrument/${symbol}`); state.payload = payload;
  setText("data-mode", payload.data_mode.replaceAll("_", " ")); setText("as-of", dateET(payload.as_of, true)); setText("session", payload.config.session); setText("chart-title", `${symbol} · setup replay`); setText("config-fingerprint", `CONFIG ${payload.config.fingerprint.slice(0, 12).toUpperCase()}`);
  updateSignal(payload); renderPriceChart(payload); renderEquity(payload); renderMetrics(payload); renderSignals(payload);
}

function renderResearch(overview) {
  const root = $("research-content"); root.replaceChildren(); const report = overview.deep_report;
  if (!report) {
    setText("research-source", "No real-data deep report loaded");
    const items = [["NQ mode", overview.instruments.NQ.data_mode], ["MNQ mode", overview.instruments.MNQ.data_mode], ["Holdout", overview.holdout_status], ["Profitability", "UNDETERMINED"]];
    items.forEach(([label, value]) => { const box = document.createElement("div"), a = document.createElement("span"), b = document.createElement("strong"); a.textContent = label; b.textContent = value.replaceAll("_", " "); box.append(a, b); root.append(box); });
    const warning = document.createElement("p"); warning.textContent = "Attach licensed 2-minute NQ/MNQ data and run sphinx deep-backtest. Demo outcomes are intentionally excluded from research conclusions."; root.append(warning); return;
  }
  setText("research-source", `${report.instrument || "MULTI"} · ${report.status || "research"}`);
  const metrics = report.validation?.metrics || report.paired_summary?.instruments?.NQ || {};
  [["Validation trades", metrics.trade_count], ["Net after costs", money(metrics.net_pnl_after_costs)], ["Expectancy", money(metrics.expectancy_per_trade)], ["Profit factor", number(metrics.profit_factor)]].forEach(([label, value]) => { const box = document.createElement("div"), a = document.createElement("span"), b = document.createElement("strong"); a.textContent = label; b.textContent = value ?? "—"; box.append(a, b); root.append(box); });
  const warning = document.createElement("p"); warning.textContent = (report.warnings || ["Research output is not a guarantee."])[0]; root.append(warning);
}

async function loadPine() {
  const payload = await getJSON("/api/pine"); state.pine = payload.code; setText("pine-code", payload.code);
}

async function init() {
  updateClock(); setInterval(updateClock, 1000);
  document.querySelectorAll(".nav-tab").forEach(button => button.addEventListener("click", () => showView(button.dataset.view)));
  document.querySelectorAll(".instrument").forEach(button => button.addEventListener("click", () => loadInstrument(button.dataset.symbol).catch(showError)));
  $("copy-pine").addEventListener("click", async () => { try { await navigator.clipboard.writeText(state.pine); setText("copy-status", "Copied"); setTimeout(() => setText("copy-status", "Ready"), 1800); } catch { setText("copy-status", "Copy blocked"); } });
  $("download-pine").addEventListener("click", () => { const blob = new Blob([state.pine], { type: "text/plain" }); const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "sphinx_signal_indicator.pine"; link.click(); URL.revokeObjectURL(link.href); });
  try { state.overview = await getJSON("/api/overview"); renderResearch(state.overview); await Promise.all([loadInstrument("NQ"), loadPine()]); } catch (error) { showError(error); }
}

function showError(error) { console.error(error); setText("data-mode", "ENGINE ERROR"); setText("signal-note", String(error)); }

document.addEventListener("DOMContentLoaded", init);
