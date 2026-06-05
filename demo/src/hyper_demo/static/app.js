const state = {
  profile: null,
  research: null,
  plan: null,
  order: null,
  run: null,
  setup: null,
  team: null,
  wallet: null,
};

const titles = {
  "/": ["Agent console", "Agent loop, guardrails, and exchange trading state."],
  "/profile": ["Risk profile", "Define the investor envelope that constrains every downstream agent."],
  "/research": ["Research station", "Launch the research agent or use the fallback transcript when credentials are missing."],
  "/proposal": ["Proposal station", "Generate a bounded guarded trade plan."],
  "/agents": ["Agent review", "Run search, quant signals, and investor-style review skills."],
  "/execution": ["Execution station", "Submit confirmed guarded Hyperliquid orders."],
  "/monitor": ["Monitor", "Track portfolio metrics, thesis state, and run events."],
  "/settings": ["System settings", "Validate credentials and load fallback material."],
};

const workflowSteps = [
  ["profile", "Risk profile", "Investor constraints locked before any autonomous action.", "profile"],
  ["research", "Research", "Market narrative, catalysts, and fallback intelligence gathered.", "research"],
  ["plan", "Proposal", "Entry, invalidation, stop, take-profit, and sizing assembled.", "plan"],
  ["team", "Agent review", "Specialist agents debate the plan before execution.", "team"],
  ["order", "Execution", "Guarded Hyperliquid or paper order submitted only after explicit confirmation.", "order"],
  ["monitor", "Monitor", "Metrics and run events keep the thesis observable.", "run"],
];

const fallbackAgents = [
  ["Research Agent", "awaiting brief", "Collects market context and narrative risk.", "INTEL"],
  ["Quant Agent", "awaiting signal", "Checks alpha, beta, VaR, and exposure.", "SIGNAL"],
  ["Risk Agent", "guardrail active", "Enforces drawdown, leverage, and stop limits.", "SAFETY"],
  ["Portfolio Agent", "standing by", "Translates plan into allocation posture.", "ALLOC"],
  ["Execution Agent", "locked", "Requires explicit confirmation before order submission.", "ORDER"],
];

function $(selector) {
  return document.querySelector(selector);
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
  if (!response.ok) {
    throw new Error(payload?.detail || response.statusText);
  }
  return payload;
}

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("visible");
  window.setTimeout(() => el.classList.remove("visible"), 2600);
}

function setRoute(path) {
  const route = titles[path] ? path : "/";
  for (const view of document.querySelectorAll(".view")) {
    view.classList.toggle("active", view.id === (route === "/" ? "dashboard" : route.slice(1)));
  }
  for (const link of document.querySelectorAll("nav a")) {
    link.classList.toggle("active", link.dataset.route === route);
  }
  $("#route-title").textContent = titles[route][0];
  $("#route-subtitle").textContent = titles[route][1];
}

async function loadState() {
  const payload = await api("/api/state");
  Object.assign(state, payload);
  renderState();
  drawMarketChart();
}

function renderState() {
  const profileId = $("#profile-id");
  const researchId = $("#research-id");
  const planId = $("#plan-id");
  const orderId = $("#order-id");
  if (profileId) profileId.textContent = state.profile?.id || "Not created";
  if (researchId) researchId.textContent = state.research?.id || "Not created";
  if (planId) planId.textContent = state.plan?.id || "Not created";
  if (orderId) orderId.textContent = state.order?.id || "Not submitted";
  $("#anthropic-status").textContent = `Claude: ${state.setup?.anthropic_configured ? "ready" : "fallback"}`;
  $("#hyperliquid-status").textContent = `Hyperliquid: ${state.setup?.hyperliquid_configured ? "ready" : "missing"}`;
  $("#mode-status").textContent = `Mode: ${state.setup?.trading_mode || "testnet"}`;
  const marketModePill = $("#market-mode-pill");
  if (marketModePill) {
    marketModePill.textContent = state.setup?.hyperliquid_environment === "mainnet" ? "MAINNET GUARDED" : "testnet";
  }
  renderWorkflowTimeline();
  renderReadiness();
  renderAgentRoster();
}

function statusFor(key) {
  if (key === "team" && state.team) return "complete";
  if (key === "monitor" && state.run) return "running";
  return state[key] ? "complete" : "pending";
}

