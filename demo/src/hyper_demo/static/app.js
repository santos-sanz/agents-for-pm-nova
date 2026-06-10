const CHAT_HUMAN_APPROVAL_TOOL_NAMES = new Set([
  "trading_execute_plan",
  "trading_close_position",
  "trading_set_protection",
]);

const state = {
  runtime: null,
  setup: null,
  analysis: null,
  plan: null,
  order: null,
  orderBook: null,
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
  liveMarket: {
    connected: false,
    lastTickAt: null,
    source: "idle",
  },
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
  ordersTab: "positions",
  orderMode: "manual",
  autoPrefs: {
    risk_appetite: "",
    close_window: "",
  },
  autoChat: {
    session: null,
    events: [],
    plans: [],
    lastAsset: "",
  },
  positionProtection: {},
  manualOrder: {
    side: "long",
    entry_type: "market",
    size_usdc: 25,
    entry_price: "",
    stop_loss: "",
    take_profit: "",
    leverage: 1,
    reduce_only: false,
    exits_enabled: false,
    take_profit_enabled: false,
    stop_loss_enabled: false,
    exit_input_mode: "price",
  },
  manualOrderDirty: false,
  lastOrderError: "",
  isSubmittingOrder: false,
  showSensitiveWalletData: false,
  masterFundingBalances: null,
  transferBalances: {
    source: null,
    destination: null,
  },
  externalTransferBalances: {
    source: null,
    destination: null,
  },
  tradingDepositBalances: {
    master: null,
    hyperliquid: null,
  },
  transferResult: null,
  externalTransferResult: null,
  tradingDepositResult: null,
  isSubmittingTransfer: false,
  isSubmittingExternalTransfer: false,
  isSubmittingTradingDeposit: false,
  external_withdrawal_address: "",
  chat: {
    resources: null,
    deployment: null,
    sessions: [],
    events: {},
    capabilities: null,
    activeSessionId: null,
    isLoading: false,
    isSending: false,
  },
};

const DEFAULT_ASSETS = ["BTC", "ETH", "SOL", "HYPE"];
const DEFAULT_NETWORK = "prodnet";
const AGENT_NAME = "HyperClaude";
const ARBITRUM_USDC_ADDRESS = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831";
const MIN_ORDER_USDC = 10;
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
const realtimeRuntime = {
  reconnectTimer: null,
  renderTimer: null,
  socket: null,
  url: "",
};
const chatRuntime = {
  pollTimer: null,
  pollUntil: 0,
};
const INTERVAL_SECONDS = {
  "15m": 15 * 60,
  "1h": 60 * 60,
  "4h": 4 * 60 * 60,
  "1d": 24 * 60 * 60,
};
const imageLessAssetSymbols = new Set(["HYPE", "SPCX"]);
const failedAssetIconUrls = new Set();

function $(selector) {
  return document.querySelector(selector);
}

function screenFromPath() {
  return window.location.pathname === "/transfer" ? "transfer" : "trading";
}

state.screen = screenFromPath();

function syncUrlForScreen() {
  const nextPath = state.screen === "transfer" ? "/transfer" : "/";
  if (window.location.pathname !== nextPath) {
    window.history.pushState({}, "", nextPath);
  }
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

function marketDataKey(value) {
  return displayAssetSymbol(value).toUpperCase();
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
  return Math.max(1, Math.floor(Math.min(10, exchangeMax || 10)));
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
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const text = await response.text();
  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  let payload = null;
  if (text && isJson) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: readableResponseText(text, response.statusText) };
    }
  } else if (text) {
    payload = { detail: readableResponseText(text, response.statusText) };
  }
  if (!response.ok) throw new Error(apiErrorMessage(payload, response.statusText));
  return payload;
}

function readableResponseText(text, fallback = "Request failed.") {
  const cleaned = String(text || "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!cleaned) return fallback || "Request failed.";
  if (cleaned.toLowerCase().includes("internal server error")) {
    return "Server error. Check the demo terminal logs, then retry the step.";
  }
  return cleaned.slice(0, 240);
}

function apiErrorMessage(payload, fallback) {
  const detail = payload?.detail;
  if (typeof detail === "string") return friendlyOrderError(detail);
  if (Array.isArray(detail)) {
    const message = detail
      .map((item) => item?.msg || item?.message || JSON.stringify(item))
      .filter(Boolean)
      .join("; ");
    return friendlyOrderError(message);
  }
  if (detail && typeof detail === "object") return friendlyOrderError(detail.message || JSON.stringify(detail));
  return fallback || "Request failed.";
}

function friendlyOrderError(message = "") {
  const normalized = String(message).toLowerCase();
  if (normalized.includes("minimum value of $10") || normalized.includes("minimum order value of 10")) {
    return "Order too small. Hyperliquid requires a minimum order value of 10 USDC. Increase Size to at least 10 USDC and try again.";
  }
  if (
    normalized.includes("no valid authorization keys") ||
    normalized.includes("user signing keys") ||
    normalized.includes("privy user authorization") ||
    normalized.includes("invalid jwt token")
  ) {
    return "Privy rejected the wallet-action authorization exchange. Check Privy JWT authentication settings for user-owned server wallet actions, then retry.";
  }
  if (normalized.includes("privy hyperliquid helper failed")) {
    return "Hyperliquid rejected this order before execution. Check Size, Leverage, available margin, and TP/SL prices, then try again.";
  }
  return message || "Request failed.";
}

function orderErrorParts(message = "") {
  const normalized = String(message).toLowerCase();
  if (normalized.includes("order too small")) {
    return {
      title: "Order too small",
      body: "Minimum order value is 10 USDC. Increase Size to 10 USDC or more.",
      details: ["Use the Size field or a preset of at least 10 USDC before submitting again."],
    };
  }
  if (normalized.includes("not enough available margin")) {
    return {
      title: "Not enough margin",
      body: "Reduce Size or Leverage, or add more collateral before trying again.",
      details: ["The wallet withdrawable balance must cover the required margin plus fees."],
    };
  }
  if (normalized.includes("reduce-only")) {
    return {
      title: "No position to reduce",
      body: "Turn off Reduce Only or open a matching position first.",
      details: ["Reduce Only can only close or reduce an existing position on the same market."],
    };
  }
  if (normalized.includes("invalid safe integer") || normalized.includes("whole number")) {
    return {
      title: "Invalid leverage",
      body: "Leverage must be a whole number because Hyperliquid only accepts integer leverage.",
      details: ["Use 1x, 2x, 3x, and so on. Decimal leverage such as 2.5x is not accepted."],
    };
  }
  if (normalized.includes("hyperliquid rejected")) {
    const exchangeReason = String(message).match(/Exchange reason:\s*(.*?)(?:\.\s*Check|$)/i)?.[1];
    return {
      title: "Exchange rejected the order",
      body: exchangeReason
        ? `Exchange reason: ${exchangeReason}.`
        : "Hyperliquid did not accept this order before execution.",
      details: [
        "For Long: Take Profit must be above entry and Stop Loss below entry.",
        "For Short: Take Profit must be below entry and Stop Loss above entry.",
        "Check Size, Leverage, available margin, and whether Stop Loss is beyond liquidation.",
      ],
    };
  }
  return {
    title: "Order blocked",
    body: message || "Review the order inputs and try again.",
    details: [
      "Check Size, Leverage, available margin, and TP/SL prices.",
      "If this keeps failing, reduce the order size and submit again.",
    ],
  };
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("visible");
  window.setTimeout(() => el.classList.remove("visible"), 2800);
}

function setOrderError(message = "") {
  state.lastOrderError = message;
  renderTicket();
}

async function loadState() {
  const payload = await api("/api/state");
  Object.assign(state, payload);
  state.screen = screenFromPath();
  state.marketCandles = state.marketCandles || {};
  syncManualOrderFromStoredPlan();
  syncAssetInputFromStoredTrade();
  try {
    state.wallet = await api("/api/wallet");
  } catch (error) {
    state.wallet = null;
    console.warn("Wallet state unavailable", error);
  }
  try {
    state.orderBook = await api("/api/orders");
  } catch (error) {
    state.orderBook = null;
    console.warn("Orders unavailable", error);
  }
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
  try {
    await loadChatState({ renderAfter: false });
  } catch (error) {
    console.warn("Managed chat unavailable", error);
  }
  render();
  startRealtimeMarketData();
  loadChartCandles().catch((error) => toast(error.message));
}

function orderAvailableUsdc() {
  const maxOrder = Number(state.runtime?.max_order_usdc || 100);
  const withdrawable = Number(state.wallet?.withdrawable_usdc);
  if (Number.isFinite(withdrawable) && withdrawable >= 0) return Math.max(0, Math.min(maxOrder, withdrawable));
  return maxOrder;
}

function render() {
  renderRuntime();
  renderSetup();
  renderConnectedWallet();
  renderTransferScreen();
  renderExternalTransferScreen();
  renderTradingView();
  renderEvents();
  renderChat();
  renderScreen();
}

function renderRuntime() {
  const runtime = state.runtime || {};
  $("#max-order").value = runtime.max_order_usdc || 100;
  const syncAssetLists = runtime.sync_asset_lists !== false;
  const syncAssetListsInput = $("#sync-asset-lists");
  if (syncAssetListsInput) syncAssetListsInput.checked = syncAssetLists;
  const autoApproveInput = $("#agent-auto-approve");
  if (autoApproveInput) autoApproveInput.checked = runtime.ui_mode === "robot";
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
  for (const button of document.querySelectorAll(".network-card[data-network]")) {
    button.classList.toggle("active", button.dataset.network === (runtime.network || DEFAULT_NETWORK));
  }
  document.body.dataset.uiMode = runtime.ui_mode || "human";
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
  const rawUrl = iconUrl || assetMeta(symbol)?.icon_url || "";
  const shouldRenderImage = rawUrl && !failedAssetIconUrls.has(rawUrl) && !imageLessAssetSymbols.has(marketDataKey(symbol));
  const safeUrl = escapeHtml(shouldRenderImage ? rawUrl : "");
  return `
    <span class="asset-icon">
      ${safeUrl ? `<img src="${safeUrl}" alt="" loading="lazy" data-asset-icon-url="${safeUrl}" />` : ""}
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
      if (image.dataset.assetIconUrl) failedAssetIconUrls.add(image.dataset.assetIconUrl);
      image.remove();
    });
  }
}

function updateMarketRailPrices() {
  const target = $("#market-rail");
  if (!target) return;
  for (const button of target.querySelectorAll("[data-quick-asset]")) {
    const asset = button.dataset.quickAsset;
    const meta = assetMeta(asset);
    const price = meta?.mark_price ? compactPrice(meta.mark_price) : "live";
    const priceEl = button.querySelector("small");
    if (priceEl && priceEl.textContent !== price) priceEl.textContent = price;
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
      if (image.dataset.assetIconUrl) failedAssetIconUrls.add(image.dataset.assetIconUrl);
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
  document.body.classList.toggle("chat-screen-active", state.screen === "chat");
  document.body.classList.toggle("transfer-screen-active", state.screen === "transfer");
  for (const button of document.querySelectorAll(".app-nav [data-screen]")) {
    button.classList.toggle("active", button.dataset.screen === state.screen);
  }
  $("#settings-screen").hidden = state.screen !== "settings";
  $("#chat-screen").hidden = state.screen !== "chat";
  $("#transfer-screen").hidden = state.screen !== "transfer";
  if (state.screen === "chat") {
    startChatPolling();
  } else {
    stopChatPolling();
  }
  if (state.screen === "settings") {
    loadChatState().catch((error) => console.warn("Managed chat unavailable", error));
  }
  if (state.screen === "transfer") {
    refreshTransferBalances().catch((error) => toast(error.message));
    refreshExternalTransferBalances().catch((error) => toast(error.message));
    refreshTradingDepositBalances().catch((error) => toast(error.message));
  }
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
  renderOrdersPanel();
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
  if (candidate) return liveProposal(candidate);
  const position = positionForAsset(currentChartAsset());
  if (!position) return null;
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
  if (state.manualOrderDirty) return;
  const storedAsset = state.plan?.source === "manual" ? state.plan.asset : state.analysis?.asset || state.plan?.asset;
  if (!input || !storedAsset) return;
  const current = currentInputAsset();
  if (!current || current === "BTC") input.value = normalizeAssetSymbol(storedAsset);
}

function syncManualOrderFromStoredPlan() {
  const plan = state.plan;
  if (state.manualOrderDirty) return;
  if (plan?.source !== "manual") return;
  state.manualOrder = {
    side: plan.side || "long",
    entry_type: plan.entry_type || "market",
    size_usdc: plan.size_usdc ?? 25,
    entry_price: plan.entry_type === "limit" ? String(plan.entry_price ?? "") : "",
    stop_loss: plan.stop_loss ? String(plan.stop_loss) : "",
    take_profit: plan.take_profit ? String(plan.take_profit) : "",
    leverage: plan.leverage ?? 1,
    reduce_only: Boolean(state.manualOrder.reduce_only),
    exits_enabled: Boolean(plan.stop_loss || plan.take_profit || state.manualOrder.exits_enabled),
    take_profit_enabled: Boolean(plan.take_profit || state.manualOrder.take_profit_enabled),
    stop_loss_enabled: Boolean(plan.stop_loss || state.manualOrder.stop_loss_enabled),
    exit_input_mode: state.manualOrder.exit_input_mode || "price",
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

function realtimeUrl() {
  return state.setup?.hyperliquid_ws_url || "";
}

function startRealtimeMarketData() {
  const url = realtimeUrl();
  if (!url || !window.WebSocket) return;
  if (realtimeRuntime.socket && realtimeRuntime.url === url) return;
  stopRealtimeMarketData();
  realtimeRuntime.url = url;
  try {
    const socket = new WebSocket(url);
    realtimeRuntime.socket = socket;
    state.liveMarket = { ...state.liveMarket, connected: false, source: "connecting" };
    socket.addEventListener("open", () => {
      state.liveMarket = { ...state.liveMarket, connected: true, source: "websocket" };
      socket.send(JSON.stringify({ method: "subscribe", subscription: { type: "allMids" } }));
    });
    socket.addEventListener("message", (event) => {
      handleRealtimeMarketMessage(event.data);
    });
    socket.addEventListener("close", () => {
      if (realtimeRuntime.socket !== socket) return;
      state.liveMarket = { ...state.liveMarket, connected: false, source: "reconnecting" };
      realtimeRuntime.socket = null;
      realtimeRuntime.reconnectTimer = window.setTimeout(startRealtimeMarketData, 2500);
      scheduleRealtimeRender();
    });
    socket.addEventListener("error", () => {
      state.liveMarket = { ...state.liveMarket, connected: false, source: "error" };
      socket.close();
    });
  } catch (error) {
    console.warn("Realtime market connection unavailable", error);
  }
}

function stopRealtimeMarketData() {
  if (realtimeRuntime.reconnectTimer) window.clearTimeout(realtimeRuntime.reconnectTimer);
  realtimeRuntime.reconnectTimer = null;
  if (realtimeRuntime.socket) {
    realtimeRuntime.socket.close();
    realtimeRuntime.socket = null;
  }
}

function handleRealtimeMarketMessage(rawMessage) {
  let payload;
  try {
    payload = JSON.parse(rawMessage);
  } catch {
    return;
  }
  const mids = payload?.data?.mids || payload?.data || payload?.mids;
  if (!mids || typeof mids !== "object") return;
  const tickTime = Date.now();
  let currentChanged = false;
  for (const [asset, rawPrice] of Object.entries(mids)) {
    const price = Number(rawPrice);
    if (!Number.isFinite(price) || price <= 0) continue;
    const normalized = normalizeAssetSymbol(asset);
    updateMarketAssetPrice(normalized, price);
    if (marketDataKey(currentChartAsset()) === marketDataKey(normalized)) {
      applyRealtimeCandleTick(currentChartAsset(), state.activeTimeframe, price, tickTime);
      currentChanged = true;
    }
  }
  if (!currentChanged) return;
  state.liveMarket = {
    connected: true,
    lastTickAt: new Date(tickTime).toISOString(),
    source: "websocket",
  };
  scheduleRealtimeRender();
}

function updateMarketAssetPrice(asset, price) {
  const key = marketDataKey(asset);
  const existing = state.marketAssets.find((item) => marketDataKey(item.symbol) === key);
  if (existing) {
    existing.mark_price = price;
    return;
  }
  state.marketAssets.push({
    symbol: normalizeAssetSymbol(asset),
    max_leverage: 0,
    mark_price: price,
    delisted: false,
  });
}

function candleBucketStart(timestampMs, interval) {
  const seconds = INTERVAL_SECONDS[interval] || INTERVAL_SECONDS["1h"];
  return Math.floor(timestampMs / 1000 / seconds) * seconds;
}

function isoFromUnixSeconds(seconds) {
  return new Date(seconds * 1000).toISOString();
}

function applyRealtimeCandleTick(asset, interval, price, timestampMs = Date.now()) {
  const normalized = normalizeAssetSymbol(asset);
  state.marketCandles[normalized] = state.marketCandles[normalized] || {};
  const candles = state.marketCandles[normalized][interval] || [];
  const bucket = candleBucketStart(timestampMs, interval);
  const latest = candles.at(-1);
  const latestTime = latest ? candleTimestamp(latest) : null;
  let candle;
  if (latest && latestTime === bucket) {
    latest.high = Math.max(Number(latest.high || price), price);
    latest.low = Math.min(Number(latest.low || price), price);
    latest.close = price;
    candle = latest;
  } else {
    candle = {
      asset: normalized,
      interval,
      opened_at: isoFromUnixSeconds(bucket),
      open: latest ? Number(latest.close) : price,
      high: price,
      low: price,
      close: price,
      volume: 0,
      source: "websocket",
    };
    candles.push(candle);
    if (candles.length > 500) candles.splice(0, candles.length - 500);
    state.marketCandles[normalized][interval] = candles;
  }
  state.candleStatus[candleStatusKey(normalized, interval)] = "loaded";
  updateLightweightCandle(candle);
}

function updateLightweightCandle(candle) {
  if (!chartRuntime.candles) return;
  const [data] = lightweightCandleData([candle]);
  if (!data) return;
  chartRuntime.candles.update(data);
  chartRuntime.key = "";
}

function scheduleRealtimeRender() {
  if (realtimeRuntime.renderTimer) return;
  realtimeRuntime.renderTimer = window.setTimeout(() => {
    realtimeRuntime.renderTimer = null;
    updateMarketRailPrices();
    renderMarketStats();
    renderTicket();
  }, 250);
}

function renderBestBet() {
  const target = $("#best-bet");
  const confidence = $("#confidence");
  if (confidence) {
    confidence.textContent = state.orderMode === "auto" ? "Auto" : "Manual";
    confidence.className = "pill neutral";
  }
  if (target) {
    target.hidden = true;
    target.classList.add("empty");
    target.innerHTML = "";
  }
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
  const liveLabel = state.liveMarket.connected ? "live" : state.liveMarket.source || "idle";
  target.innerHTML = [
    ["Mark", latest ? compactPrice(latest.close) : "--", "neutral"],
    ["Live", liveLabel, state.liveMarket.connected ? "gain" : "warning"],
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
              <span>${number(candidate.leverage, 0)}x</span>
              <span>${number(candidate.score, 1)}</span>
            </button>
          `,
        )
        .join("")
    : `<div class='empty-assets'>${state.isAnalyzing ? "Ranking candidates." : "Run analysis to compare candidates."}</div>`;
}

