from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hyper_demo.adapters.hyperliquid import ExecutionBlocked, HyperliquidAdapter
from hyper_demo.adapters.privy_hyperliquid import PrivyHyperliquidAdapter
from hyper_demo.config import Settings, get_settings, settings_for_runtime
from hyper_demo.models import (
    Candle,
    ConnectedWallet,
    ManagedAgentOpportunity,
    OrderRecord,
    PortfolioMetrics,
    PositionSnapshot,
    RunEvent,
    RuntimeNetwork,
    RuntimeSettings,
    RuntimeSettingsUpdate,
    TradePlan,
    TradeSide,
    normalize_asset_symbol,
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
DEMO_ROOT = APP_ROOT.parents[1]
LIGHTWEIGHT_CHARTS_ROOT = DEMO_ROOT / "node_modules" / "lightweight-charts" / "dist"
ARBITRUM_RPC_URL = "https://arb1.arbitrum.io/rpc"
ARBITRUM_USDC_ADDRESS = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"

app = FastAPI(title="HyperClaude", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")
if LIGHTWEIGHT_CHARTS_ROOT.exists():
    app.mount(
        "/vendor/lightweight-charts",
        StaticFiles(directory=LIGHTWEIGHT_CHARTS_ROOT),
        name="lightweight-charts",
    )


class AgentAnalyzeRequest(BaseModel):
    asset: str
    context: str | None = None


class TradeExecutionRequest(BaseModel):
    confirmed: bool = False


class ManualTradePlanRequest(BaseModel):
    asset: str
    side: TradeSide
    size_usdc: float
    entry_type: Literal["market", "limit"] = "market"
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    leverage: float = 1.0


class MasterDepositRequest(BaseModel):
    amount_usdc: float
    confirmed: bool = False


class SetupCheck(BaseModel):
    trading_mode: str
    require_confirmation: bool
    anthropic_configured: bool
    hypertracker_configured: bool
    perplexity_configured: bool
    hyperliquid_configured: bool
    hyperliquid_base_url: str
    hyperliquid_ws_url: str
    hyperliquid_environment: str
    hyperliquid_mainnet_enabled: bool
    hyperliquid_max_order_usdc: float
    hyperliquid_allowed_assets: list[str]
    hyperliquid_account_address: str | None
    privy_configured: bool
    privy_server_configured: bool
    privy_execution_enabled: bool
    warnings: list[str]


class PrivyPublicConfig(BaseModel):
    app_id: str | None
    client_id: str | None
    configured: bool


class MarketAssetResponse(BaseModel):
    symbol: str
    max_leverage: int
    sz_decimals: int
    mark_price: float | None
    delisted: bool
    icon_url: str
    dex: str | None = None


class MarketCandlesResponse(BaseModel):
    asset: str
    interval: str
    candles: list[Candle]


class ConnectedWalletRequest(BaseModel):
    address: str
    user_id: str | None = None
    email: str | None = None
    wallet_id: str | None = None


class ArbitrumBalanceResponse(BaseModel):
    address: str
    eth: float
    usdc: float
    usdc_contract: str


def managed_agent_opportunities(
    runtime: RuntimeSettings,
    settings: Settings,
) -> list[ManagedAgentOpportunity]:
    assets = ", ".join(runtime.watchlist[:5]) or "the configured watchlist"
    network_label = "mainnet" if runtime.network == RuntimeNetwork.prodnet else "testnet"
    execution_gate = (
        "Require wallet confirmation, risk check, and explicit mainnet enablement."
        if runtime.network == RuntimeNetwork.prodnet
        else "Require demo confirmation before any testnet submission."
    )
    research_tools = ["Claude web search", "Claude web fetch", "Hyperliquid candles"]
    if settings.has_hypertracker_credentials:
        research_tools.append("HyperTracker positioning")
    return [
        ManagedAgentOpportunity(
            title="Autonomous market war room",
            horizon="now",
            owner_loop=(
                f"Continuously briefs {assets} across catalyst, positioning, "
                "and chart regimes."
            ),
            tools=research_tools,
            human_gate="Human approves which thesis becomes a trade plan.",
            value="Turns the demo from one-shot analysis into a living decision desk.",
            risk="May overweight fresh narratives unless source quality is scored.",
        ),
        ManagedAgentOpportunity(
            title="Risk sentinel for live positions",
            horizon="now",
            owner_loop=(
                "Watches stops, leverage, liquidation distance, funding, "
                f"and volatility on {network_label}."
            ),
            tools=["Hyperliquid positions", "candles", "runtime guardrails", "agent event stream"],
            human_gate="Human confirms any hedge, reduce-only exit, or stop adjustment.",
            value="Makes the agent useful after entry, where most trading UX becomes passive.",
            risk="False alarms can create unnecessary intervention pressure.",
        ),
        ManagedAgentOpportunity(
            title="Portfolio allocator",
            horizon="next",
            owner_loop="Ranks the allowed universe, budgets risk, and proposes capital rotation.",
            tools=["allowed assets", "portfolio metrics", "technical signals", "risk profile"],
            human_gate="Human approves capital allocation and per-asset max loss.",
            value="Moves from single-trade advice to portfolio construction.",
            risk="Correlation and liquidity estimates must stay conservative.",
        ),
        ManagedAgentOpportunity(
            title="Execution quality coach",
            horizon="next",
            owner_loop=(
                "Compares market versus limit entries, slippage, missed fills, "
                "and TP/SL placement."
            ),
            tools=["order history", "candles", "mark price", "agent rationale"],
            human_gate="Human approves any change to execution style or leverage.",
            value="Converts every proposed trade into a learning loop for better future plans.",
            risk="Requires enough historical fills to avoid anecdotal conclusions.",
        ),
        ManagedAgentOpportunity(
            title="Compliance and incident copilot",
            horizon="moonshot",
            owner_loop=(
                "Creates audit trails, explains blocked actions, and drafts "
                "incident summaries."
            ),
            tools=["agent events", "runtime settings", "wallet state", "order records"],
            human_gate="Human signs off on incident reports and production policy changes.",
            value="Makes guarded mainnet operation reviewable by non-engineering stakeholders.",
            risk="Must never hide uncertainty or rewrite historical events.",
        ),
        ManagedAgentOpportunity(
            title="Personal trading operating system",
            horizon="moonshot",
            owner_loop=(
                "Learns the user's rejected ideas, preferred setups, and "
                "recurring mistakes."
            ),
            tools=["rejected plans", "risk profile", "watchlist", "post-trade notes"],
            human_gate=execution_gate,
            value=(
                "Turns Claude Managed Agents into a persistent trading workflow, "
                "not a chat button."
            ),
            risk="Needs strict privacy boundaries and explicit memory controls.",
        ),
    ]


def get_store() -> JsonStore:
    return JsonStore(get_settings())


def get_runtime(store: JsonStore | None = None) -> RuntimeSettings:
    return (store or get_store()).runtime_settings()


def privy_agent_wallet_id(network: RuntimeNetwork) -> str:
    return f"privy_agent_wallet_{network.value}"


def _validate_evm_address(address: str) -> str:
    clean = address.removeprefix("0x").lower()
    if len(clean) != 40 or any(char not in "0123456789abcdef" for char in clean):
        raise ValueError("Wallet address is invalid.")
    return f"0x{clean}"


def _encode_balance_of(address: str) -> str:
    clean = _validate_evm_address(address).removeprefix("0x")
    return f"0x70a08231{clean.rjust(64, '0')}"


def _format_units(raw: str, decimals: int) -> float:
    value = int(raw or "0x0", 16)
    return value / float(10**decimals)


def _arbitrum_rpc(method: str, params: list[Any]) -> str:
    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
    ).encode()
    request = urllib.request.Request(
        ARBITRUM_RPC_URL,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "HyperClaude-demo"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = json.loads(response.read().decode())
    except (TimeoutError, urllib.error.URLError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Arbitrum RPC is unavailable.") from exc
    if body.get("error"):
        message = body["error"].get("message") or "Arbitrum RPC error."
        raise HTTPException(status_code=502, detail=message)
    return str(body.get("result") or "0x0")


def get_privy_agent_wallet(store: JsonStore, runtime: RuntimeSettings) -> Any:
    network_agent = store.get("privy_agent_wallet", privy_agent_wallet_id(runtime.network))
    if network_agent:
        return network_agent
    legacy_agent = store.get("privy_agent_wallet", "privy_agent_wallet")
    if legacy_agent and legacy_agent.network == runtime.network:
        return legacy_agent
    return None


def setup_check(settings: Settings | None = None) -> SetupCheck:
    settings = settings or get_settings()
    warnings: list[str] = []
    if not settings.has_anthropic_credentials:
        warnings.append("ANTHROPIC_API_KEY is missing; research will use fallback output.")
    if not settings.has_hypertracker_credentials:
        warnings.append("HYPERTRACKER_API_KEY is missing; market intelligence enrichment disabled.")
    if not settings.has_perplexity_credentials:
        warnings.append("PERPLEXITY_API_KEY is missing; finance_search enrichment disabled.")
    if not settings.has_hyperliquid_credentials and not (
        settings.privy_execution_enabled and settings.has_privy_server_credentials
    ):
        warnings.append("Hyperliquid credentials are missing; exchange execution is blocked.")
    if settings.is_mainnet_mode and not settings.hyperliquid_mainnet_enabled:
        warnings.append(
            "Mainnet selected for market data. Execution remains blocked until "
            "HYPERLIQUID_MAINNET_ENABLED=true."
        )
    if settings.is_mainnet_mode and not settings.demo_require_confirmation:
        warnings.append("Mainnet mode should keep DEMO_REQUIRE_CONFIRMATION=true.")
    if settings.demo_require_confirmation:
        warnings.append("Order confirmation is enabled, as required for the demo.")
    if settings.privy_execution_enabled and not settings.has_privy_server_credentials:
        warnings.append("Privy execution is enabled, but PRIVY_APP_SECRET is missing.")
    return SetupCheck(
        trading_mode=settings.demo_trading_mode,
        require_confirmation=settings.demo_require_confirmation,
        anthropic_configured=settings.has_anthropic_credentials,
        hypertracker_configured=settings.has_hypertracker_credentials,
        perplexity_configured=settings.has_perplexity_credentials,
        hyperliquid_configured=settings.has_hyperliquid_credentials,
        hyperliquid_base_url=settings.hyperliquid_base_url,
        hyperliquid_ws_url=settings.hyperliquid_ws_url,
        hyperliquid_environment=settings.hyperliquid_environment,
        hyperliquid_mainnet_enabled=settings.hyperliquid_mainnet_enabled,
        hyperliquid_max_order_usdc=settings.hyperliquid_max_order_usdc,
        hyperliquid_allowed_assets=sorted(settings.allowed_assets_set),
        hyperliquid_account_address=_mask_address(settings.hyperliquid_account_address),
        privy_configured=settings.has_privy_config,
        privy_server_configured=settings.has_privy_server_credentials,
        privy_execution_enabled=settings.privy_execution_enabled,
        warnings=warnings,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/setup-check", response_model=SetupCheck)
def api_setup_check() -> SetupCheck:
    store = get_store()
    runtime = get_runtime(store)
    return setup_check(settings_for_runtime(runtime))


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
        "analysis": store.latest("analysis"),
        "research": store.latest("research"),
        "plan": store.latest("plans"),
        "order": store.latest("orders"),
        "run": store.latest("runs"),
        "runtime": runtime,
        "events": store.events_for_run(AGENT_RUN_ID),
        "setup": setup,
        "connected_wallet": store.get("connected_wallet", "connected_wallet"),
        "privy_agent_wallet": get_privy_agent_wallet(store, runtime),
    }


@app.get("/api/privy/config", response_model=PrivyPublicConfig)
def get_privy_config() -> PrivyPublicConfig:
    settings = get_settings()
    return PrivyPublicConfig(
        app_id=settings.privy_app_id,
        client_id=settings.privy_client_id,
        configured=settings.has_privy_config,
    )


@app.get("/api/wallet/arbitrum-balance/{address}", response_model=ArbitrumBalanceResponse)
def get_arbitrum_wallet_balance(address: str) -> ArbitrumBalanceResponse:
    try:
        normalized_address = _validate_evm_address(address)
        usdc_call_data = _encode_balance_of(normalized_address)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    eth_raw = _arbitrum_rpc("eth_getBalance", [normalized_address, "latest"])
    usdc_raw = _arbitrum_rpc(
        "eth_call",
        [
            {
                "to": ARBITRUM_USDC_ADDRESS,
                "data": usdc_call_data,
            },
            "latest",
        ],
    )
    return ArbitrumBalanceResponse(
        address=normalized_address,
        eth=_format_units(eth_raw, 18),
        usdc=_format_units(usdc_raw, 6),
        usdc_contract=ARBITRUM_USDC_ADDRESS,
    )


@app.get("/api/markets/assets", response_model=list[MarketAssetResponse])
def get_market_assets() -> list[MarketAssetResponse]:
    store = get_store()
    runtime = get_runtime(store)
    try:
        settings = settings_for_runtime(runtime)
    except ValueError:
        settings = get_settings()
    assets = MarketDataClient(settings).available_assets()
    return [
        MarketAssetResponse(
            symbol=asset.symbol,
            max_leverage=asset.max_leverage,
            sz_decimals=asset.sz_decimals,
            mark_price=asset.mark_price,
            delisted=asset.delisted,
            icon_url=asset.icon_url,
            dex=asset.dex,
        )
        for asset in assets
    ]


@app.get("/api/market/{asset}/candles", response_model=MarketCandlesResponse)
def get_market_candles(asset: str, interval: str = "1h", limit: int = 120) -> MarketCandlesResponse:
    try:
        runtime = get_runtime()
        settings = settings_for_runtime(runtime)
        candles = MarketDataClient(settings).candles(asset, interval, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MarketCandlesResponse(
        asset=candles[-1].asset if candles else asset,
        interval=interval,
        candles=candles,
    )


@app.post("/api/wallet/connected", response_model=ConnectedWallet)
def save_connected_wallet(request: ConnectedWalletRequest) -> ConnectedWallet:
    store = get_store()
    wallet = store.save(
        "connected_wallet",
        ConnectedWallet(
            address=request.address,
            user_id=request.user_id,
            email=request.email,
            wallet_id=request.wallet_id,
        ),
    )
    store.append_event(
        RunEvent(
            run_id=AGENT_RUN_ID,
            message=f"Privy wallet connected: {_mask_address(wallet.address)}.",
            payload=wallet.model_dump(mode="json"),
        )
    )
    return wallet


@app.post("/api/privy/agent-wallet")
def setup_privy_agent_wallet():
    store = get_store()
    runtime = get_runtime(store)
    agent_id = privy_agent_wallet_id(runtime.network)
    current = store.get("privy_agent_wallet", agent_id)
    if current and current.network != runtime.network:
        current = None
    try:
        settings = settings_for_runtime(runtime)
        if runtime.network.value == "prodnet" and not settings.hyperliquid_mainnet_enabled:
            raise ExecutionBlocked(
                "Prodnet agent registration is disabled. Set "
                "HYPERLIQUID_MAINNET_ENABLED=true in demo/.env, restart the demo server, "
                "then retry Initialize prodnet agent. This guard prevents accidental "
                "mainnet approveAgent transactions."
            )
        agent = PrivyHyperliquidAdapter(settings).setup_agent_wallet(
            runtime.network,
            current,
        )
    except (ExecutionBlocked, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    agent.id = agent_id
    store.save("privy_agent_wallet", agent)
    store.append_event(
        RunEvent(
            run_id=AGENT_RUN_ID,
            message=f"Privy Hyperliquid agent wallet ready on {agent.network}.",
            payload=agent.model_dump(mode="json"),
        )
    )
    return agent


@app.post("/api/privy/deposit-master")
def deposit_privy_master(request: MasterDepositRequest) -> dict[str, Any]:
    store = get_store()
    runtime = get_runtime(store)
    agent = get_privy_agent_wallet(store, runtime)
    if not agent:
        raise HTTPException(status_code=400, detail="Initialize a Privy agent wallet first.")
    try:
        settings = settings_for_runtime(runtime)
        result = PrivyHyperliquidAdapter(settings).deposit_master_collateral(
            agent,
            amount_usdc=request.amount_usdc,
            confirmed=request.confirmed,
            confirmation_phrase=None,
        )
    except (ExecutionBlocked, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.append_event(
        RunEvent(
            run_id=AGENT_RUN_ID,
            message=(
                "Submitted Privy master wallet deposit to Hyperliquid "
                f"({request.amount_usdc:.2f} USDC)."
            ),
            payload=result,
        )
    )
    return result


@app.post("/api/settings/runtime", response_model=RuntimeSettings)
def update_runtime_settings(update: RuntimeSettingsUpdate) -> RuntimeSettings:
    store = get_store()
    current = get_runtime(store)
    payload = current.model_dump()
    for key, value in update.model_dump(exclude_none=True).items():
        payload[key] = value
    candidate = RuntimeSettings.model_validate(payload)
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
        "analysis": result.analysis,
        "plan": result.plan,
        "order_id": None,
        "run_id": None,
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
        "analysis": result.analysis,
        "plan": result.plan,
        "order_id": None,
        "run_id": None,
    }


@app.get("/api/agent/events")
def api_agent_events():
    return get_store().events_for_run(AGENT_RUN_ID)


@app.get("/api/agent/opportunities", response_model=list[ManagedAgentOpportunity])
def api_agent_opportunities() -> list[ManagedAgentOpportunity]:
    store = get_store()
    runtime = get_runtime(store)
    return managed_agent_opportunities(runtime, settings_for_runtime(runtime))


def _max_leverage_for_asset(asset: str, market: MarketDataClient) -> float:
    try:
        for item in market.available_assets():
            if normalize_asset_symbol(item.symbol) == asset and item.max_leverage > 0:
                return float(item.max_leverage)
    except Exception:
        return 10.0
    return 10.0


def _manual_max_loss(size_usdc: float, entry_price: float, stop_loss: float | None) -> float:
    if not stop_loss:
        return 0.0
    return round(abs(entry_price - stop_loss) / entry_price * size_usdc, 2)


@app.post("/api/trades/manual-plan", response_model=TradePlan)
def api_create_manual_trade_plan(request: ManualTradePlanRequest) -> TradePlan:
    store = get_store()
    runtime = get_runtime(store)
    settings = settings_for_runtime(runtime)
    market = MarketDataClient(settings)
    asset = normalize_asset_symbol(request.asset)
    if asset not in settings.allowed_assets_set:
        raise HTTPException(
            status_code=400,
            detail=f"{asset} is not in the runtime allowed assets.",
        )
    if request.size_usdc <= 0:
        raise HTTPException(status_code=400, detail="Order size must be greater than zero.")
    if request.size_usdc > runtime.max_order_usdc:
        raise HTTPException(status_code=400, detail="Order size exceeds the runtime max order.")
    max_leverage = min(10.0, _max_leverage_for_asset(asset, market))
    if request.leverage < 1 or request.leverage > max_leverage:
        raise HTTPException(
            status_code=400,
            detail=f"Leverage must be between 1x and {max_leverage:g}x for {asset}.",
        )
    if request.entry_type == "limit" and not request.entry_price:
        raise HTTPException(status_code=400, detail="Limit orders require an entry price.")
    entry_price = request.entry_price or market.mark_price(asset).mark_price
    try:
        plan = TradePlan(
            asset=asset,
            side=request.side,
            size_usdc=request.size_usdc,
            entry_type=request.entry_type,
            entry_price=entry_price,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            max_loss_usdc=_manual_max_loss(request.size_usdc, entry_price, request.stop_loss),
            leverage=request.leverage,
            rationale="Manual order created from user inputs.",
            invalidation_criteria=(
                ["User-defined stop loss reached."] if request.stop_loss else []
            ),
            confidence=0.0,
            thesis="Manual user-created order. No Claude proposal attached.",
            evidence=["User input"],
            source="manual",
            execution_decision="proposed",
            network=runtime.network,
            execution_message="Manual plan created. Execute is required to submit orders.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.save("plans", plan)
    store.append_event(
        RunEvent(
            run_id=AGENT_RUN_ID,
            message=f"Manual trade plan created for {asset}.",
            payload=plan.model_dump(mode="json"),
        )
    )
    return plan


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
            confirmation_phrase=None,
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
        settings = settings_for_runtime(runtime)
        if settings.privy_execution_enabled:
            store = get_store()
            agent = get_privy_agent_wallet(store, runtime)
            if not agent:
                raise ExecutionBlocked("Initialize a Privy Hyperliquid agent wallet first.")
            return PrivyHyperliquidAdapter(settings).wallet_state(agent)
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
