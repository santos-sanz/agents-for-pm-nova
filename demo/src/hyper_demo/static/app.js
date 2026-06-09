const state = {
  runtime: null,
  setup: null,
  analysis: null,
  plan: null,
  order: null,
  run: null,
  events: [],
  wallet: null,
  connected_wallet: null,
  privy_agent_wallet: null,
  metrics: null,
  screen: "trading",
  activeTimeframe: "1h",
  isAnalyzing: false,
  isLoadingCandles: false,
  candleRequestId: 0,
  marketCandles: {},
  candleStatus: {},
  chartHover: null,
  chartMarks: [],
  chartViewport: null,
  selectedCandidateIndex: 0,
  marketAssets: [],
  assetSearch: {
    allowed: "",
    watchlist: "",
  },
  assetSelections: {
    allowed: [],
    watchlist: [],
  },
  manualOrder: {
    side: "long",
    entry_type: "market",
    size_usdc: 25,
    entry_price: "",
    stop_loss: "",
    take_profit: "",
    leverage: 1,
  },
  showSensitiveWalletData: false,
  masterFundingBalances: null,
};

const DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "HYPE"];
const DEFAULT_NETWORK = "prodnet";
const AGENT_NAME = "HyperClaude";
const ARBITRUM_USDC_ADDRESS = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831";
const CHART_COLORS = {
  background: "#f5f0e8",
  text: "#181715",
  grid: "rgba(24, 23, 21, 0.12)",
  up: "#2f7d4a",
  down: "#9c3f3f",
  entry: "#1f6feb",
  takeProfit: "#2f7d4a",
  stopLoss: "#9c3f3f",
};
const chartRuntime = {
  chart: null,
  candles: null,
  key: "",
  lineStyle: null,
  priceLines: [],
  resizeObserver: null,
};

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

function displayAssetSymbol(value) {
  const normalized = normalizeAssetSymbol(value);
  if (!normalized.includes(":")) return normalized;
  return normalized.split(":", 2)[1];
}

function displayPerpLabel(value) {
  return `${displayAssetSymbol(value)}-PERP`;
}

function latestMarkPrice(asset = currentChartAsset()) {
  const candles = activeCandles();
  const latest = candles.at(-1);
  if (latest?.close) return Number(latest.close);
  const meta = assetMeta(asset);
  return Number(meta?.mark_price || 0);
}

function assetMaxLeverage(asset = currentChartAsset()) {
  const meta = assetMeta(asset);
  const exchangeMax = Number(meta?.max_leverage || 10);
  return Math.max(1, Math.min(10, exchangeMax || 10));
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
  state.marketCandles = state.marketCandles || {};
  syncManualOrderFromStoredPlan();
  syncAssetInputFromStoredTrade();
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
  loadChartCandles().catch((error) => toast(error.message));
}

function render() {
  renderRuntime();
  renderSetup();
  renderConnectedWallet();
  renderTradingView();
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
  ensureCurrentAssetIsVisible();
  renderAssetPicker("allowed");
  renderAssetPicker("watchlist");
  renderMarketRail();
  for (const button of document.querySelectorAll("[data-network]")) {
    button.classList.toggle("active", button.dataset.network === (runtime.network || DEFAULT_NETWORK));
  }
  document.body.dataset.uiMode = "human";
  document.body.dataset.network = runtime.network || DEFAULT_NETWORK;
  const networkStatus = $("#network-status");
  if (networkStatus) {
    networkStatus.textContent = runtime.network === "prodnet" ? "mainnet guarded" : "testnet auto";
    networkStatus.className = runtime.network === "prodnet" ? "prodnet" : "testnet";
  }
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
  const safeDisplaySymbol = escapeHtml(displayAssetSymbol(symbol));
  const safeUrl = escapeHtml(iconUrl || assetMeta(symbol)?.icon_url || "");
  return `
    <span class="asset-icon">
      ${safeUrl ? `<img src="${safeUrl}" alt="" loading="lazy" />` : ""}
      <span>${safeDisplaySymbol.slice(0, 2)}</span>
    </span>
  `;
}

function visibleMarketAssets() {
  const watchlist = uniqueAssets((state.assetSelections.watchlist || []).join(","));
  const allowed = uniqueAssets((state.assetSelections.allowed || []).join(","));
  if (isAssetSyncEnabled()) return allowed.length ? allowed : watchlist.length ? watchlist : DEFAULT_ASSETS;
  return watchlist.length ? watchlist : allowed.length ? allowed : DEFAULT_ASSETS;
}

function ensureCurrentAssetIsVisible() {
  const input = $("#asset-input");
  if (!input) return;
  const assets = visibleMarketAssets();
  const current = currentInputAsset();
  if (!current || !assets.includes(current)) input.value = assets[0] || "BTC";
}