function configureTicketButtons(mode, { previewOnly = false, preflightBlocked = false } = {}) {
  const buttons = [...document.querySelectorAll(".ticket-panel .button-row button")];
  const [left, main, right] = buttons;
  if (!left || !main || !right) return;
  if (mode === "auto") {
    left.dataset.action = "auto-analyze";
    left.textContent = state.isAnalyzing ? "Agent running..." : "Run agent";
    left.disabled = state.isAnalyzing || !autoPrefsComplete();
    main.dataset.action = "open-auto-chat";
    main.textContent = "Open in Chat";
    main.disabled = !state.autoChat.session?.id;
    right.dataset.action = "reject-auto-proposal";
    right.textContent = "Clear";
    right.disabled = state.isAnalyzing || (!state.autoChat.session && !state.autoChat.events.length);
    return;
  }
  left.dataset.action = "create-manual-plan";
  left.textContent = "Preview";
  left.disabled = previewOnly || state.isSubmittingOrder;
  main.dataset.action = "submit-manual-order";
  main.textContent = state.isSubmittingOrder ? "Submitting..." : "Place order";
  main.disabled = previewOnly || state.isSubmittingOrder || preflightBlocked;
  right.dataset.action = "reject";
  right.textContent = "Clear";
  right.disabled = !activePlan();
}

function autoPrefsComplete() {
  return Boolean(state.autoPrefs.risk_appetite && state.autoPrefs.close_window);
}

function orderModeSwitchMarkup() {
  return `
    <div class="mode-switch" aria-label="Order mode">
      <button type="button" class="${state.orderMode === "manual" ? "active" : ""}" data-order-mode="manual">Manual</button>
      <button type="button" class="${state.orderMode === "auto" ? "active" : ""}" data-order-mode="auto">Auto</button>
    </div>
  `;
}

function proposalIssue(candidate) {
  if (!candidate) return "Run analysis to create proposals.";
  if (Number(candidate.size_usdc || 0) < MIN_ORDER_USDC) return "Size is below the 10 USDC minimum.";
  if (Number(candidate.size_usdc || 0) > Number(state.runtime?.max_order_usdc || 100)) {
    return "Size is above the runtime max order.";
  }
  const leverage = Number(candidate.leverage || 0);
  if (!Number.isInteger(leverage)) return "Leverage must be a whole number.";
  if (leverage < 1 || leverage > assetMaxLeverage(candidate.asset || currentChartAsset())) {
    return "Leverage is outside the market limit.";
  }
  const live = liveProposal(candidate, candidate.asset || currentChartAsset());
  const entry = Number(live.entry_price || 0);
  const mark = latestMarkPrice(candidate.asset || currentChartAsset());
  const hasTakeProfit = live.take_profit !== null && live.take_profit !== undefined;
  const hasStopLoss = live.stop_loss !== null && live.stop_loss !== undefined;
  const takeProfit = Number(live.take_profit || 0);
  const stopLoss = Number(live.stop_loss || 0);
  if (candidate.side === "long") {
    if (hasTakeProfit && (takeProfit <= entry || (mark && takeProfit <= mark))) {
      return "Take Profit is not above entry and mark.";
    }
    if (hasStopLoss && (stopLoss >= entry || (mark && stopLoss >= mark))) {
      return "Stop Loss is not below entry and mark.";
    }
  }
  if (candidate.side === "short") {
    if (hasTakeProfit && (takeProfit >= entry || (mark && takeProfit >= mark))) {
      return "Take Profit is not below entry and mark.";
    }
    if (hasStopLoss && (stopLoss <= entry || (mark && stopLoss <= mark))) {
      return "Stop Loss is not above entry and mark.";
    }
  }
  return "";
}

function proposalEntryPrice(candidate, asset = currentChartAsset()) {
  if (!candidate) return 0;
  if (candidate.entry_type === "market") {
    return latestMarkPrice(asset) || Number(candidate.entry_price || 0);
  }
  return Number(candidate.entry_price || 0);
}

function proposalExitPrices(candidate, entryPrice = proposalEntryPrice(candidate)) {
  const takeProfit =
    candidate?.take_profit === null || candidate?.take_profit === undefined
      ? null
      : Number(candidate.take_profit);
  const stopLoss =
    candidate?.stop_loss === null || candidate?.stop_loss === undefined ? null : Number(candidate.stop_loss);
  if (!candidate || !entryPrice) return { take_profit: takeProfit, stop_loss: stopLoss };
  const originalEntry = Number(candidate.entry_price || 0);
  if (candidate.entry_type !== "market" || !originalEntry) {
    return { take_profit: takeProfit, stop_loss: stopLoss };
  }
  const stopDistance = stopLoss === null ? null : Math.abs(originalEntry - stopLoss) / originalEntry;
  const takeDistance = takeProfit === null ? null : Math.abs(takeProfit - originalEntry) / originalEntry;
  const isShort = candidate.side === "short";
  return {
    stop_loss: stopDistance === null ? null : entryPrice * (isShort ? 1 + stopDistance : 1 - stopDistance),
    take_profit: takeDistance === null ? null : entryPrice * (isShort ? 1 - takeDistance : 1 + takeDistance),
  };
}

function liveProposal(candidate, asset = currentChartAsset()) {
  if (!candidate) return null;
  const entryPrice = proposalEntryPrice(candidate, asset);
  const exits = proposalExitPrices(candidate, entryPrice);
  return {
    ...candidate,
    entry_price: entryPrice,
    take_profit: exits.take_profit,
    stop_loss: exits.stop_loss,
  };
}

function autoPlanById(planId) {
  return (state.autoChat.plans || []).find((plan) => plan.id === planId) || null;
}

function autoChatResultsMarkup() {
  const plans = state.autoChat.plans || [];
  if (!plans.length) {
    return `<div class="empty-assets">
      ${autoPrefsComplete()
        ? "Run the agent to generate several intraday trade proposals."
        : "Choose Risk appetite and Close window, then run the agent."}
    </div>`;
  }
  return `
    ${
      plans.length
        ? `<div class="auto-plan-stack">
            ${plans
              .map((plan, index) => {
                const side = String(plan.side || "--").toUpperCase();
                const stopPolicy = plan.stop_loss
                  ? `SL ${compactPrice(plan.stop_loss)}`
                  : "No SL · monitored invalidation";
                return `
                  <article class="auto-plan-card">
                    <div class="auto-plan-card-head">
                      <span class="pill ${decisionClass(plan.execution_decision || "proposed")}">Plan ${index + 1}</span>
                      <b>${escapeHtml(displayPerpLabel(plan.asset || currentChartAsset()))}</b>
                    </div>
                    <strong>${escapeHtml(side)} · ${number(plan.leverage || 0, 0)}x · ${money(plan.size_usdc || 0)}</strong>
                    <div class="auto-plan-metrics">
                      <span><small>Entry</small><b>${escapeHtml(plan.entry_type || "market")} ${compactPrice(plan.entry_price)}</b></span>
                      <span><small>Take profit</small><b>${compactPrice(plan.take_profit)}</b></span>
                      <span><small>Risk policy</small><b>${escapeHtml(stopPolicy)}</b></span>
                    </div>
                    <p>${escapeHtml(plan.rationale || plan.thesis || "Agent-created trade plan ready for review.")}</p>
                    <div class="auto-plan-actions">
                      <button type="button" data-action="review-auto-plan" data-plan-id="${escapeHtml(plan.id || "")}">Review</button>
                      <button type="button" class="danger" data-action="execute-auto-plan" data-plan-id="${escapeHtml(plan.id || "")}">Approve & place</button>
                    </div>
                  </article>
                `;
              })
              .join("")}
          </div>`
        : ""
    }
  `;
}

function renderAutoOrderSection(ticketAsset) {
  const candidates = activeCandidates().slice(0, 5);
  const selected = selectedCandidate();
  const selectedIssue = proposalIssue(selected);
  const riskOptions = ["conservative", "balanced", "aggressive"];
  const closeOptions = ["15m", "1h", "4h", "1d"];
  const prefsReady = autoPrefsComplete();
  const autoStatus = state.isAnalyzing
    ? "Agent running"
    : state.autoChat.session
      ? "Agent proposals ready"
      : prefsReady
        ? "Ready to run agent"
        : "Choose preferences";
  return `
    <section class="manual-order-section auto-order-section">
      ${orderModeSwitchMarkup()}
      <div class="auto-agent-intro">
        <b>Managed Chat agent</b>
        <span>Generate several intraday trade proposals using wallet, allowed assets, positions, marks, and guardrails.</span>
      </div>
      <div class="auto-prefs" aria-label="Auto preferences">
        <div class="auto-pref-group risk-pref">
          <div class="auto-pref-label">
            <span>Risk appetite</span>
            <small>${escapeHtml(state.autoPrefs.risk_appetite || "required")}</small>
          </div>
          <div class="trade-segment" aria-label="Risk appetite">
            ${riskOptions
              .map(
                (item) => `
                  <button type="button" class="${state.autoPrefs.risk_appetite === item ? "active" : ""}" data-auto-pref="risk_appetite" data-value="${item}">
                    ${escapeHtml(item)}
                  </button>
                `,
              )
              .join("")}
          </div>
        </div>
        <div class="auto-pref-group close-pref">
          <div class="auto-pref-label">
            <span>Close window</span>
            <small>${escapeHtml(state.autoPrefs.close_window || "required")}</small>
          </div>
          <div class="trade-segment" aria-label="Close window">
            ${closeOptions
              .map(
                (item) => `
                  <button type="button" class="${state.autoPrefs.close_window === item ? "active" : ""}" data-auto-pref="close_window" data-value="${item}">
                    ${escapeHtml(item)}
                  </button>
                `,
              )
              .join("")}
          </div>
        </div>
      </div>
      <div class="auto-status">
        <span>${escapeHtml(autoStatus)}</span>
        <b>${escapeHtml(displayPerpLabel(ticketAsset))}</b>
      </div>
      <div class="auto-action-row">
        <button type="button" data-action="auto-analyze" ${state.isAnalyzing || !prefsReady ? "disabled" : ""}>
          ${state.isAnalyzing ? "Agent running..." : "Run agent"}
        </button>
        <button type="button" data-action="open-auto-chat" ${state.autoChat.session?.id ? "" : "disabled"}>
          Open in Chat
        </button>
        <button
          type="button"
          data-action="reject-auto-proposal"
          ${state.isAnalyzing || (!state.autoChat.session && !state.autoChat.events.length) ? "disabled" : ""}
        >
          Clear
        </button>
      </div>
      <div class="auto-agent-results">
        ${autoChatResultsMarkup()}
      </div>
      <details class="auto-legacy-proposals" ${candidates.length ? "" : "hidden"}>
        <summary>Technical candidates</summary>
        ${
          candidates.length
            ? candidates
                .map((candidate, index) => {
                  const live = liveProposal(candidate, ticketAsset);
                  const issue = proposalIssue(candidate);
                  const entryLabel = candidate.entry_type === "market" ? "Live mark" : "Entry";
                  return `
                    <button type="button" class="auto-proposal ${candidate.side} ${index === state.selectedCandidateIndex ? "active" : ""}" data-candidate-index="${index}">
                      <span>${escapeHtml(candidate.timeframe)} · ${escapeHtml(candidate.entry_type)}</span>
                      <b>${escapeHtml(candidate.side.toUpperCase())} ${number(candidate.leverage, 0)}x</b>
                      <em>${entryLabel} ${compactPrice(live.entry_price)}</em>
                      <em>TP ${compactPrice(live.take_profit)} · SL ${compactPrice(live.stop_loss)}</em>
                      <small>${issue || `Score ${number(candidate.score, 1)} · ${escapeHtml(candidate.rationale)}`}</small>
                    </button>
                  `;
                })
                .join("")
            : `<div class="empty-assets">${state.isAnalyzing ? "Building proposals." : "Switch to Auto or press Analyze to get proposals."}</div>`
        }
      </details>
      ${
        candidates.length && selectedIssue
          ? `<div class="order-error" role="alert"><span>Proposal needs review</span><b>${escapeHtml(selectedIssue)}</b></div>`
          : ""
      }
    </section>
  `;
}

function positionRows() {
  const positions = globalExecutionSnapshot().positions;
  return positions
    .map((item) => item?.position || item)
    .filter((position) => Number(position?.szi || position?.size || 0) !== 0);
}

function globalExecutionSnapshot() {
  return {
    positions: state.orderBook?.positions || state.wallet?.open_positions || [],
    orders: state.orderBook?.orders || (state.order ? [state.order] : []),
    openOrders: state.orderBook?.open_orders || state.wallet?.open_orders || [],
  };
}

function positionForAsset(asset) {
  return (
    positionRows().find(
      (position) => normalizeAssetSymbol(position.coin || position.asset) === normalizeAssetSymbol(asset),
    ) || null
  );
}

function orderForPosition(asset) {
  const orders = state.orderBook?.orders || [];
  return orders
    .slice()
    .reverse()
    .find((order) => normalizeAssetSymbol(order.asset) === normalizeAssetSymbol(asset));
}

function protectionOrderKind(order, context = {}) {
  const orderType = String(order?.orderType || order?.order_type || "").toLowerCase();
  if (orderType.includes("take profit")) return "take_profit";
  if (orderType.includes("stop")) return "stop_loss";
  const tpsl = order?.t?.trigger?.tpsl || order?.trigger?.tpsl || order?.tpsl;
  if (tpsl === "tp") return "take_profit";
  if (tpsl === "sl") return "stop_loss";
  const price = protectionOrderPrice(order);
  const reference = Number(context.mark || context.entry || 0);
  if (!price || !reference) return null;
  if (context.isLong === true) return price > reference ? "take_profit" : "stop_loss";
  if (context.isLong === false) return price < reference ? "take_profit" : "stop_loss";
  return null;
}

function protectionOrderPrice(order) {
  return Number(
    order?.triggerPx ||
      order?.trigger_px ||
      order?.limitPx ||
      order?.limit_px ||
      order?.price ||
      order?.px ||
      0,
  );
}

function protectionOrdersForAsset(asset, context = {}) {
  const normalizedAsset = normalizeAssetSymbol(asset);
  return (globalExecutionSnapshot().openOrders || [])
    .filter((order) => normalizeAssetSymbol(order?.coin || order?.asset || "") === normalizedAsset)
    .map((order) => ({
      ...order,
      protectionKind: protectionOrderKind(order, context),
      protectionPrice: protectionOrderPrice(order),
    }))
    .filter((order) => order.protectionKind && order.protectionPrice > 0);
}