function renderWorkflowTimeline() {
  const el = $("#mission-timeline");
  if (!el) return;
  el.innerHTML = workflowSteps
    .map(([key, title, description, stateKey], index) => {
      const status = statusFor(stateKey);
      const value = state[stateKey]?.id || (stateKey === "team" && state.team?.consensus) || "not started";
      return `
        <div class="mission-step ${status}">
          <b class="step-index">${String(index + 1).padStart(2, "0")}</b>
          <div>
            <h3>${title}</h3>
            <p>${description}</p>
            <small>${value}</small>
          </div>
          <span class="state-chip">${status}</span>
        </div>
      `;
    })
    .join("");
}

function renderReadiness() {
  const el = $("#readiness-list");
  if (!el) return;
  const rows = [
    ["Claude managed agent", state.setup?.anthropic_configured ? "ready" : "fallback mode"],
    ["Hyperliquid exchange", state.setup?.hyperliquid_configured ? "ready" : "credentials missing"],
    ["Environment", state.setup?.hyperliquid_environment || "testnet"],
    ["Trading mode", state.setup?.trading_mode || "testnet"],
    ["Execution guardrail", "explicit confirmation required"],
  ];
  el.innerHTML = rows
    .map(([label, value]) => `<div><b>${label}</b><small>${value}</small></div>`)
    .join("");
}

function renderAgentRoster() {
  const el = $("#agent-roster");
  if (!el) return;
  const opinions = state.team?.opinions?.length
    ? state.team.opinions.map((opinion) => [
        opinion.display_name,
        opinion.stance,
        opinion.rationale,
        "LIVE",
      ])
    : fallbackAgents;
  el.innerHTML = opinions
    .map(
      ([name, stance, detail, code]) => `
        <div class="agent-card">
          <em>${code}</em>
          <div>
            <b>${name}</b>
            <small>${detail}</small>
          </div>
          <span>${String(stance).replaceAll("_", " ")}</span>
        </div>
      `,
    )
    .join("");
}

