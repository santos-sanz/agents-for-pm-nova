from __future__ import annotations

import asyncio
import json
import math
import urllib.error
import urllib.request
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hyper_demo.adapters.hyperliquid import ExecutionBlocked, HyperliquidAdapter
from hyper_demo.adapters.privy_hyperliquid import PrivyHyperliquidAdapter
from hyper_demo.config import Settings, get_settings, settings_for_runtime
from hyper_demo.models import (
    Candle,
    ConnectedWallet,
    ManagedAgentOpportunity,
    ManagedChatDeployment,
    ManagedChatEvent,
    ManagedChatResources,
    ManagedChatSession,
    OrderRecord,
    PortfolioMetrics,
    PositionSnapshot,
    ResearchReport,
    RiskProfileInput,
    RunEvent,
    RuntimeNetwork,
    RuntimeSettings,
    RuntimeSettingsUpdate,
    TradePlan,
    TradeSide,
    normalize_asset_symbol,
)
from hyper_demo.services.formal_validation import (
    FormalValidationResult,
    validate_formal_trade_plan,
)
from hyper_demo.services.hypertracker import HyperTrackerClient
from hyper_demo.services.managed_chat import ManagedTradingChatService
from hyper_demo.services.market import MarketDataClient
from hyper_demo.services.metrics import compute_portfolio_metrics
from hyper_demo.services.monitoring import HyperliquidWebsocketMonitor
from hyper_demo.services.perplexity import PerplexityFinanceClient
from hyper_demo.services.perplexity_mcp import PerplexityMcpServer
from hyper_demo.services.risk import build_investor_profile
from hyper_demo.services.technical_analysis import (
    build_agent_trade_analysis,
    trade_plan_from_candidate,
)
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
HYPERLIQUID_MIN_ORDER_USDC = 10

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
    risk_appetite: Literal["conservative", "balanced", "aggressive"] = "balanced"
    close_window: Literal["15m", "1h", "4h", "1d"] = "1h"
    available_usdc: float | None = None
    max_leverage: int | None = None


class TradingAutoChatRequest(BaseModel):
    asset: str
    risk_appetite: Literal["conservative", "balanced", "aggressive"]
    close_window: Literal["15m", "1h", "4h", "1d"]
    available_usdc: float | None = None
    max_leverage: int | None = None


class TradeExecutionRequest(BaseModel):
    confirmed: bool = False


class ClosePositionRequest(BaseModel):
    confirmed: bool = False


class PositionProtectionRequest(BaseModel):
    take_profit: float | None = None
    stop_loss: float | None = None
    remove_take_profit: bool = False
    remove_stop_loss: bool = False
    confirmed: bool = False


class ChatBootstrapRequest(BaseModel):
    force: bool = False


class ChatSessionCreateRequest(BaseModel):
    title: str | None = None


class ChatDeploymentCreateRequest(BaseModel):
    name: str | None = None
    cron_expression: str | None = None
    timezone: str | None = None
    initial_prompt: str | None = None


class ChatMessageRequest(BaseModel):
    message: str


class ChatOutcomeRequest(BaseModel):
    description: str
    rubric: str
    max_iterations: int | None = None


class ChatToolConfirmationRequest(BaseModel):
    tool_use_id: str
    allow: bool = False
    deny_message: str | None = None


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


class UserWalletTransferRequest(BaseModel):
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


def get_chat_service(store: JsonStore | None = None) -> ManagedTradingChatService:
    return ManagedTradingChatService(get_settings(), store or get_store())


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


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


def append_trade_error_event(
    store: JsonStore,
    message: str,
    payload: dict[str, Any] | None = None,
) -> None:
    store.append_event(
        RunEvent(
            run_id=AGENT_RUN_ID,
            level="warning",
            message=message,
            payload=payload or {},
        )
    )


def wallet_state_for_runtime(
    store: JsonStore,
    runtime: RuntimeSettings,
    settings: Settings,
) -> dict[str, Any]:
    if settings.privy_execution_enabled:
        agent = get_privy_agent_wallet(store, runtime)
        if not agent:
            raise ExecutionBlocked("Initialize a Privy Hyperliquid agent wallet first.")
        return PrivyHyperliquidAdapter(settings).wallet_state(agent)
    return HyperliquidAdapter(settings).wallet_state()


def validate_available_margin(
    store: JsonStore,
    runtime: RuntimeSettings,
    settings: Settings,
    request: ManualTradePlanRequest,
) -> dict[str, Any] | None:
    if not settings.privy_execution_enabled and not settings.has_hyperliquid_credentials:
        return None
    try:
        wallet = wallet_state_for_runtime(store, runtime, settings)
    except ExecutionBlocked as exc:
        append_trade_error_event(
            store,
            f"Wallet state unavailable before manual order: {exc}",
            {"asset": request.asset, "size_usdc": request.size_usdc},
        )
        raise
    withdrawable = float(wallet.get("withdrawable_usdc") or 0)
    margin_required = request.size_usdc / max(request.leverage, 1)
    if margin_required > withdrawable:
        message = (
            "Order margin exceeds wallet withdrawable balance "
            f"({margin_required:.2f} USDC required, {withdrawable:.2f} USDC available)."
        )
        append_trade_error_event(
            store,
            message,
            {
                "asset": request.asset,
                "size_usdc": request.size_usdc,
                "leverage": request.leverage,
                "margin_required_usdc": round(margin_required, 6),
                "withdrawable_usdc": withdrawable,
                "account_address": wallet.get("account_address"),
                "agent_address": wallet.get("agent_address"),
            },
        )
        raise HTTPException(status_code=400, detail=message)
    return wallet


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


@app.post("/mcp/perplexity", response_model=None)
async def perplexity_mcp(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Response:
    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Invalid JSON body."},
            },
            status_code=400,
        )
    body, status_code = PerplexityMcpServer().handle_http(payload, authorization)
    if body is None:
        return Response(status_code=status_code)
    return JSONResponse(body, status_code=status_code)


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
        "external_withdrawal_address": get_settings().privy_external_withdrawal_address,
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


