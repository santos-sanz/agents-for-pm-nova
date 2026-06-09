from __future__ import annotations

from dataclasses import dataclass

from hyper_demo.adapters.anthropic_managed import ManagedAgentResearchClient
from hyper_demo.adapters.hyperliquid import ExecutionBlocked, HyperliquidAdapter
from hyper_demo.adapters.privy_hyperliquid import PrivyHyperliquidAdapter
from hyper_demo.config import Settings, settings_for_runtime
from hyper_demo.models import (
    AgentTradeAnalysis,
    DemoRun,
    ExecutionDecision,
    RiskProfileInput,
    RunEvent,
    RuntimeNetwork,
    RuntimeSettings,
    TradePlan,
    normalize_asset_symbol,
)
from hyper_demo.services.hypertracker import (
    HyperTrackerClient,
    enrich_research_with_market_intelligence,
)
from hyper_demo.services.market import MarketDataClient
from hyper_demo.services.perplexity import (
    PerplexityFinanceClient,
    enrich_research_with_finance_context,
    finance_context_prompt,
)
from hyper_demo.services.risk import build_investor_profile
from hyper_demo.services.technical_analysis import (
    build_agent_trade_analysis,
    trade_plan_from_candidate,
)
from hyper_demo.storage import JsonStore

AGENT_RUN_ID = "agent"


@dataclass(frozen=True)
class AgentTradeResult:
    plan: TradePlan
    analysis: AgentTradeAnalysis | None = None
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
    risk_appetite: str = "balanced",
    close_window: str = "1h",
) -> AgentTradeResult:
    effective_settings = settings_for_runtime(runtime, base_settings)
    normalized = normalize_asset_symbol(asset)
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
    finance_context = PerplexityFinanceClient(effective_settings).context_for_asset(normalized)
    if finance_context.available:
        append_agent_event(
            store,
            "Perplexity finance_search context added to research input.",
            payload={
                "asset": normalized,
                "evidence_count": len(finance_context.evidence),
                "source_count": len(finance_context.sources),
            },
        )
    else:
        append_agent_event(
            store,
            "Perplexity finance_search context unavailable.",
            level="warning",
            payload={"asset": normalized, "assumptions": finance_context.assumptions},
        )
    research_context = "\n\n".join(
        item
        for item in [
            context,
            finance_context_prompt(finance_context),
        ]
        if item
    )
    report = await ManagedAgentResearchClient(effective_settings, store).research(
        normalized,
        profile,
        external_context=research_context,
    )
    report = enrich_research_with_finance_context(report, finance_context)
    intelligence = HyperTrackerClient(effective_settings).intelligence_for_asset(normalized)
    report = enrich_research_with_market_intelligence(report, intelligence)
    store.save("research", report)
    if intelligence.available:
        append_agent_event(
            store,
            "HyperTracker market intelligence added to research.",
            payload={"asset": normalized, "evidence_count": len(intelligence.evidence)},
        )
    market = MarketDataClient(effective_settings)
    analysis = build_agent_trade_analysis(
        normalized,
        runtime,
        profile,
        report,
        market,
        risk_appetite=risk_appetite,
        close_window=close_window,
    )
    plan = trade_plan_from_candidate(
        normalized,
        profile,
        report,
        runtime,
        analysis.best_candidate,
    )
    _apply_runtime_size_cap(plan, runtime)
    plan.network = runtime.network
    plan.confidence = round(
        min(
            0.95,
            max(
                0.1,
                (plan.confidence * 0.75)
                + (
                    _confidence_from_report(
                        report.fallback_used,
                        len(report.evidence),
                        len(report.risks),
                    )
                    * 0.25
                ),
            ),
        ),
        2,
    )
    plan.execution_decision = ExecutionDecision.proposed
    plan.execution_message = "Proposed for manual review. Execute is required to submit orders."
    store.save("plans", plan)
    analysis.plan_id = plan.id
    analysis.best_candidate.confidence = plan.confidence
    store.save("analysis", analysis)
    append_agent_event(
        store,
        f"Trade analysis created for {normalized}.",
        payload={
            "analysis_id": analysis.id,
            "plan_id": plan.id,
            "side": plan.side,
            "entry_type": plan.entry_type,
            "confidence": plan.confidence,
        },
    )
    return AgentTradeResult(plan=plan, analysis=analysis)


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
        risk_appetite="balanced",
        close_window="4h",
    )


def maybe_execute_trade(
    plan: TradePlan,
    runtime: RuntimeSettings,
    store: JsonStore,
    effective_settings: Settings,
) -> AgentTradeResult:
    if runtime.network == RuntimeNetwork.prodnet:
        plan.execution_decision = ExecutionDecision.waiting_confirmation
        plan.execution_message = "Prodnet requires manual confirmation."
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
        agent = store.get("privy_agent_wallet", f"privy_agent_wallet_{runtime.network.value}")
        legacy_agent = store.get("privy_agent_wallet", "privy_agent_wallet")
        if not agent and legacy_agent and legacy_agent.network == runtime.network:
            agent = legacy_agent
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
    if plan.stop_loss is None:
        plan.max_loss_usdc = 0.0
    else:
        stop_distance_pct = abs(plan.entry_price - plan.stop_loss) / plan.entry_price
        plan.max_loss_usdc = round(plan.size_usdc * stop_distance_pct, 2)
    plan.rationale = (
        f"{plan.rationale} Position size was capped at the runtime max order "
        f"({runtime.max_order_usdc} USDC)."
    )


def _momentum_proxy(asset: str, mids: dict[str, float]) -> float:
    price = mids.get(asset, 0.0)
    return (price % 17) - 8.5
