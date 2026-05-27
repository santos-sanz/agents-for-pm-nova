const state = {
  profile: null,
  research: null,
  plan: null,
  order: null,
  run: null,
  setup: null,
};

const titles = {
  "/": ["Dashboard", "Agent loop, guardrails, and testnet trading state."],
  "/profile": ["Risk Profile", "Create the structured investor profile used by the agent."],
  "/research": ["Research", "Use Claude Managed Agents or the fallback transcript."],
  "/proposal": ["Proposal", "Generate a bounded testnet-only trade plan."],
  "/execution": ["Execution", "Submit confirmed Hyperliquid testnet orders."],
  "/monitor": ["Monitor", "Track portfolio metrics, thesis state, and run events."],
  "/settings": ["Settings", "Validate credentials and load fallback material."],
};

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
  $("#profile-id").textContent = state.profile?.id || "Not created";
  $("#research-id").textContent = state.research?.id || "Not created";
  $("#plan-id").textContent = state.plan?.id || "Not created";
  $("#order-id").textContent = state.order?.id || "Not submitted";
  $("#anthropic-status").textContent = `Claude: ${state.setup?.anthropic_configured ? "ready" : "fallback"}`;
  $("#hyperliquid-status").textContent = `Hyperliquid: ${state.setup?.hyperliquid_configured ? "ready" : "missing"}`;
  $("#mode-status").textContent = `Mode: ${state.setup?.trading_mode || "testnet"}`;
}

function drawMarketChart() {
  const canvas = $("#market-chart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#f8fbff";
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = "#d9e0ea";
  ctx.lineWidth = 1;
  for (let y = 40; y < height; y += 44) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }
  const points = [128, 118, 122, 101, 96, 83, 90, 76, 70, 64, 58, 53];
  ctx.strokeStyle = "#0f766e";
  ctx.lineWidth = 4;
  ctx.beginPath();
  points.forEach((point, index) => {
    const x = 34 + index * ((width - 68) / (points.length - 1));
    const y = 32 + point;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.fillStyle = "#162033";
  ctx.font = "18px Inter, sans-serif";
  ctx.fillText(state.plan ? `${state.plan.asset} proposal` : "Demo market pulse", 26, 34);
  ctx.fillStyle = "#667085";
  ctx.font = "14px Inter, sans-serif";
  ctx.fillText("Visual signal for the live demo; execution data comes from the API.", 26, height - 24);
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

async function executePlan() {
  if (!state.plan?.id) {
    throw new Error("Create a proposal before execution.");
  }
  const payload = { plan_id: state.plan.id, confirmed: $("#execute-confirm").checked };
  const result = await api("/api/orders/testnet", { method: "POST", body: JSON.stringify(payload) });
  state.run = result.run;
  state.order = result.order;
  $("#execution-output").textContent = pretty(result);
  renderState();
  toast("Testnet order submitted");
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
    if (action === "execute") await executePlan();
    if (action === "metrics") await updateMetrics();
    if (action === "setup") await checkSetup();
    if (action === "replay") await loadReplay();
  } catch (error) {
    toast(error.message);
  }
});

window.addEventListener("popstate", () => setRoute(location.pathname));
$("#profile-form").addEventListener("submit", createProfile);

setRoute(location.pathname);
loadState().then(updateMetrics).catch((error) => toast(error.message));
