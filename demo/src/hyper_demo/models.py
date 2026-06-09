from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def utc_now() -> datetime:
    return datetime.now(UTC)


class LeverageTolerance(StrEnum):
    none = "none"
    low = "low"
    moderate = "moderate"
    high = "high"


class RiskCategory(StrEnum):
    conservative = "conservative"
    balanced = "balanced"
    aggressive = "aggressive"


class TradeSide(StrEnum):
    long = "long"
    short = "short"


class RuntimeNetwork(StrEnum):
    testnet = "testnet"
    prodnet = "prodnet"


class ExecutionPolicy(StrEnum):
    auto_testnet_confirm_prodnet = "auto_testnet_confirm_prodnet"


class UIMode(StrEnum):
    human = "human"
    robot = "robot"


def normalize_asset_symbol(value: str) -> str:
    cleaned = value.strip().replace("-PERP", "")
    if ":" not in cleaned:
        return cleaned.upper()
    dex, symbol = cleaned.split(":", 1)
    return f"{dex.lower()}:{symbol.upper()}"


def normalize_asset_list(value: list[str]) -> list[str]:
    normalized = []
    for asset in value:
        cleaned = normalize_asset_symbol(asset)
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


class ExecutionDecision(StrEnum):
    proposed = "proposed"
    auto_executed = "auto_executed"
    waiting_confirmation = "waiting_confirmation"
    rejected = "rejected"
    blocked = "blocked"


class ConnectedWalletSource(StrEnum):
    privy = "privy"