function activeProtectionForAsset(asset, plan = {}, context = {}) {
  const protection = {
    take_profit: Number(plan.take_profit || 0),
    stop_loss: Number(plan.stop_loss || 0),
    takeProfitOrder: null,
    stopLossOrder: null,
    takeProfitCount: 0,
    stopLossCount: 0,
  };
  for (const order of protectionOrdersForAsset(asset, context)) {
    if (order.protectionKind === "take_profit") {
      protection.takeProfitCount += 1;
      if (!protection.takeProfitOrder || Number(order.timestamp || 0) >= Number(protection.takeProfitOrder.timestamp || 0)) {
        protection.take_profit = order.protectionPrice;
        protection.takeProfitOrder = order;
      }
    }
    if (order.protectionKind === "stop_loss") {
      protection.stopLossCount += 1;
      if (!protection.stopLossOrder || Number(order.timestamp || 0) >= Number(protection.stopLossOrder.timestamp || 0)) {
        protection.stop_loss = order.protectionPrice;
        protection.stopLossOrder = order;
      }
    }
  }
  return protection;
}

function orderFill(order, key) {
  const payload = order?.raw_response?.[key];
  const status = payload?.response?.data?.statuses?.[0] || payload?.data?.statuses?.[0];
  return status?.filled || null;
}

function orderFillPrice(order, key) {
  return Number(orderFill(order, key)?.avgPx || 0);
}

function orderFillSize(order, key) {
  return Number(orderFill(order, key)?.totalSz || 0);
}

function tradePnlRows(orders, positions) {
  const entries = orders.filter((order) => order.plan_id !== "manual_position_close");
  const closes = orders.filter((order) => order.plan_id === "manual_position_close");
  const closedRows = closes.map((closeOrder) => {
    const entryOrder = entries
      .slice()
      .reverse()
      .find((order) => normalizeAssetSymbol(order.asset) === normalizeAssetSymbol(closeOrder.asset));
    const entryPrice = orderFillPrice(entryOrder, "entry") || Number(entryOrder?.plan?.entry_price || 0);
    const closePrice = orderFillPrice(closeOrder, "close");
    const size = orderFillSize(closeOrder, "close") || orderFillSize(entryOrder, "entry");
    const side = entryOrder?.side || (closeOrder.side === "short" ? "long" : "short");
    const direction = side === "short" ? -1 : 1;
    const pnl = entryPrice && closePrice && size ? (closePrice - entryPrice) * size * direction : null;
    return {
      asset: closeOrder.asset,
      status: "closed",
      side,
      entryPrice,
      exitPrice: closePrice,
      size,
      pnl,
      openedAt: entryOrder?.created_at,
      closedAt: closeOrder.created_at,
    };
  });
  const openRows = positions.map((position) => {
    const asset = normalizeAssetSymbol(position.coin || position.asset);
    const signedSize = Number(position.szi || position.size || 0);
    return {
      asset,
      status: "open",
      side: signedSize < 0 ? "short" : "long",
      entryPrice: Number(position.entryPx || position.entry_price || 0),
      exitPrice: positionMarkPrice(position),
      size: Math.abs(signedSize),
      pnl: Number(position.unrealizedPnl || position.unrealized_pnl_usdc || 0),
      openedAt: orderForPosition(asset)?.created_at,
      closedAt: null,
    };
  });
  return [...openRows, ...closedRows];
}

function positionMarkPrice(position) {
  const size = Math.abs(Number(position.szi || position.size || 0));
  const value = Number(position.positionValue || position.position_value_usdc || 0);
  if (size > 0 && value > 0) return value / size;
  return latestMarkPrice(position.coin || position.asset);
}

function percentAway(current, target) {
  const from = Number(current);
  const to = Number(target);
  if (!Number.isFinite(from) || !Number.isFinite(to) || from <= 0 || to <= 0) return null;
  return Math.abs((to - from) / from) * 100;
}

function progressTowardLevel(entry, current, target) {
  const start = Number(entry);
  const mark = Number(current);
  const goal = Number(target);
  if (![start, mark, goal].every((value) => Number.isFinite(value) && value > 0)) return 0;
  const total = Math.abs(goal - start);
  if (!total) return 100;
  const progress = ((mark - start) / (goal - start)) * 100;
  return Math.max(0, Math.min(100, progress));
}

function positionLevelRow(label, price, entry, current, className = "") {
  const hasPrice = Number(price) > 0;
  const away = hasPrice ? percentAway(current, price) : null;
  const progress = hasPrice ? progressTowardLevel(entry, current, price) : 0;
  return `
    <div class="position-level ${className || "neutral"} ${hasPrice ? "" : "muted-level"}">
      <div>
        <span>${label}</span>
        <b>${hasPrice ? compactPrice(price) : "Not set"}</b>
        <em>${away === null ? "--" : `${number(away, 1)}% away`}</em>
      </div>
      <div class="level-track" aria-hidden="true">
        <i style="width: ${number(progress, 1)}%"></i>
      </div>
    </div>
  `;
}

function protectionDraft(asset) {
  const key = normalizeAssetSymbol(asset);
  if (!state.positionProtection[key]) {
    state.positionProtection[key] = { take_profit: "", stop_loss: "", touched: false };
  }
  return state.positionProtection[key];
}

function protectionPriceFromEntry(kind, isLong, entry, percent) {
  const reference = Number(entry);
  const pct = Number(percent);
  if (!Number.isFinite(reference) || reference <= 0 || !Number.isFinite(pct) || pct <= 0) return "";
  const direction = kind === "take_profit" ? 1 : -1;
  const sideMultiplier = isLong ? 1 : -1;
  return inputPriceValue(reference * (1 + (direction * sideMultiplier * pct) / 100));
}

function inputPriceValue(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return "";
  return parsed.toFixed(6).replace(/0+$/, "").replace(/\.$/, "");
}

function defaultProtectionDraft(isLong, entry) {
  return {
    take_profit: protectionPriceFromEntry("take_profit", isLong, entry, 1),
    stop_loss: "",
  };
}

function syncProtectionDraftFromDom() {
  document.querySelectorAll("[data-protection-field]").forEach((field) => {
    const asset = normalizeAssetSymbol(field.dataset.protectionAsset);
    const draft = protectionDraft(asset);
    draft[field.dataset.protectionField] = field.value;
  });
}

function isProtectionEditorActive() {
  return Boolean(document.activeElement?.closest?.(".protection-editor"));
}

function applyProtectionPreset(asset, isLong, entry) {
  const draft = protectionDraft(asset);
  const defaults = defaultProtectionDraft(isLong, entry);
  draft.take_profit = defaults.take_profit;
  draft.touched = true;
  document
    .querySelectorAll(`[data-protection-asset="${CSS.escape(normalizeAssetSymbol(asset))}"]`)
    .forEach((field) => {
      if (!field.dataset.protectionField) return;
      field.value = draft[field.dataset.protectionField] || "";
    });
}

function protectionEditor(asset, isLong, entry, mark, takeProfit, stopLoss, activeProtection) {
  const draft = protectionDraft(asset);
  if (!draft.touched || (!draft.take_profit && !draft.stop_loss)) {
    draft.take_profit = takeProfit ? inputPriceValue(takeProfit) : "";
    draft.stop_loss = stopLoss ? inputPriceValue(stopLoss) : "";
  }
  const protection = activeProtection || activeProtectionForAsset(asset, {}, { isLong, entry, mark });
  const status = [
    protection.takeProfitCount
      ? `TP active at ${compactPrice(protection.take_profit)}`
      : "TP not set",
    protection.stopLossCount
      ? `SL active at ${compactPrice(protection.stop_loss)}`
      : "SL not set",
  ].join(" · ");
  return `
    <div class="protection-editor">
      <div class="protection-editor-title">
        <b>Edit active protection</b>
        <span>${escapeHtml(status)}</span>
      </div>
      <label>
        <span>Take Profit</span>
        <input
          type="number"
          min="0"
          step="0.000001"
          data-protection-asset="${escapeHtml(asset)}"
          data-protection-field="take_profit"
          value="${escapeHtml(draft.take_profit || "")}"
          placeholder="${escapeHtml(protection.takeProfitCount ? inputPriceValue(protection.take_profit) : protectionPriceFromEntry("take_profit", isLong, entry, 1))}"
        />
      </label>
      <label>
        <span>Stop Loss</span>
        <input
          type="number"
          min="0"
          step="0.000001"
          data-protection-asset="${escapeHtml(asset)}"
          data-protection-field="stop_loss"
          value="${escapeHtml(draft.stop_loss || "")}"
          placeholder="${escapeHtml(protection.stopLossCount ? inputPriceValue(protection.stop_loss) : "Optional")}"
        />
      </label>
      <button
        type="button"
        class="protection-preset"
        data-protection-preset="entry-risk"
        data-protection-asset="${escapeHtml(asset)}"
        data-protection-side="${isLong ? "long" : "short"}"
        data-protection-entry="${escapeHtml(String(entry || ""))}"
      >
        Use TP +1%
      </button>
      <button type="button" data-action="set-protection" data-asset="${escapeHtml(asset)}">
        Update protection
      </button>
    </div>
  `;
}

function positionCard(position) {
  const asset = normalizeAssetSymbol(position.coin || position.asset);
  const order = orderForPosition(asset);
  const plan = order?.plan || {};
  const size = Number(position.szi || position.size || 0);
  const isLong = size >= 0;
  const side = isLong ? "Long" : "Short";
  const leverage = position.leverage?.value || position.leverage || plan.leverage || "--";
  const entry = Number(position.entryPx || position.entry_price || plan.entry_price || 0);
  const mark = positionMarkPrice(position);
  const liquidation = Number(position.liquidationPx || position.liquidation_price || 0);
  const pnl = Number(position.unrealizedPnl || position.unrealized_pnl_usdc || 0);
  const funding = Number(position.cumFunding?.sinceOpen || 0);
  const activeProtection = activeProtectionForAsset(asset, plan, { isLong, entry, mark });
  const takeProfit = activeProtection.take_profit;
  const stopLoss = activeProtection.stop_loss;
  return `
    <article class="active-trade-card">
      <div class="active-trade-main">
        <div class="asset-badge">${escapeHtml(displayAssetSymbol(asset).slice(0, 2))}</div>
        <div>
          <h3>${escapeHtml(displayAssetSymbol(asset))} <span>${compactPrice(mark)}</span></h3>
          <p class="${isLong ? "gain" : "loss"}">${escapeHtml(String(leverage))}x ${side.toLowerCase()}</p>
        </div>
        <div class="trade-pnl">
          <span class="${pnl >= 0 ? "gain" : "loss"}">${money(pnl)}</span>
          <b>${money(position.positionValue || position.position_value_usdc || order?.size_usdc || 0)}</b>
        </div>
      </div>
      <div class="trade-summary">
        <div><span>Current PnL</span><b class="${pnl >= 0 ? "gain" : "loss"}">${money(pnl)}</b></div>
        <div><span>Funding</span><b>${money(funding)}</b></div>
        <div><span>Entry</span><b>${compactPrice(entry)}</b></div>
      </div>
      <div class="position-levels">
        ${positionLevelRow("Take Profit", takeProfit, entry, mark, "profit")}
        ${positionLevelRow("Stop Loss", stopLoss, entry, mark, "stop")}
        ${positionLevelRow("Liquidation", liquidation, entry, mark, "liquidation")}
      </div>
      ${protectionEditor(asset, isLong, entry, mark, takeProfit, stopLoss, activeProtection)}
      <p class="close-path-note">Happy path close step: submit a reduce-only market order after the tiny mainnet proof.</p>
      <div class="active-trade-actions">
        <button type="button" class="danger" data-action="close-position" data-asset="${escapeHtml(asset)}">
          Close position
        </button>
      </div>
    </article>
  `;
}

function exitPercentPreview(kind, manual, entryPrice) {
  const price = exitPriceFromManualPercent(kind, manual, entryPrice);
  return price ? compactPrice(price) : "--";
}

function exitFieldMarkup(kind, label, manual, exitMode, entryPrice, placeholder, exitStep, exitUnit) {
  const value = manual[kind] || "";
  if (exitMode !== "percent") {
    return `
      <label>${label}
        <span>
          <input type="number" min="0" step="${exitStep}" data-manual-field="${kind}" value="${escapeHtml(value)}" placeholder="${placeholder}" />
          <em>${escapeHtml(exitUnit)}</em>
        </span>
      </label>
    `;
  }
  const percent = Math.max(0, Math.min(50, Number(value || (kind === "take_profit" ? 3 : 2))));
  const angle = (percent / 50) * 270;
  return `
    <div class="zoom-dial ${kind === "take_profit" ? "profit" : "stop"}">
      <div class="zoom-dial-head">
        <span>${label}</span>
        <b>${number(percent, 1)}%</b>
      </div>
      <div class="zoom-wheel" style="--zoom-angle: ${number(angle, 2)}deg">
        <button type="button" aria-label="Decrease ${label}" data-exit-step="${kind}" data-delta="-0.5">-</button>
        <output>${exitPercentPreview(kind, { ...manual, [kind]: percent }, entryPrice)}</output>
        <button type="button" aria-label="Increase ${label}" data-exit-step="${kind}" data-delta="0.5">+</button>
      </div>
      <input
        type="range"
        min="0.5"
        max="50"
        step="0.5"
        data-manual-field="${kind}"
        value="${escapeHtml(percent)}"
        aria-label="${label} percent"
      />
    </div>
  `;
}

function renderOrdersPanel() {
  const target = $("#orders-panel");
  if (!target) return;
  syncProtectionDraftFromDom();
  const snapshot = globalExecutionSnapshot();
  const positions = positionRows();
  const orders = snapshot.orders;
  const scope = $("#orders-scope");
  if (scope) scope.textContent = "All markets";
  const tabs = [
    ["positions", "Open positions", positions.length],
    ["pnl", "Trade P&L", tradePnlRows(orders, positions).length],
    ["history", "Order history", orders.length],
  ];
  if (!tabs.some(([key]) => key === state.ordersTab)) state.ordersTab = "positions";
  const positionMarkup = positions.length
    ? positions
        .map((position) => positionCard(position))
        .join("")
    : "<div class='orders-empty'>No open positions.</div>";
  const pnlRows = tradePnlRows(orders, positions);
  const pnlMarkup = pnlRows.length
    ? pnlRows
        .map(
          (row) => `
            <div class="order-row pnl-row">
              <div><span>Asset</span><b>${escapeHtml(displayPerpLabel(row.asset))}</b></div>
              <div><span>Status</span><b>${escapeHtml(row.status)}</b></div>
              <div><span>Side</span><b class="${row.side === "long" ? "gain" : "loss"}">${escapeHtml(row.side)}</b></div>
              <div><span>Entry</span><b>${row.entryPrice ? compactPrice(row.entryPrice) : "--"}</b></div>
              <div><span>${row.status === "open" ? "Mark" : "Exit"}</span><b>${row.exitPrice ? compactPrice(row.exitPrice) : "--"}</b></div>
              <div><span>Size</span><b>${row.size ? number(row.size, 6) : "--"}</b></div>
              <div><span>P&L</span><b class="${Number(row.pnl || 0) >= 0 ? "gain" : "loss"}">${row.pnl === null ? "--" : money(row.pnl)}</b></div>
              <div><span>${row.status === "open" ? "Opened" : "Closed"}</span><b>${row.closedAt || row.openedAt ? new Date(row.closedAt || row.openedAt).toLocaleTimeString() : "--"}</b></div>
            </div>
          `,
        )
        .join("")
    : "<div class='orders-empty'>No P&L yet.</div>";
  const orderMarkup = orders.length
    ? orders
        .slice()
        .reverse()
        .map(
          (order) => `
            <div class="order-row history-row">
              <div><span>Order</span><b>${escapeHtml(order.entry_order_id || order.id || "--")}</b></div>
              <div><span>Asset</span><b>${escapeHtml(displayPerpLabel(order.asset))}</b></div>
              <div><span>Side</span><b class="${order.side === "long" ? "gain" : "loss"}">${escapeHtml(order.side || "--")}</b></div>
              <div><span>Value</span><b>${money(order.size_usdc || 0)}</b></div>
              <div><span>Status</span><b>${escapeHtml(order.status || "--")}</b></div>
              <div><span>Exchange</span><b>${escapeHtml(order.exchange || "--")}</b></div>
              <div><span>Created</span><b>${order.created_at ? new Date(order.created_at).toLocaleTimeString() : "--"}</b></div>
              <p>${escapeHtml(order.message || "")}</p>
            </div>
          `,
        )
        .join("")
    : "<div class='orders-empty'>No submitted orders yet.</div>";
  const activeMarkup =
    state.ordersTab === "positions"
      ? positionMarkup
      : state.ordersTab === "pnl"
      ? pnlMarkup
      : orderMarkup;
  target.innerHTML = `
    <section class="orders-section">
      <div class="orders-tabs" role="tablist" aria-label="Orders and positions">
        ${tabs
          .map(
            ([key, label, count]) => `
              <button
                type="button"
                role="tab"
                aria-selected="${state.ordersTab === key}"
                class="${state.ordersTab === key ? "active" : ""}"
                data-orders-tab="${key}"
              >
                <span>${escapeHtml(label)}</span>
                <b>${count}</b>
              </button>
            `,
          )
          .join("")}
      </div>
      <div class="orders-tab-panel">
        ${activeMarkup}
      </div>
    </section>
  `;
}

