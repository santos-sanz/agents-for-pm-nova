from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hyper_demo.adapters.hyperliquid import ExecutionBlocked, HyperliquidAdapter
from hyper_demo.config import Settings, get_settings, settings_for_runtime
from hyper_demo.models import (
    OrderRecord,
    PortfolioMetrics,
    PositionSnapshot,
    RunEvent,
    RuntimeNetwork,
    RuntimeSettings,
    RuntimeSettingsUpdate,
    TradePlan,
)
from hyper_demo.services.market import MarketDataClient
from hyper_demo.services.metrics import compute_portfolio_metrics
from hyper_demo.services.monitoring import HyperliquidWebsocketMonitor
from hyper_demo.services.trading_agent import (
    AGENT_RUN_ID,
    analyze_trade,
    manual_execute_trade,
    reject_trade,
    run_proactive_scan,
)
from hyper_demo.storage import JsonStore

APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "static"

app = FastAPI(title="Hyperliquid Claude Trading Agent Demo", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")


class AgentAnalyzeRequest(BaseModel):
    asset: str
    context: str | None = None


class TradeExecutionRequest(BaseModel):
    confirmed: bool = False
    confirmation_phrase: str | None = None


class SetupCheck(BaseModel):
    trading_mode: str
    require_confirmation: bool
    anthropic_configured: bool
    hypertracker_configured: bool
    hyperliquid_configured: bool
    hyperliquid_base_url: str
    hyperliquid_ws_url: str
    hyperliquid_environment: str
    hyperliquid_mainnet_enabled: bool
    hyperliquid_max_order_usdc: float
    hyperliquid_allowed_assets: list[str]
    hyperliquid_account_address: str | None
    warnings: list[str]


def get_store() -> JsonStore:
    return JsonStore(get_settings())


def get_runtime(store: JsonStore | None = None) -> RuntimeSettings:
    return (store or get_store()).runtime_settings()


def setup_check(settings: Settings | None = None) -> SetupCheck:
    settings = settings or get_settings()
    warnings: list[str] = []
    if not settings.has_anthropic_credentials:
        warnings.append("ANTHROPIC_API_KEY is missing; research will use fallback output.")
    if not settings.has_hypertracker_credentials:
        warnings.append("HYPERTRACKER_API_KEY is missing; market intelligence enrichment disabled.")
    if not settings.has_hyperliquid_credentials:
        warnings.append("Hyperliquid credentials are missing; exchange execution is blocked.")
    if settings.is_mainnet_mode and not settings.hyperliquid_mainnet_enabled:
        warnings.append("Mainnet mode selected, but HYPERLIQUID_MAINNET_ENABLED is false.")
    if settings.is_mainnet_mode and not settings.demo_require_confirmation:
        warnings.append("Mainnet mode should keep DEMO_REQUIRE_CONFIRMATION=true.")
    if settings.demo_require_confirmation:
        warnings.append("Order confirmation is enabled, as required for the demo.")
    return SetupCheck(
        trading_mode=settings.demo_trading_mode,
        require_confirmation=settings.demo_require_confirmation,
        anthropic_configured=settings.has_anthropic_credentials,
        hypertracker_configured=settings.has_hypertracker_credentials,
        hyperliquid_configured=settings.has_hyperliquid_credentials,
        hyperliquid_base_url=settings.hyperliquid_base_url,
        hyperliquid_ws_url=settings.hyperliquid_ws_url,
        hyperliquid_environment=settings.hyperliquid_environment,
        hyperliquid_mainnet_enabled=settings.hyperliquid_mainnet_enabled,
        hyperliquid_max_order_usdc=settings.hyperliquid_max_order_usdc,
        hyperliquid_allowed_assets=sorted(settings.allowed_assets_set),
        hyperliquid_account_address=_mask_address(settings.hyperliquid_account_address),
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
    runtime = get_runtime(store)
    try:
        effective_settings = settings_for_runtime(runtime)
        setup = setup_check(effective_settings)
    except ValueError as exc:
        setup = setup_check()
        setup.warnings.append(str(exc))
    return {
        "profile": store.latest("profiles"),
        "research": store.latest("research"),
        "plan": store.latest("plans"),
        "order": store.latest("orders"),
        "run": store.latest("runs"),
        "runtime": runtime,
        "events": store.events_for_run(AGENT_RUN_ID),
        "setup": setup,
    }


@app.post("/api/settings/runtime", response_model=RuntimeSettings)
def update_runtime_settings(update: RuntimeSettingsUpdate) -> RuntimeSettings:
    store = get_store()
    current = get_runtime(store)
    payload = current.model_dump()
    for key, value in update.model_dump(exclude_none=True).items():
        payload[key] = value
    candidate = RuntimeSettings.model_validate(payload)
    if (
        candidate.network == RuntimeNetwork.prodnet
        and not get_settings().hyperliquid_mainnet_enabled
    ):
        raise HTTPException(
            status_code=400,
            detail="Prodnet requires HYPERLIQUID_MAINNET_ENABLED=true.",
        )
    settings_for_runtime(candidate)
    store.save("runtime", candidate)
    store.append_event(
        RunEvent(
            run_id=AGENT_RUN_ID,
            message=f"Runtime settings updated: {candidate.network}/{candidate.ui_mode}.",
            payload=candidate.model_dump(mode="json"),
        )
    )
    return candidate


@app.post("/api/agent/analyze")
async def api_agent_analyze(request: AgentAnalyzeRequest):
    store = get_store()
    runtime = get_runtime(store)
    try:
        result = await analyze_trade(request.asset, runtime, store, request.context)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "plan": result.plan,
        "order_id": result.order_id,
        "run_id": result.run_id,
    }


@app.post("/api/agent/proactive-scan")
async def api_proactive_scan():
    store = get_store()
    runtime = get_runtime(store)
    try:
        result = await run_proactive_scan(runtime, store)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "plan": result.plan,
        "order_id": result.order_id,
        "run_id": result.run_id,
    }


