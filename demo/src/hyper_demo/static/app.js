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
  showSensitiveWalletData: false,
  fundingBalances: null,
};

const DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "HYPE"];
const AGENT_NAME = "HyperClaude";
const ARBITRUM_RPC_URL = "https://arb1.arbitrum.io/rpc";
const ARBITRUM_USDC_ADDRESS = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831";

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
    rows.push(["User wallet", sensitiveValue(wallet.address, redactAddress(wallet.address)), true]);
    rows.push(["Source", wallet.source]);
    rows.push(["Email", sensitiveValue(wallet.email, redactEmail(wallet.email)), Boolean(wallet.email)]);
  }
  if (activeAgent) {
    rows.push(["Network", activeAgent.network]);
    rows.push(["Master", sensitiveValue(activeAgent.master_wallet_address, redactAddress(activeAgent.master_wallet_address)), true]);
    rows.push(["Agent", sensitiveValue(activeAgent.agent_wallet_address, redactAddress(activeAgent.agent_wallet_address)), true]);
    rows.push(["Agent name", activeAgent.agent_name || AGENT_NAME]);
    rows.push(["Registered", activeAgent.registered ? "yes" : "no"]);
    const actionRequired = activeAgent.raw_response?.registerResponse?.action_required;
    if (actionRequired && activeAgent.registered) rows.push(["Action required", actionRequired]);
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
  renderSensitiveToggle(hasWallet);
  renderWalletFundingFlow(wallet, activeAgent);
  target.innerHTML = rows
    .map(([label, value, redacted]) => {
      const valueClass = redacted && !state.showSensitiveWalletData ? ' class="redacted-value" aria-label="redacted"' : "";
      return `<div><span>${escapeHtml(label)}</span><b${valueClass}>${escapeHtml(value)}</b></div>`;
    })
    .join("");
}