function renderTicket() {
  const plan = activePlan();
  const isManualPlan = plan?.source === "manual";
  const candidate = selectedCandidate();
  const previewOnly = Boolean(candidate && plan && !candidateMatchesPlan(candidate, plan));
  const ticketAsset = currentChartAsset();
  document.querySelector(".ticket-panel")?.classList.toggle("auto-mode", state.orderMode === "auto");
  const manual = state.manualOrder;
  const maxLeverage = assetMaxLeverage(ticketAsset);
  manual.leverage = boundedLeverage(manual.leverage, maxLeverage);
  const decision = previewOnly ? "preview_only" : plan?.execution_decision || "manual_draft";
  const decisionPill = $("#decision-pill");
  if (decisionPill) {
    decisionPill.textContent = state.orderMode === "auto"
      ? "auto mode"
      : isManualPlan && decision === "proposed"
        ? "manual mode"
        : !plan
        ? "manual mode"
        : decision.replaceAll("_", " ");
    decisionPill.className = `pill ${decisionClass(decision)}`;
  }
  $("#ticket-title").textContent = `Trade ${displayPerpLabel(ticketAsset)}`;
  if (state.orderMode === "auto") {
    configureTicketButtons("auto");
    $("#ticket").innerHTML = renderAutoOrderSection(ticketAsset);
    return;
  }
  const source = candidate || plan;
  const livePosition = positionForAsset(ticketAsset);
  const livePositionSize = Number(livePosition?.szi || livePosition?.size || 0);
  const livePositionLabel = livePosition
    ? `${livePositionSize >= 0 ? "long" : "short"} ${money(
        livePosition.positionValue || livePosition.position_value_usdc || 0,
      )}`
    : "None";
  const mark = latestMarkPrice(ticketAsset);
  const maxOrder = Number(state.runtime?.max_order_usdc || 100);
  const available = orderAvailableUsdc();
  const leverage = boundedLeverage(manual.leverage, maxLeverage);
  manual.leverage = leverage;
  if (available > 0 && Number(manual.size_usdc) > available * leverage) {
    manual.size_usdc = Math.max(1, Math.floor(available * leverage * 100) / 100);
  }
  const maxNotional = available > 0 ? available * leverage : maxOrder;
  if (maxNotional >= MIN_ORDER_USDC && Number(manual.size_usdc) < MIN_ORDER_USDC) {
    manual.size_usdc = MIN_ORDER_USDC;
  }
  const size = Number(manual.size_usdc) || 0;
  const orderValue = size;
  const marginRequired = leverage > 0 ? orderValue / leverage : orderValue;
  const effectiveEntryPrice = manual.entry_type === "limit" ? optionalNumber(manual.entry_price) || mark : mark;
  const liquidationPrice = estimatedLiquidationPrice(manual.side, effectiveEntryPrice, leverage);
  const sizeBase = available > 0 ? available * Math.max(1, leverage) : maxOrder;
  const minSize = sizeBase >= MIN_ORDER_USDC ? MIN_ORDER_USDC : 1;
  const sizePercent = sizeBase > 0 ? Math.min(100, Math.round((size / sizeBase) * 100)) : 0;
  const percentStops = [25, 50, 75, 100];
  const limitHiddenClass = manual.entry_type !== "limit" ? " hidden" : "";
  const exitMode = manual.exit_input_mode || "price";
  const takeProfitEnabled = Boolean(manual.take_profit_enabled || (manual.exits_enabled && manual.take_profit));
  const stopLossEnabled = Boolean(manual.stop_loss_enabled || (manual.exits_enabled && manual.stop_loss));
  const anyExitEnabled = takeProfitEnabled || stopLossEnabled;
  const exitStep = exitMode === "percent" ? "0.1" : "0.000001";
  const exitUnit = exitMode === "percent" ? "%" : displayAssetSymbol(ticketAsset);
  const takeProfitPlaceholder =
    exitMode === "percent" ? "3.0" : mark ? number(manual.side === "short" ? mark * 0.97 : mark * 1.03, 6) : "0.00";
  const stopLossPlaceholder =
    exitMode === "percent" ? "2.0" : mark ? number(manual.side === "short" ? mark * 1.02 : mark * 0.98, 6) : "0.00";
  const preflightView = manualOrderPreflight({
    asset: ticketAsset,
    mark,
    maxLeverage,
    leverage,
    entryPrice: effectiveEntryPrice,
    liquidationPrice,
    available,
    marginRequired,
    livePosition,
  });
  const blockedPlanError =
    plan?.execution_decision === "blocked" ? plan.execution_message || "Execution blocked." : "";
  const orderErrorView = state.lastOrderError
    ? orderErrorParts(state.lastOrderError)
    : preflightView || (blockedPlanError ? orderErrorParts(blockedPlanError) : null);
  configureTicketButtons("manual", {
    previewOnly,
    preflightBlocked: Boolean(preflightView?.blocking),
  });
  $("#ticket").innerHTML = `
    <section class="manual-order-section order-ticket-core">
      ${orderModeSwitchMarkup()}
      <div class="order-ticket-meta">
        <div><span>Available</span><b>${money(available)}</b><small>${state.wallet ? "wallet withdrawable" : "order limit"}</small></div>
        <div><span>Position</span><b>${escapeHtml(livePositionLabel)}</b><small>${displayPerpLabel(ticketAsset)}</small></div>
      </div>
      <div class="trade-segment" aria-label="Order type">
        <button type="button" class="${manual.entry_type === "market" ? "active" : ""}" data-manual-pick="entry_type" data-value="market">Market</button>
        <button type="button" class="${manual.entry_type === "limit" ? "active" : ""}" data-manual-pick="entry_type" data-value="limit">Limit</button>
      </div>
      <div class="trade-segment side-picker" aria-label="Side">
        <button type="button" class="${manual.side === "long" ? "active" : ""}" data-manual-pick="side" data-value="long">Long</button>
        <button type="button" class="${manual.side === "short" ? "active" : ""}" data-manual-pick="side" data-value="short">Short</button>
      </div>
      <label class="primary-number">Size
        <span>
          <input type="number" min="${escapeHtml(minSize)}" max="${escapeHtml(sizeBase || maxOrder)}" step="1" data-manual-field="size_usdc" value="${escapeHtml(manual.size_usdc)}" />
          <em class="asset-select-pill">USDC</em>
        </span>
      </label>
      <div class="percent-slider" aria-label="Size percentage">
        <input type="range" min="1" max="100" step="1" data-manual-percent value="${escapeHtml(sizePercent || 1)}" />
        <output>${sizePercent}%</output>
      </div>
      <div class="size-presets" aria-label="Size presets">
        ${percentStops
          .map(
            (percent) => `
              <button type="button" class="${sizePercent === percent ? "active" : ""}" data-manual-percent-preset="${percent}">
                ${percent}%
              </button>
            `,
          )
          .join("")}
      </div>
      <label class="leverage-control">Leverage
        <span>${number(leverage, 0)}x</span>
      </label>
      <div class="percent-slider leverage-slider" aria-label="Leverage">
        <input type="range" min="1" max="${escapeHtml(maxLeverage)}" step="1" data-manual-leverage value="${escapeHtml(leverage)}" />
        <output>${number(maxLeverage, 0)}x max</output>
      </div>
      <label class="primary-number${limitHiddenClass}">Limit price
        <input type="number" min="0" step="0.000001" data-manual-field="entry_price" value="${escapeHtml(manual.entry_price)}" placeholder="${mark ? number(mark, 6) : "0.00"}" />
      </label>
      <div class="order-options">
        <label class="toggle-row">
          <input type="checkbox" data-manual-checkbox="reduce_only" ${manual.reduce_only ? "checked" : ""} />
          <span>Reduce Only</span>
        </label>
        <label class="toggle-row">
          <input type="checkbox" data-manual-checkbox="take_profit_enabled" ${takeProfitEnabled ? "checked" : ""} />
          <span>Take Profit</span>
        </label>
        <label class="toggle-row">
          <input type="checkbox" data-manual-checkbox="stop_loss_enabled" ${stopLossEnabled ? "checked" : ""} />
          <span>Stop Loss</span>
        </label>
      </div>
      <div class="exit-fields ${anyExitEnabled ? "" : "hidden"} ${exitMode === "percent" ? "dial-mode" : ""}">
        <div class="trade-segment exit-mode-picker" aria-label="TP SL input mode">
          <button type="button" class="${exitMode === "price" ? "active" : ""}" data-manual-pick="exit_input_mode" data-value="price">Price</button>
          <button type="button" class="${exitMode === "percent" ? "active" : ""}" data-manual-pick="exit_input_mode" data-value="percent">%</button>
        </div>
        ${
          takeProfitEnabled
            ? exitFieldMarkup("take_profit", "Take profit", manual, exitMode, effectiveEntryPrice, takeProfitPlaceholder, exitStep, exitUnit)
            : ""
        }
        ${
          stopLossEnabled
            ? exitFieldMarkup("stop_loss", "Stop loss", manual, exitMode, effectiveEntryPrice, stopLossPlaceholder, exitStep, exitUnit)
            : ""
        }
      </div>
      <div class="order-footprint">
        <div><span>Mark price</span><b>${mark ? compactPrice(mark) : "--"}</b></div>
        <div><span>Liquidation price</span><b>${liquidationPrice ? compactPrice(liquidationPrice) : "--"}</b></div>
        <div><span>Order value</span><b>${money(orderValue)}</b></div>
        <div><span>Margin required</span><b>${money(marginRequired)}</b></div>
        <div><span>Slippage</span><b>Checked at submit</b></div>
        <div><span>Fees</span><b>Est. on submit</b></div>
      </div>
      ${
        plan?.validation
          ? `<div class="guardrail-checklist ticket-validation">
              ${planGuardrailRows(plan, plan.validation)}
            </div>`
          : ""
      }
      ${
        orderErrorView
          ? `<div class="order-error" role="alert">
              <span>${escapeHtml(orderErrorView.title)}</span>
              <b>${escapeHtml(orderErrorView.body)}</b>
              ${
                orderErrorView.details?.length
                  ? `<ul>${orderErrorView.details.map((detail) => `<li>${escapeHtml(detail)}</li>`).join("")}</ul>`
                  : ""
              }
            </div>`
          : ""
      }
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

async function loadChatState({ renderAfter = true } = {}) {
  const payload = await api("/api/chat/state");
  state.chat.resources = payload.resources;
  state.chat.deployment = payload.deployment || null;
  state.chat.sessions = payload.sessions || [];
  state.chat.capabilities = payload.capabilities || null;
  if (!state.chat.activeSessionId && state.chat.sessions.length) {
    state.chat.activeSessionId = state.chat.sessions[0].id;
  }
  if (state.chat.activeSessionId) {
    await loadChatEvents(state.chat.activeSessionId, { renderAfter: false });
  }
  if (renderAfter) renderChat();
}

async function loadChatEvents(sessionId = state.chat.activeSessionId, { renderAfter = true } = {}) {
  if (!sessionId) return [];
  const payload = await api(`/api/chat/sessions/${encodeURIComponent(sessionId)}`);
  if (payload.session) mergeChatSession(payload.session);
  const events = payload.events || [];
  state.chat.events[sessionId] = events;
  if (renderAfter) renderChat();
  return events;
}

function mergeChatSession(session) {
  if (!session?.id) return;
  const sessions = state.chat.sessions || [];
  const index = sessions.findIndex((item) => item.id === session.id);
  if (index >= 0) {
    sessions[index] = session;
  } else {
    sessions.unshift(session);
  }
  state.chat.sessions = sessions;
}

function selectedChatSession() {
  return (state.chat.sessions || []).find((session) => session.id === state.chat.activeSessionId) || null;
}

function activeChatEvents() {
  const session = selectedChatSession();
  if (!session) return [];
  return state.chat.events[session.id] || [];
}

function renderChat() {
  if (!$("#chat-screen")) return;
  renderChatTranscript();
  renderAgentSettings();
}

function renderAgentSettings() {
  renderChatResources();
  renderChatDeployment();
  renderChatSessions();
  renderVaultStatus();
  renderPendingChatActions();
  renderChatPlanActions();
  renderChatCapabilities();
}

function renderChatResources() {
  const resources = state.chat.resources || {};
  const status = $("#chat-bootstrap-status");
  if (status) {
    status.className = `pill ${chatStatusClass(resources.status)}`;
    status.textContent = resources.status || "disabled";
  }
  const grid = $("#chat-resource-grid");
  if (!grid) return;
  const skillCount = Object.keys(resources.skill_ids || {}).length;
  const memoryCount = Object.keys(resources.memory_store_ids || {}).length;
  const vaultCount = (resources.vault_ids || []).length;
  const mcpCount = (resources.mcp_servers || []).length;
  grid.innerHTML = [
    ["Environment", resources.environment_id ? shortId(resources.environment_id) : "not ready"],
    ["Coordinator", resources.coordinator_agent_id ? shortId(resources.coordinator_agent_id) : "not ready"],
    ["Skills", String(skillCount)],
    ["Memory", String(memoryCount)],
    ["Vaults", String(vaultCount)],
    ["MCP", String(mcpCount)],
  ]
    .map(([label, value]) => `<div><span>${label}</span><b>${escapeHtml(value)}</b></div>`)
    .join("");
  if (resources.disabled_reason || resources.error) {
    grid.innerHTML += `<p class="chat-warning">${escapeHtml(resources.disabled_reason || resources.error)}</p>`;
  }
}

function renderChatDeployment() {
  const deployment = state.chat.deployment || {};
  const status = $("#chat-deployment-status");
  if (status) {
    status.className = `pill ${chatStatusClass(deployment.status)}`;
    status.textContent = deployment.status || "not created";
  }
  const summary = $("#chat-deployment-summary");
  if (summary) {
    const upcoming = deployment.upcoming_runs_at || [];
    summary.innerHTML = [
      ["Deployment", deployment.anthropic_deployment_id ? shortId(deployment.anthropic_deployment_id) : "not created"],
      ["Schedule", deployment.cron_expression || "*/30 * * * *"],
      ["Timezone", deployment.timezone || "Europe/Madrid"],
      ["Next", upcoming[0] ? new Date(upcoming[0]).toLocaleString() : "--"],
      ["Last run", deployment.last_run_id ? shortId(deployment.last_run_id) : "--"],
      ["Session", deployment.last_session_id ? shortId(deployment.last_session_id) : "--"],
    ]
      .map(([label, value]) => `<div><span>${label}</span><b>${escapeHtml(String(value))}</b></div>`)
      .join("");
    if (deployment.last_error) {
      summary.innerHTML += `<p class="chat-warning">${escapeHtml(deployment.last_error)}</p>`;
    }
  }
  syncInputValue("#chat-deployment-name", deployment.name || "HyperClaude intraday watch");
  syncInputValue("#chat-deployment-cron", deployment.cron_expression || "*/30 * * * *");
  syncInputValue("#chat-deployment-timezone", deployment.timezone || "Europe/Madrid");
  syncInputValue("#chat-deployment-prompt", deployment.initial_prompt || defaultDeploymentPrompt());
}

function syncInputValue(selector, value) {
  const input = $(selector);
  if (!input || document.activeElement === input) return;
  input.value = value;
}

function defaultDeploymentPrompt() {
  return [
    "Run the scheduled HyperClaude intraday watch.",
    "Gather runtime settings, wallet state, open positions, allowed assets, mark prices, and market context.",
    "Propose or validate short-horizon leveraged trades only when formally valid.",
    "On testnet, execute only after trading_validate_plan returns valid=true and all host guardrails pass.",
    "On prodnet, do not execute, close, or modify exchange orders without explicit host human approval.",
    "Record non-secret lessons from accurate calls, failed validations, rejected orders, exchange errors, and missed assumptions.",
  ].join(" ");
}

function renderChatSessions() {
  const list = $("#chat-session-list");
  if (!list) return;
  const sessions = state.chat.sessions || [];
  list.innerHTML = sessions.length
    ? sessions
        .map(
          (session) => `
            <button
              type="button"
              class="chat-session-item ${session.id === state.chat.activeSessionId ? "active" : ""}"
              data-chat-session="${escapeHtml(session.id)}"
            >
              <span>${escapeHtml(session.title || "Chat session")}</span>
              <small>${escapeHtml(session.status || "idle")} · ${chatTime(session.updated_at || session.created_at)}</small>
            </button>
          `,
        )
        .join("")
    : "<div class='chat-empty-state'>No sessions yet.</div>";
}

function renderChatTranscript() {
  const session = selectedChatSession();
  const title = $("#chat-session-title");
  if (title) title.textContent = session?.title || "Chat";
  const status = $("#chat-session-status");
  if (status) {
    status.className = `pill ${chatStatusClass(session?.status || "idle")}`;
    status.textContent = session?.status || "idle";
  }
  const list = $("#chat-events-list");
  if (!list) return;
  const events = activeChatEvents().filter(isChatVisibleEvent);
  list.innerHTML = events.length
    ? events
        .map(
          (event) => `
            <article class="chat-event ${escapeHtml(chatEventKind(event))} ${escapeHtml(event.level || "info")}">
              <div class="chat-event-meta">
                <span>${escapeHtml(chatEventDisplayLabel(event))}</span>
                <time>${chatTime(event.created_at)}</time>
              </div>
              <div class="chat-event-body">${chatEventBody(event)}</div>
              ${chatEventPayload(event)}
            </article>
          `,
        )
        .join("")
    : `<div class="chat-empty-state rich-empty">
        <b>No messages in this session.</b>
        <span>Start with a portfolio brief or ask for intraday trade proposals.</span>
      </div>`;
  list.scrollTop = list.scrollHeight;
}

function isChatVisibleEvent(event) {
  return [
    "user.message",
    "agent.message",
    "agent.custom_tool_use",
    "user.custom_tool_result",
    "session.error",
  ].includes(event.type);
}

function chatEventKind(event) {
  if (event.type === "user.message") return "user";
  if (event.type === "agent.message") return "agent";
  if (event.type === "agent.custom_tool_use" || event.type === "user.custom_tool_result") return "tool";
  if (event.level === "error" || event.type === "session.error") return "error";
  return event.role || "system";
}

function chatEventDisplayLabel(event) {
  if (event.type === "user.message") return "You";
  if (event.type === "agent.message") return "Agent";
  if (event.type === "agent.custom_tool_use") return `Tool request · ${event.payload?.name || "tool"}`;
  if (event.type === "user.custom_tool_result") return event.payload?.is_error ? "Tool error" : "Tool result";
  if (event.type === "session.error") return "Session error";
  return chatEventLabel(event.type);
}

function chatEventBody(event) {
  if (event.type === "agent.message") return renderChatMarkdown(chatEventText(event));
  if (event.type === "user.message") return `<p>${escapeHtml(chatEventText(event))}</p>`;
  if (event.type === "agent.custom_tool_use") {
    const name = event.payload?.name || "tool";
    return `<p>${escapeHtml(toolDisplayName(name))}</p>${compactToolInput(event.payload?.input)}`;
  }
  if (event.type === "user.custom_tool_result") {
    return `<p>${escapeHtml(toolResultSummary(event.payload?.result, event.payload?.is_error))}</p>`;
  }
  return `<p>${escapeHtml(chatEventText(event))}</p>`;
}

function renderChatMarkdown(value) {
  const lines = String(value || "").split("\n");
  const html = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }
    if (/^-{3,}$/.test(line)) {
      html.push("<hr>");
      index += 1;
      continue;
    }
    if (line.startsWith("### ")) {
      html.push(`<h4>${renderInlineMarkdown(line.slice(4))}</h4>`);
      index += 1;
      continue;
    }
    if (line.startsWith("## ")) {
      html.push(`<h3>${renderInlineMarkdown(line.slice(3))}</h3>`);
      index += 1;
      continue;
    }
    if (isMarkdownTableLine(line)) {
      const tableLines = [];
      while (index < lines.length && isMarkdownTableLine(lines[index].trim())) {
        tableLines.push(lines[index].trim());
        index += 1;
      }
      html.push(renderMarkdownTable(tableLines));
      continue;
    }
    if (line.startsWith("- ")) {
      const items = [];
      while (index < lines.length && lines[index].trim().startsWith("- ")) {
        items.push(`<li>${renderInlineMarkdown(lines[index].trim().slice(2))}</li>`);
        index += 1;
      }
      html.push(`<ul>${items.join("")}</ul>`);
      continue;
    }
    const paragraph = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !lines[index].trim().startsWith("## ") &&
      !lines[index].trim().startsWith("### ") &&
      !lines[index].trim().startsWith("- ") &&
      !isMarkdownTableLine(lines[index].trim()) &&
      !/^-{3,}$/.test(lines[index].trim())
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    html.push(`<p>${renderInlineMarkdown(paragraph.join(" "))}</p>`);
  }
  return `<div class="chat-markdown">${html.join("")}</div>`;
}

function renderInlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function isMarkdownTableLine(line) {
  return line.startsWith("|") && line.endsWith("|") && line.includes("|");
}

function renderMarkdownTable(lines) {
  const rows = lines
    .filter((line) => !/^\|[\s:|-]+\|$/.test(line))
    .map((line) => line.slice(1, -1).split("|").map((cell) => renderInlineMarkdown(cell.trim())));
  if (!rows.length) return "";
  const [head, ...body] = rows;
  return `
    <div class="chat-table-wrap">
      <table class="chat-markdown-table">
        <thead><tr>${head.map((cell) => `<th>${cell}</th>`).join("")}</tr></thead>
        <tbody>${body.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>
    </div>
  `;
}

function compactToolInput(input) {
  if (!input || typeof input !== "object" || !Object.keys(input).length) return "";
  const entries = Object.entries(input)
    .slice(0, 4)
    .map(([key, value]) => `<span>${escapeHtml(key)}: <b>${escapeHtml(formatCompactToolValue(value))}</b></span>`)
    .join("");
  return `<div class="chat-tool-chips">${entries}</div>`;
}

function formatCompactToolValue(value) {
  if (value === null || value === undefined) return "--";
  if (typeof value === "object") return JSON.stringify(value).slice(0, 80);
  return String(value).slice(0, 80);
}

function toolDisplayName(name) {
  return String(name || "tool").replace(/^trading_/, "").replaceAll("_", " ");
}

function toolResultSummary(result, isError) {
  if (isError) return result?.error || "Tool failed.";
  if (result?.order_id) return `Order submitted: ${result.order_id}`;
  if (result?.validation) return result.validation.valid ? "Formal validation passed." : "Formal validation failed.";
  if (result?.plan) return `Plan ready: ${result.plan.asset || "asset"} ${result.plan.side || ""}`;
  if (result?.runtime) return "Runtime and market context loaded.";
  return "Tool completed.";
}

function latestChatValidation() {
  return activeChatEvents()
    .slice()
    .reverse()
    .map((event) => event.payload?.result?.validation)
    .find(Boolean);
}

function validationBadge(validation) {
  if (!validation) return `<span class="pill warning">validate before execution</span>`;
  return validation.valid
    ? `<span class="pill gain">formal validation passed</span>`
    : `<span class="pill loss">formal validation failed</span>`;
}

function planGuardrailRows(plan, validation) {
  const rows = [
    ["Asset", plan?.asset ? `${displayPerpLabel(plan.asset)} allowlisted` : "Plan asset required", Boolean(plan?.asset)],
    ["Size", `${money(plan?.size_usdc || 0)} notional`, Number(plan?.size_usdc || 0) >= MIN_ORDER_USDC],
    ["Leverage", `${number(plan?.leverage || 0, 1)}x integer`, Number.isInteger(Number(plan?.leverage || 0))],
    [
      "Exit",
      plan?.take_profit ? `TP ${compactPrice(plan.take_profit)}` : "Take profit required",
      Boolean(plan?.take_profit),
    ],
    [
      "Stop policy",
      plan?.stop_loss
        ? `SL ${compactPrice(plan.stop_loss)}`
        : "No SL under 10x; active invalidation",
      Boolean(plan?.stop_loss) || Number(plan?.leverage || 0) < 10,
    ],
  ];
  if (validation) {
    rows.push([
      "Formal validation",
      validation.valid ? "valid=true" : `${validation.errors?.length || 1} blocker(s)`,
      Boolean(validation.valid),
    ]);
  }
  return rows
    .map(
      ([label, value, passed]) => `
        <div class="${passed ? "pass" : "fail"}">
          <span>${escapeHtml(label)}</span>
          <b>${escapeHtml(value)}</b>
        </div>
      `,
    )
    .join("");
}

function renderVaultStatus() {
  const target = $("#chat-vault-status");
  if (!target) return;
  const credentials = state.chat.resources?.credentials || [];
  target.innerHTML = credentials.length
    ? credentials
        .map(
          (credential) => `
            <div class="vault-row">
              <span class="pill ${chatStatusClass(credential.status)}">${escapeHtml(credential.status)}</span>
              <div>
                <b>${escapeHtml(credential.name)}</b>
                <small>${escapeHtml(credential.kind)}${credential.mcp_server ? ` · ${escapeHtml(credential.mcp_server)}` : ""}</small>
                <p>${escapeHtml(credential.message || "")}</p>
              </div>
            </div>
          `,
        )
        .join("")
    : "<div class='chat-empty-state'>No credential status yet.</div>";
}

function renderPendingChatActions() {
  const target = $("#chat-pending-actions");
  if (!target) return;
  const events = activeChatEvents();
  const resolvedToolIds = new Set(
    events
      .filter((event) => event.type === "user.custom_tool_result")
      .map((event) => event.payload?.custom_tool_use_id)
      .filter(Boolean),
  );
  const pending = events.filter((event) => {
    const toolId = event.payload?.id || event.payload?.custom_tool_use_id || "";
    return (
      event.requires_action &&
      event.type === "agent.custom_tool_use" &&
      CHAT_HUMAN_APPROVAL_TOOL_NAMES.has(event.payload?.name) &&
      toolId &&
      !resolvedToolIds.has(toolId)
    );
  });
  target.innerHTML = pending.length
    ? pending
        .map((event) => {
          const toolId = event.payload?.id || event.payload?.tool_use_id || "";
          return `
            <div class="pending-action">
              <b>${escapeHtml(event.payload?.name || chatEventLabel(event.type))}</b>
              <p>${escapeHtml(chatEventText(event))}</p>
              ${
                toolId
                  ? `<div class="button-row">
                      <button type="button" data-action="chat-confirm-tool" data-tool-id="${escapeHtml(toolId)}" data-tool-allow="true">Allow</button>
                      <button type="button" class="danger" data-action="chat-confirm-tool" data-tool-id="${escapeHtml(toolId)}" data-tool-allow="false">Deny</button>
                    </div>`
                  : ""
              }
            </div>
          `;
        })
        .join("")
    : "<div class='chat-empty-state'>No pending tool confirmations.</div>";
}

function renderChatPlanActions() {
  const target = $("#chat-plan-actions");
  if (!target) return;
  const eventPlan = activeChatEvents()
    .slice()
    .reverse()
    .map((event) => event.payload?.result?.plan)
    .find(Boolean);
  const plan = state.plan || eventPlan;
  const validation = plan?.validation || latestChatValidation();
  target.innerHTML = plan
    ? `
      <div class="chat-plan-card">
        <div class="plan-status-row">
          <span class="pill ${decisionClass(plan.execution_decision)}">${escapeHtml(plan.execution_decision || "proposed")}</span>
          ${validationBadge(validation)}
        </div>
        <h3>${escapeHtml(displayPerpLabel(plan.asset))} ${escapeHtml(plan.side)}</h3>
        <p>${escapeHtml(plan.rationale || plan.thesis || "Latest stored plan.")}</p>
        <div class="kv mini">
          <div><span>Size</span><b>${money(plan.size_usdc)}</b></div>
          <div><span>Entry</span><b>${compactPrice(plan.entry_price)}</b></div>
          <div><span>Lev</span><b>${number(plan.leverage, 1)}x</b></div>
        </div>
        <div class="guardrail-checklist">
          ${planGuardrailRows(plan, validation)}
        </div>
        <button type="button" data-action="chat-execute-plan">Execute guarded</button>
      </div>
    `
    : "<div class='chat-empty-state'>No stored trade plan.</div>";
}

function renderChatCapabilities() {
  const target = $("#chat-capabilities");
  if (!target) return;
  const resources = state.chat.resources || {};
  const capabilities = state.chat.capabilities || {};
  const tools = capabilities.custom_tools || resources.custom_tools || [];
  target.innerHTML = `
    <div class="capability-list">
      <div><span>Sandbox tools</span><b>${capabilities.managed_agents ? "enabled" : "disabled"}</b></div>
      <div><span>Outcome max</span><b>${escapeHtml(String(capabilities.max_outcome_iterations || 5))}</b></div>
      <div><span>Dreams</span><b>${capabilities.dreams ? "opt-in on" : "off"}</b></div>
      <div><span>Custom tools</span><b>${tools.length}</b></div>
    </div>
    <div class="tool-chip-list">
      ${tools.map((tool) => `<span>${escapeHtml(tool)}</span>`).join("")}
    </div>
  `;
}

function chatStatusClass(status) {
  if (["ready", "connected", "idle"].includes(status)) return "gain";
  if (["error", "missing", "terminated"].includes(status)) return "loss";
  if (["disabled", "waiting_action", "running", "unavailable"].includes(status)) return "warning";
  return "neutral";
}

function shortId(value) {
  const text = String(value || "");
  if (text.length <= 16) return text || "--";
  return `${text.slice(0, 8)}...${text.slice(-4)}`;
}

function chatTime(value) {
  if (!value) return "--";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function chatEventLabel(type) {
  return String(type || "event").replaceAll(".", " ");
}

function chatEventText(event) {
  if (event.text) return event.text;
  if (event.payload?.message) return event.payload.message;
  if (event.payload?.name) return `Tool requested: ${event.payload.name}`;
  return "";
}

function chatEventPayload(event) {
  if (!["agent.custom_tool_use", "user.custom_tool_result", "session.error"].includes(event.type)) {
    return "";
  }
  const payload = event.payload || {};
  const interesting = {};
  for (const key of ["name", "input", "result", "usage", "stop_reason", "thread_id"]) {
    if (payload[key] !== undefined) interesting[key] = payload[key];
  }
  if (!Object.keys(interesting).length) return "";
  return `
    <details class="chat-event-details">
      <summary>Details</summary>
      <pre>${escapeHtml(JSON.stringify(interesting, null, 2))}</pre>
    </details>
  `;
}

async function refreshChat() {
  await loadChatState();
  toast("Chat refreshed");
}

async function bootstrapChat() {
  state.chat.isLoading = true;
  renderChat();
  try {
    state.chat.resources = await api("/api/chat/bootstrap", {
      method: "POST",
      body: JSON.stringify({ force: true }),
    });
    await loadChatState();
    toast("Managed Agents resources rebuilt");
  } finally {
    state.chat.isLoading = false;
    renderChat();
  }
}

async function createChatDeployment() {
  state.chat.isLoading = true;
  renderChat();
  try {
    state.chat.deployment = await api("/api/chat/deployment", {
      method: "POST",
      body: JSON.stringify({
        name: $("#chat-deployment-name")?.value.trim(),
        cron_expression: $("#chat-deployment-cron")?.value.trim(),
        timezone: $("#chat-deployment-timezone")?.value.trim(),
        initial_prompt: $("#chat-deployment-prompt")?.value.trim(),
      }),
    });
    await loadChatState();
    if (state.chat.deployment?.status === "error") {
      toast("Deployment failed");
    } else {
      toast("Claude deployment created");
    }
  } finally {
    state.chat.isLoading = false;
    renderChat();
  }
}

async function runChatDeployment() {
  state.chat.isLoading = true;
  renderChat();
  try {
    state.chat.deployment = await api("/api/chat/deployment/run", { method: "POST" });
    await loadChatState();
    if (state.chat.deployment?.last_error || state.chat.deployment?.status === "error") {
      toast("Deployment run failed");
    } else {
      toast("Deployment run started");
    }
  } finally {
    state.chat.isLoading = false;
    renderChat();
  }
}

async function createChatSession() {
  const session = await api("/api/chat/sessions", {
    method: "POST",
    body: JSON.stringify({ title: `Trading Chat ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` }),
  });
  state.chat.activeSessionId = session.id;
  await loadChatState();
  startChatPolling();
  toast("Chat session ready");
}

async function ensureChatSession() {
  if (state.chat.activeSessionId) return state.chat.activeSessionId;
  await createChatSession();
  return state.chat.activeSessionId;
}

async function sendChatMessage() {
  const input = $("#chat-message-input");
  const message = input?.value.trim();
  if (!message) throw new Error("Enter a chat message.");
  const sessionId = await ensureChatSession();
  state.chat.isSending = true;
  renderChat();
  try {
    const session = await api(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`, {
      method: "POST",
      body: JSON.stringify({ message }),
    });
    mergeChatSession(session);
    input.value = "";
    await loadChatEvents(sessionId);
    startChatPolling({ tailMs: 8000 });
  } finally {
    state.chat.isSending = false;
    renderChat();
  }
}