class ConnectedWallet(BaseModel):
    id: str = "connected_wallet"
    created_at: datetime = Field(default_factory=utc_now)
    source: ConnectedWalletSource = ConnectedWalletSource.privy
    address: str
    user_id: str | None = None
    email: str | None = None
    wallet_id: str | None = None

    @field_validator("address")
    @classmethod
    def normalize_address(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.startswith("0x") or len(cleaned) != 42:
            raise ValueError("Wallet address must be a 0x-prefixed EVM address.")
        return cleaned


class PrivyAgentWallet(BaseModel):
    id: str = "privy_agent_wallet"
    created_at: datetime = Field(default_factory=utc_now)
    network: RuntimeNetwork = RuntimeNetwork.prodnet
    master_wallet_id: str
    master_wallet_address: str
    agent_wallet_id: str
    agent_wallet_address: str
    agent_name: str = "HyperClaude"
    registered: bool = False
    raw_response: dict[str, Any] = Field(default_factory=dict)

    @field_validator("master_wallet_address", "agent_wallet_address")
    @classmethod
    def normalize_wallet_address(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.startswith("0x") or len(cleaned) != 42:
            raise ValueError("Wallet address must be a 0x-prefixed EVM address.")
        return cleaned


class RuntimeSettings(BaseModel):
    id: str = "runtime"
    created_at: datetime = Field(default_factory=utc_now)
    network: RuntimeNetwork = RuntimeNetwork.prodnet
    execution_policy: ExecutionPolicy = ExecutionPolicy.auto_testnet_confirm_prodnet
    ui_mode: UIMode = UIMode.human
    watchlist: list[str] = Field(default_factory=lambda: ["BTC", "ETH", "SOL", "HYPE"])
    max_order_usdc: float = Field(default=100.0, gt=0)
    allowed_assets: list[str] = Field(default_factory=lambda: ["BTC", "ETH", "SOL", "HYPE"])
    sync_asset_lists: bool = True

    @field_validator("watchlist", "allowed_assets")
    @classmethod
    def normalize_assets(cls, value: list[str]) -> list[str]:
        return normalize_asset_list(value)

    @model_validator(mode="after")
    def sync_assets_when_enabled(self) -> RuntimeSettings:
        if self.sync_asset_lists:
            self.watchlist = list(self.allowed_assets)
        return self


class RuntimeSettingsUpdate(BaseModel):
    network: RuntimeNetwork | None = None
    execution_policy: ExecutionPolicy | None = None
    ui_mode: UIMode | None = None
    watchlist: list[str] | None = None
    max_order_usdc: float | None = Field(default=None, gt=0)
    allowed_assets: list[str] | None = None
    sync_asset_lists: bool | None = None

    @field_validator("watchlist", "allowed_assets")
    @classmethod
    def normalize_optional_assets(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return normalize_asset_list(value)


class RiskProfileInput(BaseModel):
    horizon_days: int = Field(default=30, ge=1, le=365)
    max_drawdown_pct: float = Field(default=8.0, ge=1.0, le=80.0)
    leverage_tolerance: LeverageTolerance = LeverageTolerance.low
    asset_preference: str = Field(default="BTC", min_length=2, max_length=16)
    capital_at_risk_usdc: float = Field(default=100.0, ge=10.0, le=1_000_000.0)
    stop_loss_pct: float = Field(default=4.0, ge=0.5, le=50.0)

    @field_validator("asset_preference")
    @classmethod
    def normalize_asset(cls, value: str) -> str:
        return normalize_asset_symbol(value)


class InvestorProfile(BaseModel):
    id: str = Field(default_factory=lambda: new_id("profile"))
    created_at: datetime = Field(default_factory=utc_now)
    inputs: RiskProfileInput
    risk_score: int = Field(ge=0, le=100)
    category: RiskCategory
    max_position_notional_usdc: float
    recommended_leverage_cap: float
    summary: str
    guardrails: list[str]


class ResearchRequest(BaseModel):
    asset: str = Field(default="BTC", min_length=2, max_length=16)
    profile_id: str | None = None

    @field_validator("asset")
    @classmethod
    def normalize_asset(cls, value: str) -> str:
        return normalize_asset_symbol(value)


class ResearchReport(BaseModel):
    id: str = Field(default_factory=lambda: new_id("research"))
    created_at: datetime = Field(default_factory=utc_now)
    asset: str
    profile_id: str | None = None
    thesis: str
    evidence: list[str]
    risks: list[str]
    assumptions: list[str]
    why_not_invest: list[str]
    sources: list[str] = Field(default_factory=list)
    raw_agent_output: str | None = None
    agent_session_id: str | None = None
    fallback_used: bool = False


class ManagedAgentOpportunity(BaseModel):
    title: str
    horizon: Literal["now", "next", "moonshot"]
    owner_loop: str
    tools: list[str]
    human_gate: str
    value: str
    risk: str


class ProposalRequest(BaseModel):
    asset: str = Field(default="BTC", min_length=2, max_length=16)
    profile_id: str | None = None
    research_id: str | None = None

    @field_validator("asset")
    @classmethod
    def normalize_asset(cls, value: str) -> str:
        return normalize_asset_symbol(value)


class Candle(BaseModel):
    asset: str
    interval: Literal["15m", "1h", "4h", "1d"]
    opened_at: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(default=0.0, ge=0)
    source: str = "hyperliquid"

    @model_validator(mode="after")
    def validate_ohlc(self) -> Candle:
        high = max(self.high, self.open, self.close)
        low = min(self.low, self.open, self.close)
        self.high = high
        self.low = low
        return self


class TimeframeSignal(BaseModel):
    interval: Literal["15m", "1h", "4h", "1d"]
    direction: Literal["bullish", "bearish", "neutral"]
    score: float = Field(ge=-100.0, le=100.0)
    return_pct: float
    volatility_pct: float = Field(ge=0.0)
    rsi: float = Field(ge=0.0, le=100.0)
    atr_pct: float = Field(ge=0.0)
    support: float = Field(gt=0)
    resistance: float = Field(gt=0)
    reason: str


class TradeCandidate(BaseModel):
    side: TradeSide
    entry_type: Literal["market", "limit"]
    timeframe: Literal["15m", "1h", "4h", "1d"]
    score: float = Field(ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0)
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)
    size_usdc: float = Field(gt=0)
    max_loss_usdc: float = Field(gt=0)
    leverage: float = Field(ge=1.0, le=10.0)
    risk_reward: float = Field(gt=0)
    rationale: str

    @model_validator(mode="after")
    def validate_candidate_exits(self) -> TradeCandidate:
        if self.side == TradeSide.long:
            if not self.stop_loss < self.entry_price < self.take_profit:
                raise ValueError("Long candidates require stop_loss < entry_price < take_profit.")
        if self.side == TradeSide.short:
            if not self.take_profit < self.entry_price < self.stop_loss:
                raise ValueError("Short candidates require take_profit < entry_price < stop_loss.")
        return self


class AgentTradeAnalysis(BaseModel):
    id: str = Field(default_factory=lambda: new_id("analysis"))
    created_at: datetime = Field(default_factory=utc_now)
    asset: str
    network: RuntimeNetwork = RuntimeNetwork.prodnet
    thesis: str
    summary: str
    best_candidate: TradeCandidate
    candidates: list[TradeCandidate]
    timeframes: list[TimeframeSignal]
    candles_by_timeframe: dict[str, list[Candle]]
    sources: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    plan_id: str | None = None


class TradePlan(BaseModel):
    id: str = Field(default_factory=lambda: new_id("plan"))
    created_at: datetime = Field(default_factory=utc_now)
    asset: str
    side: TradeSide
    size_usdc: float = Field(gt=0)
    entry_type: Literal["market", "limit"] = "limit"
    entry_price: float = Field(gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    max_loss_usdc: float = Field(default=0.0, ge=0)
    leverage: float = Field(default=1.0, ge=1.0, le=10.0)
    profile_id: str | None = None
    research_id: str | None = None
    rationale: str
    invalidation_criteria: list[str]
    confidence: float = Field(default=0.62, ge=0.0, le=1.0)
    thesis: str | None = None
    evidence: list[str] = Field(default_factory=list)
    source: Literal["agent", "manual"] = "agent"
    execution_decision: ExecutionDecision = ExecutionDecision.proposed
    network: RuntimeNetwork = RuntimeNetwork.prodnet
    agent_session_id: str | None = None
    raw_agent_output: str | None = None
    execution_message: str | None = None
    monitoring_cadence: str = "Every 60 seconds during the live demo."
    status: Literal["draft", "confirmed", "executed", "cancelled"] = "draft"

    @model_validator(mode="after")
    def validate_directional_exits(self) -> TradePlan:
        if self.side == TradeSide.long:
            if self.stop_loss is not None and self.stop_loss >= self.entry_price:
                raise ValueError("Long plans require stop_loss < entry_price.")
            if self.take_profit is not None and self.take_profit <= self.entry_price:
                raise ValueError("Long plans require entry_price < take_profit.")
        if self.side == TradeSide.short:
            if self.stop_loss is not None and self.stop_loss <= self.entry_price:
                raise ValueError("Short plans require entry_price < stop_loss.")
            if self.take_profit is not None and self.take_profit >= self.entry_price:
                raise ValueError("Short plans require take_profit < entry_price.")
        return self


class OrderRequest(BaseModel):
    plan_id: str
    confirmed: bool = False
    confirmation_phrase: str | None = None


class OrderRecord(BaseModel):
    id: str = Field(default_factory=lambda: new_id("order"))
    created_at: datetime = Field(default_factory=utc_now)
    plan_id: str
    exchange: Literal["hyperliquid-testnet", "hyperliquid-mainnet"] = "hyperliquid-testnet"
    asset: str
    side: TradeSide
    size_usdc: float
    entry_order_id: str | None = None
    stop_order_id: str | None = None
    take_profit_order_id: str | None = None
    raw_response: dict[str, Any] = Field(default_factory=dict)
    status: Literal["submitted", "simulated", "rejected"] = "submitted"
    message: str


class RunEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("event"))
    created_at: datetime = Field(default_factory=utc_now)
    run_id: str
    level: Literal["info", "warning", "error"] = "info"
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ManagedChatCredentialStatus(BaseModel):
    name: str
    kind: Literal["vault", "backend_env", "mcp"]
    configured: bool = False
    status: Literal["connected", "missing", "error", "unavailable"] = "missing"
    vault_id: str | None = None
    credential_id: str | None = None
    mcp_server: str | None = None
    message: str | None = None


class ManagedChatResources(BaseModel):
    id: str = "managed_chat_resources"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    status: Literal["disabled", "ready", "error"] = "disabled"
    disabled_reason: str | None = None
    environment_id: str | None = None
    coordinator_agent_id: str | None = None
    coordinator_agent_version: int | None = None
    subagent_ids: dict[str, str] = Field(default_factory=dict)
    skill_ids: dict[str, str] = Field(default_factory=dict)
    skill_versions: dict[str, int] = Field(default_factory=dict)
    memory_store_ids: dict[str, str] = Field(default_factory=dict)
    vault_ids: list[str] = Field(default_factory=list)
    credentials: list[ManagedChatCredentialStatus] = Field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = Field(default_factory=list)
    custom_tools: list[str] = Field(default_factory=list)
    error: str | None = None


class ManagedChatSession(BaseModel):
    id: str = Field(default_factory=lambda: new_id("chat_session"))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    title: str
    claude_session_id: str | None = None
    status: Literal["disabled", "idle", "running", "waiting_action", "terminated", "error"] = "idle"
    resource_id: str = "managed_chat_resources"
    vault_ids: list[str] = Field(default_factory=list)
    memory_store_ids: dict[str, str] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    last_error: str | None = None


class ManagedChatEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("chat_event"))
    created_at: datetime = Field(default_factory=utc_now)
    session_id: str
    type: str
    level: Literal["info", "warning", "error"] = "info"
    role: Literal["user", "agent", "tool", "system"] | None = None
    text: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    requires_action: bool = False


class DemoRun(BaseModel):
    id: str = Field(default_factory=lambda: new_id("run"))
    created_at: datetime = Field(default_factory=utc_now)
    profile_id: str | None = None
    research_id: str | None = None
    plan_id: str | None = None
    order_id: str | None = None
    status: Literal["draft", "researching", "planned", "executed", "monitoring", "error"] = "draft"


class PositionSnapshot(BaseModel):
    asset: str
    side: TradeSide
    entry_price: float
    mark_price: float
    size_usdc: float
    unrealized_pnl_usdc: float
    leverage: float = 1.0


class PortfolioMetrics(BaseModel):
    computed_at: datetime = Field(default_factory=utc_now)
    equity_usdc: float
    alpha: float
    beta: float
    delta_like_exposure: float
    volatility: float
    max_drawdown: float
    sharpe_like: float
    value_at_risk_95: float
    btc_correlation: float
    eth_correlation: float
    exposure_by_asset: dict[str, float]
    realized_pnl_usdc: float = 0.0
    unrealized_pnl_usdc: float = 0.0
