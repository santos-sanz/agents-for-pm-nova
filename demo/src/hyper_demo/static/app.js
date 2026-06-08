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
  screen: "trading",
  marketAssets: [],
  assetSearch: {
    allowed: "",
    watchlist: "",
  },
  assetSelections: {
    allowed: [],
    watchlist: [],
  },
};

const DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "HYPE"];
const AGENT_NAME = "HyperClaude";

function $(selector) {
  return document.querySelector(selector);
}

function assetList(value) {
  return String(value || "")
    .split(/[,\n]/)
    .map(normalizeAssetSymbol)
    .filter(Boolean);
}

function normalizeAssetSymbol(value) {
  const cleaned = String(value || "").trim().replace("-PERP", "");
  if (!cleaned) return "";
  if (!cleaned.includes(":")) return cleaned.toUpperCase();
  const [dex, symbol] = cleaned.split(":", 2);
  return `${dex.toLowerCase()}:${symbol.toUpperCase()}`;
}

function uniqueAssets(value) {
  return [...new Set(assetList(value))];
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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
  try {
    state.marketAssets = await api("/api/markets/assets");
  } catch (error) {
    state.marketAssets = [];
    console.warn("Hyperliquid assets unavailable", error);
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
}

function renderRuntime() {
  const runtime = state.runtime || {};
  $("#max-order").value = runtime.max_order_usdc || 100;
  const syncAssetLists = runtime.sync_asset_lists !== false;
  const syncAssetListsInput = $("#sync-asset-lists");
  if (syncAssetListsInput) syncAssetListsInput.checked = syncAssetLists;
  const runtimeAllowedAssets = runtime.allowed_assets?.length ? runtime.allowed_assets : DEFAULT_ASSETS;
  const runtimeWatchlist = runtime.watchlist?.length ? runtime.watchlist : DEFAULT_ASSETS;
  const syncedAssets = uniqueAssets(runtimeAllowedAssets.length ? runtimeAllowedAssets.join(",") : runtimeWatchlist.join(","));
  state.assetSelections.allowed = syncAssetLists ? syncedAssets : uniqueAssets(runtimeAllowedAssets.join(","));
  state.assetSelections.watchlist = syncAssetLists ? syncedAssets : uniqueAssets(runtimeWatchlist.join(","));
  if (!state.assetSelections.allowed.length) state.assetSelections.allowed = [...DEFAULT_ASSETS];
  if (!state.assetSelections.watchlist.length) state.assetSelections.watchlist = [...DEFAULT_ASSETS];
  renderAssetPicker("allowed");
  renderAssetPicker("watchlist");
  for (const button of document.querySelectorAll("[data-network]")) {
    button.classList.toggle("active", button.dataset.network === (runtime.network || "testnet"));
  }
  document.body.dataset.uiMode = "human";
  document.body.dataset.network = runtime.network || "testnet";
  const networkStatus = $("#network-status");
  networkStatus.textContent = runtime.network === "prodnet" ? "mainnet guarded" : "testnet auto";
  networkStatus.className = runtime.network === "prodnet" ? "prodnet" : "testnet";
  const settingsNetworkPill = $("#settings-network-pill");
  if (settingsNetworkPill) {
    settingsNetworkPill.textContent = runtime.network === "prodnet" ? "mainnet guarded" : "testnet auto";
    settingsNetworkPill.className = `pill ${runtime.network === "prodnet" ? "warning" : "gain"}`;
  }
  document.body.dataset.assetSync = syncAssetLists ? "on" : "off";
  renderScreen();
}

function assetMeta(symbol) {
  return state.marketAssets.find((asset) => asset.symbol === symbol);
}

function assetIcon(symbol, iconUrl = null) {
  const safeSymbol = escapeHtml(symbol);
  const safeUrl = escapeHtml(iconUrl || assetMeta(symbol)?.icon_url || "");
  return `
    <span class="asset-icon">
      ${safeUrl ? `<img src="${safeUrl}" alt="" loading="lazy" />` : ""}
      <span>${safeSymbol.slice(0, 2)}</span>
    </span>
  `;
}

function renderAssetPicker(kind) {
  const inputId = kind === "allowed" ? "allowed-assets" : "watchlist";
  const chipsId = kind === "allowed" ? "allowed-assets-chips" : "watchlist-chips";
  const input = $(`#${inputId}`);
  const chips = $(`#${chipsId}`);
  if (!input || !chips) return;
  const assets = uniqueAssets((state.assetSelections[kind] || []).join(","));
  state.assetSelections[kind] = assets;
  input.value = assets.join(",");
  chips.innerHTML = assets.length
    ? assets
        .map(
          (asset) => `
            <button type="button" class="asset-chip" data-asset-remove="${kind}" data-asset="${asset}">
              ${assetIcon(asset)}
              <span>${escapeHtml(asset)}</span>
              <b aria-label="Remove ${escapeHtml(asset)}">Remove</b>
            </button>
          `,
        )
        .join("")
    : "<span class='empty-assets'>No assets selected</span>";

  for (const button of document.querySelectorAll(`[data-asset-toggle="${kind}"]`)) {
    button.classList.toggle("active", assets.includes(button.dataset.asset));
  }
  for (const button of chips.querySelectorAll("[data-asset-remove]")) {
    button.addEventListener("click", () => removeAsset(kind, button.dataset.asset));
  }
  renderAssetOptions(kind);
}

function renderAssetOptions(kind) {
  const targetId = kind === "allowed" ? "allowed-asset-options" : "watchlist-asset-options";
  const target = $(`#${targetId}`);
  if (!target) return;
  const selected = new Set(state.assetSelections[kind] || []);
  const query = String(state.assetSearch[kind] || "").trim().toUpperCase();
  target.hidden = !query;
  if (!query) {
    target.innerHTML = "";
    return;
  }
  const source = state.marketAssets.length
    ? state.marketAssets
    : uniqueAssets("BTC,ETH,SOL,HYPE").map((symbol) => ({ symbol, max_leverage: 0, mark_price: null, delisted: false }));
  const filtered = source
    .filter((asset) => !asset.delisted)
    .filter((asset) => asset.symbol.toUpperCase().includes(query))
    .slice(0, 36);
  target.innerHTML = filtered.length
    ? filtered
        .map((asset) => {
          const active = selected.has(asset.symbol);
          const leverage = asset.max_leverage ? `${asset.max_leverage}x` : "perp";
          const price = asset.mark_price ? compactPrice(asset.mark_price) : "live";
          return `
            <button type="button" class="asset-option ${active ? "active" : ""}" data-asset-toggle="${kind}" data-asset="${asset.symbol}">
              ${assetIcon(asset.symbol, asset.icon_url)}
              <span>
                <b>${escapeHtml(asset.symbol)}</b>
                <small>${escapeHtml(leverage)} · ${escapeHtml(price)}</small>
              </span>
            </button>
          `;
        })
        .join("")
    : "<span class='empty-assets'>No matching Hyperliquid markets</span>";
  for (const image of target.querySelectorAll(".asset-icon img")) {
    image.addEventListener("error", () => {
      image.remove();
    });
  }
}

function setAssetList(kind, assets) {
  const next = uniqueAssets(assets.join(","));
  const shouldSync = isAssetSyncEnabled();
  const kinds = shouldSync ? ["allowed", "watchlist"] : [kind];
  for (const targetKind of kinds) {
    const inputId = targetKind === "allowed" ? "allowed-assets" : "watchlist";
    const input = $(`#${inputId}`);
    if (!input) continue;
    state.assetSelections[targetKind] = next;
    input.value = next.join(",");
  }
  renderAssetPicker("allowed");
  renderAssetPicker("watchlist");
}

function isAssetSyncEnabled() {
  const input = $("#sync-asset-lists");
  if (input) return input.checked;
  return state.runtime?.sync_asset_lists !== false;
}

function syncAssetListsFromAllowed() {
  if (!isAssetSyncEnabled()) return;
  setAssetList("allowed", state.assetSelections.allowed?.length ? state.assetSelections.allowed : DEFAULT_ASSETS);
}

function removeAsset(kind, asset) {
  setAssetList(
    kind,
    uniqueAssets((state.assetSelections[kind] || []).join(",")).filter((item) => item !== asset),
  );
}

function toggleAsset(kind, asset) {
  const assets = uniqueAssets((state.assetSelections[kind] || []).join(","));
  if (assets.includes(asset)) {
    setAssetList(
      kind,
      assets.filter((item) => item !== asset),
    );
  } else {
    setAssetList(kind, [...assets, asset]);
  }
}

function renderSetup() {
  const setup = state.setup || {};
  $("#claude-status").textContent = `Claude: ${setup.anthropic_configured ? "ready" : "fallback"}`;
  $("#hypertracker-status").textContent = `HyperTracker: ${setup.hypertracker_configured ? "ready" : "off"}`;
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
  const wallet = state.connected_wallet;
  const agent = state.privy_agent_wallet;
  const runtimeNetwork = state.runtime?.network || "testnet";
  const activeAgent = agent?.network === runtimeNetwork ? agent : null;
  const hasWallet = Boolean(wallet?.address);
  document.body.dataset.wallet = hasWallet ? "connected" : "empty";

  const walletStatus = $("#wallet-status");
  if (walletStatus) {
    walletStatus.textContent = hasWallet ? `Wallet ${maskAddress(wallet.address)}` : "No wallet";
    walletStatus.className = hasWallet ? "wallet-status connected" : "wallet-status";
  }

  const authPanel = $("#privy-auth-panel");
  if (authPanel) authPanel.hidden = hasWallet;

  const connectedPanel = $("#connected-wallet-panel");
  if (connectedPanel) connectedPanel.hidden = !hasWallet;

  if (!target) return;
  const rows = [];
  if (wallet) {
    rows.push(["User wallet", maskAddress(wallet.address)]);
    rows.push(["Source", wallet.source]);
    rows.push(["Email", wallet.email || "not shared"]);
  }
  if (activeAgent) {
    rows.push(["Network", activeAgent.network]);
    rows.push(["Master", maskAddress(activeAgent.master_wallet_address)]);
    rows.push(["Agent", maskAddress(activeAgent.agent_wallet_address)]);
    rows.push(["Agent name", activeAgent.agent_name || AGENT_NAME]);
    rows.push(["Registered", activeAgent.registered ? "yes" : "no"]);
    const actionRequired = activeAgent.raw_response?.registerResponse?.action_required;
    if (actionRequired) rows.push(["Action required", actionRequired]);
  } else if (wallet) {
    if (agent) rows.push(["Saved agent", `${agent.network} agent does not match ${runtimeNetwork}`]);
    rows.push(["Agent wallet", `Not initialized on ${runtimeNetwork}`]);
  }
  const setupButton = $('[data-action="privy-setup-agent"]');
  if (setupButton) {
    setupButton.textContent = activeAgent
      ? activeAgent.registered
        ? "Refresh agent"
        : "Retry registration"
      : `Initialize ${runtimeNetwork} agent`;
  }
  target.innerHTML = rows
    .map(([label, value]) => `<div><span>${label}</span><b>${value}</b></div>`)
    .join("");
}

function renderScreen() {
  document.body.dataset.screen = state.screen;
  document.body.classList.remove("active");
  document.body.classList.toggle("trading-screen", state.screen === "trading");
  document.body.classList.toggle("settings-screen-active", state.screen === "settings");
  for (const button of document.querySelectorAll(".app-nav [data-screen]")) {
    button.classList.toggle("active", button.dataset.screen === state.screen);
  }
  $("#settings-screen").hidden = state.screen !== "settings";
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

function money(value, includeCurrency = true) {
  const formatted = Number(value || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return includeCurrency ? `${formatted} USDC` : formatted;
}

function compactPrice(value) {
  const numeric = Number(value || 0);
  if (!numeric) return "0";
  if (Math.abs(numeric) >= 1000) {
    return numeric.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  if (Math.abs(numeric) >= 1) {
    return numeric.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 5 });
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
  const syncAssetLists = isAssetSyncEnabled();
  let watchlist = uniqueAssets($("#watchlist").value);
  let allowedAssets = uniqueAssets($("#allowed-assets").value);
  if (syncAssetLists) {
    const synced = allowedAssets.length ? allowedAssets : watchlist.length ? watchlist : DEFAULT_ASSETS;
    allowedAssets = synced;
    watchlist = synced;
  }
  const payload = {
    network: state.runtime?.network || "testnet",
    ui_mode: "human",
    execution_policy: "auto_testnet_confirm_prodnet",
    watchlist: watchlist.length ? watchlist : DEFAULT_ASSETS,
    allowed_assets: allowedAssets.length ? allowedAssets : DEFAULT_ASSETS,
    sync_asset_lists: syncAssetLists,
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

async function setupPrivyAgent() {
  state.privy_agent_wallet = await api("/api/privy/agent-wallet", { method: "POST" });
  await loadState();
  if (state.privy_agent_wallet?.registered) {
    toast("Privy agent wallet registered");
    return;
  }
  const actionRequired = state.privy_agent_wallet?.raw_response?.registerResponse?.action_required;
  toast(actionRequired || "Agent wallet created, but registration is pending");
}

document.addEventListener("click", async (event) => {
  if (event.target.closest(".app-nav")) return;
  const assetToggle = event.target.closest("[data-asset-toggle]");
  if (assetToggle) {
    toggleAsset(assetToggle.dataset.assetToggle, assetToggle.dataset.asset);
    return;
  }
  const assetRemove = event.target.closest("[data-asset-remove]");
  if (assetRemove) {
    removeAsset(assetRemove.dataset.assetRemove, assetRemove.dataset.asset);
    return;
  }
  const assetClear = event.target.closest("[data-asset-clear]");
  if (assetClear) {
    setAssetList(assetClear.dataset.assetClear, []);
    return;
  }
  const networkButton = event.target.closest("[data-network]");
  if (networkButton) {
    try {
      await saveRuntime({ network: networkButton.dataset.network });
    } catch (error) {
      toast(error.message);
    }
    return;
  }
  const screenButton = event.target.closest(".app-nav [data-screen]");
  if (screenButton) {
    state.screen = screenButton.dataset.screen || "trading";
    renderScreen();
    return;
  }
  const action = event.target.dataset.action;
  if (!action) return;
  try {
    if (action === "save-settings") await saveRuntime();
    if (action === "scan") {
      await saveRuntime();
      await scan();
    }
    if (action === "execute") await executeTrade();
    if (action === "reject") await rejectTrade();
    if (action === "privy-setup-agent") await setupPrivyAgent();
    if (action === "events" || action === "refresh") await loadState();
  } catch (error) {
    toast(error.message);
  }
});

for (const button of document.querySelectorAll(".app-nav [data-screen]")) {
  button.addEventListener("click", () => {
    state.screen = button.dataset.screen || "trading";
    renderScreen();
  });
}

$("#sync-asset-lists")?.addEventListener("change", async () => {
  try {
    document.body.dataset.assetSync = isAssetSyncEnabled() ? "on" : "off";
    if (isAssetSyncEnabled()) syncAssetListsFromAllowed();
    await saveRuntime({ sync_asset_lists: isAssetSyncEnabled() });
  } catch (error) {
    toast(error.message);
  }
});

for (const search of document.querySelectorAll("#allowed-asset-search, #watchlist-asset-search")) {
  search.addEventListener("input", () => {
    const kind = search.id === "allowed-asset-search" ? "allowed" : "watchlist";
    state.assetSearch[kind] = search.value;
    renderAssetOptions(kind);
  });
}

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
