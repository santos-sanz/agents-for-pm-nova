from __future__ import annotations

from dataclasses import dataclass

from hyper_demo.adapters.anthropic_managed import ManagedAgentResearchClient
from hyper_demo.adapters.hyperliquid import ExecutionBlocked, HyperliquidAdapter
from hyper_demo.adapters.privy_hyperliquid import PrivyHyperliquidAdapter
from hyper_demo.config import Settings, settings_for_runtime
from hyper_demo.models import (
    DemoRun,
    ExecutionDecision,
    ProposalRequest,
    RiskProfileInput,
    RunEvent,
    RuntimeNetwork,
    RuntimeSettings,
    TradePlan,
)
from hyper_demo.services.market import MarketDataClient
from hyper_demo.services.proposals import build_trade_plan
from hyper_demo.services.risk import build_investor_profile
from hyper_demo.storage import JsonStore

AGENT_RUN_ID = "agent"


@dataclass(frozen=True)
class AgentTradeResult:
    plan: TradePlan
    order_id: str | None = None
    run_id: str | None = None


def append_agent_event(
    store: JsonStore,
    message: str,
    level: str = "info",
    payload: dict | None = None,
) -> RunEvent:
    return store.append_event(
        RunEvent(
            run_id=AGENT_RUN_ID,
            level=level,  # type: ignore[arg-type]
            message=message,
            payload=payload or {},
        )
    )


async def analyze_trade(
    asset: str,
    runtime: RuntimeSettings,
    store: JsonStore,
    context: str | None = None,
    base_settings: Settings | None = None,
) -> AgentTradeResult:
    effective_settings = settings_for_runtime(runtime, base_settings)
    normalized = asset.strip().upper().replace("-PERP", "")
    append_agent_event(
        store,
        f"Analyzing {normalized} on Hyperliquid {runtime.network}.",
        payload={"asset": normalized, "network": runtime.network, "context": context},
    )
    profile = build_investor_profile(
        RiskProfileInput(
            asset_preference=normalized,
            capital_at_risk_usdc=max(10.0, runtime.max_order_usdc),
            stop_loss_pct=4.0,
        )
    )
    store.save("profiles", profile)
    report = await ManagedAgentResearchClient(effective_settings).research(normalized, profile)
    store.save("research", report)
    plan = build_trade_plan(
        ProposalRequest(asset=normalized, profile_id=profile.id, research_id=report.id),
        profile,
        report,
        MarketDataClient(effective_settings),
    )
    _apply_runtime_size_cap(plan, runtime)
    plan.network = runtime.network
    plan.confidence = _confidence_from_report(
        report.fallback_used,
        len(report.evidence),
        len(report.risks),
    )
    plan.thesis = report.thesis
    plan.evidence = report.evidence
    plan.agent_session_id = report.agent_session_id
    plan.raw_agent_output = report.raw_agent_output
    store.save("plans", plan)
    append_agent_event(
        store,
        f"Trade proposal created for {normalized}.",
        payload={"plan_id": plan.id, "side": plan.side, "confidence": plan.confidence},
    )
    return maybe_execute_trade(plan, runtime, store, effective_settings)


async def run_proactive_scan(
    runtime: RuntimeSettings,
    store: JsonStore,
    base_settings: Settings | None = None,
) -> AgentTradeResult:
    watchlist = runtime.watchlist or runtime.allowed_assets or ["BTC"]
    effective_settings = settings_for_runtime(runtime, base_settings)
    mids = MarketDataClient(effective_settings).all_mids()
    candidates = [asset for asset in watchlist if asset in mids] or watchlist
    ranked = sorted(candidates, key=lambda asset: abs(_momentum_proxy(asset, mids)), reverse=True)
    selected = ranked[0]
    append_agent_event(
        store,
        f"Proactive scan selected {selected}.",
        payload={"watchlist": watchlist, "selected": selected},
    )
    return await analyze_trade(
        selected,
        runtime,
        store,
        context="Proactive scan selected this asset from the configured watchlist.",
        base_settings=base_settings,
    )