async function defineChatOutcome() {
  const description = $("#chat-outcome-description")?.value.trim();
  const rubric = $("#chat-outcome-rubric")?.value.trim();
  const maxIterations = Number($("#chat-outcome-iterations")?.value || 5);
  if (!description || !rubric) throw new Error("Outcome and rubric are required.");
  const sessionId = await ensureChatSession();
  await api(`/api/chat/sessions/${encodeURIComponent(sessionId)}/outcomes`, {
    method: "POST",
    body: JSON.stringify({
      description,
      rubric,
      max_iterations: maxIterations,
    }),
  });
  await loadChatState();
  startChatPolling();
}

async function confirmChatTool(actionTarget) {
  const sessionId = state.chat.activeSessionId;
  if (!sessionId) throw new Error("No active Chat session.");
  const session = await api(`/api/chat/sessions/${encodeURIComponent(sessionId)}/tool-confirmations`, {
    method: "POST",
    body: JSON.stringify({
      tool_use_id: actionTarget.dataset.toolId,
      allow: actionTarget.dataset.toolAllow === "true",
      deny_message: actionTarget.dataset.toolAllow === "true" ? null : "Denied from HyperClaude UI.",
    }),
  });
  mergeChatSession(session);
  await loadState();
  startChatPolling({ tailMs: 8000 });
}