function drawMarketChart() {
  const canvas = $("#market-chart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#000";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#34343a";
  ctx.lineWidth = 1;
  for (let y = 40; y < height; y += 44) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
  const points = [128, 118, 122, 101, 96, 83, 90, 76, 70, 64, 58, 53];
  ctx.strokeStyle = "#fff";
  ctx.lineWidth = 3;
  ctx.beginPath();
  points.forEach((point, index) => {
    const x = 34 + index * ((width - 68) / (points.length - 1));
    const y = 32 + point;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.fillStyle = "#fff";
  ctx.font = "700 18px Arial Narrow, Arial, sans-serif";
  ctx.fillText((state.plan ? `${state.plan.asset} proposal` : "Demo market pulse").toUpperCase(), 26, 34);
  ctx.fillStyle = "#b7b7bd";
  ctx.font = "14px Arial Narrow, Arial, sans-serif";
  ctx.fillText("Signal display only. Execution data comes from the API.".toUpperCase(), 26, height - 24);
}

async function createProfile(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target).entries());
  for (const key of ["horizon_days", "max_drawdown_pct", "capital_at_risk_usdc", "stop_loss_pct"]) {
    data[key] = Number(data[key]);
  }
  state.profile = await api("/api/profile", { method: "POST", body: JSON.stringify(data) });
  $("#profile-output").textContent = pretty(state.profile);
  renderState();
  toast("Risk profile created");
}

async function runResearch() {
  const payload = { asset: $("#research-asset").value, profile_id: state.profile?.id };
  state.research = await api("/api/research", { method: "POST", body: JSON.stringify(payload) });
  $("#research-output").textContent = pretty(state.research);
  renderState();
  toast("Research completed");
}

async function createProposal() {
  const payload = {
    asset: $("#proposal-asset").value,
    profile_id: state.profile?.id,
    research_id: state.research?.id,
  };
  state.plan = await api("/api/proposals", { method: "POST", body: JSON.stringify(payload) });
  $("#proposal-output").textContent = pretty(state.plan);
  renderState();
  drawMarketChart();
  toast("Proposal created");
}

async function runAgentTeam() {
  const payload = {
    asset: $("#agents-asset").value,
    profile_id: state.profile?.id,
    research_id: state.research?.id,
  };
  state.team = await api("/api/agents/debate", { method: "POST", body: JSON.stringify(payload) });
  $("#agents-output").textContent = pretty(state.team);
  $("#consensus-pill").textContent = state.team.consensus.replaceAll("_", " ");
  $("#agent-opinions").innerHTML = state.team.opinions
    .map(
      (opinion) => `<div><b>${opinion.display_name}</b><span>${opinion.stance}</span><small>${opinion.rationale}</small></div>`,
    )
    .join("");
  toast("Agent team review completed");
}

async function executePlan() {
  if (!state.plan?.id) {
    throw new Error("Create a proposal before execution.");
  }
  const payload = {
    plan_id: state.plan.id,
    confirmed: $("#execute-confirm").checked,
    confirmation_phrase: $("#mainnet-phrase").value || null,
  };
  const result = await api("/api/orders/testnet", { method: "POST", body: JSON.stringify(payload) });
  state.run = result.run;
  state.order = result.order;
  $("#execution-output").textContent = pretty(result);
  renderState();
  toast(`${result.order.exchange} order submitted`);
}

async function executePaperPlan() {
  if (!state.plan?.id) {
    throw new Error("Create a proposal before paper trading.");
  }
  const payload = { plan_id: state.plan.id, confirmed: $("#paper-confirm").checked };
  const result = await api("/api/orders/paper", { method: "POST", body: JSON.stringify(payload) });
  state.run = result.run;
  state.order = result.order;
  $("#execution-output").textContent = pretty(result);
  renderState();
  toast("Paper trade simulated");
}

async function updateMetrics() {
  const metrics = await api("/api/portfolio/metrics");
  $("#metric-alpha").textContent = metrics.alpha;
  $("#metric-beta").textContent = metrics.beta;
  $("#metric-var").textContent = `${metrics.value_at_risk_95} USDC`;
  $("#metrics-list").innerHTML = Object.entries(metrics)
    .filter(([key]) => !["computed_at", "exposure_by_asset"].includes(key))
    .map(([key, value]) => `<div>${key.replaceAll("_", " ")} <b>${value}</b></div>`)
    .join("");
  if (state.run?.id) {
    const events = await api(`/api/runs/${state.run.id}/events`);
    $("#events-list").innerHTML = events.map((event) => `<div>${event.created_at}<br>${event.message}</div>`).join("");
  }
}

async function checkSetup() {
  state.setup = await api("/api/setup-check");
  $("#settings-output").textContent = pretty(state.setup);
  renderState();
  toast("Setup checked");
}

async function loadWallet() {
  state.wallet = await api("/api/wallet");
  $("#wallet-output").textContent = pretty(state.wallet);
  $("#wallet-summary").innerHTML = [
    ["Account", state.setup?.hyperliquid_account_address || state.wallet.account_address],
    ["Collateral", `${state.wallet.collateral_usdc} USDC`],
    ["Margin used", `${state.wallet.total_margin_used_usdc} USDC`],
    ["Exposure", `${state.wallet.exposure_usdc} USDC`],
    ["Positions", state.wallet.open_positions.length],
  ]
    .map(([label, value]) => `<div>${label} <b>${value}</b></div>`)
    .join("");
  toast("Wallet state loaded");
}

async function loadReplay() {
  const result = await api("/api/replay/fallback", { method: "POST" });
  $("#settings-output").textContent = pretty(result);
  await loadState();
  toast("Fallback replay loaded");
}

document.addEventListener("click", async (event) => {
  const link = event.target.closest("a[data-route]");
  if (link) {
    event.preventDefault();
    history.pushState(null, "", link.dataset.route);
    setRoute(link.dataset.route);
    return;
  }
  const action = event.target.dataset.action;
  if (!action) return;
  try {
    if (action === "refresh") await loadState();
    if (action === "research") await runResearch();
    if (action === "proposal") await createProposal();
    if (action === "agents") await runAgentTeam();
    if (action === "execute") await executePlan();
    if (action === "paper") await executePaperPlan();
    if (action === "metrics") await updateMetrics();
    if (action === "setup") await checkSetup();
    if (action === "wallet") await loadWallet();
    if (action === "replay") await loadReplay();
  } catch (error) {
    toast(error.message);
  }
});

window.addEventListener("popstate", () => setRoute(location.pathname));
$("#profile-form").addEventListener("submit", createProfile);

setRoute(location.pathname);
loadState().then(updateMetrics).catch((error) => toast(error.message));