function renderWalletFundingFlow(wallet, activeAgent) {
  const target = $("#wallet-funding-flow");
  if (!target) return;
  const actionRequired = activeAgent?.raw_response?.registerResponse?.action_required;
  const shouldShow = Boolean(wallet?.address && activeAgent && (!activeAgent.registered || actionRequired));
  target.hidden = !shouldShow;
  if (!shouldShow) {
    target.innerHTML = "";
    return;
  }

  const sensitiveClass = state.showSensitiveWalletData ? "" : " redacted-value";
  const masterAddress = sensitiveValue(
    activeAgent.master_wallet_address,
    redactAddress(activeAgent.master_wallet_address),
  );
  const agentAddress = sensitiveValue(
    activeAgent.agent_wallet_address,
    redactAddress(activeAgent.agent_wallet_address),
  );
  const userAddress = sensitiveValue(wallet.address, redactAddress(wallet.address));
  const depositNetwork = depositNetworkLabel(activeAgent.network);
  const balances = state.fundingBalances?.address === wallet.address ? state.fundingBalances : null;
  const usdcBalance = balances?.usdc ?? null;
  const ethBalance = balances?.eth ?? null;
  const hasUsdcBalance = usdcBalance !== null && usdcBalance !== undefined;
  const usdcValue = hasUsdcBalance ? Math.min(Number(usdcBalance), 5) : 5;
  const fundingBalanceText = state.showSensitiveWalletData
    ? formatFundingBalanceLabel(usdcBalance, ethBalance)
    : redactFundingBalanceLabel(usdcBalance, ethBalance);
  const fundingBalanceClass = state.showSensitiveWalletData ? "" : " redacted-value";
  const usdcMaxAttribute = state.showSensitiveWalletData ? usdcBalance ?? "" : "";
  const status = actionRequired || "Master wallet needs a Hyperliquid deposit before agent registration.";
  target.innerHTML = `
    <div class="funding-head">
      <span class="eyebrow">Funding flow</span>
      <b>${activeAgent.registered ? "Agent ready" : "Registration blocked"}</b>
      <p>${escapeHtml(status)}</p>
    </div>
    <div class="funding-steps">
      <section class="funding-step">
        <span class="step-badge">1</span>
        <div>
          <b>Prepare funds in the user wallet</b>
          <p>Use the connected Privy wallet as the source wallet when funding Hyperliquid.</p>
          <div class="address-row">
            <code class="sensitive-code${sensitiveClass}">${escapeHtml(userAddress)}</code>
            <button type="button" class="small-button" data-action="copy-wallet-address" data-wallet-target="user">Copy</button>
          </div>
        </div>
      </section>
      <section class="funding-step current">
        <span class="step-badge">2</span>
        <div>
          <b>Fund the master wallet on Arbitrum</b>
          <p>Send native USDC from the connected user wallet to the master wallet. The sender pays the Arbitrum transaction gas.</p>
          <div class="network-row">
            <span>Protocol / network</span>
            <b>${escapeHtml(depositNetwork)}</b>
          </div>
          <div class="network-row">
            <span>User wallet balance</span>
            <b id="funding-balance-label" class="sensitive-balance${fundingBalanceClass}">${escapeHtml(fundingBalanceText)}</b>
          </div>
          <div class="address-row">
            <code class="sensitive-code${sensitiveClass}">${escapeHtml(masterAddress)}</code>
            <button type="button" class="small-button" data-action="copy-wallet-address" data-wallet-target="master">Copy</button>
          </div>
          <div class="funding-form">
            <label>
              USDC to master
              <span class="input-action compact-input-action">
                <input id="funding-usdc-amount" type="number" min="0" max="${escapeHtml(usdcMaxAttribute)}" step="0.01" value="${escapeHtml(formatFundingInputValue(usdcValue))}" />
                <button type="button" data-action="funding-max-usdc">Max</button>
              </span>
            </label>
            <label class="check-row compact-check">
              <input id="funding-confirm" type="checkbox" />
              Confirm wallet funding transactions
            </label>
            <div class="button-row funding-actions">
              <button type="button" data-action="fund-master-usdc">Send USDC</button>
            </div>
          </div>
        </div>
      </section>
      <section class="funding-step">
        <span class="step-badge">3</span>
        <div>
          <b>Deposit master collateral, then retry</b>
          <p>After the master wallet has gas and USDC, submit the master wallet deposit to Hyperliquid Bridge2 and retry setup.</p>
          <div class="address-row">
            <code class="sensitive-code${sensitiveClass}">${escapeHtml(agentAddress)}</code>
          </div>
          <label>
            Mainnet phrase
            <input id="funding-phrase" placeholder="CONFIRM MAINNET ORDER" />
          </label>
          <div class="button-row funding-actions">
            <button type="button" data-action="deposit-master-hyperliquid">Deposit master to Hyperliquid</button>
            <button type="button" data-action="privy-setup-agent">Retry registration</button>
          </div>
        </div>
      </section>
    </div>
  `;
  refreshFundingBalances(wallet.address).catch(() => {});
}

function renderSensitiveToggle(hasWallet) {
  const button = $("#sensitive-toggle");
  if (!button) return;
  button.hidden = !hasWallet;
  button.setAttribute("aria-pressed", String(state.showSensitiveWalletData));
  button.setAttribute(
    "aria-label",
    state.showSensitiveWalletData ? "Hide sensitive wallet data" : "Show sensitive wallet data",
  );
  button.title = state.showSensitiveWalletData ? "Hide sensitive wallet data" : "Show sensitive wallet data";
  button.innerHTML = state.showSensitiveWalletData ? eyeOffIcon() : eyeIcon();
}

function sensitiveValue(realValue, redactedValue) {
  return state.showSensitiveWalletData ? realValue || "" : redactedValue || "";
}

function eyeIcon() {
  return `
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path>
      <circle cx="12" cy="12" r="3"></circle>
    </svg>
  `;
}