async function interruptChat() {
  const sessionId = state.chat.activeSessionId;
  if (!sessionId) return;
  await api(`/api/chat/sessions/${encodeURIComponent(sessionId)}/interrupt`, { method: "POST" });
  await loadChatState();
}

async function archiveChat() {
  const sessionId = state.chat.activeSessionId;
  if (!sessionId) return;
  await api(`/api/chat/sessions/${encodeURIComponent(sessionId)}/archive`, { method: "POST" });
  state.chat.activeSessionId = null;
  await loadChatState();
}

async function executeChatPlan() {
  if (!state.plan?.id) throw new Error("No trade plan to execute.");
  await executeTrade({ confirmed: true });
  await loadChatState();
  startChatPolling({ tailMs: 3000 });
}

function startChatPolling({ tailMs = 0 } = {}) {
  const session = selectedChatSession();
  if (tailMs > 0) chatRuntime.pollUntil = Math.max(chatRuntime.pollUntil, Date.now() + tailMs);
  if (!session || !shouldPollChatSession(session)) {
    stopChatPolling();
    return;
  }
  if (chatRuntime.pollTimer) return;
  chatRuntime.pollTimer = window.setInterval(() => {
    const active = selectedChatSession();
    if (!active || !shouldPollChatSession(active)) {
      stopChatPolling();
      return;
    }
    loadChatEvents(active.id).catch((error) => console.warn("Chat polling failed", error));
  }, 1500);
}

function shouldPollChatSession(session) {
  return Boolean(session && (["running", "waiting_action"].includes(session.status) || Date.now() < chatRuntime.pollUntil));
}