function renderMarketRail() {
  const target = $("#market-rail");
  if (!target) return;
  const activeAsset = currentChartAsset();
  const assets = visibleMarketAssets();
  target.innerHTML = assets
    .map((asset) => {
      const meta = assetMeta(asset);
      const price = meta?.mark_price ? compactPrice(meta.mark_price) : "live";
      return `
        <button type="button" class="${asset === activeAsset ? "active" : ""}" data-quick-asset="${escapeHtml(asset)}">
          ${assetIcon(asset, meta?.icon_url)}
          <b>${escapeHtml(displayAssetSymbol(asset))}</b>
          <small>${escapeHtml(price)}</small>
        </button>
      `;
    })
    .join("");
  for (const image of target.querySelectorAll(".asset-icon img")) {
    image.addEventListener("error", () => {
      image.remove();
    });
  }
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
  ensureCurrentAssetIsVisible();
  renderAssetPicker("allowed");
  renderAssetPicker("watchlist");
  renderMarketRail();
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
  if ($("#claude-status")) $("#claude-status").textContent = `Claude: ${setup.anthropic_configured ? "ready" : "fallback"}`;
  if ($("#hypertracker-status")) $("#hypertracker-status").textContent = `HyperTracker: ${setup.hypertracker_configured ? "ready" : "off"}`;
  if ($("#perplexity-status")) $("#perplexity-status").textContent = `Perplexity: ${setup.perplexity_configured ? "ready" : "off"}`;
  let hyperliquidStatus = "missing creds";
  if (setup.hyperliquid_configured) {
    hyperliquidStatus = "ready";
  } else if (setup.privy_execution_enabled && setup.privy_server_configured) {
    hyperliquidStatus = "Privy ready";
  }
  if ($("#hyperliquid-status")) $("#hyperliquid-status").textContent = `Hyperliquid: ${hyperliquidStatus}`;
  const privyStatus = $("#privy-status");
  if (privyStatus && privyStatus.textContent === "checking") {
    privyStatus.textContent = setup.privy_configured ? "configured" : "missing config";
  }
}

