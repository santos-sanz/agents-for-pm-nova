const state = {
  profile: null,
  verification: null,
  research: null,
  allocation: null,
  rebalance: null,
  approvalMessage: null,
  events: [],
  chart: null,
  series: null,
};

const $ = (selector) => document.querySelector(selector);

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(payload?.detail || response.statusText || "Request failed.");
  }
  return payload;
}

function pct(value) {
  return `${Number(value || 0).toFixed(2)}%`;
}

function pctOrUnavailable(value) {
  if (value === null || value === undefined) return "unavailable";
  return pct(value);
}

function signedPct(value) {
  if (value === null || value === undefined) return "unavailable";
  const numeric = Number(value || 0);
  const prefix = numeric > 0 ? "+" : "";
  return `${prefix}${numeric.toFixed(2)}%`;
}

function money(value) {
  if (value === null || value === undefined) return "unavailable";
  return Number(value).toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function statusText(value) {
  return String(value || "draft").replaceAll("_", " ");
}

async function loadState() {
  const payload = await api("/api/state");
  state.profile = payload.workshop_profile;
  state.verification = payload.workshop_verification;
  state.research = payload.workshop_research;
  state.allocation = payload.workshop_allocation;
  state.events = payload.workshop_events || [];
  render();
}

async function saveProfile(event) {
  event.preventDefault();
  const riskScore = Number($("#risk-score").value);
  state.rebalance = null;
  state.approvalMessage = null;
  state.profile = await api("/api/workshop/profile", {
    method: "POST",
    body: JSON.stringify({ risk_score: riskScore }),
  });
  state.allocation = await api("/api/workshop/allocate", {
    method: "POST",
    body: JSON.stringify({ risk_score: riskScore }),
  });
  await loadState();
}

async function verifyAssets() {
  state.verification = await api("/api/workshop/verify-assets", { method: "POST" });
  render();
}

async function runAllocation() {
  const riskScore = state.profile?.risk_score ?? Number($("#risk-score").value);
  state.rebalance = null;
  state.approvalMessage = null;
  state.allocation = await api("/api/workshop/allocate", {
    method: "POST",
    body: JSON.stringify({ risk_score: riskScore }),
  });
  await loadState();
}

async function prepareRebalance() {
  if (!state.allocation?.id) {
    await runAllocation();
  }
  const result = await api("/api/workshop/rebalance", {
    method: "POST",
    body: JSON.stringify({ allocation_id: state.allocation.id, confirmed: false }),
  });
  state.rebalance = result;
  state.approvalMessage = { level: "info", message: result.message };
  state.allocation.validation_status = result.status;
  state.events = [
    {
      created_at: new Date().toISOString(),
      level: "info",
      message: result.message,
    },
    ...state.events,
  ];
  render();
}

async function approveTrades() {
  if (!state.allocation?.id) return;
  try {
    const result = await api("/api/workshop/rebalance", {
      method: "POST",
      body: JSON.stringify({ allocation_id: state.allocation.id, confirmed: true }),
    });
    state.rebalance = result;
    state.approvalMessage = { level: "success", message: result.message };
    state.allocation.validation_status = result.status;
    $("#approval-check").checked = false;
    state.events = [
      {
        created_at: new Date().toISOString(),
        level: "info",
        message: result.message,
      },
      ...state.events,
    ];
  } catch (error) {
    state.approvalMessage = { level: "error", message: error.message };
    state.events = [
      { created_at: new Date().toISOString(), level: "error", message: error.message },
      ...state.events,
    ];
  }
  render();
}

async function rejectTrades() {
  if (!state.allocation?.id) return;
  try {
    const result = await api("/api/workshop/rebalance/reject", {
      method: "POST",
      body: JSON.stringify({ allocation_id: state.allocation.id, confirmed: false }),
    });
    state.rebalance = result;
    state.approvalMessage = { level: "warning", message: result.message };
    state.allocation.validation_status = result.status;
    $("#approval-check").checked = false;
    state.events = [
      {
        created_at: new Date().toISOString(),
        level: "warning",
        message: result.message,
      },
      ...state.events,
    ];
  } catch (error) {
    state.approvalMessage = { level: "error", message: error.message };
    state.events = [
      { created_at: new Date().toISOString(), level: "error", message: error.message },
      ...state.events,
    ];
  }
  render();
}

function render() {
  renderProfile();
  renderSummary();
  renderAllocation();
  renderApproval();
  renderAssets();
  renderSources();
  renderWorkflow();
  renderEvents();
}

function renderProfile() {
  const hasProfile = Boolean(state.profile);
  $("#profile-section").hidden = hasProfile;
  if (!hasProfile) return;
  $("#risk-score").value = state.profile.risk_score;
  $("#risk-score-label").textContent = state.profile.risk_score;
}

function renderSummary() {
  $("#risk-profile").textContent = state.profile
    ? `${state.profile.risk_score}/100 ${statusText(state.profile.band)}`
    : "not set";
  const allocation = state.allocation;
  $("#cash-target").textContent = allocation ? pct(allocation.cash_pct) : "--%";
  $("#hero-cash").textContent = allocation ? pct(allocation.cash_pct) : "--%";
  $("#confidence").textContent = allocation ? `${Math.round(allocation.confidence * 100)}%` : "--";
  $("#validation-status").textContent = statusText(allocation?.validation_status || "draft");
}

function renderAllocation() {
  const allocation = state.allocation;
  const items = allocation
    ? [
        { label: "USDC", value: allocation.cash_pct, rationale: "Capital reserve" },
        ...allocation.positions.map((position) => ({
          label: position.display_label,
          value: position.target_pct,
          rationale: position.rationale,
        })),
      ]
    : [];
  $("#allocation-list").innerHTML = items.length
    ? items
        .map(
          (item) => `
          <article>
            <span>${escapeHtml(item.label)}</span>
            <strong>${pct(item.value)}</strong>
            <p>${escapeHtml(item.rationale)}</p>
          </article>
        `,
        )
        .join("")
    : `<p class="muted">Save the risk slider or run agents to generate a proposal.</p>`;
  renderChart(items);
}

function renderApproval() {
  const allocation = state.allocation;
  const status = allocation?.validation_status || "draft";
  const visible = Boolean(
    allocation && ["pending_approval", "approved", "submitted", "rejected", "failed"].includes(status),
  );
  const section = $("#trade-approval-section");
  section.hidden = !visible;
  if (!visible) return;

  const orders = state.rebalance?.orders?.length
    ? state.rebalance.orders
    : buildApprovalOrders(allocation);
  const isPending = status === "pending_approval";
  const checkbox = $("#approval-check");
  const message = state.approvalMessage?.message || approvalDefaultMessage(status);
  const messageLevel = state.approvalMessage?.level || "info";

  $("#approval-message").className = `approval-note ${messageLevel}`;
  $("#approval-message").textContent = message;
  $("#approval-proposal").textContent = allocation.id;
  $("#approval-status").textContent = statusText(status);
  $("#approval-ticket-count").textContent = String(orders.length);
  $("#approval-trades").innerHTML = orders.length
    ? orders
        .map(
          (order) => `
            <tr>
              <td><strong>${escapeHtml(statusText(order.action))}</strong></td>
              <td>${escapeHtml(order.display_label || order.canonical_id)}</td>
              <td>${escapeHtml(pctOrUnavailable(order.current_pct))}</td>
              <td>${escapeHtml(pctOrUnavailable(order.target_pct))}</td>
              <td>${escapeHtml(signedPct(order.delta_pct))}</td>
              <td>${escapeHtml(order.rationale || "Within approved allocation constraints.")}</td>
            </tr>
          `,
        )
        .join("")
    : `<tr><td colspan="6">No rebalance tickets are ready for approval.</td></tr>`;

  checkbox.disabled = !isPending;
  if (!isPending) checkbox.checked = false;
  updateApprovalControls();
}

function updateApprovalControls() {
  const allocation = state.allocation;
  const isPending = allocation?.validation_status === "pending_approval";
  const approved = Boolean($("#approval-check")?.checked);
  $("#approve-trades").disabled = !isPending || !approved;
  $("#reject-trades").disabled = !isPending;
}

function buildApprovalOrders(allocation) {
  if (!allocation) return [];
  const current = new Map(
    (allocation.current_wallet_allocation || []).map((item) => [
      item.canonical_id,
      Number(item.target_pct || 0),
    ]),
  );
  const hasWalletSnapshot = current.size > 0;
  const targets = [
    {
      canonical_id: "USDC",
      display_label: "USDC",
      category: "cash",
      target_pct: allocation.cash_pct,
      rationale: "Capital reserve after rebalance.",
    },
    ...(allocation.positions || []),
  ];
  const targetIds = new Set(targets.map((target) => target.canonical_id));
  current.forEach((_currentPct, canonicalId) => {
    if (!canonicalId || targetIds.has(canonicalId)) return;
    targets.push({
      canonical_id: canonicalId,
      display_label: canonicalId,
      category: "outside_target",
      target_pct: 0,
      rationale: "Existing wallet exposure is outside the approved target allocation.",
    });
  });
  return targets.map((target) => {
    const currentPct = hasWalletSnapshot ? Number(current.get(target.canonical_id) || 0) : null;
    const targetPct = Number(target.target_pct || 0);
    const deltaPct = currentPct === null ? null : Number((targetPct - currentPct).toFixed(2));
    return {
      canonical_id: target.canonical_id,
      display_label: target.display_label,
      category: target.category,
      action: rebalanceAction(target.canonical_id, deltaPct),
      current_pct: currentPct,
      target_pct: targetPct,
      delta_pct: deltaPct,
      rationale: target.rationale,
    };
  });
}

function rebalanceAction(canonicalId, deltaPct) {
  if (deltaPct === null || deltaPct === undefined) return canonicalId === "USDC" ? "reserve" : "stage";
  if (Math.abs(deltaPct) < 0.01) return "hold";
  if (canonicalId === "USDC") return deltaPct > 0 ? "raise cash" : "deploy cash";
  return deltaPct > 0 ? "increase" : "trim";
}

function approvalDefaultMessage(status) {
  if (status === "approved") {
    return "Human approval is recorded. No rebalance tickets cleared execution thresholds.";
  }
  if (status === "submitted") {
    return "Human approval is recorded and rebalance orders were submitted.";
  }
  if (status === "rejected") {
    return "This rebalance preview was rejected. Run agents again to create a new proposal.";
  }
  if (status === "failed") {
    return "The rebalance could not be approved. Review the audit log before retrying.";
  }
  return "Explicit approval is required before this rebalance can move past review.";
}

function renderChart(items) {
  const root = $("#allocation-chart");
  if (!window.LightweightCharts || !items.length) {
    root.innerHTML = `<div class="chart-empty">Allocation chart appears after a proposal.</div>`;
    return;
  }
  root.innerHTML = "";
  state.chart = window.LightweightCharts.createChart(root, {
    height: 260,
    layout: { background: { color: "#ffffff" }, textColor: "#1d1d1f" },
    grid: { vertLines: { color: "#f0f0f0" }, horzLines: { color: "#f0f0f0" } },
    rightPriceScale: { visible: false },
    timeScale: { visible: true, borderColor: "#e0e0e0" },
  });
  const seriesOptions = { color: "#0066cc", priceFormat: { type: "percent" } };
  state.series =
    typeof state.chart.addHistogramSeries === "function"
      ? state.chart.addHistogramSeries(seriesOptions)
      : state.chart.addSeries(window.LightweightCharts.HistogramSeries, seriesOptions);
  state.series.setData(
    items.map((item, index) => ({
      time: `2026-06-${String(index + 1).padStart(2, "0")}`,
      value: Number(item.value),
      color: item.label === "USDC" ? "#1d1d1f" : "#0066cc",
    })),
  );
  state.chart.timeScale().fitContent();
}

function renderAssets() {
  const allocationById = new Map(
    (state.allocation?.positions || []).map((position) => [position.canonical_id, position.target_pct]),
  );
  const assets = state.verification?.assets || [];
  $("#asset-table").innerHTML = assets.length
    ? assets
        .map((asset) => {
          const failure = !asset.active || asset.delisted;
          return `
            <tr>
              <td>${escapeHtml(asset.display_label)}</td>
              <td>${escapeHtml(asset.canonical_id)}</td>
              <td>${statusText(asset.category)}</td>
              <td>${failure ? "blocked" : "active"}</td>
              <td>${money(asset.mark_price)}</td>
              <td>${asset.funding === null || asset.funding === undefined ? "coverage gap" : money(asset.funding)}</td>
              <td>${asset.open_interest === null || asset.open_interest === undefined ? "coverage gap" : money(asset.open_interest)}</td>
              <td>${asset.max_leverage}x</td>
              <td>${pct(asset.allocation_cap_pct)}</td>
              <td>${pct(allocationById.get(asset.canonical_id) || 0)}</td>
            </tr>
          `;
        })
        .join("")
    : `<tr><td colspan="10">Asset verification has not run yet.</td></tr>`;
  const failures = assets.filter((asset) => !asset.active || asset.delisted);
  $("#runtime-failures").hidden = failures.length === 0;
  $("#runtime-failures").innerHTML = failures
    .map((asset) => `<p>${escapeHtml(asset.display_label)}: ${escapeHtml(asset.issues.join(", "))}</p>`)
    .join("");
}

function renderSources() {
  const allocation = state.allocation;
  const sources = allocation?.research_sources || state.research?.sources || [];
  const gaps = allocation?.coverage_gaps || state.research?.coverage_gaps || [];
  $("#sources").innerHTML = `
    ${sources
      .map(
        (source) => `
          <article>
            <strong>${escapeHtml(source.name || "Source")}</strong>
            <span>${escapeHtml(source.checked_at || "")}</span>
            <p>${escapeHtml(source.url || "local")}</p>
          </article>
        `,
      )
      .join("")}
    ${gaps.map((gap) => `<article class="gap"><strong>Coverage gap</strong><p>${escapeHtml(gap)}</p></article>`).join("")}
  `;
}

function renderWorkflow() {
  const explanations = state.allocation?.explanations || [
    "Research agent waits for profile input.",
    "Portfolio agent will size a 100% allocation including USDC.",
    "Safety agent blocks unverified markets and execution without confirmation.",
  ];
  $("#workflow").innerHTML = explanations
    .map((item, index) => `<article><span>${index + 1}</span><p>${escapeHtml(item)}</p></article>`)
    .join("");
}

function renderEvents() {
  $("#events").innerHTML = state.events.length
    ? state.events
        .slice()
        .reverse()
        .slice(0, 10)
        .map(
          (event) => `
            <article>
              <span>${escapeHtml(new Date(event.created_at).toLocaleString())}</span>
              <strong>${escapeHtml(event.level || "info")}</strong>
              <p>${escapeHtml(event.message)}</p>
            </article>
          `,
        )
        .join("")
    : `<p class="muted">No workshop events yet.</p>`;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function bindEvents() {
  $("#profile-form").addEventListener("submit", saveProfile);
  $("#risk-score").addEventListener("input", (event) => {
    $("#risk-score-label").textContent = event.target.value;
  });
  $("#approval-check").addEventListener("input", updateApprovalControls);
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        if (button.dataset.action === "refresh") await loadState();
        if (button.dataset.action === "verify") await verifyAssets();
        if (button.dataset.action === "allocate") await runAllocation();
        if (button.dataset.action === "rebalance") await prepareRebalance();
        if (button.dataset.action === "approve-trades") await approveTrades();
        if (button.dataset.action === "reject-trades") await rejectTrades();
      } catch (error) {
        state.events = [
          { created_at: new Date().toISOString(), level: "error", message: error.message },
          ...state.events,
        ];
        if (button.dataset.action === "rebalance") {
          state.approvalMessage = { level: "error", message: error.message };
        }
        renderEvents();
        renderApproval();
      }
    });
  });
}

bindEvents();
loadState().catch((error) => {
  state.events = [{ created_at: new Date().toISOString(), level: "error", message: error.message }];
  renderEvents();
});