function stopChatPolling() {
  if (!chatRuntime.pollTimer) return;
  window.clearInterval(chatRuntime.pollTimer);
  chatRuntime.pollTimer = null;
  chatRuntime.pollUntil = 0;
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

function activePrivyAgent() {
  const runtimeNetwork = state.runtime?.network || DEFAULT_NETWORK;
  const agent = state.privy_agent_wallet;
  return agent?.network === runtimeNetwork ? agent : null;
}

function transferExplorerUrl(hash) {
  return `https://arbiscan.io/tx/${encodeURIComponent(hash)}`;
}

function renderTransferScreen() {
  const summary = $("#transfer-summary");
  if (!summary) return;
  const source = state.connected_wallet?.address || "";
  const agent = activePrivyAgent();
  const destination = agent?.master_wallet_address || "";
  const sourceBalance = state.transferBalances.source;
  const destinationBalance = state.transferBalances.destination;
  const canTransfer = Boolean(source && destination && agent?.network === "prodnet");
  const amountInput = $("#transfer-usdc-amount");
  if (amountInput && sourceBalance?.usdc != null && !amountInput.dataset.touched) {
    amountInput.value = formatFundingInputValue(sourceBalance.usdc);
    amountInput.max = String(sourceBalance.usdc);
  }
  const status = $("#transfer-status");
  if (status) {
    status.textContent = state.isSubmittingTransfer ? "submitting" : canTransfer ? "sponsored" : "blocked";
    status.className = `pill ${canTransfer ? "gain" : "warning"}`;
  }
  summary.innerHTML = `
    <div class="transfer-route">
      <div>
        <span>From</span>
        <code>${escapeHtml(source || "Connect Privy wallet")}</code>
        <b>${sourceBalance ? `${formatTokenAmount(sourceBalance.usdc, 6)} USDC / ${formatTokenAmount(sourceBalance.eth, 5)} ETH` : "Balance not loaded"}</b>
      </div>
      <div>
        <span>To</span>
        <code>${escapeHtml(destination || "Initialize prodnet master wallet")}</code>
        <b>${destinationBalance ? `${formatTokenAmount(destinationBalance.usdc, 6)} USDC / ${formatTokenAmount(destinationBalance.eth, 5)} ETH` : "Balance not loaded"}</b>
      </div>
    </div>
    <div class="transfer-contract">
      <span>Network</span><b>Arbitrum One</b>
      <span>Token</span><b>Native USDC</b>
      <span>Contract</span><code>${escapeHtml(ARBITRUM_USDC_ADDRESS)}</code>
    </div>
    <div class="transfer-warning">This path sends from the connected Privy embedded wallet. Gas is sponsored by Privy client-side sponsorship on Arbitrum.</div>
  `;
  const transferButton = $('[data-action="transfer-usdc-to-master"]');
  if (transferButton) transferButton.disabled = !canTransfer || state.isSubmittingTransfer;
  renderTransferResult();
  renderTradingDepositScreen();
}

function renderTransferResult() {
  const target = $("#transfer-result");
  if (!target) return;
  const result = state.transferResult;
  target.hidden = !result;
  if (!result) {
    target.innerHTML = "";
    return;
  }
  const hash = result.hash || "";
  const reference = hash || result.actionId || result.status || "pending";
  const href = hash ? transferExplorerUrl(hash) : "https://dashboard.privy.io";
  target.innerHTML = `
    <span>Submitted</span>
    <a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(maskHash(reference))}</a>
  `;
}

function renderExternalTransferScreen() {
  const summary = $("#external-transfer-summary");
  if (!summary) return;
  const source = state.connected_wallet?.address || "";
  const destination = state.external_withdrawal_address || "";
  const sourceBalance = state.externalTransferBalances.source;
  const destinationBalance = state.externalTransferBalances.destination;
  const canTransfer = Boolean(source && destination && (state.runtime?.network || DEFAULT_NETWORK) === "prodnet");
  const amountInput = $("#external-transfer-usdc-amount");
  if (amountInput && sourceBalance?.usdc != null && !amountInput.dataset.touched) {
    amountInput.value = formatFundingInputValue(sourceBalance.usdc);
    amountInput.max = String(sourceBalance.usdc);
  }
  const status = $("#external-transfer-status");
  if (status) {
    status.textContent = state.isSubmittingExternalTransfer
      ? "submitting"
      : canTransfer
      ? "sponsored"
      : "blocked";
    status.className = `pill ${canTransfer ? "gain" : "warning"}`;
  }
  summary.innerHTML = `
    <div class="transfer-route">
      <div>
        <span>From</span>
        <code>${escapeHtml(source || "Connect Privy wallet")}</code>
        <b>${sourceBalance ? `${formatTokenAmount(sourceBalance.usdc, 6)} USDC / ${formatTokenAmount(sourceBalance.eth, 5)} ETH` : "Balance not loaded"}</b>
      </div>
      <div>
        <span>To</span>
        <code>${escapeHtml(destination || "Set PRIVY_EXTERNAL_WITHDRAWAL_ADDRESS")}</code>
        <b>${destinationBalance ? `${formatTokenAmount(destinationBalance.usdc, 6)} USDC / ${formatTokenAmount(destinationBalance.eth, 5)} ETH` : "Balance not loaded"}</b>
      </div>
    </div>
    <div class="transfer-contract">
      <span>Network</span><b>Arbitrum One</b>
      <span>Token</span><b>Native USDC</b>
      <span>Contract</span><code>${escapeHtml(ARBITRUM_USDC_ADDRESS)}</code>
    </div>
    <div class="transfer-warning">External withdrawals use the configured PRIVY_EXTERNAL_WITHDRAWAL_ADDRESS and the connected Privy embedded wallet session.</div>
  `;
  const transferButton = $('[data-action="transfer-usdc-to-external"]');
  if (transferButton) {
    transferButton.disabled = !canTransfer || state.isSubmittingExternalTransfer;
  }
  renderExternalTransferResult();
}

function renderTradingDepositScreen() {
  const summary = $("#trading-deposit-summary");
  if (!summary) return;
  const agent = activePrivyAgent();
  const masterAddress = agent?.master_wallet_address || "";
  const masterBalance = state.tradingDepositBalances.master || state.transferBalances.destination;
  const hyperliquidWallet = state.tradingDepositBalances.hyperliquid || state.wallet;
  const withdrawable = Number(hyperliquidWallet?.withdrawable_usdc);
  const masterUsdc = Number(masterBalance?.usdc);
  const canDeposit = Boolean(
    agent?.network === "prodnet" &&
      masterAddress &&
      Number.isFinite(masterUsdc) &&
      masterUsdc >= 5,
  );
  const amountInput = $("#trading-deposit-usdc-amount");
  if (amountInput && Number.isFinite(masterUsdc) && masterUsdc > 0 && !amountInput.dataset.touched) {
    amountInput.value = formatFundingInputValue(masterUsdc);
    amountInput.max = String(masterUsdc);
  }
  const status = $("#trading-deposit-status");
  if (status) {
    status.textContent = state.isSubmittingTradingDeposit
      ? "submitting"
      : canDeposit
      ? "ready"
      : Number.isFinite(masterUsdc) && masterUsdc > 0
      ? "min 5 USDC"
      : "blocked";
    status.className = `pill ${canDeposit ? "gain" : "warning"}`;
  }
  summary.innerHTML = `
    <div class="transfer-route">
      <div>
        <span>Master wallet on Arbitrum</span>
        <code>${escapeHtml(masterAddress || "Initialize prodnet master wallet")}</code>
        <b>${masterBalance ? `${formatTokenAmount(masterBalance.usdc, 6)} USDC / ${formatTokenAmount(masterBalance.eth, 5)} ETH` : "Balance not loaded"}</b>
      </div>
      <div>
        <span>Available in Hyperliquid</span>
        <code>${escapeHtml(hyperliquidWallet?.account_address || masterAddress || "Wallet state not loaded")}</code>
        <b>${Number.isFinite(withdrawable) ? `${formatTokenAmount(withdrawable, 6)} USDC withdrawable` : "Wallet state not loaded"}</b>
      </div>
    </div>
    <div class="transfer-contract">
      <span>Bridge</span><b>Hyperliquid Bridge2</b>
      <span>Network</span><b>Arbitrum One</b>
      <span>Minimum</span><b>5 USDC</b>
    </div>
    <div class="transfer-warning">USDC sent to the master wallet remains an Arbitrum token balance. It becomes trading collateral only after depositing the master wallet balance to Hyperliquid Bridge2.</div>
  `;
  const depositButton = $('[data-action="deposit-master-trading"]');
  if (depositButton) {
    depositButton.disabled = !canDeposit || state.isSubmittingTradingDeposit;
  }
  renderTradingDepositResult();
}

function renderTradingDepositResult() {
  const target = $("#trading-deposit-result");
  if (!target) return;
  const result = state.tradingDepositResult;
  target.hidden = !result;
  if (!result) {
    target.innerHTML = "";
    return;
  }
  const hash = result.hash || "";
  const reference = hash || result.actionId || result.status || "pending";
  const href = hash ? transferExplorerUrl(hash) : "https://dashboard.privy.io";
  target.innerHTML = `
    <span>Submitted</span>
    <a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(maskHash(reference))}</a>
  `;
}

function renderExternalTransferResult() {
  const target = $("#external-transfer-result");
  if (!target) return;
  const result = state.externalTransferResult;
  target.hidden = !result;
  if (!result) {
    target.innerHTML = "";
    return;
  }
  const hash = result.hash || "";
  const reference = hash || result.actionId || result.status || "pending";
  const href = hash ? transferExplorerUrl(hash) : "https://dashboard.privy.io";
  target.innerHTML = `
    <span>Submitted</span>
    <a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(maskHash(reference))}</a>
  `;
}

async function refreshTransferBalances() {
  const source = state.connected_wallet?.address;
  const destination = activePrivyAgent()?.master_wallet_address;
  const [sourceBalance, destinationBalance] = await Promise.all([
    source ? api(`/api/wallet/arbitrum-balance/${encodeURIComponent(source)}`) : Promise.resolve(null),
    destination ? api(`/api/wallet/arbitrum-balance/${encodeURIComponent(destination)}`) : Promise.resolve(null),
  ]);
  state.transferBalances = {
    source: sourceBalance,
    destination: destinationBalance,
  };
  renderTransferScreen();
}

async function refreshExternalTransferBalances() {
  const source = state.connected_wallet?.address;
  const destination = state.external_withdrawal_address;
  const [sourceBalance, destinationBalance] = await Promise.all([
    source ? api(`/api/wallet/arbitrum-balance/${encodeURIComponent(source)}`) : Promise.resolve(null),
    destination ? api(`/api/wallet/arbitrum-balance/${encodeURIComponent(destination)}`) : Promise.resolve(null),
  ]);
  state.externalTransferBalances = {
    source: sourceBalance,
    destination: destinationBalance,
  };
  renderExternalTransferScreen();
}

async function refreshTradingDepositBalances() {
  const master = activePrivyAgent()?.master_wallet_address;
  const [masterBalance, hyperliquidWallet] = await Promise.all([
    master ? api(`/api/wallet/arbitrum-balance/${encodeURIComponent(master)}`) : Promise.resolve(null),
    api("/api/wallet").catch(() => null),
  ]);
  state.tradingDepositBalances = {
    master: masterBalance,
    hyperliquid: hyperliquidWallet,
  };
  if (hyperliquidWallet) state.wallet = hyperliquidWallet;
  renderTradingDepositScreen();
  renderTradingView();
}

function transferAmountInput() {
  const amount = Number($("#transfer-usdc-amount")?.value || 0);
  if (!Number.isFinite(amount) || amount <= 0) throw new Error("Enter a valid USDC amount.");
  const balance = Number(state.transferBalances.source?.usdc);
  if (Number.isFinite(balance) && amount > balance) throw new Error("Amount exceeds source wallet USDC balance.");
  return amount;
}

function externalTransferAmountInput() {
  const amount = Number($("#external-transfer-usdc-amount")?.value || 0);
  if (!Number.isFinite(amount) || amount <= 0) throw new Error("Enter a valid USDC amount.");
  const balance = Number(state.externalTransferBalances.source?.usdc);
  if (Number.isFinite(balance) && amount > balance) throw new Error("Amount exceeds source wallet USDC balance.");
  return amount;
}

async function preflightTransferSession(amount) {
  const source = state.connected_wallet?.address;
  const agent = activePrivyAgent();
  const destination = agent?.master_wallet_address;
  if (!source) throw new Error("Connect the Privy user wallet first.");
  if (!destination) throw new Error("Initialize the prodnet master wallet first.");
  if (agent?.network !== "prodnet") {
    throw new Error("Integrated user wallet transfers are only configured for prodnet.");
  }
  if (!window.hyperDemoPrivy?.validateNativeUsdcTransfer) {
    throw new Error("Privy session helper is not ready.");
  }
  return window.hyperDemoPrivy.validateNativeUsdcTransfer({
    from: source,
    to: destination,
    amount,
  });
}

async function preflightExternalTransferSession(amount) {
  const source = state.connected_wallet?.address;
  const destination = state.external_withdrawal_address;
  if (!source) throw new Error("Connect the Privy user wallet first.");
  if (!destination) throw new Error("Set PRIVY_EXTERNAL_WITHDRAWAL_ADDRESS first.");
  if ((state.runtime?.network || DEFAULT_NETWORK) !== "prodnet") {
    throw new Error("External wallet withdrawals are only configured for prodnet.");
  }
  if (!window.hyperDemoPrivy?.validateNativeUsdcTransfer) {
    throw new Error("Privy session helper is not ready.");
  }
  return window.hyperDemoPrivy.validateNativeUsdcTransfer({
    from: source,
    to: destination,
    amount,
  });
}

async function validateTransferSession() {
  const amount = transferAmountInput();
  await preflightTransferSession(amount);
  toast("Privy session is valid for sponsored transfer.");
}

async function validateExternalTransferSession() {
  const amount = externalTransferAmountInput();
  await preflightExternalTransferSession(amount);
  toast("Privy session is valid for external withdrawal.");
}

async function transferUsdcToMaster() {
  const source = state.connected_wallet?.address;
  const destination = activePrivyAgent()?.master_wallet_address;
  if (!source) throw new Error("Connect the Privy user wallet first.");
  if (!destination) throw new Error("Initialize the prodnet master wallet first.");
  if (!$("#transfer-confirm")?.checked) throw new Error("Confirm the Arbitrum USDC transfer first.");
  const amount = transferAmountInput();
  await preflightTransferSession(amount);
  state.isSubmittingTransfer = true;
  state.transferResult = null;
  renderTransferScreen();
  try {
    const transfer = await window.hyperDemoPrivy.transferNativeUsdc({
      from: source,
      to: destination,
      amount,
    });
    const result = {
      network: "prodnet",
      protocol: "Privy client-sponsored Arbitrum USDC wallet transfer",
      sourceWalletAddress: source,
      masterWalletAddress: destination,
      usdcAddress: ARBITRUM_USDC_ADDRESS,
      amountUsdc: amount,
      actionId: transfer.actionId || null,
      hash: transfer.hash,
      status: "submitted",
      raw: transfer,
    };
    state.transferResult = result;
    await refreshTransferBalances();
    toast(`Transfer submitted: ${maskHash(result.hash)}`);
  } finally {
    state.isSubmittingTransfer = false;
    renderTransferScreen();
  }
}

async function transferUsdcToExternal() {
  const source = state.connected_wallet?.address;
  const destination = state.external_withdrawal_address;
  if (!source) throw new Error("Connect the Privy user wallet first.");
  if (!destination) throw new Error("Set PRIVY_EXTERNAL_WITHDRAWAL_ADDRESS first.");
  if (!$("#external-transfer-confirm")?.checked) {
    throw new Error("Confirm the external USDC transfer first.");
  }
  const amount = externalTransferAmountInput();
  await preflightExternalTransferSession(amount);
  state.isSubmittingExternalTransfer = true;
  state.externalTransferResult = null;
  renderExternalTransferScreen();
  try {
    const transfer = await window.hyperDemoPrivy.transferNativeUsdc({
      from: source,
      to: destination,
      amount,
    });
    const result = {
      network: "prodnet",
      protocol: "Privy client-sponsored Arbitrum USDC external withdrawal",
      sourceWalletAddress: source,
      externalWalletAddress: destination,
      usdcAddress: ARBITRUM_USDC_ADDRESS,
      amountUsdc: amount,
      actionId: transfer.actionId || null,
      hash: transfer.hash,
      status: "submitted",
      raw: transfer,
    };
    state.externalTransferResult = result;
    await refreshExternalTransferBalances();
    toast(`External transfer submitted: ${maskHash(result.hash)}`);
  } finally {
    state.isSubmittingExternalTransfer = false;
    renderExternalTransferScreen();
  }
}

function walletAddressForTarget(target) {
  if (target === "user") return state.connected_wallet?.address;
  if (target === "master") return state.privy_agent_wallet?.master_wallet_address;
  if (target === "agent") return state.privy_agent_wallet?.agent_wallet_address;
  if (target === "transfer-source") return state.connected_wallet?.address;
  if (target === "transfer-master") return activePrivyAgent()?.master_wallet_address;
  if (target === "transfer-external") return state.external_withdrawal_address;
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

function requireFundingConfirmation(confirmSelector = "#funding-confirm") {
  if (!$(confirmSelector)?.checked) {
    throw new Error("Confirm wallet funding transactions first.");
  }
}

function currentMasterAddress() {
  const address = state.privy_agent_wallet?.master_wallet_address;
  if (!address) throw new Error("Initialize a Privy master wallet first.");
  return address;
}

function depositMasterAmount(inputSelector = "#funding-usdc-amount") {
  const amount = Number($(inputSelector)?.value || 0);
  if (!Number.isFinite(amount) || amount < 5) {
    throw new Error("Hyperliquid Bridge2 deposits require at least 5 USDC.");
  }
  const balance = Number(state.tradingDepositBalances.master?.usdc ?? state.transferBalances.destination?.usdc);
  if (Number.isFinite(balance) && amount > balance) {
    throw new Error("Amount exceeds master wallet USDC balance.");
  }
  return amount;
}

async function depositMasterToHyperliquid({
  inputSelector = "#funding-usdc-amount",
  confirmSelector = "#funding-confirm",
  transferScreen = false,
} = {}) {
  requireFundingConfirmation(confirmSelector);
  const amount = depositMasterAmount(inputSelector);
  if (transferScreen) {
    state.isSubmittingTradingDeposit = true;
    state.tradingDepositResult = null;
    renderTradingDepositScreen();
  }
  try {
    const result = await api("/api/privy/deposit-master", {
      method: "POST",
      body: JSON.stringify({
        amount_usdc: amount,
        confirmed: true,
      }),
    });
    await loadState();
    if (transferScreen) {
      state.tradingDepositResult = result;
      await refreshTradingDepositBalances();
    }
    const reference = result.hash || result.actionId || result.status || "submitted";
    toast(`Master deposit submitted: ${maskHash(reference)}`);
  } finally {
    if (transferScreen) {
      state.isSubmittingTradingDeposit = false;
      renderTradingDepositScreen();
    }
  }
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
    ui_mode: $("#agent-auto-approve")?.checked ? "robot" : "human",
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
}

async function analyze(event) {
  event.preventDefault();
  if (state.isAnalyzing) return;
  const asset = normalizeAssetSymbol($("#asset-input")?.value || "BTC");
  const context = $("#context-input")?.value || null;
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

function autoContext(asset) {
  const available = orderAvailableUsdc();
  const maxLeverage = assetMaxLeverage(asset);
  return [
    `Auto mode for ${displayPerpLabel(asset)}.`,
    `Risk appetite: ${state.autoPrefs.risk_appetite}.`,
    `Preferred close window: ${state.autoPrefs.close_window}.`,
    `Available trading input: ${money(available)}.`,
    `${displayPerpLabel(asset)} max supported leverage: ${maxLeverage}x.`,
    "Return several proposals that can pass order validation without user edits.",
  ].join(" ");
}

async function analyzeAutoProposals() {
  if (state.isAnalyzing) return;
  if (!autoPrefsComplete()) {
    throw new Error("Choose Risk appetite and Close window before running Auto.");
  }
  const asset = currentChartAsset();
  state.orderMode = "auto";
  state.analysis = null;
  state.plan = null;
  state.order = null;
  state.autoChat = { session: null, events: [], plans: [], lastAsset: asset };
  state.selectedCandidateIndex = 0;
  state.lastOrderError = "";
  try {
    await loadChartCandles(asset, state.activeTimeframe);
    state.isAnalyzing = true;
    renderTradingView();
    const result = await api("/api/agent/chat-auto", {
      method: "POST",
      body: JSON.stringify({
        asset,
        risk_appetite: state.autoPrefs.risk_appetite,
        close_window: state.autoPrefs.close_window,
        available_usdc: orderAvailableUsdc(),
        max_leverage: assetMaxLeverage(asset),
      }),
    });
    state.autoChat = {
      session: result.session || null,
      events: result.events || [],
      plans: result.plans || [],
      lastAsset: asset,
    };
    if (result.session?.id) {
      state.chat.activeSessionId = result.session.id;
      state.chat.events[result.session.id] = result.events || [];
      if (!state.chat.sessions.some((session) => session.id === result.session.id)) {
        state.chat.sessions = [result.session, ...state.chat.sessions];
      }
    }
    state.plan = result.plan || null;
    state.selectedCandidateIndex = 0;
    if (result.analysis?.candles_by_timeframe) {
      state.marketCandles[result.analysis.asset] = {
        ...(state.marketCandles[result.analysis.asset] || {}),
        ...result.analysis.candles_by_timeframe,
      };
    }
    await loadState();
    state.orderMode = "auto";
    toast("Agent proposals ready");
  } finally {
    state.isAnalyzing = false;
    renderTradingView();
  }
}

async function openAutoChat() {
  const sessionId = state.autoChat.session?.id;
  if (!sessionId) throw new Error("Run the Auto agent first.");
  state.chat.activeSessionId = sessionId;
  state.chat.events[sessionId] = state.autoChat.events || [];
  state.screen = "chat";
  renderScreen();
  await loadChatEvents(sessionId);
  startChatPolling();
}

async function reviewAutoPlan(actionTarget) {
  const planId = actionTarget?.dataset.planId || "";
  const plan = autoPlanById(planId);
  if (!plan) throw new Error("Trade plan was not found.");
  state.plan = plan;
  state.order = null;
  renderTradingView();
  try {
    const validation = await validateActivePlan();
    toast(validation.valid ? "Trade plan loaded and validated" : "Trade plan loaded with validation blockers");
  } catch (error) {
    toast(error.message);
  }
}

async function executeAutoPlan(actionTarget) {
  const planId = actionTarget?.dataset.planId || "";
  const plan = autoPlanById(planId);
  if (!plan) throw new Error("Trade plan was not found.");
  state.plan = plan;
  await executeTrade({ confirmed: true });
}

async function approveAutoProposal() {
  const candidate = selectedCandidate();
  if (!candidate) throw new Error("Run auto analysis before approving a proposal.");
  const issue = proposalIssue(candidate);
  if (issue) throw new Error(issue);
  state.lastOrderError = "";
  state.isSubmittingOrder = true;
  renderTicket();
  try {
    const result = await api(`/api/agent/proposals/${state.selectedCandidateIndex || 0}/approve`, {
      method: "POST",
    });
    state.plan = result.plan;
    state.analysis = result.analysis || state.analysis;
    toast("Auto proposal ready for review");
  } finally {
    state.isSubmittingOrder = false;
    renderTradingView();
  }
}

async function rejectAutoProposal() {
  state.lastOrderError = "";
  state.plan = null;
  state.analysis = null;
  state.autoChat = { session: null, events: [], plans: [], lastAsset: "" };
  state.selectedCandidateIndex = 0;
  renderTradingView();
  toast("Auto proposals cleared");
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
  const parsed = Number(normalizeNumericInput(value));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function normalizeNumericInput(value) {
  if (typeof value !== "string") return value;
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (trimmed.includes(",") && trimmed.includes(".")) return trimmed.replaceAll(",", "");
  if (trimmed.includes(",")) return trimmed.replace(",", ".");
  return trimmed;
}

function boundedLeverage(value, maxLeverage = 10) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return 1;
  return Math.max(1, Math.min(maxLeverage, Math.round(parsed)));
}

function estimatedLiquidationPrice(side, entryPrice, leverage) {
  const entry = Number(entryPrice);
  const lev = Number(leverage);
  if (!Number.isFinite(entry) || entry <= 0 || !Number.isFinite(lev) || lev <= 1) return null;
  const move = 1 / lev;
  const price = side === "short" ? entry * (1 + move) : entry * (1 - move);
  return Math.max(0, price);
}

function exitPriceFromManualPercent(kind, manual, entryPrice) {
  const value = optionalNumber(manual[kind]);
  const entry = Number(entryPrice);
  if (!value || !Number.isFinite(entry) || entry <= 0) return null;
  const direction = kind === "take_profit" ? 1 : -1;
  const sideMultiplier = manual.side === "short" ? -1 : 1;
  return entry * (1 + (direction * sideMultiplier * value) / 100);
}

function manualExitPrice(kind, manual, entryPrice) {
  const enabledKey = kind === "take_profit" ? "take_profit_enabled" : "stop_loss_enabled";
  if (!manual[enabledKey] && !(manual.exits_enabled && manual[kind])) return null;
  if ((manual.exit_input_mode || "price") === "percent") {
    const price = exitPriceFromManualPercent(kind, manual, entryPrice);
    return price ? Number(price.toFixed(6)) : null;
  }
  return optionalNumber(manual[kind]);
}

function manualOrderPayload() {
  const asset = currentChartAsset();
  const manual = state.manualOrder;
  const mark = latestMarkPrice(asset);
  const entryPrice =
    manual.entry_type === "limit" ? optionalNumber(manual.entry_price) : mark || null;
  const leverage = boundedLeverage(manual.leverage, assetMaxLeverage(asset));
  const stopLoss = manualExitPrice("stop_loss", manual, entryPrice);
  const takeProfit = manualExitPrice("take_profit", manual, entryPrice);
  const anyExitEnabled = Boolean(manual.take_profit_enabled || manual.stop_loss_enabled);
  return {
    asset,
    side: manual.side,
    entry_type: manual.entry_type,
    size_usdc: Number(manual.size_usdc),
    entry_price: entryPrice,
    stop_loss: stopLoss,
    take_profit: takeProfit,
    leverage,
  };
}

function manualOrderPreflight(context = {}) {
  const asset = context.asset || currentChartAsset();
  const manual = state.manualOrder;
  const mark = context.mark ?? latestMarkPrice(asset);
  const maxLeverage = context.maxLeverage ?? assetMaxLeverage(asset);
  const leverage = context.leverage ?? boundedLeverage(manual.leverage, maxLeverage);
  const entryPrice =
    context.entryPrice ??
    (manual.entry_type === "limit" ? optionalNumber(manual.entry_price) : mark || null);
  const size = Number(normalizeNumericInput(manual.size_usdc)) || 0;
  const available = context.available ?? orderAvailableUsdc();
  const marginRequired = context.marginRequired ?? (leverage > 0 ? size / leverage : size);
  const liquidationPrice =
    context.liquidationPrice ?? estimatedLiquidationPrice(manual.side, entryPrice, leverage);
  const livePosition = context.livePosition ?? positionForAsset(asset);
  const stopLoss = manualExitPrice("stop_loss", manual, entryPrice);
  const takeProfit = manualExitPrice("take_profit", manual, entryPrice);
  const anyExitEnabled = Boolean(manual.take_profit_enabled || manual.stop_loss_enabled);
  const preflightDetails = [
    "This check runs before sending anything to Hyperliquid.",
    "Review the highlighted field, adjust the order, then submit again.",
  ];

  const issue = (body, details = preflightDetails) => ({
    blocking: true,
    title: "Check order before submitting",
    body,
    details,
  });

  if (!Number.isFinite(size) || size <= 0) return issue("Enter an order Size greater than zero.");
  if (size < MIN_ORDER_USDC) {
    return issue(`Minimum order value is ${MIN_ORDER_USDC} USDC. Increase Size before submitting.`);
  }
  if (size > Number(state.runtime?.max_order_usdc || 100)) {
    return issue("Size is above the runtime max order. Lower Size or change runtime settings.");
  }
  if (!Number.isFinite(leverage) || leverage < 1 || leverage > maxLeverage) {
    return issue(`Leverage must be between 1x and ${number(maxLeverage, 1)}x for ${displayAssetSymbol(asset)}.`);
  }
  if (manual.entry_type === "market" && (!mark || mark <= 0)) {
    return issue("Live mark price is not available yet. Wait for the market price before submitting.");
  }
  if (manual.entry_type === "limit" && (!entryPrice || entryPrice <= 0)) {
    return issue("Limit orders require a valid entry price.");
  }
  if (mark && entryPrice && manual.entry_type === "limit" && Math.abs(entryPrice - mark) / mark > 0.95) {
    return issue(`Limit price is more than 95% away from the current mark price (${compactPrice(mark)}).`);
  }
  if (available > 0 && marginRequired > available) {
    return issue(
      `Margin required is ${money(marginRequired)}, but available wallet collateral is ${money(available)}.`,
      ["Reduce Size, reduce Leverage, or add collateral before submitting."],
    );
  }
  if (manual.reduce_only && !livePosition) {
    return issue("Reduce Only needs an open position on this market.");
  }
  if (manual.take_profit_enabled && !takeProfit) {
    return issue("Take Profit is enabled. Enter a Take Profit value or turn it off.");
  }
  if (manual.stop_loss_enabled && !stopLoss) {
    return issue("Stop Loss is enabled. Enter a Stop Loss value or turn it off.");
  }
  if (!anyExitEnabled || (!takeProfit && !stopLoss) || !entryPrice || !mark) return null;

  if (manual.side === "long") {
    if (takeProfit && (takeProfit <= entryPrice || takeProfit <= mark)) {
      return issue("Take Profit would be invalid for this Long. Set it above entry and current mark price.");
    }
    if (stopLoss && (stopLoss >= entryPrice || stopLoss >= mark)) {
      return issue("Stop Loss would be invalid for this Long. Set it below entry and current mark price.");
    }
    if (stopLoss && liquidationPrice && stopLoss <= liquidationPrice) {
      return issue(
        `Stop Loss is beyond estimated liquidation (${compactPrice(liquidationPrice)}). Move Stop Loss above liquidation.`,
      );
    }
  }
  if (manual.side === "short") {
    if (takeProfit && (takeProfit >= entryPrice || takeProfit >= mark)) {
      return issue("Take Profit would be invalid for this Short. Set it below entry and current mark price.");
    }
    if (stopLoss && (stopLoss <= entryPrice || stopLoss <= mark)) {
      return issue("Stop Loss would be invalid for this Short. Set it above entry and current mark price.");
    }
    if (stopLoss && liquidationPrice && stopLoss >= liquidationPrice) {
      return issue(
        `Stop Loss is beyond estimated liquidation (${compactPrice(liquidationPrice)}). Move Stop Loss below liquidation.`,
      );
    }
  }
  return null;
}

async function createManualPlan({ silent = false } = {}) {
  state.lastOrderError = "";
  const preflight = manualOrderPreflight();
  if (preflight?.blocking) {
    renderTicket();
    toast(preflight.body);
    return null;
  }
  const plan = await api("/api/trades/manual-plan", {
    method: "POST",
    body: JSON.stringify(manualOrderPayload()),
  });
  state.plan = plan;
  state.analysis = null;
  state.selectedCandidateIndex = 0;
  state.manualOrderDirty = false;
  await loadState();
  if (!silent) toast("Manual plan created");
  return plan;
}

async function executeTrade({ confirmed = true } = {}) {
  state.lastOrderError = "";
  if (!state.plan?.id) throw new Error("No trade plan to execute.");
  const validation = await validateActivePlan();
  if (!validation.valid) {
    const errors = validation.errors?.length ? validation.errors.join("; ") : "Formal validation failed.";
    throw new Error(`Formal validation failed: ${errors}`);
  }
  const result = await api(`/api/trades/${state.plan.id}/execute`, {
    method: "POST",
    body: JSON.stringify({
      confirmed: Boolean(confirmed),
    }),
  });
  state.plan = result.plan;
  await loadState();
  toast("Execution submitted");
}

async function validateActivePlan() {
  if (!state.plan?.id) throw new Error("No trade plan to validate.");
  const validation = await api(`/api/trades/${encodeURIComponent(state.plan.id)}/validation`);
  state.plan.validation = validation;
  renderTradingView();
  renderChat();
  return validation;
}

async function submitManualOrder() {
  state.lastOrderError = "";
  const preflight = manualOrderPreflight();
  if (preflight?.blocking) {
    renderTicket();
    toast(preflight.body);
    return;
  }
  state.isSubmittingOrder = true;
  renderTicket();
  try {
    const result = await api("/api/trades/manual-submit", {
      method: "POST",
      body: JSON.stringify(manualOrderPayload()),
    });
    state.plan = result.plan;
    state.order = result.order;
    state.analysis = null;
    state.selectedCandidateIndex = 0;
    state.manualOrderDirty = false;
    await loadState();
    toast("Order submitted");
  } finally {
    state.isSubmittingOrder = false;
    renderTicket();
  }
}

async function rejectTrade() {
  state.manualOrderDirty = false;
  if (!state.plan?.id) {
    clearTradeDisplay();
    toast("Order cleared");
    return;
  }
  state.plan = await api(`/api/trades/${state.plan.id}/reject`, { method: "POST" });
  await loadState();
  toast("Trade rejected");
}

async function refreshOrders({ silent = false } = {}) {
  state.wallet = await api("/api/wallet");
  state.orderBook = await api("/api/orders");
  renderTradingView();
  if (!silent) toast("Orders refreshed");
}

async function closePosition(asset) {
  const label = displayPerpLabel(asset);
  if (!window.confirm(`Close ${label} with a reduce-only market order?`)) return;
  const result = await api(`/api/positions/${encodeURIComponent(asset)}/close`, {
    method: "POST",
    body: JSON.stringify({ confirmed: true }),
  });
  state.order = result.order;
  await loadState();
  toast(`Close order submitted for ${label}`);
}

async function setPositionProtection(asset) {
  const normalizedAsset = normalizeAssetSymbol(asset);
  const label = displayPerpLabel(normalizedAsset);
  const draft = protectionDraft(normalizedAsset);
  const position = positionForAsset(normalizedAsset);
  const size = Number(position?.szi || position?.size || 0);
  const isLong = size >= 0;
  const entry = Number(position?.entryPx || position?.entry_price || 0);
  const mark = position ? positionMarkPrice(position) : latestMarkPrice(normalizedAsset);
  const activeProtection = activeProtectionForAsset(normalizedAsset, {}, { isLong, entry, mark });
  const takeProfit = optionalNumber(draft.take_profit);
  const stopLoss = optionalNumber(draft.stop_loss);
  const removeTakeProfit = Boolean(activeProtection.takeProfitCount && !takeProfit);
  const removeStopLoss = Boolean(activeProtection.stopLossCount && !stopLoss);
  if (!takeProfit && !stopLoss && !removeTakeProfit && !removeStopLoss) {
    throw new Error("Enter or clear an active take profit, stop loss, or both.");
  }
  const actions = [
    takeProfit ? `set TP ${compactPrice(takeProfit)}` : removeTakeProfit ? "remove TP" : null,
    stopLoss ? `set SL ${compactPrice(stopLoss)}` : removeStopLoss ? "remove SL" : null,
  ].filter(Boolean);
  if (!window.confirm(`Update reduce-only protection for ${label}: ${actions.join(", ")}?`)) {
    return;
  }
  await api(`/api/positions/${encodeURIComponent(normalizedAsset)}/protection`, {
    method: "POST",
    body: JSON.stringify({
      confirmed: true,
      take_profit: takeProfit,
      stop_loss: stopLoss,
      remove_take_profit: removeTakeProfit,
      remove_stop_loss: removeStopLoss,
    }),
  });
  state.positionProtection[normalizedAsset] = { take_profit: "", stop_loss: "" };
  await loadState();
  toast(`Protection updated for ${label}`);
}

async function runAction(action, actionTarget) {
  if (action === "chat-bootstrap") await bootstrapChat();
  if (action === "chat-refresh") await refreshChat();
  if (action === "chat-create-deployment") await createChatDeployment();
  if (action === "chat-run-deployment") await runChatDeployment();
  if (action === "chat-new-session") await createChatSession();
  if (action === "chat-send-message") await sendChatMessage();
  if (action === "chat-define-outcome") await defineChatOutcome();
  if (action === "chat-confirm-tool") await confirmChatTool(actionTarget);
  if (action === "chat-interrupt") await interruptChat();
  if (action === "chat-archive") await archiveChat();
  if (action === "chat-execute-plan") await executeChatPlan();
  if (action === "save-settings") await saveRuntime();
  if (action === "scan") {
    await saveRuntime();
    await scan();
  }
  if (action === "create-manual-plan") await createManualPlan();
  if (action === "submit-manual-order") await submitManualOrder();
  if (action === "auto-analyze") await analyzeAutoProposals();
  if (action === "open-auto-chat") await openAutoChat();
  if (action === "review-auto-plan") await reviewAutoPlan(actionTarget);
  if (action === "execute-auto-plan") await executeAutoPlan(actionTarget);
  if (action === "approve-auto-proposal") await approveAutoProposal();
  if (action === "reject-auto-proposal") await rejectAutoProposal();
  if (action === "execute") await executeTrade();
  if (action === "reject") await rejectTrade();
  if (action === "privy-setup-agent") await setupPrivyAgent();
  if (action === "toggle-sensitive") toggleSensitiveWalletData();
  if (action === "copy-wallet-address") await copyWalletAddress(actionTarget.dataset.walletTarget);
  if (action === "open-hyperliquid-deposit") openHyperliquidDeposit();
  if (action === "deposit-master-hyperliquid") await depositMasterToHyperliquid();
  if (action === "refresh-transfer-balances") await refreshTransferBalances();
  if (action === "refresh-trading-deposit-balances") await refreshTradingDepositBalances();
  if (action === "validate-transfer-session") await validateTransferSession();
  if (action === "transfer-usdc-to-master") await transferUsdcToMaster();
  if (action === "deposit-master-trading") {
    await depositMasterToHyperliquid({
      inputSelector: "#trading-deposit-usdc-amount",
      confirmSelector: "#trading-deposit-confirm",
      transferScreen: true,
    });
  }
  if (action === "refresh-external-transfer-balances") await refreshExternalTransferBalances();
  if (action === "validate-external-transfer-session") await validateExternalTransferSession();
  if (action === "transfer-usdc-to-external") await transferUsdcToExternal();
  if (action === "events" || action === "refresh") await loadState();
  if (action === "refresh-orders") await refreshOrders();
  if (action === "close-position") await closePosition(actionTarget.dataset.asset);
  if (action === "set-protection") await setPositionProtection(actionTarget.dataset.asset);
}

function handleActionError(action, error) {
  const message = error.message || "Request failed.";
  if (
    [
      "create-manual-plan",
      "submit-manual-order",
      "auto-analyze",
      "open-auto-chat",
      "review-auto-plan",
      "execute-auto-plan",
      "approve-auto-proposal",
      "execute",
      "close-position",
      "set-protection",
    ].includes(action)
  ) {
    setOrderError(message);
  }
  toast(message);
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
  const chatSessionButton = event.target.closest("[data-chat-session]");
  if (chatSessionButton) {
    event.preventDefault();
    event.stopPropagation();
    state.chat.activeSessionId = chatSessionButton.dataset.chatSession;
    try {
      await loadChatEvents(state.chat.activeSessionId);
      startChatPolling();
    } catch (error) {
      toast(error.message);
    }
    return;
  }
  const chatPromptButton = event.target.closest("[data-chat-prompt]");
  if (chatPromptButton) {
    event.preventDefault();
    event.stopPropagation();
    const input = $("#chat-message-input");
    if (input) {
      input.value = chatPromptButton.dataset.chatPrompt || "";
      input.focus();
    }
    return;
  }
  if (event.target.closest(".app-nav")) return;
  const orderMode = event.target.closest("[data-order-mode]");
  if (orderMode) {
    state.orderMode = orderMode.dataset.orderMode || "manual";
    state.lastOrderError = "";
    renderTradingView();
    return;
  }
  const autoPref = event.target.closest("[data-auto-pref]");
  if (autoPref) {
    state.autoPrefs[autoPref.dataset.autoPref] = autoPref.dataset.value;
    state.analysis = null;
    state.plan = null;
    state.autoChat = { session: null, events: [], plans: [], lastAsset: "" };
    state.selectedCandidateIndex = 0;
    renderTradingView();
    return;
  }
  const ordersTab = event.target.closest("[data-orders-tab]");
  if (ordersTab) {
    state.ordersTab = ordersTab.dataset.ordersTab || "positions";
    renderOrdersPanel();
    return;
  }
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
  const networkButton = event.target.closest(".network-card[data-network]");
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
    syncUrlForScreen();
    renderScreen();
    return;
  }
  const actionTarget = event.target.closest("[data-action]");
  const action = actionTarget?.dataset.action;
  if (!action) return;
  try {
    await runAction(action, actionTarget);
  } catch (error) {
    handleActionError(action, error);
  }
});

document.querySelectorAll(".ticket-panel [data-action]").forEach((button) => {
  button.addEventListener("click", async (event) => {
    event.preventDefault();
    event.stopPropagation();
    const action = button.dataset.action;
    try {
      await runAction(action, button);
    } catch (error) {
      handleActionError(action, error);
    }
  });
});

document.addEventListener("input", (event) => {
  if (
    event.target?.id === "transfer-usdc-amount" ||
    event.target?.id === "external-transfer-usdc-amount" ||
    event.target?.id === "trading-deposit-usdc-amount"
  ) {
    event.target.dataset.touched = "true";
    return;
  }
  const protectionField = event.target.closest("[data-protection-field]");
  if (protectionField) {
    const asset = normalizeAssetSymbol(protectionField.dataset.protectionAsset);
    const draft = protectionDraft(asset);
    draft[protectionField.dataset.protectionField] = protectionField.value;
    draft.touched = true;
    return;
  }
  const leverage = event.target.closest("[data-manual-leverage]");
  if (leverage) {
    state.lastOrderError = "";
    state.manualOrderDirty = true;
    state.manualOrder.leverage = boundedLeverage(leverage.value, assetMaxLeverage(currentChartAsset()));
    renderTradingView();
    return;
  }
  const percent = event.target.closest("[data-manual-percent]");
  if (percent) {
    const maxOrder = orderAvailableUsdc() * Math.max(1, Number(state.manualOrder.leverage) || 1);
    state.lastOrderError = "";
    state.manualOrderDirty = true;
    const nextSize = Math.round((maxOrder * Number(percent.value || 1)) / 100);
    state.manualOrder.size_usdc = Math.max(maxOrder >= MIN_ORDER_USDC ? MIN_ORDER_USDC : 1, nextSize);
    renderTradingView();
    return;
  }
  const field = event.target.closest("[data-manual-field]");
  if (!field) return;
  state.lastOrderError = "";
  state.manualOrderDirty = true;
  state.manualOrder[field.dataset.manualField] = field.value;
  if (
    field.dataset.manualField === "leverage" ||
    (state.manualOrder.exit_input_mode === "percent" &&
      ["take_profit", "stop_loss"].includes(field.dataset.manualField))
  ) {
    renderTradingView();
  }
});

document.addEventListener("change", (event) => {
  const protectionField = event.target.closest("[data-protection-field]");
  if (protectionField) {
    const asset = normalizeAssetSymbol(protectionField.dataset.protectionAsset);
    const draft = protectionDraft(asset);
    draft[protectionField.dataset.protectionField] = protectionField.value;
    draft.touched = true;
    return;
  }
  const checkbox = event.target.closest("[data-manual-checkbox]");
  if (checkbox) {
    state.lastOrderError = "";
    state.manualOrderDirty = true;
    state.manualOrder[checkbox.dataset.manualCheckbox] = checkbox.checked;
    if (["take_profit_enabled", "stop_loss_enabled"].includes(checkbox.dataset.manualCheckbox)) {
      state.manualOrder.exits_enabled = Boolean(
        state.manualOrder.take_profit_enabled || state.manualOrder.stop_loss_enabled,
      );
      if (checkbox.checked && state.manualOrder.exit_input_mode === "percent") {
        const field = checkbox.dataset.manualCheckbox === "take_profit_enabled" ? "take_profit" : "stop_loss";
        if (!state.manualOrder[field]) state.manualOrder[field] = field === "take_profit" ? "3" : "2";
      }
    }
    renderTradingView();
    return;
  }
  const field = event.target.closest("[data-manual-field]");
  if (!field) return;
  state.lastOrderError = "";
  state.manualOrderDirty = true;
  state.manualOrder[field.dataset.manualField] = field.value;
  renderTradingView();
});

document.addEventListener("click", (event) => {
  const exitStep = event.target.closest("[data-exit-step]");
  if (exitStep) {
    state.lastOrderError = "";
    state.manualOrderDirty = true;
    const field = exitStep.dataset.exitStep;
    const delta = Number(exitStep.dataset.delta || 0);
    const current = Number(state.manualOrder[field] || (field === "take_profit" ? 3 : 2));
    state.manualOrder[field] = inputPriceValue(Math.max(0.5, Math.min(50, current + delta)));
    renderTradingView();
    return;
  }
  const protectionPreset = event.target.closest("[data-protection-preset]");
  if (protectionPreset) {
    const asset = normalizeAssetSymbol(protectionPreset.dataset.protectionAsset);
    const isLong = protectionPreset.dataset.protectionSide !== "short";
    applyProtectionPreset(asset, isLong, Number(protectionPreset.dataset.protectionEntry || 0));
    renderOrdersPanel();
    return;
  }
  const pick = event.target.closest("[data-manual-pick]");
  if (pick) {
    state.lastOrderError = "";
    state.manualOrderDirty = true;
    const previousValue = state.manualOrder[pick.dataset.manualPick];
    state.manualOrder[pick.dataset.manualPick] = pick.dataset.value;
    if (pick.dataset.manualPick === "entry_type" && pick.dataset.value === "market") {
      state.manualOrder.entry_price = "";
    }
    if (pick.dataset.manualPick === "exit_input_mode" && previousValue !== pick.dataset.value) {
      if (pick.dataset.value === "percent") {
        if (state.manualOrder.take_profit_enabled && !state.manualOrder.take_profit) {
          state.manualOrder.take_profit = "3";
        }
        if (state.manualOrder.stop_loss_enabled && !state.manualOrder.stop_loss) {
          state.manualOrder.stop_loss = "2";
        }
      } else {
        if (!state.manualOrder.take_profit_enabled) state.manualOrder.take_profit = "";
        if (!state.manualOrder.stop_loss_enabled) state.manualOrder.stop_loss = "";
      }
    }
    renderTradingView();
    return;
  }
  const size = event.target.closest("[data-manual-size]");
  if (size) {
    state.lastOrderError = "";
    state.manualOrderDirty = true;
    state.manualOrder.size_usdc = Number(size.dataset.manualSize);
    renderTradingView();
    return;
  }
  const percent = event.target.closest("[data-manual-percent-preset]");
  if (percent) {
    const maxOrder = orderAvailableUsdc() * Math.max(1, Number(state.manualOrder.leverage) || 1);
    state.lastOrderError = "";
    state.manualOrderDirty = true;
    const nextSize = Math.round((maxOrder * Number(percent.dataset.manualPercentPreset)) / 100);
    state.manualOrder.size_usdc = Math.max(maxOrder >= MIN_ORDER_USDC ? MIN_ORDER_USDC : 1, nextSize);
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
    syncUrlForScreen();
    renderScreen();
  });
}

window.addEventListener("popstate", () => {
  state.screen = screenFromPath();
  renderScreen();
});

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

$("#analyze-form")?.addEventListener("submit", async (event) => {
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
