const state = {
  runtime: null,
  setup: null,
  plan: null,
  order: null,
  run: null,
  events: [],
  wallet: null,
  connected_wallet: null,
  privy_agent_wallet: null,
  metrics: null,
};

function $(selector) {
  return document.querySelector(selector);
}

function assetList(value) {
  return String(value || "")
    .split(/[,\n]/)
    .map((asset) => asset.trim().toUpperCase().replace("-PERP", ""))
    .filter(Boolean);
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) throw new Error(payload?.detail || response.statusText);
  return payload;
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("visible");
  window.setTimeout(() => el.classList.remove("visible"), 2800);
}

async function loadState() {
  const payload = await api("/api/state");
  Object.assign(state, payload);
  try {
    state.metrics = await api("/api/portfolio/metrics");
  } catch (error) {
    state.metrics = null;
    console.warn("Portfolio metrics unavailable", error);
  }
  render();
}

function render() {
  renderRuntime();
  renderSetup();
  renderConnectedWallet();
  renderPortfolio();
  renderProposal();
  renderEvents();
  renderRobot();
}

function renderRuntime() {
  const runtime = state.runtime || {};
  $("#ui-mode").value = runtime.ui_mode || "human";
  $("#max-order").value = runtime.max_order_usdc || 100;
  $("#allowed-assets").value = (runtime.allowed_assets || []).join(",");
  $("#watchlist").value = (runtime.watchlist || []).join(",");
  for (const button of document.querySelectorAll("[data-network]")) {
    button.classList.toggle("active", button.dataset.network === (runtime.network || "testnet"));
  }
  document.body.dataset.uiMode = runtime.ui_mode || "human";
  document.body.dataset.network = runtime.network || "testnet";
  const networkStatus = $("#network-status");
  networkStatus.textContent = runtime.network === "prodnet" ? "prodnet guarded" : "testnet auto";
  networkStatus.className = runtime.network === "prodnet" ? "prodnet" : "testnet";
}

function renderSetup() {
  const setup = state.setup || {};
  $("#claude-status").textContent = `Claude: ${setup.anthropic_configured ? "ready" : "fallback"}`;
  let hyperliquidStatus = "missing creds";
  if (setup.hyperliquid_configured) {
    hyperliquidStatus = "ready";
  } else if (setup.privy_execution_enabled && setup.privy_server_configured) {
    hyperliquidStatus = "Privy ready";
  }
  $("#hyperliquid-status").textContent = `Hyperliquid: ${hyperliquidStatus}`;
  const privyStatus = $("#privy-status");
  if (privyStatus && privyStatus.textContent === "checking") {
    privyStatus.textContent = setup.privy_configured ? "configured" : "missing config";
  }
}

function renderConnectedWallet() {
  const target = $("#privy-wallet-summary");
  if (!target) return;
  const wallet = state.connected_wallet;
  const agent = state.privy_agent_wallet;
  const rows = [];
  if (wallet) {
    rows.push(["User wallet", maskAddress(wallet.address)]);
    rows.push(["Source", wallet.source]);
    rows.push(["Email", wallet.email || "not shared"]);
  } else {
    rows.push(["User wallet", "No wallet connected"]);
  }
  if (agent) {
    rows.push(["Master", maskAddress(agent.master_wallet_address)]);
    rows.push(["Agent", maskAddress(agent.agent_wallet_address)]);
    rows.push(["Registered", agent.registered ? "yes" : "no"]);
  }
  target.innerHTML = rows
    .map(([label, value]) => `<div><span>${label}</span><b>${value}</b></div>`)
    .join("");
}

function renderPortfolio() {
  const metrics = state.metrics || {};
  const equity = Number(metrics.equity_usdc || 0);
  const unrealized = Number(metrics.unrealized_pnl_usdc || 0);
  const realized = Number(metrics.realized_pnl_usdc || 0);
  const totalPnl = unrealized + realized;
  const pnlClass = totalPnl > 0 ? "gain" : totalPnl < 0 ? "loss" : "neutral";
  $("#portfolio-value").textContent = money(equity || 10180, false);
  const pnl = $("#portfolio-pnl");
  pnl.className = `portfolio-delta ${pnlClass}`;
  pnl.textContent = `${signedMoney(totalPnl)} total PnL`;
  $("#hero-stats").innerHTML = [
    ["Alpha", number(metrics.alpha, 6)],
    ["Beta", number(metrics.beta, 4)],
    ["VaR 95", money(metrics.value_at_risk_95)],
  ]
    .map(([label, value]) => `<div><span>${label}</span><b>${value}</b></div>`)
    .join("");
  $("#metrics-strip").innerHTML = [
    ["Exposure", signedNumber(metrics.delta_like_exposure, 4), semanticClass(metrics.delta_like_exposure)],
    ["Drawdown", percent(metrics.max_drawdown), "loss"],
    ["Sharpe", number(metrics.sharpe_like, 4), semanticClass(metrics.sharpe_like)],
    ["BTC corr", number(metrics.btc_correlation, 4), "neutral"],
  ]
    .map(([label, value, className]) => `<article class="${className}"><span>${label}</span><b>${value}</b></article>`)
    .join("");
}