function eyeOffIcon() {
  return `
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M3 3l18 18"></path>
      <path d="M10.6 6.2A9.7 9.7 0 0 1 12 6c6 0 9.5 6 9.5 6a17.7 17.7 0 0 1-3 3.6"></path>
      <path d="M6.5 6.8A17.7 17.7 0 0 0 2.5 12s3.5 6 9.5 6a9.8 9.8 0 0 0 3.4-.6"></path>
      <path d="M10 10.2a3 3 0 0 0 3.8 3.8"></path>
    </svg>
  `;
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

function redactAddress(address) {
  return maskAddress(address);
}

function redactEmail(email) {
  if (!email) return "not shared";
  const [local = "", domain = ""] = email.split("@");
  if (!domain) return "hidden email";
  const [domainName = "", ...domainRest] = domain.split(".");
  const tld = domainRest.length ? `.${domainRest.at(-1)}` : "";
  const safeLocal = `${local.slice(0, 1)}${"*".repeat(Math.max(4, Math.min(local.length - 1, 8)))}`;
  const safeDomain = `${domainName.slice(0, 1)}${"*".repeat(Math.max(3, Math.min(domainName.length - 1, 6)))}`;
  return `${safeLocal}@${safeDomain}${tld}`;
}

function depositNetworkLabel(network) {
  if (network === "prodnet") return "Arbitrum One USDC -> Hyperliquid mainnet";
  return "Hyperliquid testnet funds";
}

function formatFundingBalanceLabel(usdc, eth) {
  if (usdc === null || eth === null) return "Loading Arbitrum balances";
  return `${formatTokenAmount(usdc)} USDC / ${formatTokenAmount(eth, 5)} ETH`;
}

function redactFundingBalanceLabel(usdc, eth) {
  if (usdc === null || eth === null) return "Loading Arbitrum balances";
  return "•••• USDC / •••• ETH";
}

function formatFundingInputValue(value) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric) || numeric <= 0) return "0";
  return String(Math.floor(numeric * 100) / 100);
}

function formatTokenAmount(value, decimals = 2) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) return "0";
  return numeric.toLocaleString("en-US", {
    maximumFractionDigits: decimals,
    minimumFractionDigits: 0,
  });
}

function encodeBalanceOf(address) {
  const clean = String(address || "").replace(/^0x/, "").toLowerCase();
  if (!/^[0-9a-f]{40}$/.test(clean)) throw new Error("Wallet address is invalid.");
  return `0x70a08231${clean.padStart(64, "0")}`;
}

async function arbitrumRpc(method, params) {
  const response = await fetch(ARBITRUM_RPC_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: Date.now(),
      method,
      params,
    }),
  });
  const payload = await response.json();
  if (payload.error) throw new Error(payload.error.message || "Arbitrum RPC error.");
  return payload.result;
}

function formatUnits(raw, decimals) {
  const value = BigInt(raw || "0x0");
  const scale = 10n ** BigInt(decimals);
  const whole = value / scale;
  const fraction = value % scale;
  const fractionText = fraction.toString().padStart(decimals, "0").replace(/0+$/, "");
  return Number(`${whole.toString()}${fractionText ? `.${fractionText}` : ""}`);
}

async function refreshFundingBalances(address) {
  if (!address) return;
  if (state.fundingBalances?.address === address && !state.fundingBalances.loading) return;
  state.fundingBalances = { address, loading: true, usdc: null, eth: null };
  const [ethRaw, usdcRaw] = await Promise.all([
    arbitrumRpc("eth_getBalance", [address, "latest"]),
    arbitrumRpc("eth_call", [
      {
        to: ARBITRUM_USDC_ADDRESS,
        data: encodeBalanceOf(address),
      },
      "latest",
    ]),
  ]);
  const balances = {
    address,
    loading: false,
    eth: formatUnits(ethRaw, 18),
    usdc: formatUnits(usdcRaw, 6),
  };
  state.fundingBalances = balances;
  updateFundingBalanceDom(balances);
}

function updateFundingBalanceDom(balances) {
  const label = $("#funding-balance-label");
  if (label) {
    label.textContent = state.showSensitiveWalletData
      ? formatFundingBalanceLabel(balances.usdc, balances.eth)
      : redactFundingBalanceLabel(balances.usdc, balances.eth);
    label.classList.toggle("redacted-value", !state.showSensitiveWalletData);
  }
  const usdcInput = $("#funding-usdc-amount");
  if (usdcInput) {
    if (state.showSensitiveWalletData) {
      usdcInput.max = String(balances.usdc);
    } else {
      usdcInput.removeAttribute("max");
    }
    const current = Number(usdcInput.value || 0);
    if (!current || current > balances.usdc) {
      usdcInput.value = formatFundingInputValue(balances.usdc);
    }
  }
}

