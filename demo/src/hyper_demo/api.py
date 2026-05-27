from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hyper_demo.adapters.anthropic_managed import ManagedAgentResearchClient
from hyper_demo.adapters.hyperliquid import ExecutionBlocked, HyperliquidTestnetAdapter
from hyper_demo.config import Settings, get_settings
from hyper_demo.models import (
    DemoRun,
    OrderRequest,
    PortfolioMetrics,
    PositionSnapshot,
    ProposalRequest,
    ResearchRequest,
    RiskProfileInput,
    RunEvent,
    TradePlan,
)
from hyper_demo.services.market import MarketDataClient
from hyper_demo.services.metrics import compute_portfolio_metrics
from hyper_demo.services.monitoring import HyperliquidWebsocketMonitor
from hyper_demo.services.proposals import build_trade_plan
from hyper_demo.services.risk import build_investor_profile
from hyper_demo.storage import JsonStore

APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "static"
FIXTURE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

app = FastAPI(title="Hyperliquid Testnet Investment Agent Demo", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")


class SetupCheck(BaseModel):
    trading_mode: str
    require_confirmation: bool
    anthropic_configured: bool
    hyperliquid_configured: bool
    hyperliquid_base_url: str
    hyperliquid_ws_url: str
    warnings: list[str]


def get_store() -> JsonStore:
    return JsonStore(get_settings())


def setup_check(settings: Settings | None = None) -> SetupCheck:
    settings = settings or get_settings()
    warnings: list[str] = []
    if not settings.has_anthropic_credentials:
        warnings.append("ANTHROPIC_API_KEY is missing; research will use fallback output.")
    if not settings.has_hyperliquid_credentials:
        warnings.append("Hyperliquid testnet credentials are missing; execution is blocked.")
    if settings.demo_require_confirmation:
        warnings.append("Order confirmation is enabled, as required for the demo.")
    return SetupCheck(
        trading_mode=settings.demo_trading_mode,
        require_confirmation=settings.demo_require_confirmation,
        anthropic_configured=settings.has_anthropic_credentials,
        hyperliquid_configured=settings.has_hyperliquid_credentials,
        hyperliquid_base_url=settings.hyperliquid_base_url,
        hyperliquid_ws_url=settings.hyperliquid_ws_url,
        warnings=warnings,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/setup-check", response_model=SetupCheck)
def api_setup_check() -> SetupCheck:
    return setup_check()


@app.get("/api/state")
def api_state() -> dict[str, Any]:
    store = get_store()
    return {
        "profile": store.latest("profiles"),
        "research": store.latest("research"),
        "plan": store.latest("plans"),
        "order": store.latest("orders"),
        "run": store.latest("runs"),
        "setup": setup_check(),
    }


@app.post("/api/profile")
def create_profile(inputs: RiskProfileInput):
    profile = build_investor_profile(inputs)
    store = get_store()
    store.save("profiles", profile)
    return profile


@app.post("/api/research")
async def create_research(request: ResearchRequest):
    store = get_store()
    profile = (
        store.get("profiles", request.profile_id)
        if request.profile_id
        else store.latest("profiles")
    )
    client = ManagedAgentResearchClient(get_settings())
    report = await client.research(request.asset, profile)
    store.save("research", report)
    return report


@app.post("/api/proposals", response_model=TradePlan)
def create_proposal(request: ProposalRequest):
    store = get_store()
    profile = (
        store.get("profiles", request.profile_id)
        if request.profile_id
        else store.latest("profiles")
    )
    if not profile:
        profile = build_investor_profile(RiskProfileInput(asset_preference=request.asset))
        store.save("profiles", profile)
    research = (
        store.get("research", request.research_id)
        if request.research_id
        else store.latest("research")
    )
    plan = build_trade_plan(request, profile, research, MarketDataClient(get_settings()))
    store.save("plans", plan)
    return plan


@app.post("/api/orders/testnet")
def submit_testnet_order(request: OrderRequest):
    store = get_store()
    plan = store.get("plans", request.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    try:
        order = HyperliquidTestnetAdapter(get_settings()).execute_plan(plan, request.confirmed)
    except ExecutionBlocked as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.save("orders", order)
    run = DemoRun(
        profile_id=plan.profile_id,
        research_id=plan.research_id,
        plan_id=plan.id,
        order_id=order.id,
        status="executed",
    )
    store.save("runs", run)
    store.append_event(
        RunEvent(
            run_id=run.id,
            message="Submitted Hyperliquid testnet order set.",
            payload={"order_id": order.id, "plan_id": plan.id},
        )
    )
    return {"run": run, "order": order}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = get_store().get("runs", run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@app.get("/api/runs/{run_id}/events")
def get_run_events(run_id: str):
    return get_store().events_for_run(run_id)


@app.get("/api/portfolio/metrics", response_model=PortfolioMetrics)
def get_portfolio_metrics():
    store = get_store()
    plan = store.latest("plans")
    position = None
    if plan:
        current = MarketDataClient(get_settings()).mark_price(plan.asset).mark_price
        direction = 1 if plan.side.value == "long" else -1
        pnl = (current - plan.entry_price) / plan.entry_price * plan.size_usdc * direction
        position = PositionSnapshot(
            asset=plan.asset,
            side=plan.side,
            entry_price=plan.entry_price,
            mark_price=current,
            size_usdc=plan.size_usdc,
            unrealized_pnl_usdc=pnl,
            leverage=plan.leverage,
        )
    equity_curve = [10_000, 10_040, 10_015, 10_120, 10_090, 10_180]
    if position:
        equity_curve[-1] = equity_curve[-1] + position.unrealized_pnl_usdc
    return compute_portfolio_metrics(
        equity_curve=equity_curve,
        btc_benchmark=[100, 101.2, 100.4, 102.8, 101.9, 103.1],
        eth_benchmark=[100, 100.7, 99.8, 101.6, 101.1, 102.0],
        positions=[position] if position else [],
    )


@app.get("/api/market/{asset}/ws-sample")
async def sample_market_websocket(asset: str):
    price = await HyperliquidWebsocketMonitor(get_settings()).sample_mark_price(asset)
    return price


@app.post("/api/replay/{fixture_name}")
def replay_fixture(fixture_name: str):
    if not FIXTURE_NAME_PATTERN.fullmatch(fixture_name):
        raise HTTPException(status_code=400, detail="Invalid fixture name.")
    fixture_root = (Path(__file__).resolve().parents[2] / "fixtures").resolve()
    fixture_path = (fixture_root / f"{fixture_name}.json").resolve()
    if not fixture_path.is_relative_to(fixture_root):
        raise HTTPException(status_code=400, detail="Invalid fixture path.")
    if not fixture_path.exists():
        raise HTTPException(status_code=404, detail="Fixture not found.")
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    store = get_store()
    saved: dict[str, Any] = {}
    for collection, model_name in [
        ("profiles", "profile"),
        ("research", "research"),
        ("plans", "plan"),
        ("orders", "order"),
        ("runs", "run"),
    ]:
        if model_name in payload:
            model = JsonStore.collections[collection].model_validate(payload[model_name])
            saved[model_name] = store.save(collection, model)
    for event in payload.get("events", []):
        store.append_event(RunEvent.model_validate(event))
    return saved


@app.get("/", response_class=HTMLResponse)
@app.get("/profile", response_class=HTMLResponse)
@app.get("/research", response_class=HTMLResponse)
@app.get("/proposal", response_class=HTMLResponse)
@app.get("/execution", response_class=HTMLResponse)
@app.get("/monitor", response_class=HTMLResponse)
@app.get("/settings", response_class=HTMLResponse)
def spa() -> HTMLResponse:
    return HTMLResponse((STATIC_ROOT / "index.html").read_text(encoding="utf-8"))