function renderProposal() {
  const plan = state.plan;
  const decision = plan?.execution_decision || "no_proposal";
  const decisionPill = $("#decision-pill");
  decisionPill.textContent = decision.replaceAll("_", " ");
  decisionPill.className = `pill ${decisionClass(decision)}`;
  $("#ticket-title").textContent = plan ? `${plan.asset}-PERP ${plan.side}`.toUpperCase() : "Awaiting plan";
  const confidence = $("#confidence");
  confidence.textContent = plan ? `${Math.round((plan.confidence || 0) * 100)}%` : "0%";
  confidence.className = `pill ${plan && plan.confidence >= 0.7 ? "gain" : "neutral"}`;
  if (!plan) {
    $("#human-summary").classList.add("empty");
    $("#human-summary").innerHTML = "<h3>No trade idea yet</h3><p>Run analysis or a proactive scan to create the first proposal.</p>";
    $("#ticket").innerHTML = "";
    return;
  }
  $("#human-summary").classList.remove("empty");
  $("#human-summary").classList.toggle("short", plan.side === "short");
  $("#human-summary").innerHTML = `
    <h3><span>${plan.side.toUpperCase()}</span> ${plan.asset}-PERP</h3>
    <p>${plan.thesis || plan.rationale}</p>
    <div class="summary-grid">
      <div><span>Why</span><b>${(plan.evidence || []).slice(0, 2).join(" ") || "Agent evidence pending."}</b></div>
      <div><span>Risk</span><b>Max loss ${money(plan.max_loss_usdc)} with stop at ${number(plan.stop_loss)}</b></div>
      <div><span>Action</span><b>${actionText(plan)}</b></div>
    </div>
    <ul>${(plan.invalidation_criteria || []).slice(0, 4).map((item) => `<li>${item}</li>`).join("")}</ul>
  `;
  $("#ticket").innerHTML = [
    ["Network", plan.network, plan.network],
    ["Entry", number(plan.entry_price), "neutral"],
    ["Stop loss", number(plan.stop_loss), "loss"],
    ["Take profit", number(plan.take_profit), "gain"],
    ["Size", money(plan.size_usdc), "neutral"],
    ["Leverage", `${plan.leverage}x`, "neutral"],
    ["Status", plan.execution_message || plan.execution_decision, decisionClass(plan.execution_decision)],
  ]
    .map(([label, value, className]) => `<div class="${className}"><span>${label}</span><b>${value}</b></div>`)
    .join("");
}

function actionText(plan) {
  if (plan.execution_decision === "auto_executed") return "Auto-executed on testnet.";
  if (plan.execution_decision === "waiting_confirmation") return "Waiting for prodnet confirmation.";
  if (plan.execution_decision === "blocked") return plan.execution_message || "Blocked by guardrails.";
  if (plan.execution_decision === "rejected") return "Rejected.";
  return "Review and execute or reject.";
}

function renderEvents() {
  const events = state.events || [];
  $("#events-list").innerHTML = events.length
    ? events
        .slice()
        .reverse()
        .map(
          (event) => `
            <div class="event ${event.level}">
              <time>${new Date(event.created_at).toLocaleTimeString()}</time>
              <b>${event.level}</b>
              <p>${event.message}</p>
            </div>
          `,
        )
        .join("")
    : "<div class='event'><p>No events yet.</p></div>";
}

function renderRobot() {
  $("#raw-output").textContent = pretty({
    runtime: state.runtime,
    setup: state.setup,
    plan: state.plan,
    order: state.order,
    run: state.run,
    wallet: state.wallet,
    connected_wallet: state.connected_wallet,
    privy_agent_wallet: state.privy_agent_wallet,
    metrics: state.metrics,
    events: state.events,
  });
}