function setFundingUsdcMax() {
  const input = $("#funding-usdc-amount");
  const max = state.fundingBalances?.usdc;
  if (!input || max === null || max === undefined) {
    throw new Error("User wallet USDC balance is still loading.");
  }
  input.value = formatFundingInputValue(max);
}

function walletAddressForTarget(target) {
  if (target === "user") return state.connected_wallet?.address;
  if (target === "master") return state.privy_agent_wallet?.master_wallet_address;
  if (target === "agent") return state.privy_agent_wallet?.agent_wallet_address;
  return null;
}

async function copyWalletAddress(target) {
  const address = walletAddressForTarget(target);
  if (!address) throw new Error("Wallet address is not available yet.");
  await copyText(address);
  toast("Wallet address copied");
}

async function copyText(value) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // Fall back for browser contexts that block async clipboard writes.
    }
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) throw new Error("Could not copy wallet address.");
}

function openHyperliquidDeposit() {
  window.open("https://app.hyperliquid.xyz", "_blank", "noopener,noreferrer");
}

function requireFundingConfirmation() {
  if (!$("#funding-confirm")?.checked) {
    throw new Error("Confirm wallet funding transactions first.");
  }
}

function currentMasterAddress() {
  const address = state.privy_agent_wallet?.master_wallet_address;
  if (!address) throw new Error("Initialize a Privy master wallet first.");
  return address;
}

async function fundMasterUsdc() {
  requireFundingConfirmation();
  if (!window.hyperDemoPrivyFunding?.transferUserUsdcToMaster) {
    throw new Error("Privy wallet funding is not ready yet.");
  }
  const hash = await window.hyperDemoPrivyFunding.transferUserUsdcToMaster({
    masterAddress: currentMasterAddress(),
    amountUsdc: $("#funding-usdc-amount").value,
  });
  toast(`USDC transfer submitted: ${maskHash(hash)}`);
}

async function depositMasterToHyperliquid() {
  requireFundingConfirmation();
  const result = await api("/api/privy/deposit-master", {
    method: "POST",
    body: JSON.stringify({
      amount_usdc: Number($("#funding-usdc-amount").value),
      confirmed: true,
      confirmation_phrase: $("#funding-phrase").value || null,
    }),
  });
  await loadState();
  toast(`Master deposit submitted: ${maskHash(result.hash)}`);
}

function maskHash(hash) {
  if (!hash || hash.length <= 12) return hash || "";
  return `${hash.slice(0, 6)}...${hash.slice(-4)}`;
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

function toggleSensitiveWalletData() {
  state.showSensitiveWalletData = !state.showSensitiveWalletData;
  renderConnectedWallet();
}

document.addEventListener("click", async (event) => {
  const copyTarget = event.target.closest('[data-action="copy-wallet-address"]');
  if (copyTarget) {
    event.preventDefault();
    event.stopPropagation();
    try {
      await copyWalletAddress(copyTarget.dataset.walletTarget);
    } catch (error) {
      toast(error.message);
    }
    return;
  }
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
  const actionTarget = event.target.closest("[data-action]");
  const action = actionTarget?.dataset.action;
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
    if (action === "toggle-sensitive") toggleSensitiveWalletData();
    if (action === "copy-wallet-address") await copyWalletAddress(actionTarget.dataset.walletTarget);
    if (action === "open-hyperliquid-deposit") openHyperliquidDeposit();
    if (action === "funding-max-usdc") setFundingUsdcMax();
    if (action === "fund-master-usdc") await fundMasterUsdc();
    if (action === "deposit-master-hyperliquid") await depositMasterToHyperliquid();
    if (action === "events" || action === "refresh") await loadState();
  } catch (error) {
    toast(error.message);
  }
});

$("#sensitive-toggle")?.addEventListener("click", (event) => {
  event.stopPropagation();
  toggleSensitiveWalletData();
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