@app.get("/api/agent/events")
def api_agent_events():
    return get_store().events_for_run(AGENT_RUN_ID)


@app.post("/api/trades/{plan_id}/execute")
def api_execute_trade(plan_id: str, request: TradeExecutionRequest):
    store = get_store()
    runtime = get_runtime(store)
    plan = store.get("plans", plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    try:
        result = manual_execute_trade(
            plan,
            runtime,
            store,
            confirmed=request.confirmed,
            confirmation_phrase=request.confirmation_phrase,
        )
    except (ExecutionBlocked, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "plan": result.plan,
        "order_id": result.order_id,
        "run_id": result.run_id,
    }


@app.post("/api/trades/{plan_id}/reject", response_model=TradePlan)
def api_reject_trade(plan_id: str):
    store = get_store()
    plan = store.get("plans", plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    return reject_trade(plan, store)


@app.get("/api/wallet")
def get_wallet_state():
    runtime = get_runtime()
    try:
        return HyperliquidAdapter(settings_for_runtime(runtime)).wallet_state()
    except (ExecutionBlocked, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = get_store().get("runs", run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run


@app.get("/api/runs/{run_id}/events")
def get_run_events(run_id: str):
    return get_store().events_for_run(run_id)


def _position_from_latest_state(
    plan: TradePlan | None,
    order: OrderRecord | None,
    settings: Settings,
) -> PositionSnapshot | None:
    if not plan:
        return None
    entry_price = plan.entry_price
    size_usdc = plan.size_usdc
    current = MarketDataClient(settings).mark_price(plan.asset).mark_price
    direction = 1 if plan.side.value == "long" else -1
    pnl = (current - entry_price) / entry_price * size_usdc * direction
    return PositionSnapshot(
        asset=plan.asset,
        side=plan.side,
        entry_price=entry_price,
        mark_price=current,
        size_usdc=size_usdc,
        unrealized_pnl_usdc=pnl,
        leverage=plan.leverage,
    )


@app.get("/api/portfolio/metrics", response_model=PortfolioMetrics)
def get_portfolio_metrics():
    store = get_store()
    runtime = get_runtime(store)
    settings = settings_for_runtime(runtime)
    plan = store.latest("plans")
    position = _position_from_latest_state(plan, store.latest("orders"), settings)
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


@app.get("/", response_class=HTMLResponse)
def spa() -> HTMLResponse:
    return HTMLResponse((STATIC_ROOT / "index.html").read_text(encoding="utf-8"))


def _mask_address(address: str | None) -> str | None:
    if not address:
        return None
    if len(address) <= 12:
        return address
    return f"{address[:6]}...{address[-4:]}"