@app.post("/api/privy/transfer-user-usdc-to-master")
def transfer_user_usdc_to_master(
    request: UserWalletTransferRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    store = get_store()
    runtime = get_runtime(store)
    agent = get_privy_agent_wallet(store, runtime)
    if not agent:
        raise HTTPException(status_code=400, detail="Initialize a Privy agent wallet first.")
    connected_wallet = store.get("connected_wallet", "connected_wallet")
    if not connected_wallet or not connected_wallet.wallet_id:
        raise HTTPException(
            status_code=400,
            detail="Connect a Privy wallet with a wallet_id first.",
        )
    user_jwt = _bearer_token(authorization)
    if not user_jwt:
        raise HTTPException(
            status_code=400,
            detail=(
                "Privy user authorization is required for a sponsored user wallet "
                "transfer. Log in with Privy again, then retry."
            ),
        )
    try:
        settings = settings_for_runtime(runtime)
        adapter = PrivyHyperliquidAdapter(settings)
        verification = adapter.verify_user_jwt(user_jwt)
        verified_user_id = verification.get("userId")
        if (
            connected_wallet.user_id
            and verified_user_id
            and connected_wallet.user_id != verified_user_id
        ):
            raise ExecutionBlocked("Privy session user does not match the connected wallet user.")
        result = adapter.transfer_user_usdc_to_master(
            source_wallet_id=connected_wallet.wallet_id,
            source_wallet_address=connected_wallet.address,
            agent=agent,
            amount_usdc=request.amount_usdc,
            confirmed=request.confirmed,
            user_jwt=user_jwt,
        )
    except (ExecutionBlocked, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.append_event(
        RunEvent(
            run_id=AGENT_RUN_ID,
            message=(
                "Submitted Privy user wallet USDC transfer to master wallet "
                f"({request.amount_usdc:.6f} USDC)."
            ),
            payload=result,
        )
    )
    return result


@app.post("/api/privy/transfer-user-usdc-to-master/preflight")
def preflight_user_wallet_transfer(
    request: UserWalletTransferRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    store = get_store()
    runtime = get_runtime(store)
    agent = get_privy_agent_wallet(store, runtime)
    if not agent:
        raise HTTPException(status_code=400, detail="Initialize a Privy agent wallet first.")
    connected_wallet = store.get("connected_wallet", "connected_wallet")
    if not connected_wallet or not connected_wallet.wallet_id:
        raise HTTPException(
            status_code=400,
            detail="Connect a Privy wallet with a wallet_id first.",
        )
    if request.amount_usdc <= 0:
        raise HTTPException(
            status_code=400,
            detail="USDC transfer amount must be greater than zero.",
        )
    user_jwt = _bearer_token(authorization)
    if not user_jwt:
        raise HTTPException(
            status_code=400,
            detail=(
                "Privy user authorization is required for a sponsored user wallet "
                "transfer. Log in with Privy again, then retry."
            ),
        )
    try:
        settings = settings_for_runtime(runtime)
        verification = PrivyHyperliquidAdapter(settings).verify_user_jwt(user_jwt)
    except (ExecutionBlocked, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    expected_user_id = connected_wallet.user_id
    verified_user_id = verification.get("userId")
    if expected_user_id and verified_user_id and expected_user_id != verified_user_id:
        raise HTTPException(
            status_code=400,
            detail="Privy session user does not match the connected wallet user.",
        )
    return {
        "ok": True,
        "source_wallet_id": connected_wallet.wallet_id,
        "source_wallet_address": connected_wallet.address,
        "master_wallet_address": agent.master_wallet_address,
        "amount_usdc": request.amount_usdc,
        "verified_user_id": verified_user_id,
        "token_expires_at": verification.get("expiresAt"),
    }


@app.post("/api/privy/transfer-user-usdc-to-external")
def transfer_user_usdc_to_external(
    request: UserWalletTransferRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    store = get_store()
    runtime = get_runtime(store)
    connected_wallet = store.get("connected_wallet", "connected_wallet")
    if not connected_wallet or not connected_wallet.wallet_id:
        raise HTTPException(
            status_code=400,
            detail="Connect a Privy wallet with a wallet_id first.",
        )
    user_jwt = _bearer_token(authorization)
    if not user_jwt:
        raise HTTPException(
            status_code=400,
            detail=(
                "Privy user authorization is required for a sponsored external "
                "wallet transfer. Log in with Privy again, then retry."
            ),
        )
    try:
        settings = settings_for_runtime(runtime)
        external_address = _validate_evm_address(settings.privy_external_withdrawal_address)
        adapter = PrivyHyperliquidAdapter(settings)
        verification = adapter.verify_user_jwt(user_jwt)
        verified_user_id = verification.get("userId")
        if (
            connected_wallet.user_id
            and verified_user_id
            and connected_wallet.user_id != verified_user_id
        ):
            raise ExecutionBlocked("Privy session user does not match the connected wallet user.")
        result = adapter.transfer_user_usdc_to_external(
            source_wallet_id=connected_wallet.wallet_id,
            source_wallet_address=connected_wallet.address,
            external_wallet_address=external_address,
            agent_network=runtime.network,
            amount_usdc=request.amount_usdc,
            confirmed=request.confirmed,
            user_jwt=user_jwt,
        )
    except (ExecutionBlocked, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.append_event(
        RunEvent(
            run_id=AGENT_RUN_ID,
            message=(
                "Submitted Privy user wallet USDC transfer to external wallet "
                f"({request.amount_usdc:.6f} USDC)."
            ),
            payload=result,
        )
    )
    return result


@app.post("/api/privy/transfer-user-usdc-to-external/preflight")
def preflight_external_wallet_transfer(
    request: UserWalletTransferRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    store = get_store()
    runtime = get_runtime(store)
    connected_wallet = store.get("connected_wallet", "connected_wallet")
    if not connected_wallet or not connected_wallet.wallet_id:
        raise HTTPException(
            status_code=400,
            detail="Connect a Privy wallet with a wallet_id first.",
        )
    if request.amount_usdc <= 0:
        raise HTTPException(
            status_code=400,
            detail="USDC transfer amount must be greater than zero.",
        )
    user_jwt = _bearer_token(authorization)
    if not user_jwt:
        raise HTTPException(
            status_code=400,
            detail=(
                "Privy user authorization is required for a sponsored external "
                "wallet transfer. Log in with Privy again, then retry."
            ),
        )
    try:
        settings = settings_for_runtime(runtime)
        external_address = _validate_evm_address(settings.privy_external_withdrawal_address)
        verification = PrivyHyperliquidAdapter(settings).verify_user_jwt(user_jwt)
    except (ExecutionBlocked, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    expected_user_id = connected_wallet.user_id
    verified_user_id = verification.get("userId")
    if expected_user_id and verified_user_id and expected_user_id != verified_user_id:
        raise HTTPException(
            status_code=400,
            detail="Privy session user does not match the connected wallet user.",
        )
    return {
        "ok": True,
        "source_wallet_id": connected_wallet.wallet_id,
        "source_wallet_address": connected_wallet.address,
        "external_wallet_address": external_address,
        "amount_usdc": request.amount_usdc,
        "verified_user_id": verified_user_id,
        "token_expires_at": verification.get("expiresAt"),
    }


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
    settings = settings_for_runtime(runtime)
    asset = normalize_asset_symbol(request.asset)
    market = MarketDataClient(settings)
    available_usdc = _available_usdc_for_agent_input(store, runtime, settings)
    if request.available_usdc is not None:
        available_usdc = max(0.0, min(available_usdc, request.available_usdc))
    max_leverage = int(min(10.0, _max_leverage_for_asset(asset, market)))
    if request.max_leverage is not None:
        max_leverage = int(max(1, min(max_leverage, request.max_leverage)))
    preference_context = (
        f"Auto mode preferences: risk appetite={request.risk_appetite}; "
        f"preferred close window={request.close_window}. "
        f"Available trading input={available_usdc:.2f} USDC; "
        f"{asset} max supported leverage={max_leverage}x. "
        "Return several executable proposals that respect Hyperliquid validation, "
        "integer leverage, minimum order value, available margin, max leverage, "
        "and TP/SL directionality."
    )
    context = "\n".join([item for item in [preference_context, request.context] if item])
    try:
        result = await analyze_trade(
            asset,
            runtime,
            store,
            context,
            risk_appetite=request.risk_appetite,
            close_window=request.close_window,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "analysis": result.analysis,
        "plan": result.plan,
        "order_id": None,
        "run_id": None,
    }


@app.post("/api/agent/chat-auto")
async def api_agent_chat_auto(request: TradingAutoChatRequest):
    store = get_store()
    runtime = get_runtime(store)
    settings = settings_for_runtime(runtime)
    asset = normalize_asset_symbol(request.asset)
    market = MarketDataClient(settings)
    available_usdc = _available_usdc_for_agent_input(store, runtime, settings)
    if request.available_usdc is not None:
        available_usdc = max(0.0, min(available_usdc, request.available_usdc))
    max_leverage = int(min(10.0, _max_leverage_for_asset(asset, market)))
    if request.max_leverage is not None:
        max_leverage = int(max(1, min(max_leverage, request.max_leverage)))
    service = get_chat_service(store)
    resources = service.resources()
    if resources.status != "ready" and settings.anthropic_chat_auto_bootstrap:
        resources = await service.bootstrap()
    if resources.status != "ready":
        raise HTTPException(
            status_code=400,
            detail=resources.disabled_reason or resources.error or "Managed Chat is not ready.",
        )
    session = await service.create_session(f"Trading Auto intraday - {asset}")
    prompt = _trading_auto_chat_prompt(
        asset=asset,
        runtime=runtime,
        risk_appetite=request.risk_appetite,
        close_window=request.close_window,
        available_usdc=available_usdc,
        max_leverage=max_leverage,
    )
    try:
        session = await asyncio.wait_for(
            service.send_message(
                session.id,
                prompt,
                tool_runner=run_chat_custom_tool,
            ),
            timeout=14,
        )
    except TimeoutError:
        pass
    events = service.events(session.id)
    plans = _plans_from_chat_events(events)
    if not plans:
        plans = _technical_auto_trade_plans(
            asset,
            runtime,
            store,
            settings,
            risk_appetite=request.risk_appetite,
            close_window=request.close_window,
            max_plans=5,
        )
    latest_plan = plans[-1] if plans else None
    return {
        "session": session,
        "events": events,
        "plans": plans,
        "plan": latest_plan,
        "analysis": None,
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


@app.post("/api/agent/proposals/{candidate_index}/approve")
def api_approve_agent_proposal(candidate_index: int):
    store = get_store()
    runtime = get_runtime(store)
    settings = settings_for_runtime(runtime)
    analysis = store.latest("analysis")
    if not analysis:
        raise HTTPException(
            status_code=404,
            detail="Run auto analysis before approving a proposal.",
        )
    if candidate_index < 0 or candidate_index >= len(analysis.candidates):
        raise HTTPException(status_code=404, detail="Proposal not found.")
    candidate = analysis.candidates[candidate_index]
    asset = normalize_asset_symbol(analysis.asset)
    market = MarketDataClient(settings)
    mark = market.mark_price(asset)
    mark_price = mark.mark_price
    if mark.source == "fallback":
        candles = analysis.candles_by_timeframe.get(candidate.timeframe) or []
        if candles:
            mark_price = candles[-1].close
    entry_price, stop_loss, take_profit = _live_proposal_prices(
        candidate,
        mark_price=mark_price,
    )
    leverage = float(int(candidate.leverage))
    plan_stop_loss = stop_loss if leverage >= 10 else None
    request = ManualTradePlanRequest(
        asset=asset,
        side=candidate.side,
        entry_type=candidate.entry_type,
        entry_price=entry_price,
        size_usdc=candidate.size_usdc,
        stop_loss=plan_stop_loss,
        take_profit=take_profit,
        leverage=leverage,
    )
    if request.size_usdc < HYPERLIQUID_MIN_ORDER_USDC:
        raise HTTPException(
            status_code=400,
            detail="Proposal is below the 10 USDC minimum order value.",
        )
    if request.size_usdc > runtime.max_order_usdc:
        raise HTTPException(status_code=400, detail="Proposal is above the runtime max order.")
    max_leverage = int(min(10.0, _max_leverage_for_asset(asset, market)))
    if request.leverage < 1 or request.leverage > max_leverage:
        raise HTTPException(
            status_code=400,
            detail=f"Proposal leverage must be between 1x and {max_leverage:g}x for {asset}.",
        )
    try:
        validate_available_margin(store, runtime, settings, request)
    except ExecutionBlocked as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    preflight_error = _manual_preflight_error(
        request,
        entry_price=entry_price,
        mark_price=mark_price,
    )
    if preflight_error:
        raise HTTPException(status_code=400, detail=preflight_error)
    updated_candidate = candidate.model_copy(
        update={
            "entry_price": entry_price,
            "stop_loss": plan_stop_loss or stop_loss,
            "take_profit": take_profit,
            "max_loss_usdc": _manual_max_loss(candidate.size_usdc, entry_price, plan_stop_loss),
        }
    )
    rationale = candidate.rationale
    if plan_stop_loss is None:
        rationale = (
            f"{rationale} No stop-loss is attached because leverage is below 10x; "
            "use active monitoring, thesis invalidation, and take-profit for the intraday exit."
        )
    plan = TradePlan(
        asset=asset,
        side=candidate.side,
        size_usdc=candidate.size_usdc,
        entry_type=candidate.entry_type,
        entry_price=entry_price,
        stop_loss=plan_stop_loss,
        take_profit=take_profit,
        max_loss_usdc=_manual_max_loss(candidate.size_usdc, entry_price, plan_stop_loss),
        leverage=request.leverage,
        rationale=rationale,
        invalidation_criteria=[
            "The selected timeframe flips direction against the approved proposal.",
            "Stop-loss or take-profit placement can no longer be verified before execution.",
        ],
        confidence=candidate.confidence,
        thesis=analysis.thesis,
        evidence=[analysis.summary],
        source="agent",
        execution_decision="proposed",
        network=runtime.network,
        execution_message="Auto proposal approved. Submit is required to place the order.",
    )
    store.save("plans", plan)
    analysis.plan_id = plan.id
    analysis.candidates[candidate_index] = updated_candidate
    analysis.best_candidate = updated_candidate
    store.save("analysis", analysis)
    store.append_event(
        RunEvent(
            run_id=AGENT_RUN_ID,
            message=f"Auto proposal approved for {asset}.",
            payload={
                "plan_id": plan.id,
                "candidate_index": candidate_index,
                "side": candidate.side,
                "timeframe": candidate.timeframe,
            },
        )
    )
    return {"plan": plan, "analysis": analysis}


@app.get("/api/agent/events")
def api_agent_events():
    return get_store().events_for_run(AGENT_RUN_ID)


@app.get("/api/agent/opportunities", response_model=list[ManagedAgentOpportunity])
def api_agent_opportunities() -> list[ManagedAgentOpportunity]:
    store = get_store()
    runtime = get_runtime(store)
    return managed_agent_opportunities(runtime, settings_for_runtime(runtime))


@app.post("/api/chat/bootstrap", response_model=ManagedChatResources)
async def api_chat_bootstrap(
    request: ChatBootstrapRequest | None = None,
) -> ManagedChatResources:
    request = request or ChatBootstrapRequest()
    return await get_chat_service().bootstrap(force=request.force)


@app.get("/api/chat/state")
async def api_chat_state() -> dict[str, Any]:
    store = get_store()
    settings = get_settings()
    service = get_chat_service(store)
    persisted_resources = store.get("managed_chat_resources", "managed_chat_resources")
    resources = persisted_resources or service.resources()
    if (
        settings.anthropic_chat_auto_bootstrap
        and settings.has_anthropic_credentials
        and resources.status != "ready"
        and (
            persisted_resources is None
            or resources.disabled_reason == "Managed Agents resources have not been bootstrapped."
        )
    ):
        await service.bootstrap(force=False)
    return service.state()


@app.post("/api/chat/sessions", response_model=ManagedChatSession)
async def api_chat_create_session(
    request: ChatSessionCreateRequest | None = None,
) -> ManagedChatSession:
    request = request or ChatSessionCreateRequest()
    return await get_chat_service().create_session(request.title)


@app.post("/api/chat/deployment", response_model=ManagedChatDeployment)
async def api_chat_create_deployment(
    request: ChatDeploymentCreateRequest | None = None,
) -> ManagedChatDeployment:
    request = request or ChatDeploymentCreateRequest()
    try:
        return await get_chat_service().create_deployment(
            name=request.name,
            cron_expression=request.cron_expression,
            timezone=request.timezone,
            initial_prompt=request.initial_prompt,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/chat/deployment/run", response_model=ManagedChatDeployment)
async def api_chat_run_deployment() -> ManagedChatDeployment:
    return await get_chat_service().run_deployment()


@app.get("/api/chat/sessions", response_model=list[ManagedChatSession])
def api_chat_sessions() -> list[ManagedChatSession]:
    return sorted(
        get_store().list("managed_chat_sessions"),
        key=lambda item: item.created_at,
        reverse=True,
    )


@app.get("/api/chat/sessions/{session_id}")
def api_chat_session(session_id: str) -> dict[str, Any]:
    store = get_store()
    session = store.get("managed_chat_sessions", session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return {
        "session": session,
        "events": get_chat_service(store).events(session_id),
    }


@app.post("/api/chat/sessions/{session_id}/messages", response_model=ManagedChatSession)
async def api_chat_send_message(
    session_id: str,
    request: ChatMessageRequest,
) -> ManagedChatSession:
    try:
        return await get_chat_service().send_message(
            session_id,
            request.message,
            tool_runner=run_chat_custom_tool,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/chat/sessions/{session_id}/events", response_model=list[ManagedChatEvent])
def api_chat_events(session_id: str) -> list[ManagedChatEvent]:
    try:
        return get_chat_service().events(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/chat/sessions/{session_id}/outcomes", response_model=ManagedChatSession)
async def api_chat_define_outcome(
    session_id: str,
    request: ChatOutcomeRequest,
) -> ManagedChatSession:
    try:
        return await get_chat_service().define_outcome(
            session_id,
            request.description,
            request.rubric,
            request.max_iterations,
            tool_runner=run_chat_custom_tool,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/chat/sessions/{session_id}/tool-confirmations", response_model=ManagedChatSession)
async def api_chat_confirm_tool(
    session_id: str,
    request: ChatToolConfirmationRequest,
) -> ManagedChatSession:
    try:
        return await get_chat_service().confirm_tool(
            session_id,
            request.tool_use_id,
            request.allow,
            request.deny_message,
            tool_runner=run_chat_custom_tool,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/chat/sessions/{session_id}/interrupt", response_model=ManagedChatSession)
def api_chat_interrupt(session_id: str) -> ManagedChatSession:
    try:
        return get_chat_service().interrupt(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/chat/sessions/{session_id}/archive", response_model=ManagedChatSession)
def api_chat_archive(session_id: str) -> ManagedChatSession:
    try:
        return get_chat_service().archive(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _max_leverage_for_asset(asset: str, market: MarketDataClient) -> float:
    try:
        for item in market.available_assets():
            if normalize_asset_symbol(item.symbol) == asset and item.max_leverage > 0:
                return float(int(item.max_leverage))
    except Exception:
        return 10.0
    return 10.0


def _available_usdc_for_agent_input(
    store: JsonStore,
    runtime: RuntimeSettings,
    settings: Settings,
) -> float:
    if not settings.privy_execution_enabled and not settings.has_hyperliquid_credentials:
        return float(runtime.max_order_usdc)
    try:
        wallet = wallet_state_for_runtime(store, runtime, settings)
    except ExecutionBlocked:
        return float(runtime.max_order_usdc)
    withdrawable = wallet.get("withdrawable_usdc")
    try:
        available = float(withdrawable)
    except (TypeError, ValueError):
        return float(runtime.max_order_usdc)
    return max(0.0, min(float(runtime.max_order_usdc), available))


def run_chat_custom_tool(session: ManagedChatSession, event: dict[str, Any]) -> dict[str, Any]:
    name = str(event.get("name") or "")
    payload = event.get("input")
    if payload is None:
        payload = event.get("arguments")
    if not isinstance(payload, dict):
        payload = {}
    store = get_store()
    runtime = get_runtime(store)
    settings = settings_for_runtime(runtime)

    if name == "trading_market_snapshot":
        return _chat_market_snapshot(store, runtime, settings, payload)
    if name == "trading_create_plan":
        plan = api_create_manual_trade_plan(ManualTradePlanRequest.model_validate(payload))
        return {"plan": plan.model_dump(mode="json")}
    if name == "trading_validate_plan":
        plan = _chat_plan_or_blocked(store, str(payload.get("plan_id") or ""))
        return {"validation": _formal_validation_for_plan(store, runtime, settings, plan).as_dict()}
    if name == "trading_execute_plan":
        plan = _chat_plan_or_blocked(store, str(payload.get("plan_id") or ""))
        validation = _formal_validation_for_plan(store, runtime, settings, plan)
        if not validation.valid:
            raise ExecutionBlocked(
                "Formal validation failed: " + "; ".join(validation.errors)
            )
        _require_chat_trade_action_approval(runtime, event)
        if not bool(payload.get("confirmed")):
            raise ExecutionBlocked("Tool execution requires confirmed=true.")
        result = api_execute_trade(
            plan.id,
            TradeExecutionRequest(confirmed=True),
        )
        return _json_safe(result)
    if name == "trading_close_position":
        _require_chat_trade_action_approval(runtime, event)
        if not bool(payload.get("confirmed")):
            raise ExecutionBlocked("Position close requires confirmed=true.")
        return _json_safe(
            close_position(
                str(payload.get("asset") or ""),
                ClosePositionRequest(confirmed=True),
            )
        )
    if name == "trading_set_protection":
        _require_chat_trade_action_approval(runtime, event)
        if not bool(payload.get("confirmed")):
            raise ExecutionBlocked("TP/SL update requires confirmed=true.")
        return _json_safe(
            set_position_protection(
                str(payload.get("asset") or ""),
                PositionProtectionRequest(
                    confirmed=True,
                    take_profit=payload.get("take_profit"),
                    stop_loss=payload.get("stop_loss"),
                ),
            )
        )
    if name == "trading_hypertracker_intelligence":
        intelligence = HyperTrackerClient(settings).intelligence_for_asset(
            str(payload.get("asset") or "BTC")
        )
        return intelligence.__dict__
    if name == "trading_perplexity_context":
        context = PerplexityFinanceClient(settings).context_for_asset(
            str(payload.get("asset") or "BTC")
        )
        return context.__dict__
    if name == "trading_runtime_get_settings":
        return {
            "runtime": runtime.model_dump(mode="json"),
            "setup": setup_check(settings).model_dump(mode="json"),
        }
    if name == "trading_runtime_update_settings":
        update = RuntimeSettingsUpdate.model_validate(
            {
                key: value
                for key, value in payload.items()
                if key
                in {
                    "network",
                    "ui_mode",
                    "execution_policy",
                    "max_order_usdc",
                    "allowed_assets",
                    "watchlist",
                    "sync_asset_lists",
                }
            }
        )
        updated = update_runtime_settings(update)
        return {"runtime": updated.model_dump(mode="json")}
    if name in {"trading_skill_proposal", "trading_tool_proposal", "trading_memory_note"}:
        service = get_chat_service(store)
        service.append_event(
            session.id,
            name,
            str(payload.get("title") or payload.get("name") or payload.get("note") or name),
            role="agent",
            payload=payload,
        )
        return {"recorded": True, "proposal": _json_safe(payload)}
    raise ExecutionBlocked(f"Unknown or disabled custom tool: {name}.")


def _require_chat_trade_action_approval(
    runtime: RuntimeSettings,
    event: dict[str, Any],
) -> None:
    if runtime.network != RuntimeNetwork.prodnet:
        return
    if bool(event.get("host_human_approved")):
        return
    raise ExecutionBlocked(
        "Prodnet trade actions require explicit host human approval."
    )


def _chat_plan_or_blocked(store: JsonStore, plan_id: str) -> TradePlan:
    plan = store.get("plans", plan_id)
    if not plan:
        raise ExecutionBlocked("Stored trade plan was not found.")
    return plan


def _formal_validation_for_plan(
    store: JsonStore,
    runtime: RuntimeSettings,
    settings: Settings,
    plan: TradePlan,
) -> FormalValidationResult:
    market = MarketDataClient(settings)
    mark_price: float | None = None
    max_leverage = 10.0
    try:
        mark = market.mark_price(plan.asset)
        mark_price = mark.mark_price
    except Exception:
        mark_price = None
    try:
        max_leverage = float(int(min(10.0, _max_leverage_for_asset(plan.asset, market))))
    except Exception:
        max_leverage = 10.0
    wallet: dict[str, Any] | None = None
    try:
        wallet = wallet_state_for_runtime(store, runtime, settings)
    except (ExecutionBlocked, ValueError):
        wallet = None
    return validate_formal_trade_plan(
        plan,
        runtime=runtime,
        allowed_assets=settings.allowed_assets_set,
        wallet=wallet,
        mark_price=mark_price,
        max_leverage=max_leverage,
        minimum_order_usdc=HYPERLIQUID_MIN_ORDER_USDC,
    )


def _chat_market_snapshot(
    store: JsonStore,
    runtime: RuntimeSettings,
    settings: Settings,
    payload: dict[str, Any],
) -> dict[str, Any]:
    default_asset = runtime.watchlist[0] if runtime.watchlist else "BTC"
    asset = normalize_asset_symbol(str(payload.get("asset") or default_asset))
    interval = str(payload.get("interval") or "1h")
    snapshot: dict[str, Any] = {
        "runtime": runtime.model_dump(mode="json"),
        "setup": setup_check(settings).model_dump(mode="json"),
        "asset": asset,
    }
    try:
        snapshot["wallet"] = _public_wallet_snapshot(
            wallet_state_for_runtime(store, runtime, settings)
        )
    except (ExecutionBlocked, ValueError) as exc:
        snapshot["wallet_error"] = str(exc)
    try:
        snapshot["orders"] = _json_safe(get_orders_state())
    except Exception as exc:
        snapshot["orders_error"] = str(exc)
    try:
        snapshot["portfolio_metrics"] = get_portfolio_metrics().model_dump(mode="json")
    except Exception as exc:
        snapshot["portfolio_error"] = str(exc)
    try:
        market = MarketDataClient(settings)
        snapshot["mark_price"] = _json_safe(market.mark_price(asset))
        snapshot["candles"] = [
            candle.model_dump(mode="json") for candle in market.candles(asset, interval, limit=80)
        ]
    except Exception as exc:
        snapshot["market_error"] = str(exc)
    return snapshot


def _public_wallet_snapshot(wallet: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_address": _mask_address(wallet.get("account_address")),
        "agent_address": _mask_address(wallet.get("agent_address")),
        "withdrawable_usdc": wallet.get("withdrawable_usdc"),
        "total_margin_used_usdc": wallet.get("total_margin_used_usdc"),
        "open_positions": wallet.get("open_positions") or [],
        "open_orders": wallet.get("open_orders") or [],
    }


def _json_safe(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {
            key: _json_safe(item)
            for key, item in value.items()
            if "secret" not in key.lower()
            and "private" not in key.lower()
            and "api_key" not in key.lower()
            and key.lower() not in {"token", "authorization", "cookie"}
        }
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _technical_auto_trade_plans(
    asset: str,
    runtime: RuntimeSettings,
    store: JsonStore,
    settings: Settings,
    *,
    risk_appetite: str,
    close_window: str,
    max_plans: int = 5,
) -> list[dict[str, Any]]:
    profile = build_investor_profile(
        RiskProfileInput(
            asset_preference=asset,
            capital_at_risk_usdc=max(HYPERLIQUID_MIN_ORDER_USDC, runtime.max_order_usdc),
            stop_loss_pct=4.0,
        )
    )
    report = ResearchReport(
        asset=asset,
        profile_id=profile.id,
        thesis=(
            "Fast Trading Auto fallback: local market structure generated reviewable "
            "intraday trade plans while the Managed Agent session continues separately."
        ),
        evidence=[
            (
                "Runtime wallet, allowed assets, current marks, and local timeframe "
                "candles were loaded."
            ),
            "Plans are stored for human review; no exchange order is submitted by generation.",
        ],
        risks=[
            "Intraday signals can reverse quickly.",
            "Open positions and available margin must be reviewed before execution.",
        ],
        assumptions=[
            f"Risk appetite: {risk_appetite}.",
            f"Preferred close window: {close_window}.",
        ],
        why_not_invest=[
            "Momentum flips against the selected timeframe.",
            "Available margin falls below the order requirement before approval.",
            "Take-profit cannot be validated against the current mark.",
        ],
        sources=["local-market-structure"],
        fallback_used=True,
    )
    store.save("profiles", profile)
    store.save("research", report)
    market = MarketDataClient(settings)
    analysis = build_agent_trade_analysis(
        asset,
        runtime,
        profile,
        report,
        market,
        risk_appetite=risk_appetite,
        close_window=close_window,
    )
    plans: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, float]] = set()
    available_usdc = _available_usdc_for_agent_input(store, runtime, settings)
    market_max_leverage = int(min(10.0, _max_leverage_for_asset(asset, market)))
    if available_usdc <= 0:
        max_viable_notional = 0.0
    else:
        max_viable_notional = math.floor(available_usdc * market_max_leverage * 95) / 100
    for candidate in analysis.candidates:
        if len(plans) >= max_plans:
            break
        if max_viable_notional < HYPERLIQUID_MIN_ORDER_USDC:
            break
        key = (
            candidate.side.value,
            candidate.entry_type,
            candidate.timeframe,
            candidate.entry_price,
        )
        if key in seen:
            continue
        seen.add(key)
        try:
            plan = trade_plan_from_candidate(asset, profile, report, runtime, candidate)
        except ValueError:
            continue
        leverage = max(
            int(candidate.leverage),
            math.ceil(HYPERLIQUID_MIN_ORDER_USDC / max(available_usdc, 0.01)),
        )
        leverage = max(1, min(market_max_leverage, leverage))
        size_usdc = min(runtime.max_order_usdc, math.floor(available_usdc * leverage * 95) / 100)
        if size_usdc < HYPERLIQUID_MIN_ORDER_USDC:
            continue
        stop_loss = plan.stop_loss if leverage >= 10 else None
        rationale = plan.rationale
        if stop_loss is None and plan.stop_loss is not None:
            rationale = (
                f"{candidate.rationale} No stop-loss is attached because leverage is below 10x; "
                "use active monitoring, thesis invalidation, and take-profit for the intraday exit."
            )
        plan = plan.model_copy(
            update={
                "size_usdc": round(size_usdc, 2),
                "leverage": float(leverage),
                "stop_loss": stop_loss,
                "max_loss_usdc": _manual_max_loss(size_usdc, plan.entry_price, stop_loss),
                "rationale": rationale,
            }
        )
        plan.execution_message = (
            "Auto plan ready for review. Approve & place is required to submit."
        )
        store.save("plans", plan)
        plans.append(plan.model_dump(mode="json"))
    if plans:
        analysis.plan_id = plans[0]["id"]
    store.save("analysis", analysis)
    store.append_event(
        RunEvent(
            run_id=AGENT_RUN_ID,
            message=f"Trading Auto created {len(plans)} reviewable plan(s) for {asset}.",
            payload={
                "asset": asset,
                "risk_appetite": risk_appetite,
                "close_window": close_window,
                "plan_ids": [plan["id"] for plan in plans],
            },
        )
    )
    return plans


def _trading_auto_chat_prompt(
    *,
    asset: str,
    runtime: RuntimeSettings,
    risk_appetite: str,
    close_window: str,
    available_usdc: float,
    max_leverage: int,
) -> str:
    allowed_assets = ", ".join(runtime.allowed_assets or [])
    watchlist = ", ".join(runtime.watchlist or runtime.allowed_assets or [])
    return "\n".join(
        [
            "Trading Auto mode request.",
            "",
            "Use the same Managed Agents workflow as Chat, but focus on several intraday "
            "leveraged trade proposals for the Trading screen.",
            "",
            f"Primary chart asset: {asset}.",
            f"Runtime network: {runtime.network}.",
            f"Runtime UI mode: {runtime.ui_mode}.",
            f"Allowed assets: {allowed_assets or 'none configured'}.",
            f"Watchlist: {watchlist or 'none configured'}.",
            f"Risk appetite: {risk_appetite}.",
            f"Preferred close window: {close_window}.",
            f"Available trading input: {available_usdc:.2f} USDC.",
            f"Runtime max order: {runtime.max_order_usdc:.2f} USDC.",
            f"{asset} max supported leverage: {max_leverage}x.",
            "",
            "Required workflow:",
            "- Call trading_market_snapshot before proposing anything.",
            "- Use current wallet, open positions, protection orders, allowed assets, and marks.",
            "- Propose several intraday trades that are intended to close within minutes or hours.",
            "- Prefer assets from the allowed list and include at least the primary chart asset "
            "when it makes sense.",
            "- For each proposal include asset, side, entry type, entry price or market-entry "
            "assumption, notional size, leverage, take profit, stop loss policy, validation "
            "assumptions, monitoring cadence, and rationale.",
            "- For trades below 10x leverage, do not attach stop loss by default; use take "
            "profit, active monitoring, and explicit thesis invalidation unless a hard stop is "
            "clearly justified.",
            "- Create stored trade plans only for proposals that are formally coherent and likely "
            "to pass validation. Do not execute any trade from this Auto request.",
            "- End with a compact ranked list and say which plan, if any, should be reviewed next.",
        ]
    )


def _plans_from_chat_events(events: list[ManagedChatEvent]) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events:
        result = event.payload.get("result") if isinstance(event.payload, dict) else None
        if not isinstance(result, dict):
            continue
        plan = result.get("plan")
        if not isinstance(plan, dict):
            continue
        plan_id = str(plan.get("id") or "")
        if plan_id and plan_id in seen:
            continue
        if plan_id:
            seen.add(plan_id)
        plans.append(plan)
    return plans


def _live_proposal_prices(
    candidate: Any,
    *,
    mark_price: float,
) -> tuple[float, float | None, float | None]:
    entry_price = float(candidate.entry_price)
    stop_loss = candidate.stop_loss
    take_profit = candidate.take_profit
    if candidate.entry_type != "market":
        return entry_price, stop_loss, take_profit

    live_entry = float(mark_price)
    if entry_price <= 0 or live_entry <= 0:
        return live_entry, stop_loss, take_profit

    stop_distance = (
        abs(entry_price - float(stop_loss)) / entry_price if stop_loss is not None else None
    )
    take_distance = (
        abs(float(take_profit) - entry_price) / entry_price if take_profit is not None else None
    )
    if candidate.side == TradeSide.short:
        live_stop = live_entry * (1 + stop_distance) if stop_distance is not None else None
        live_take = live_entry * (1 - take_distance) if take_distance is not None else None
    else:
        live_stop = live_entry * (1 - stop_distance) if stop_distance is not None else None
        live_take = live_entry * (1 + take_distance) if take_distance is not None else None
    return (
        round(live_entry, 6),
        round(live_stop, 6) if live_stop is not None else None,
        round(live_take, 6) if live_take is not None else None,
    )


def _manual_max_loss(size_usdc: float, entry_price: float, stop_loss: float | None) -> float:
    if not stop_loss:
        return 0.0
    return round(abs(entry_price - stop_loss) / entry_price * size_usdc, 2)


def _estimated_liquidation_price(
    side: TradeSide,
    entry_price: float,
    leverage: float,
) -> float | None:
    if entry_price <= 0 or leverage <= 1:
        return None
    move = 1 / leverage
    price = entry_price * (1 + move) if side == TradeSide.short else entry_price * (1 - move)
    return max(0.0, price)


def _manual_preflight_error(
    request: ManualTradePlanRequest,
    *,
    entry_price: float,
    mark_price: float,
) -> str | None:
    if request.stop_loss is None and request.take_profit is None:
        return None
    side = request.side
    liquidation_price = _estimated_liquidation_price(side, entry_price, request.leverage)
    if side == TradeSide.long:
        if request.take_profit is not None and (
            request.take_profit <= entry_price or request.take_profit <= mark_price
        ):
            return (
                "Take Profit would be invalid for this Long. Set Take Profit above both "
                "the entry price and the current mark price."
            )
        if request.stop_loss is not None and (
            request.stop_loss >= entry_price or request.stop_loss >= mark_price
        ):
            return (
                "Stop Loss would be invalid for this Long. Set Stop Loss below both "
                "the entry price and the current mark price."
            )
        if (
            request.stop_loss is not None
            and liquidation_price is not None
            and request.stop_loss <= liquidation_price
        ):
            return (
                "Stop Loss is beyond the estimated liquidation price for this Long. "
                f"Move Stop Loss above {liquidation_price:g} before submitting."
            )
    if side == TradeSide.short:
        if request.take_profit is not None and (
            request.take_profit >= entry_price or request.take_profit >= mark_price
        ):
            return (
                "Take Profit would be invalid for this Short. Set Take Profit below both "
                "the entry price and the current mark price."
            )
        if request.stop_loss is not None and (
            request.stop_loss <= entry_price or request.stop_loss <= mark_price
        ):
            return (
                "Stop Loss would be invalid for this Short. Set Stop Loss above both "
                "the entry price and the current mark price."
            )
        if (
            request.stop_loss is not None
            and liquidation_price is not None
            and request.stop_loss >= liquidation_price
        ):
            return (
                "Stop Loss is beyond the estimated liquidation price for this Short. "
                f"Move Stop Loss below {liquidation_price:g} before submitting."
            )
    return None


@app.post("/api/trades/manual-plan", response_model=TradePlan)
def api_create_manual_trade_plan(request: ManualTradePlanRequest) -> TradePlan:
    store = get_store()
    runtime = get_runtime(store)
    settings = settings_for_runtime(runtime)
    market = MarketDataClient(settings)
    asset = normalize_asset_symbol(request.asset)
    if asset not in settings.allowed_assets_set:
        append_trade_error_event(
            store,
            f"Manual trade plan blocked: {asset} is not allowed.",
            {"asset": asset, "allowed_assets": sorted(settings.allowed_assets_set)},
        )
        raise HTTPException(
            status_code=400,
            detail=f"{asset} is not in the runtime allowed assets.",
        )
    if request.size_usdc <= 0:
        append_trade_error_event(
            store,
            "Manual trade plan blocked: order size must be greater than zero.",
            {"asset": asset, "size_usdc": request.size_usdc},
        )
        raise HTTPException(status_code=400, detail="Order size must be greater than zero.")
    if request.size_usdc < HYPERLIQUID_MIN_ORDER_USDC:
        message = (
            "Order too small. Hyperliquid requires a minimum order value of "
            f"{HYPERLIQUID_MIN_ORDER_USDC} USDC. Increase Size and try again."
        )
        append_trade_error_event(
            store,
            message,
            {
                "asset": asset,
                "size_usdc": request.size_usdc,
                "minimum_order_usdc": HYPERLIQUID_MIN_ORDER_USDC,
            },
        )
        raise HTTPException(status_code=400, detail=message)
    if request.size_usdc > runtime.max_order_usdc:
        append_trade_error_event(
            store,
            "Manual trade plan blocked: order size exceeds runtime max order.",
            {
                "asset": asset,
                "size_usdc": request.size_usdc,
                "max_order_usdc": runtime.max_order_usdc,
            },
        )
        raise HTTPException(status_code=400, detail="Order size exceeds the runtime max order.")
    max_leverage = int(min(10.0, _max_leverage_for_asset(asset, market)))
    if not float(request.leverage).is_integer():
        append_trade_error_event(
            store,
            f"Manual trade plan blocked: leverage must be a whole number for {asset}.",
            {"asset": asset, "leverage": request.leverage},
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "Leverage must be a whole number because Hyperliquid only accepts "
                "integer leverage."
            ),
        )
    if request.leverage < 1 or request.leverage > max_leverage:
        append_trade_error_event(
            store,
            f"Manual trade plan blocked: invalid leverage for {asset}.",
            {"asset": asset, "leverage": request.leverage, "max_leverage": max_leverage},
        )
        raise HTTPException(
            status_code=400,
            detail=f"Leverage must be between 1x and {max_leverage:g}x for {asset}.",
        )
    if request.entry_type == "limit" and not request.entry_price:
        append_trade_error_event(
            store,
            "Manual trade plan blocked: limit order missing entry price.",
            {"asset": asset},
        )
        raise HTTPException(status_code=400, detail="Limit orders require an entry price.")
    validate_available_margin(store, runtime, settings, request)
    mark_price = market.mark_price(asset).mark_price
    entry_price = request.entry_price or mark_price
    preflight_error = _manual_preflight_error(
        request,
        entry_price=entry_price,
        mark_price=mark_price,
    )
    if preflight_error:
        append_trade_error_event(
            store,
            f"Manual trade plan blocked: {preflight_error}",
            {
                "asset": asset,
                "side": request.side,
                "entry_price": entry_price,
                "mark_price": mark_price,
                "take_profit": request.take_profit,
                "stop_loss": request.stop_loss,
                "leverage": request.leverage,
            },
        )
        raise HTTPException(status_code=400, detail=preflight_error)
    if request.entry_type == "limit" and abs(entry_price - mark_price) / mark_price > 0.95:
        append_trade_error_event(
            store,
            "Manual trade plan blocked: limit price too far from reference.",
            {
                "asset": asset,
                "entry_price": entry_price,
                "mark_price": mark_price,
            },
        )
        raise HTTPException(
            status_code=400,
            detail=(
                "Limit price is more than 95% away from the current reference price "
                f"({mark_price:g}). Adjust the entry price before submitting."
            ),
        )
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
        append_trade_error_event(
            store,
            f"Manual trade plan blocked: {exc}",
            request.model_dump(mode="json"),
        )
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
    settings = settings_for_runtime(runtime)
    plan = store.get("plans", plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    validation = _formal_validation_for_plan(store, runtime, settings, plan)
    if not validation.valid:
        raise HTTPException(
            status_code=400,
            detail="Formal validation failed: " + "; ".join(validation.errors),
        )
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


@app.get("/api/trades/{plan_id}/validation")
def api_validate_trade(plan_id: str):
    store = get_store()
    runtime = get_runtime(store)
    settings = settings_for_runtime(runtime)
    plan = store.get("plans", plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")
    return _formal_validation_for_plan(store, runtime, settings, plan).as_dict()


@app.post("/api/trades/manual-submit")
def api_submit_manual_trade(request: ManualTradePlanRequest):
    plan = api_create_manual_trade_plan(request)
    store = get_store()
    runtime = get_runtime(store)
    try:
        result = manual_execute_trade(
            plan,
            runtime,
            store,
            confirmed=True,
            confirmation_phrase=None,
        )
    except (ExecutionBlocked, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    order = store.get("orders", result.order_id) if result.order_id else None
    return {
        "plan": result.plan,
        "order": order,
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
        store = get_store()
        settings = settings_for_runtime(runtime)
        return wallet_state_for_runtime(store, runtime, settings)
    except (ExecutionBlocked, ValueError) as exc:
        append_trade_error_event(get_store(), f"Wallet state request failed: {exc}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/orders")
def get_orders_state():
    store = get_store()
    runtime = get_runtime(store)
    settings = settings_for_runtime(runtime)
    try:
        wallet = wallet_state_for_runtime(store, runtime, settings)
    except (ExecutionBlocked, ValueError):
        wallet = {"open_positions": [], "open_orders": []}
    submitted_orders = [order for order in store.list("orders") if order.status == "submitted"]
    enriched_orders = []
    for order in submitted_orders:
        payload = order.model_dump(mode="json")
        plan = store.get("plans", order.plan_id)
        if plan:
            payload["plan"] = plan.model_dump(mode="json")
        enriched_orders.append(payload)
    return {
        "orders": enriched_orders,
        "positions": wallet.get("open_positions") or [],
        "open_orders": wallet.get("open_orders") or [],
        "wallet": {
            "account_address": wallet.get("account_address"),
            "agent_address": wallet.get("agent_address"),
            "withdrawable_usdc": wallet.get("withdrawable_usdc"),
            "total_margin_used_usdc": wallet.get("total_margin_used_usdc"),
        },
    }


def _position_for_asset(wallet: dict[str, Any], asset: str) -> dict[str, Any] | None:
    normalized_asset = normalize_asset_symbol(asset)
    return next(
        (
            item.get("position")
            for item in wallet.get("open_positions", [])
            if normalize_asset_symbol(item.get("position", {}).get("coin")) == normalized_asset
        ),
        None,
    )


def _position_mark_price(position: dict[str, Any]) -> float:
    for key in ("markPx", "mark_price", "markPrice"):
        value = float(position.get(key) or 0)
        if value > 0:
            return value
    signed_size = abs(float(position.get("szi") or 0))
    position_value = abs(float(position.get("positionValue") or 0))
    if signed_size > 0 and position_value > 0:
        return position_value / signed_size
    return float(position.get("entryPx") or 0)


def _latest_position_order(store: JsonStore, asset: str) -> OrderRecord | None:
    normalized_asset = normalize_asset_symbol(asset)
    orders = [
        order
        for order in store.list("orders")
        if order.status == "submitted"
        and normalize_asset_symbol(order.asset) == normalized_asset
        and order.plan_id != "manual_position_close"
    ]
    if not orders:
        return None
    return sorted(orders, key=lambda item: item.created_at)[-1]


def _validate_position_protection(
    side: TradeSide,
    entry_price: float,
    mark_price: float,
    take_profit: float | None,
    stop_loss: float | None,
    remove_take_profit: bool = False,
    remove_stop_loss: bool = False,
) -> None:
    if (
        take_profit is None
        and stop_loss is None
        and not remove_take_profit
        and not remove_stop_loss
    ):
        raise ExecutionBlocked("Set or remove at least one take profit or stop loss price.")
    reference = mark_price or entry_price
    if side == TradeSide.long:
        if take_profit is not None and (take_profit <= entry_price or take_profit <= reference):
            raise ExecutionBlocked("Long take profit must be above entry and current price.")
        if stop_loss is not None and (stop_loss >= entry_price or stop_loss >= reference):
            raise ExecutionBlocked("Long stop loss must be below entry and current price.")
    if side == TradeSide.short:
        if take_profit is not None and (take_profit >= entry_price or take_profit >= reference):
            raise ExecutionBlocked("Short take profit must be below entry and current price.")
        if stop_loss is not None and (stop_loss <= entry_price or stop_loss <= reference):
            raise ExecutionBlocked("Short stop loss must be above entry and current price.")


@app.post("/api/positions/{asset}/close")
def close_position(asset: str, request: ClosePositionRequest):
    store = get_store()
    runtime = get_runtime(store)
    settings = settings_for_runtime(runtime)
    normalized_asset = normalize_asset_symbol(asset)
    try:
        if not request.confirmed:
            raise ExecutionBlocked("Confirm position close before submitting a reduce-only order.")
        if not settings.privy_execution_enabled:
            raise ExecutionBlocked("Position close is currently configured for Privy execution.")
        agent = get_privy_agent_wallet(store, runtime)
        if not agent:
            raise ExecutionBlocked("Initialize a Privy Hyperliquid agent wallet first.")
        wallet = wallet_state_for_runtime(store, runtime, settings)
        position = _position_for_asset(wallet, normalized_asset)
        if not position:
            raise ExecutionBlocked(f"No open {normalized_asset} position to close.")
        signed_size = float(position.get("szi") or 0)
        if signed_size == 0:
            raise ExecutionBlocked(f"No open {normalized_asset} position to close.")
        side = TradeSide.long if signed_size > 0 else TradeSide.short
        order = PrivyHyperliquidAdapter(settings).close_position(
            agent=agent,
            asset=normalized_asset,
            size=abs(signed_size),
            side=side,
            position_value_usdc=abs(float(position.get("positionValue") or 0)),
            confirmed=request.confirmed,
        )
    except (ExecutionBlocked, ValueError) as exc:
        append_trade_error_event(
            store,
            f"Position close blocked: {exc}",
            {"asset": normalized_asset},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    store.save("orders", order)
    store.append_event(
        RunEvent(
            run_id=AGENT_RUN_ID,
            level="info",
            message=f"Submitted reduce-only close order for {normalized_asset}.",
            payload={
                "asset": normalized_asset,
                "order_id": order.id,
                "entry_order_id": order.entry_order_id,
            },
        )
    )
    return {"order": order, "wallet": wallet_state_for_runtime(store, runtime, settings)}


@app.post("/api/positions/{asset}/protection")
def set_position_protection(asset: str, request: PositionProtectionRequest):
    store = get_store()
    runtime = get_runtime(store)
    settings = settings_for_runtime(runtime)
    normalized_asset = normalize_asset_symbol(asset)
    try:
        if not request.confirmed:
            raise ExecutionBlocked("Confirm TP/SL before submitting reduce-only trigger orders.")
        if not settings.privy_execution_enabled:
            raise ExecutionBlocked("TP/SL updates are currently configured for Privy execution.")
        agent = get_privy_agent_wallet(store, runtime)
        if not agent:
            raise ExecutionBlocked("Initialize a Privy Hyperliquid agent wallet first.")
        wallet = wallet_state_for_runtime(store, runtime, settings)
        position = _position_for_asset(wallet, normalized_asset)
        if not position:
            raise ExecutionBlocked(f"No open {normalized_asset} position to protect.")
        signed_size = float(position.get("szi") or 0)
        if signed_size == 0:
            raise ExecutionBlocked(f"No open {normalized_asset} position to protect.")
        side = TradeSide.long if signed_size > 0 else TradeSide.short
        entry_price = float(position.get("entryPx") or 0)
        if entry_price <= 0:
            raise ExecutionBlocked(f"Entry price unavailable for {normalized_asset}.")
        mark_price = _position_mark_price(position)
        _validate_position_protection(
            side,
            entry_price,
            mark_price,
            request.take_profit,
            request.stop_loss,
            request.remove_take_profit,
            request.remove_stop_loss,
        )
        protection = PrivyHyperliquidAdapter(settings).set_position_protection(
            agent=agent,
            asset=normalized_asset,
            size=abs(signed_size),
            side=side,
            take_profit=request.take_profit,
            stop_loss=request.stop_loss,
            remove_take_profit=request.remove_take_profit,
            remove_stop_loss=request.remove_stop_loss,
            confirmed=request.confirmed,
        )
    except (ExecutionBlocked, ValueError) as exc:
        append_trade_error_event(
            store,
            f"TP/SL update blocked: {exc}",
            {"asset": normalized_asset},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    order = _latest_position_order(store, normalized_asset)
    plan = store.get("plans", order.plan_id) if order else None
    if plan:
        updated_take_profit = (
            None
            if request.remove_take_profit
            else request.take_profit if request.take_profit is not None else plan.take_profit
        )
        updated_stop_loss = (
            None
            if request.remove_stop_loss
            else request.stop_loss if request.stop_loss is not None else plan.stop_loss
        )
        plan = plan.model_copy(
            update={
                "take_profit": updated_take_profit,
                "stop_loss": updated_stop_loss,
            }
        )
        store.save("plans", plan)
    if order:
        order = order.model_copy(
            update={
                "take_profit_order_id": protection.get("takeProfitOrderId")
                or (None if request.remove_take_profit else order.take_profit_order_id),
                "stop_order_id": protection.get("stopOrderId")
                or (None if request.remove_stop_loss else order.stop_order_id),
                "raw_response": {
                    **order.raw_response,
                    "protection": protection,
                },
            }
        )
        store.save("orders", order)
    store.append_event(
        RunEvent(
            run_id=AGENT_RUN_ID,
            level="info",
            message=f"Updated TP/SL protection for {normalized_asset}.",
            payload={
                "asset": normalized_asset,
                "take_profit": request.take_profit,
                "stop_loss": request.stop_loss,
                "remove_take_profit": request.remove_take_profit,
                "remove_stop_loss": request.remove_stop_loss,
                "take_profit_order_id": protection.get("takeProfitOrderId"),
                "stop_order_id": protection.get("stopOrderId"),
            },
        )
    )
    return {
        "protection": protection,
        "order": order,
        "plan": plan,
        "wallet": wallet_state_for_runtime(store, runtime, settings),
    }


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
@app.get("/transfer", response_class=HTMLResponse)
def spa() -> HTMLResponse:
    return HTMLResponse((STATIC_ROOT / "index.html").read_text(encoding="utf-8"))


def _mask_address(address: str | None) -> str | None:
    if not address:
        return None
    if len(address) <= 12:
        return address
    return f"{address[:6]}...{address[-4:]}"
