const state = {
  runtime: null,
  setup: null,
  plan: null,
  order: null,
  run: null,
  events: [],
  wallet: null,
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
  render();
}

function render() {
  renderRuntime();
  renderSetup();
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
  $("#network-status").textContent = runtime.network === "prodnet" ? "prodnet guarded" : "testnet auto";
}

function renderSetup() {
  const setup = state.setup || {};
  $("#claude-status").textContent = `Claude: ${setup.anthropic_configured ? "ready" : "fallback"}`;
  $("#hyperliquid-status").textContent = `Hyperliquid: ${setup.hyperliquid_configured ? "ready" : "missing creds"}`;
}

function renderProposal() {
  const plan = state.plan;
  $("#decision-pill").textContent = plan?.execution_decision?.replaceAll("_", " ") || "no proposal";
  $("#ticket-title").textContent = plan ? `${plan.asset}-PERP ${plan.side}`.toUpperCase() : "Awaiting plan";
  $("#confidence").textContent = plan ? `${Math.round((plan.confidence || 0) * 100)}%` : "0%";
  if (!plan) {
    $("#human-summary").innerHTML = "<h3>No trade idea yet</h3><p>Run analysis or a proactive scan to create the first proposal.</p>";
    $("#ticket").innerHTML = "";
    return;
  }
  $("#human-summary").classList.remove("empty");
  $("#human-summary").innerHTML = `
    <h3>${plan.side.toUpperCase()} ${plan.asset}-PERP</h3>
    <p>${plan.thesis || plan.rationale}</p>
    <div class="summary-grid">
      <div><span>Why</span><b>${(plan.evidence || []).slice(0, 2).join(" ") || "Agent evidence pending."}</b></div>
      <div><span>Risk</span><b>Max loss ${money(plan.max_loss_usdc)} with stop at ${number(plan.stop_loss)}</b></div>
      <div><span>Action</span><b>${actionText(plan)}</b></div>
    </div>
    <ul>${(plan.invalidation_criteria || []).slice(0, 4).map((item) => `<li>${item}</li>`).join("")}</ul>
  `;
  $("#ticket").innerHTML = [
    ["Network", plan.network],
    ["Entry", number(plan.entry_price)],
    ["Stop loss", number(plan.stop_loss)],
    ["Take profit", number(plan.take_profit)],
    ["Size", money(plan.size_usdc)],
    ["Leverage", `${plan.leverage}x`],
    ["Status", plan.execution_message || plan.execution_decision],
  ]
    .map(([label, value]) => `<div><span>${label}</span><b>${value}</b></div>`)
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
    events: state.events,
  });
}

function money(value) {
  return `${Number(value || 0).toFixed(2)} USDC`;
}

function number(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 4 });
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