function renderConnectedWallet() {
  const target = $("#privy-wallet-summary");
  const wallet = state.connected_wallet;
  const agent = state.privy_agent_wallet;
  const runtimeNetwork = state.runtime?.network || DEFAULT_NETWORK;
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
  const depositNetwork = depositNetworkLabel(activeAgent.network);
  const balances = state.masterFundingBalances?.address === activeAgent.master_wallet_address
    ? state.masterFundingBalances
    : null;
  const balanceText = state.showSensitiveWalletData
    ? formatFundingBalanceLabel(balances?.usdc ?? null, balances?.eth ?? null)
    : redactFundingBalanceLabel(balances?.usdc ?? null, balances?.eth ?? null);
  const balanceClass = state.showSensitiveWalletData ? "" : " redacted-value";
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
          <b>Send funds from the external system</b>
          <p>Use the external funding source directly. Send native Arbitrum USDC to the Privy master wallet below.</p>
        </div>
      </section>
      <section class="funding-step current">
        <span class="step-badge">2</span>
        <div>
          <b>External transfer destination</b>
          <p>This is the only address that should receive the external funding transfer for this setup.</p>
          <div class="network-row">
            <span>Network</span>
            <b>${escapeHtml(depositNetwork)}</b>
          </div>
          <div class="network-row">
            <span>Token</span>
            <b>Native USDC</b>
          </div>
          <div class="network-row">
            <span>USDC contract</span>
            <code class="sensitive-code${sensitiveClass}">${escapeHtml(sensitiveValue(ARBITRUM_USDC_ADDRESS, redactAddress(ARBITRUM_USDC_ADDRESS)))}</code>
          </div>
          <div class="address-row">
            <code class="sensitive-code${sensitiveClass}">${escapeHtml(masterAddress)}</code>
            <button type="button" class="small-button" data-action="copy-wallet-address" data-wallet-target="master">Copy</button>
          </div>
          <div class="network-row">
            <span>Master wallet funds</span>
            <b id="master-funding-balance-label" class="sensitive-balance${balanceClass}">${escapeHtml(balanceText)}</b>
          </div>
        </div>
      </section>
      <section class="funding-step">
        <span class="step-badge">3</span>
        <div>
          <b>Deposit master collateral, then retry</b>
          <p>After the external transfer arrives in the master wallet, submit the master wallet deposit to Hyperliquid Bridge2 and retry setup.</p>
          <div class="address-row">
            <code class="sensitive-code${sensitiveClass}">${escapeHtml(agentAddress)}</code>
          </div>
          <label>
            USDC to deposit
            <input id="funding-usdc-amount" type="number" min="5" step="0.000001" value="5" />
          </label>
          <label class="check-row compact-check">
            <input id="funding-confirm" type="checkbox" />
            Confirm master wallet deposit
          </label>
          <div class="button-row funding-actions">
            <button type="button" data-action="deposit-master-hyperliquid">Deposit master to Hyperliquid</button>
            <button type="button" data-action="privy-setup-agent">Retry registration</button>
          </div>
        </div>
      </section>
    </div>
  `;
  refreshMasterFundingBalances(activeAgent.master_wallet_address).catch(() => {});
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

function renderTradingView() {
  const analysis = activeAnalysis();
  const asset = currentChartAsset();
  syncTimeframeButtons();
  syncQuickAssetButtons(asset);
  const label = $("#active-asset-label");
  if (label) label.textContent = displayPerpLabel(asset);
  const status = $("#analysis-status");
  if (status) {
    status.textContent = state.isAnalyzing
      ? `Claude is analyzing ${displayPerpLabel(asset)} across timeframes.`
      : state.isLoadingCandles
      ? `Loading ${displayPerpLabel(asset)} candles.`
      : analysis
      ? analysis.summary
      : "Build a manual order from the ticket. Run AI analysis only when you want guidance.";
  }
  renderAnalyzeControls();
  renderChart();
  renderMarketStats();
  renderBestBet();
  renderTimeframeCards();
  renderCandidateList();
  renderTicket();
}

function currentInputAsset() {
  return normalizeAssetSymbol($("#asset-input")?.value || "");
}

function currentChartAsset() {
  return currentInputAsset() || state.analysis?.asset || state.plan?.asset || "BTC";
}

function activeAnalysis() {
  const analysis = state.analysis;
  if (!analysis) return null;
  return normalizeAssetSymbol(analysis.asset) === currentChartAsset() ? analysis : null;
}

function activePlan() {
  const plan = state.plan;
  if (!plan) return null;
  return normalizeAssetSymbol(plan.asset) === currentChartAsset() ? plan : null;
}

function activeCandidates() {
  const analysis = activeAnalysis();
  if (!analysis) return [];
  const plan = activePlan();
  if (plan?.source === "manual") return [];
  if (plan && analysis.plan_id && analysis.plan_id !== plan.id) return [];
  return analysis.candidates || [];
}

function selectedCandidate() {
  const candidates = activeCandidates();
  if (!candidates.length) return null;
  const index = Math.min(Math.max(Number(state.selectedCandidateIndex) || 0, 0), candidates.length - 1);
  return candidates[index] || null;
}

function selectedTradeLevels() {
  const candidate = selectedCandidate();
  if (candidate) return candidate;
  const plan = activePlan();
  if (!plan) return null;
  return {
    side: plan.side,
    entry_price: plan.entry_price,
    stop_loss: plan.stop_loss,
    take_profit: plan.take_profit,
  };
}

function candidateMatchesPlan(candidate, plan) {
  if (!candidate || !plan) return false;
  return (
    candidate.side === plan.side &&
    Math.abs(Number(candidate.entry_price) - Number(plan.entry_price)) < 0.000001 &&
    Math.abs(Number(candidate.stop_loss) - Number(plan.stop_loss)) < 0.000001 &&
    Math.abs(Number(candidate.take_profit) - Number(plan.take_profit)) < 0.000001
  );
}

function syncAssetInputFromStoredTrade() {
  const input = $("#asset-input");
  const storedAsset = state.plan?.source === "manual" ? state.plan.asset : state.analysis?.asset || state.plan?.asset;
  if (!input || !storedAsset) return;
  const current = currentInputAsset();
  if (!current || current === "BTC") input.value = normalizeAssetSymbol(storedAsset);
}

function syncManualOrderFromStoredPlan() {
  const plan = state.plan;
  if (plan?.source !== "manual") return;
  state.manualOrder = {
    side: plan.side || "long",
    entry_type: plan.entry_type || "market",
    size_usdc: plan.size_usdc ?? 25,
    entry_price: plan.entry_type === "limit" ? String(plan.entry_price ?? "") : "",
    stop_loss: plan.stop_loss ? String(plan.stop_loss) : "",
    take_profit: plan.take_profit ? String(plan.take_profit) : "",
    leverage: plan.leverage ?? 1,
  };
}

function activeCandles() {
  const asset = currentChartAsset();
  const analysis = activeAnalysis();
  return (
    state.marketCandles?.[asset]?.[state.activeTimeframe] ||
    analysis?.candles_by_timeframe?.[state.activeTimeframe] ||
    []
  );
}

function syncTimeframeButtons() {
  for (const button of document.querySelectorAll("[data-timeframe]")) {
    button.classList.toggle("active", button.dataset.timeframe === state.activeTimeframe);
  }
}

function syncQuickAssetButtons(asset) {
  renderMarketRail();
  for (const button of document.querySelectorAll("[data-quick-asset]")) {
    button.classList.toggle("active", button.dataset.quickAsset === asset);
  }
}

function renderAnalyzeControls() {
  const button = $("#analyze-form button[type='submit']");
  if (button) {
    button.disabled = state.isAnalyzing;
    button.textContent = state.isAnalyzing ? "Analyzing" : "AI assist";
  }
  document.body.dataset.analyzing = state.isAnalyzing ? "true" : "false";
  document.body.dataset.loadingCandles = state.isLoadingCandles ? "true" : "false";
}

function candleStatusKey(asset = currentChartAsset(), interval = state.activeTimeframe) {
  return `${normalizeAssetSymbol(asset || "BTC")}::${interval}`;
}

function currentCandleStatus() {
  return state.candleStatus[candleStatusKey()] || "idle";
}

function clearTradeDisplay({ render = true } = {}) {
  state.analysis = null;
  state.plan = null;
  state.order = null;
  state.selectedCandidateIndex = 0;
  if (render) renderTradingView();
}

function selectChartAsset(asset) {
  const normalized = normalizeAssetSymbol(asset || "BTC");
  const input = $("#asset-input");
  if (input) input.value = normalized;
  state.chartHover = null;
  state.selectedCandidateIndex = 0;
  if (!state.marketCandles?.[normalized]?.[state.activeTimeframe]?.length) {
    state.candleStatus[candleStatusKey(normalized, state.activeTimeframe)] = "loading";
    state.isLoadingCandles = true;
  }
  renderTradingView();
  loadChartCandles(normalized, state.activeTimeframe).catch((error) => toast(error.message));
}

async function loadChartCandles(asset = currentChartAsset(), interval = state.activeTimeframe) {
  const normalized = normalizeAssetSymbol(asset || "BTC");
  const statusKey = candleStatusKey(normalized, interval);
  if (state.marketCandles?.[normalized]?.[interval]?.length) {
    state.candleStatus[statusKey] = "loaded";
    renderTradingView();
    return;
  }
  const requestId = state.candleRequestId + 1;
  state.candleRequestId = requestId;
  state.isLoadingCandles = true;
  state.candleStatus[statusKey] = "loading";
  renderTradingView();
  try {
    const payload = await api(
      `/api/market/${encodeURIComponent(normalized)}/candles?interval=${encodeURIComponent(interval)}&limit=120`,
    );
    if (requestId !== state.candleRequestId) return;
    state.marketCandles[normalized] = {
      ...(state.marketCandles[normalized] || {}),
      [payload.interval]: payload.candles,
    };
    state.candleStatus[statusKey] = payload.candles?.length ? "loaded" : "empty";
  } catch (error) {
    if (requestId === state.candleRequestId) state.candleStatus[statusKey] = "error";
    throw error;
  } finally {
    if (requestId === state.candleRequestId) {
      state.isLoadingCandles = false;
      renderTradingView();
    }
  }
}

function renderBestBet() {
  const analysis = activeAnalysis();
  const plan = activePlan();
  if (plan?.source === "manual") {
    const confidence = $("#confidence");
    if (confidence) {
      confidence.textContent = "Manual";
      confidence.className = "pill neutral";
    }
    $("#best-bet").classList.remove("empty");
    $("#best-bet").innerHTML = `
      <div class="manual-mode-banner">
        <span>Manual mode</span>
        <b>${escapeHtml(plan.side.toUpperCase())} ${displayAssetSymbol(plan.asset)}</b>
      </div>
      <div class="best-metrics compact">
        <div><span>Type</span><b>${escapeHtml(plan.entry_type)}</b></div>
        <div><span>Leverage</span><b>${number(plan.leverage, 2)}x</b></div>
        <div><span>Entry</span><b>${number(plan.entry_price, 6)}</b></div>
        <div><span>Size</span><b>${money(plan.size_usdc)}</b></div>
      </div>
    `;
    return;
  }
  const best = selectedCandidate() || analysis?.best_candidate;
  const title = $("#best-title");
  const confidence = $("#confidence");
  if (!best || !plan) {
    if (title) title.textContent = "Awaiting analysis";
    if (confidence) {
      confidence.textContent = "0%";
      confidence.className = "pill neutral";
    }
    $("#best-bet").classList.add("empty");
    $("#best-bet").innerHTML = state.isAnalyzing
      ? "<p>Building the best setup.</p>"
      : "<p>No recommendation yet.</p>";
    return;
  }
  if (title) title.textContent = `${best.side.toUpperCase()} ${displayAssetSymbol(analysis.asset)}`;
  if (confidence) {
    confidence.textContent = `${Math.round((plan.confidence || best.confidence || 0) * 100)}%`;
    confidence.className = `pill ${plan.confidence >= 0.7 ? "gain" : "neutral"}`;
  }
  $("#best-bet").classList.remove("empty");
  $("#best-bet").innerHTML = `
    <div class="side-toggle ${best.side}">
      <span class="${best.side === "long" ? "active" : ""}">Long</span>
      <span class="${best.side === "short" ? "active" : ""}">Short</span>
    </div>
    <div class="best-metrics compact">
      <div><span>Type</span><b>${escapeHtml(best.entry_type)}</b></div>
      <div><span>Leverage</span><b>${number(best.leverage, 2)}x</b></div>
      <div><span>Entry</span><b>${number(best.entry_price, 6)}</b></div>
      <div><span>Size</span><b>${money(best.size_usdc)}</b></div>
    </div>
  `;
}

function renderMarketStats() {
  const target = $("#market-stats");
  if (!target) return;
  const analysis = activeAnalysis();
  const plan = activePlan();
  const signal = analysis?.timeframes?.find((item) => item.interval === state.activeTimeframe);
  const candles = activeCandles();
  const latest = candles.at(-1);
  const side = plan?.side || analysis?.best_candidate?.side || "none";
  target.innerHTML = [
    ["Mark", latest ? compactPrice(latest.close) : "--", "neutral"],
    [
      "Signal",
      state.isAnalyzing
        ? "analyzing"
        : state.isLoadingCandles
          ? "loading"
        : signal
          ? `${signal.direction} ${signedNumber(signal.return_pct, 2)}%`
          : "--",
      signal?.direction === "bullish" ? "gain" : signal?.direction === "bearish" ? "loss" : "neutral",
    ],
    ["Confidence", plan ? `${Math.round((plan.confidence || 0) * 100)}%` : "0%", plan?.confidence >= 0.7 ? "gain" : "neutral"],
    ["Bias", side, side === "long" ? "gain" : side === "short" ? "loss" : "neutral"],
  ]
    .map(([label, value, className]) => `<div><span>${label}</span><b class="${className}">${escapeHtml(value)}</b></div>`)
    .join("");
}

function renderTimeframeCards() {
  const target = $("#timeframe-cards");
  if (!target) return;
  const signals = activeAnalysis()?.timeframes || [];
  target.innerHTML = signals.length
    ? signals
        .map((signal) => {
          const className = signal.direction === "bullish" ? "gain" : signal.direction === "bearish" ? "loss" : "neutral";
          return `
            <button type="button" class="timeframe-card ${state.activeTimeframe === signal.interval ? "active" : ""}" data-timeframe="${signal.interval}">
              <span>${escapeHtml(signal.interval)}</span>
              <b class="${className}">${escapeHtml(signal.direction)}</b>
              <em>${signedNumber(signal.return_pct, 2)}%</em>
              <em>RSI ${number(signal.rsi, 1)}</em>
              <em>ATR ${number(signal.atr_pct, 2)}%</em>
            </button>
          `;
        })
        .join("")
    : `<div class='empty-assets'>${state.isAnalyzing ? "Analyzing timeframes." : "No timeframe signals yet."}</div>`;
}

function renderCandidateList() {
  const target = $("#candidate-list");
  if (!target) return;
  const candidates = activeCandidates();
  if (state.selectedCandidateIndex >= candidates.length) state.selectedCandidateIndex = 0;
  target.innerHTML = candidates.length
    ? candidates
        .slice(0, 6)
        .map(
          (candidate, index) => `
            <button type="button" class="candidate ${candidate.side} ${index === state.selectedCandidateIndex ? "active" : ""}" data-candidate-index="${index}">
              <span>${index + 1}</span>
              <b>${escapeHtml(candidate.side.toUpperCase())}</b>
              <span>${escapeHtml(candidate.entry_type)}</span>
              <span>${escapeHtml(candidate.timeframe)}</span>
              <span>${number(candidate.entry_price, 6)}</span>
              <span>${number(candidate.leverage, 2)}x</span>
              <span>${number(candidate.score, 1)}</span>
            </button>
          `,
        )
        .join("")
    : `<div class='empty-assets'>${state.isAnalyzing ? "Ranking candidates." : "Run analysis to compare candidates."}</div>`;
}

function renderTicket() {
  const plan = activePlan();
  const isManualPlan = plan?.source === "manual";
  const candidate = selectedCandidate();
  const previewOnly = Boolean(candidate && plan && !candidateMatchesPlan(candidate, plan));
  const ticketAsset = currentChartAsset();
  const manual = state.manualOrder;
  const maxLeverage = assetMaxLeverage(ticketAsset);
  if (Number(manual.leverage) > maxLeverage) manual.leverage = maxLeverage;
  const decision = previewOnly ? "preview_only" : plan?.execution_decision || "manual_draft";
  const decisionPill = $("#decision-pill");
  if (decisionPill) {
    decisionPill.textContent =
      isManualPlan && decision === "proposed"
        ? "manual mode"
        : !plan
        ? "manual mode"
        : decision.replaceAll("_", " ");
    decisionPill.className = `pill ${decisionClass(decision)}`;
  }
  $("#ticket-title").textContent = `Trade ${displayPerpLabel(ticketAsset)}`;
  const submitButton = $('[data-action="submit-manual-order"]');
  const rejectButton = $('[data-action="reject"]');
  if (submitButton) submitButton.disabled = previewOnly;
  if (rejectButton) rejectButton.disabled = !plan;
  const source = candidate || plan;
  const mark = latestMarkPrice(ticketAsset);
  const limitHidden = manual.entry_type !== "limit" ? " hidden" : "";
  $("#ticket").innerHTML = `
    <section class="manual-order-section order-ticket-core">
      <div class="order-ticket-meta">
        <div><span>Market</span><b>${displayPerpLabel(ticketAsset)}</b></div>
        <div><span>Mark</span><b>${mark ? compactPrice(mark) : "--"}</b></div>
      </div>
      <div class="trade-segment side-picker" aria-label="Side">
        <button type="button" class="${manual.side === "long" ? "active" : ""}" data-manual-pick="side" data-value="long">Buy</button>
        <button type="button" class="${manual.side === "short" ? "active" : ""}" data-manual-pick="side" data-value="short">Sell</button>
      </div>
      <div class="trade-segment" aria-label="Order type">
        <button type="button" class="${manual.entry_type === "market" ? "active" : ""}" data-manual-pick="entry_type" data-value="market">Market</button>
        <button type="button" class="${manual.entry_type === "limit" ? "active" : ""}" data-manual-pick="entry_type" data-value="limit">Limit</button>
      </div>
      <label class="primary-number">Size
        <span>
          <input type="number" min="1" step="1" data-manual-field="size_usdc" value="${escapeHtml(manual.size_usdc)}" />
          <em>USDC</em>
        </span>
      </label>
      <div class="size-presets" aria-label="Size presets">
        ${[25, 50, 100]
          .map(
            (size) => `
              <button type="button" class="${Number(manual.size_usdc) === size ? "active" : ""}" data-manual-size="${size}">
                ${size}
              </button>
            `,
          )
          .join("")}
      </div>
      <label class="primary-number"${limitHidden}>Limit price
        <input type="number" min="0" step="0.000001" data-manual-field="entry_price" value="${escapeHtml(manual.entry_price)}" placeholder="${mark ? number(mark, 6) : "0.00"}" />
      </label>
      <div class="order-footprint">
        <div><span>Leverage</span><b>1x</b></div>
        <div><span>Max</span><b>${money(state.runtime?.max_order_usdc || 100)}</b></div>
        <div><span>Network</span><b>${escapeHtml(state.runtime?.network || DEFAULT_NETWORK)}</b></div>
      </div>
    </section>
    <section class="manual-order-section provided-data order-status-card">
      <div class="ticket-section-head">
        <span class="ticket-label">Status</span>
        <em>${isManualPlan ? "active plan" : "draft"}</em>
      </div>
      <div class="provided-grid">
        <div><span>Mode</span><b>${isManualPlan || !plan ? "Manual" : "AI assisted"}</b></div>
        <div><span>Active plan</span><b>${source ? `${escapeHtml(source.side)} ${number(source.entry_price, 4)}` : "none"}</b></div>
        <div><span>Decision</span><b>${escapeHtml(decision.replaceAll("_", " "))}</b></div>
        <div><span>Confirm</span><b>${$("#execute-confirm")?.checked ? "ready" : "required"}</b></div>
      </div>
    </section>
  `;
}

function renderChart() {
  const container = $("#candle-chart");
  const empty = $("#chart-empty");
  if (!container) return;
  const candles = activeCandles();
  if (empty) empty.hidden = Boolean(candles.length);
  if (!candles.length) {
    if (empty) {
      const status = currentCandleStatus();
      empty.textContent =
        state.isLoadingCandles || status === "loading" || status === "idle"
          ? "Loading candles."
          : "Candles unavailable.";
    }
    clearLightweightChart();
    return;
  }
  drawLightweightCandles(container, candles);
}

function clearLightweightChart() {
  state.chartViewport = null;
  if (chartRuntime.candles) chartRuntime.candles.setData([]);
  chartRuntime.key = "";
  clearChartPriceLines();
}

function ensureLightweightChart(container) {
  const library = window.LightweightCharts;
  if (!library?.createChart || !library?.CandlestickSeries) {
    const empty = $("#chart-empty");
    if (empty) {
      empty.hidden = false;
      empty.textContent = "TradingView chart library unavailable.";
    }
    return false;
  }
  if (chartRuntime.chart) return true;
  const { CandlestickSeries, ColorType, CrosshairMode, LineStyle, createChart } = library;
  const chart = createChart(container, {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: CHART_COLORS.background },
      textColor: CHART_COLORS.text,
      attributionLogo: false,
    },
    grid: {
      vertLines: { color: CHART_COLORS.grid },
      horzLines: { color: CHART_COLORS.grid },
    },
    crosshair: { mode: CrosshairMode.Normal },
    rightPriceScale: {
      borderVisible: false,
      scaleMargins: { top: 0.12, bottom: 0.14 },
    },
    timeScale: {
      borderVisible: false,
      secondsVisible: false,
      timeVisible: true,
    },
    handleScale: true,
    handleScroll: true,
  });
  chartRuntime.chart = chart;
  chartRuntime.candles = chart.addSeries(CandlestickSeries, {
    borderDownColor: CHART_COLORS.down,
    borderUpColor: CHART_COLORS.up,
    downColor: CHART_COLORS.down,
    lastValueVisible: true,
    priceLineVisible: true,
    upColor: CHART_COLORS.up,
    wickDownColor: CHART_COLORS.down,
    wickUpColor: CHART_COLORS.up,
  });
  chartRuntime.lineStyle = LineStyle;
  chartRuntime.resizeObserver = new ResizeObserver(() => chart.timeScale().fitContent());
  chartRuntime.resizeObserver.observe(container);
  return true;
}

function candleTimestamp(candle) {
  const value = candle?.opened_at || candle?.time;
  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) return Math.floor(date.getTime() / 1000);
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function lightweightCandleData(candles) {
  return candles
    .map((candle) => {
      const time = candleTimestamp(candle);
      if (!time) return null;
      return {
        close: Number(candle.close),
        high: Number(candle.high),
        low: Number(candle.low),
        open: Number(candle.open),
        time,
      };
    })
    .filter(
      (candle) =>
        candle &&
        Number.isFinite(candle.open) &&
        Number.isFinite(candle.high) &&
        Number.isFinite(candle.low) &&
        Number.isFinite(candle.close),
    );
}

function drawLightweightCandles(container, candles) {
  if (!ensureLightweightChart(container)) return;
  const visible = lightweightCandleData(candles.slice(-180));
  const latest = visible.at(-1);
  const key = `${currentChartAsset()}::${state.activeTimeframe}::${visible.length}::${latest?.time || ""}::${latest?.close || ""}`;
  if (key !== chartRuntime.key) {
    chartRuntime.candles.setData(visible);
    chartRuntime.chart.timeScale().fitContent();
    chartRuntime.key = key;
  }
  const width = Math.max(320, container.clientWidth || 960);
  const height = Math.max(240, container.clientHeight || 420);
  const highs = visible.map((candle) => candle.high);
  const lows = visible.map((candle) => candle.low);
  const maxPrice = highs.length ? Math.max(...highs) : 0;
  const minPrice = lows.length ? Math.min(...lows) : 0;
  state.chartViewport = {
    asset: currentChartAsset(),
    height,
    interval: state.activeTimeframe,
    maxPrice,
    minPrice,
    pad: { bottom: 0, left: 0, right: 0, top: 0 },
    plotHeight: height,
    plotWidth: width,
    priceRange: Math.max(0.0001, maxPrice - minPrice),
    step: visible.length ? width / visible.length : 0,
    visible,
    width,
  };
  drawLightweightTradeLevels();
}

function clearChartPriceLines() {
  if (!chartRuntime.candles) return;
  for (const line of chartRuntime.priceLines) chartRuntime.candles.removePriceLine(line);
  chartRuntime.priceLines = [];
}

function addChartPriceLine(price, title, color, dashed = false) {
  const value = Number(price);
  if (!chartRuntime.candles || !Number.isFinite(value)) return;
  chartRuntime.priceLines.push(
    chartRuntime.candles.createPriceLine({
      axisLabelVisible: true,
      color,
      lineStyle: dashed ? chartRuntime.lineStyle.Dashed : chartRuntime.lineStyle.Solid,
      lineWidth: 2,
      price: value,
      title,
    }),
  );
}

function drawLightweightTradeLevels() {
  clearChartPriceLines();
  const levels = selectedTradeLevels();
  if (!levels) return;
  addChartPriceLine(levels.entry_price, "Entry", CHART_COLORS.entry);
  addChartPriceLine(levels.take_profit, "TP", CHART_COLORS.takeProfit, true);
  addChartPriceLine(levels.stop_loss, "SL", CHART_COLORS.stopLoss, true);
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
  if (network === "prodnet") return "Arbitrum One";
  return "Hyperliquid testnet funds";
}

function formatFundingBalanceLabel(usdc, eth) {
  if (usdc === null || eth === null) return "Loading Arbitrum balances";
  return `${formatTokenAmount(usdc, 6)} USDC / ${formatTokenAmount(eth, 5)} ETH`;
}

function redactFundingBalanceLabel(usdc, eth) {
  if (usdc === null || eth === null) return "Loading Arbitrum balances";
  return "•••• USDC / •••• ETH";
}

function formatTokenAmount(value, decimals = 2) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric)) return "0";
  return numeric.toLocaleString("en-US", {
    maximumFractionDigits: decimals,
    minimumFractionDigits: 0,
  });
}

function formatFundingInputValue(value) {
  const numeric = Number(value || 0);
  if (!Number.isFinite(numeric) || numeric <= 0) return "0";
  return numeric.toFixed(6).replace(/\.?0+$/, "");
}

async function refreshMasterFundingBalances(address) {
  if (!address) return;
  if (state.masterFundingBalances?.address === address && !state.masterFundingBalances.loading) return;
  state.masterFundingBalances = { address, loading: true, usdc: null, eth: null };
  const balance = await api(`/api/wallet/arbitrum-balance/${encodeURIComponent(address)}`);
  const balances = {
    address: balance.address,
    loading: false,
    eth: balance.eth,
    usdc: balance.usdc,
  };
  state.masterFundingBalances = balances;
  updateMasterFundingBalanceDom(balances);
}

function updateMasterFundingBalanceDom(balances) {
  const label = $("#master-funding-balance-label");
  if (label) {
    label.textContent = state.showSensitiveWalletData
      ? formatFundingBalanceLabel(balances.usdc, balances.eth)
      : redactFundingBalanceLabel(balances.usdc, balances.eth);
    label.classList.toggle("redacted-value", !state.showSensitiveWalletData);
  }
  const depositInput = $("#funding-usdc-amount");
  if (depositInput && Number(balances.usdc) >= 5) {
    const current = Number(depositInput.value || 0);
    if (!current || current === 5 || current > balances.usdc) {
      depositInput.value = formatFundingInputValue(balances.usdc);
    }
    depositInput.max = String(balances.usdc);
  }
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

async function depositMasterToHyperliquid() {
  requireFundingConfirmation();
  const result = await api("/api/privy/deposit-master", {
    method: "POST",
    body: JSON.stringify({
      amount_usdc: Number($("#funding-usdc-amount").value),
      confirmed: true,
    }),
  });
  await loadState();
  const reference = result.hash || result.actionId || result.status || "submitted";
  toast(`Master deposit submitted: ${maskHash(reference)}`);
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
    network: state.runtime?.network || DEFAULT_NETWORK,
    ui_mode: "human",
    execution_policy: "auto_testnet_confirm_prodnet",
    watchlist: watchlist.length ? watchlist : DEFAULT_ASSETS,
    allowed_assets: allowedAssets.length ? allowedAssets : DEFAULT_ASSETS,
    sync_asset_lists: syncAssetLists,
    max_order_usdc: Number($("#max-order").value),
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
  if (state.isAnalyzing) return;
  const asset = normalizeAssetSymbol($("#asset-input").value || "BTC");
  const context = $("#context-input").value || null;
  state.analysis = null;
  state.plan = null;
  state.order = null;
  renderTradingView();
  const status = $("#analysis-status");
  if (status) status.textContent = `Loading ${displayPerpLabel(asset)} candles before analysis.`;
  try {
    await loadChartCandles(asset, state.activeTimeframe);
    state.isAnalyzing = true;
    renderTradingView();
    if (status) status.textContent = "Claude and market tools are analyzing the setup.";
    const result = await api("/api/agent/analyze", {
      method: "POST",
      body: JSON.stringify({
        asset,
        context,
      }),
    });
    state.analysis = result.analysis;
    state.plan = result.plan;
    state.selectedCandidateIndex = 0;
    if (result.analysis?.candles_by_timeframe) {
      state.marketCandles[result.analysis.asset] = {
        ...(state.marketCandles[result.analysis.asset] || {}),
        ...result.analysis.candles_by_timeframe,
      };
    }
    await loadState();
    toast("Analysis complete");
  } finally {
    state.isAnalyzing = false;
    renderTradingView();
  }
}

async function scan() {
  const result = await api("/api/agent/proactive-scan", { method: "POST" });
  state.analysis = result.analysis;
  state.plan = result.plan;
  state.selectedCandidateIndex = 0;
  await loadState();
  toast("Proactive scan complete");
}

function optionalNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

async function createManualPlan() {
  const asset = currentChartAsset();
  const manual = state.manualOrder;
  const mark = latestMarkPrice(asset);
  const entryPrice =
    manual.entry_type === "limit" ? optionalNumber(manual.entry_price) : mark || null;
  const leverage = 1;
  const plan = await api("/api/trades/manual-plan", {
    method: "POST",
    body: JSON.stringify({
      asset,
      side: manual.side,
      entry_type: manual.entry_type,
      size_usdc: Number(manual.size_usdc),
      entry_price: entryPrice,
      stop_loss: null,
      take_profit: null,
      leverage,
    }),
  });
  state.plan = plan;
  state.analysis = null;
  state.selectedCandidateIndex = 0;
  await loadState();
  toast("Manual plan created");
  return plan;
}

async function executeTrade() {
  if (!state.plan?.id) throw new Error("No trade plan to execute.");
  const result = await api(`/api/trades/${state.plan.id}/execute`, {
    method: "POST",
    body: JSON.stringify({
      confirmed: $("#execute-confirm").checked,
    }),
  });
  state.plan = result.plan;
  await loadState();
  toast("Execution submitted");
}

async function submitManualOrder() {
  if (!$("#execute-confirm").checked) throw new Error("Confirm order submission first.");
  await createManualPlan();
  await executeTrade();
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
  const quickAssetButton = event.target.closest("[data-quick-asset]");
  if (quickAssetButton) {
    const nextAsset = quickAssetButton.dataset.quickAsset || "BTC";
    selectChartAsset(nextAsset);
    return;
  }
  const timeframeButton = event.target.closest("[data-timeframe]");
  if (timeframeButton) {
    state.activeTimeframe = timeframeButton.dataset.timeframe || "1h";
    state.chartHover = null;
    const asset = currentChartAsset();
    if (!state.marketCandles?.[asset]?.[state.activeTimeframe]?.length) {
      state.candleStatus[candleStatusKey(asset, state.activeTimeframe)] = "loading";
      state.isLoadingCandles = true;
    }
    syncTimeframeButtons();
    renderTradingView();
    loadChartCandles(asset, state.activeTimeframe).catch((error) => toast(error.message));
    return;
  }
  const candidateButton = event.target.closest("[data-candidate-index]");
  if (candidateButton) {
    state.selectedCandidateIndex = Number(candidateButton.dataset.candidateIndex) || 0;
    renderTradingView();
    return;
  }
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
    if (action === "create-manual-plan") await createManualPlan();
    if (action === "submit-manual-order") await submitManualOrder();
    if (action === "execute") await executeTrade();
    if (action === "reject") await rejectTrade();
    if (action === "privy-setup-agent") await setupPrivyAgent();
    if (action === "toggle-sensitive") toggleSensitiveWalletData();
    if (action === "copy-wallet-address") await copyWalletAddress(actionTarget.dataset.walletTarget);
    if (action === "open-hyperliquid-deposit") openHyperliquidDeposit();
    if (action === "deposit-master-hyperliquid") await depositMasterToHyperliquid();
    if (action === "events" || action === "refresh") await loadState();
  } catch (error) {
    toast(error.message);
  }
});

document.addEventListener("input", (event) => {
  const field = event.target.closest("[data-manual-field]");
  if (!field) return;
  state.manualOrder[field.dataset.manualField] = field.value;
  if (field.dataset.manualField === "leverage") renderTradingView();
});

document.addEventListener("change", (event) => {
  const field = event.target.closest("[data-manual-field]");
  if (!field) return;
  state.manualOrder[field.dataset.manualField] = field.value;
  renderTradingView();
});

document.addEventListener("click", (event) => {
  const pick = event.target.closest("[data-manual-pick]");
  if (pick) {
    state.manualOrder[pick.dataset.manualPick] = pick.dataset.value;
    renderTradingView();
    return;
  }
  const size = event.target.closest("[data-manual-size]");
  if (size) {
    state.manualOrder.size_usdc = Number(size.dataset.manualSize);
    renderTradingView();
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

$("#asset-input")?.addEventListener("input", () => {
  selectChartAsset(currentChartAsset());
});

window.addEventListener("resize", () => {
  if (state.screen === "trading") renderChart();
});

loadState().catch((error) => toast(error.message));

window.hyperDemo = {
  api,
  loadState,
  state,
  toast,
  maskAddress,
};