def maybe_execute_trade(
    plan: TradePlan,
    runtime: RuntimeSettings,
    store: JsonStore,
    effective_settings: Settings,
) -> AgentTradeResult:
    if runtime.network == RuntimeNetwork.prodnet:
        plan.execution_decision = ExecutionDecision.waiting_confirmation
        plan.execution_message = "Prodnet requires manual confirmation and the mainnet phrase."
        store.save("plans", plan)
        append_agent_event(
            store,
            "Prodnet trade is waiting for confirmation.",
            level="warning",
            payload={"plan_id": plan.id},
        )
        return AgentTradeResult(plan=plan)

    try:
        order = _execute_plan_with_configured_adapter(
            plan,
            runtime,
            store,
            effective_settings,
            confirmed=True,
            confirmation_phrase=None,
        )
    except ExecutionBlocked as exc:
        plan.execution_decision = ExecutionDecision.blocked
        plan.execution_message = str(exc)
        store.save("plans", plan)
        append_agent_event(
            store,
            f"Auto-execution blocked: {exc}",
            level="warning",
            payload={"plan_id": plan.id},
        )
        return AgentTradeResult(plan=plan)

    plan.execution_decision = ExecutionDecision.auto_executed
    plan.execution_message = order.message
    plan.status = "executed"
    store.save("plans", plan)
    store.save("orders", order)
    run = DemoRun(
        profile_id=plan.profile_id,
        research_id=plan.research_id,
        plan_id=plan.id,
        order_id=order.id,
        status="executed",
    )
    store.save("runs", run)
    append_agent_event(
        store,
        "Testnet trade auto-executed.",
        payload={"plan_id": plan.id, "order_id": order.id, "run_id": run.id},
    )
    return AgentTradeResult(plan=plan, order_id=order.id, run_id=run.id)


def manual_execute_trade(
    plan: TradePlan,
    runtime: RuntimeSettings,
    store: JsonStore,
    confirmed: bool,
    confirmation_phrase: str | None,
    base_settings: Settings | None = None,
) -> AgentTradeResult:
    effective_settings = settings_for_runtime(runtime, base_settings)
    try:
        order = _execute_plan_with_configured_adapter(
            plan,
            runtime,
            store,
            effective_settings,
            confirmed=confirmed,
            confirmation_phrase=confirmation_phrase,
        )
    except ExecutionBlocked as exc:
        plan.execution_decision = ExecutionDecision.blocked
        plan.execution_message = str(exc)
        store.save("plans", plan)
        append_agent_event(
            store,
            f"Manual execution blocked: {exc}",
            level="warning",
            payload={"plan_id": plan.id},
        )
        raise

    if runtime.network == RuntimeNetwork.testnet:
        plan.execution_decision = ExecutionDecision.auto_executed
    else:
        plan.execution_decision = ExecutionDecision.proposed
    plan.execution_message = order.message
    plan.status = "executed"
    store.save("plans", plan)
    store.save("orders", order)
    run = DemoRun(
        profile_id=plan.profile_id,
        research_id=plan.research_id,
        plan_id=plan.id,
        order_id=order.id,
        status="executed",
    )
    store.save("runs", run)
    append_agent_event(
        store,
        "Manual trade execution submitted.",
        payload={"plan_id": plan.id, "order_id": order.id, "run_id": run.id},
    )
    return AgentTradeResult(plan=plan, order_id=order.id, run_id=run.id)


def _execute_plan_with_configured_adapter(
    plan: TradePlan,
    runtime: RuntimeSettings,
    store: JsonStore,
    effective_settings: Settings,
    confirmed: bool,
    confirmation_phrase: str | None,
):
    if effective_settings.privy_execution_enabled:
        agent = store.get("privy_agent_wallet", "privy_agent_wallet")
        if not agent:
            raise ExecutionBlocked("Initialize a Privy Hyperliquid agent wallet first.")
        return PrivyHyperliquidAdapter(effective_settings).execute_plan(
            plan,
            runtime_agent=agent,
            confirmed=confirmed,
            confirmation_phrase=confirmation_phrase,
        )
    return HyperliquidAdapter(effective_settings).execute_plan(
        plan,
        confirmed=confirmed,
        confirmation_phrase=confirmation_phrase,
    )


def reject_trade(plan: TradePlan, store: JsonStore) -> TradePlan:
    plan.execution_decision = ExecutionDecision.rejected
    plan.status = "cancelled"
    plan.execution_message = "Rejected by the demo operator."
    store.save("plans", plan)
    append_agent_event(store, "Trade proposal rejected.", payload={"plan_id": plan.id})
    return plan


def _confidence_from_report(fallback_used: bool, evidence_count: int, risk_count: int) -> float:
    base = 0.52 if fallback_used else 0.66
    score = base + min(evidence_count, 4) * 0.04 - min(risk_count, 4) * 0.025
    return round(max(0.1, min(0.92, score)), 2)


def _apply_runtime_size_cap(plan: TradePlan, runtime: RuntimeSettings) -> None:
    if plan.size_usdc <= runtime.max_order_usdc:
        return
    plan.size_usdc = round(runtime.max_order_usdc, 2)
    stop_distance_pct = abs(plan.entry_price - plan.stop_loss) / plan.entry_price
    plan.max_loss_usdc = round(plan.size_usdc * stop_distance_pct, 2)
    plan.rationale = (
        f"{plan.rationale} Position size was capped at the runtime max order "
        f"({runtime.max_order_usdc} USDC)."
    )


def _momentum_proxy(asset: str, mids: dict[str, float]) -> float:
    price = mids.get(asset, 0.0)
    return (price % 17) - 8.5