function money(value, includeCurrency = true) {
  const formatted = Number(value || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return includeCurrency ? `${formatted} USDC` : formatted;
}

function signedMoney(value) {
  const numeric = Number(value || 0);
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${numeric.toFixed(2)} USDC`;
}

function number(value, maximumFractionDigits = 4) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits });
}

function signedNumber(value, maximumFractionDigits = 4) {
  const numeric = Number(value || 0);
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${number(numeric, maximumFractionDigits)}`;
}

function percent(value) {
  return `${(Number(value || 0) * 100).toFixed(2)}%`;
}

function semanticClass(value) {
  const numeric = Number(value || 0);
  if (numeric > 0) return "gain";
  if (numeric < 0) return "loss";
  return "neutral";
}

function decisionClass(decision) {
  if (decision === "auto_executed" || decision === "proposed") return "gain";
  if (decision === "blocked" || decision === "rejected") return "loss";
  if (decision === "waiting_confirmation") return "warning";
  return "neutral";
}

function maskAddress(address) {
  if (!address || address.length <= 12) return address || "";
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

async function saveRuntime(partial = {}) {
  const payload = {
    network: state.runtime?.network || "testnet",
    ui_mode: $("#ui-mode").value,
    execution_policy: "auto_testnet_confirm_prodnet",
    watchlist: assetList($("#watchlist").value),
    allowed_assets: assetList($("#allowed-assets").value),
    max_order_usdc: Number($("#max-order").value),
    require_prodnet_phrase: true,
    ...partial,
  };
  state.runtime = await api("/api/settings/runtime", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await loadState();
  toast("Runtime updated");
}

async function analyze(event) {
  event.preventDefault();
  const result = await api("/api/agent/analyze", {
    method: "POST",
    body: JSON.stringify({
      asset: $("#asset-input").value,
      context: $("#context-input").value || null,
    }),
  });
  state.plan = result.plan;
  await loadState();
  toast("Analysis complete");
}

async function scan() {
  const result = await api("/api/agent/proactive-scan", { method: "POST" });
  state.plan = result.plan;
  await loadState();
  toast("Proactive scan complete");
}

async function executeTrade() {
  if (!state.plan?.id) throw new Error("No trade plan to execute.");
  const result = await api(`/api/trades/${state.plan.id}/execute`, {
    method: "POST",
    body: JSON.stringify({
      confirmed: $("#execute-confirm").checked,
      confirmation_phrase: $("#mainnet-phrase").value || null,
    }),
  });
  state.plan = result.plan;
  await loadState();
  toast("Execution submitted");
}

async function rejectTrade() {
  if (!state.plan?.id) throw new Error("No trade plan to reject.");
  state.plan = await api(`/api/trades/${state.plan.id}/reject`, { method: "POST" });
  await loadState();
  toast("Trade rejected");
}

async function loadWallet() {
  state.wallet = await api("/api/wallet");
  $("#wallet-summary").innerHTML = [
    ["Collateral", money(state.wallet.collateral_usdc)],
    ["Margin", money(state.wallet.total_margin_used_usdc)],
    ["Exposure", money(state.wallet.exposure_usdc)],
    ["Positions", state.wallet.open_positions.length],
  ]
    .map(([label, value]) => `<div><span>${label}</span><b>${value}</b></div>`)
    .join("");
  renderRobot();
  toast("Wallet refreshed");
}

async function setupPrivyAgent() {
  state.privy_agent_wallet = await api("/api/privy/agent-wallet", { method: "POST" });
  await loadState();
  toast("Privy agent wallet ready");
}

document.addEventListener("click", async (event) => {
  const networkButton = event.target.closest("[data-network]");
  if (networkButton) {
    try {
      await saveRuntime({ network: networkButton.dataset.network });
    } catch (error) {
      toast(error.message);
    }
    return;
  }
  const action = event.target.dataset.action;
  if (!action) return;
  try {
    if (action === "save-settings") await saveRuntime();
    if (action === "scan") await scan();
    if (action === "execute") await executeTrade();
    if (action === "reject") await rejectTrade();
    if (action === "wallet") await loadWallet();
    if (action === "privy-setup-agent") await setupPrivyAgent();
    if (action === "events" || action === "refresh") await loadState();
  } catch (error) {
    toast(error.message);
  }
});

$("#ui-mode").addEventListener("change", async () => {
  try {
    await saveRuntime({ ui_mode: $("#ui-mode").value });
  } catch (error) {
    toast(error.message);
  }
});

$("#analyze-form").addEventListener("submit", async (event) => {
  try {
    await analyze(event);
  } catch (error) {
    toast(error.message);
  }
});

loadState().catch((error) => toast(error.message));

window.hyperDemo = {
  api,
  loadState,
  state,
  toast,
  maskAddress,
};
