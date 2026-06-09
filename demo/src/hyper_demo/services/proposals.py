from __future__ import annotations

from hyper_demo.models import (
    InvestorProfile,
    ProposalRequest,
    ResearchReport,
    TradePlan,
    TradeSide,
)
from hyper_demo.services.market import MarketDataClient


def infer_side(report: ResearchReport | None) -> TradeSide:
    if not report:
        return TradeSide.long
    negative_terms = ("downside", "risk", "weak", "bear", "short", "liquidity stress")
    positive_terms = ("trend", "momentum", "growth", "strength", "breakout", "adoption")
    text = " ".join([report.thesis, *report.evidence, *report.risks]).lower()
    positive = sum(text.count(term) for term in positive_terms)
    negative = sum(text.count(term) for term in negative_terms)
    return TradeSide.short if negative > positive + 2 else TradeSide.long


def build_trade_plan(
    request: ProposalRequest,
    profile: InvestorProfile,
    research: ResearchReport | None,
    market: MarketDataClient | None = None,
) -> TradePlan:
    market = market or MarketDataClient()
    price = market.mark_price(request.asset)
    side = infer_side(research)

    stop_pct = profile.inputs.stop_loss_pct / 100
    reward_multiple = 1.7 if profile.category.value == "conservative" else 2.0
    max_loss = min(
        profile.inputs.capital_at_risk_usdc,
        profile.max_position_notional_usdc * stop_pct,
    )
    size_usdc = min(profile.max_position_notional_usdc, max_loss / stop_pct)
    leverage = min(profile.recommended_leverage_cap, 2.0)

    if side == TradeSide.long:
        calculated_stop_loss = price.mark_price * (1 - stop_pct)
        take_profit = price.mark_price * (1 + stop_pct * reward_multiple)
    else:
        calculated_stop_loss = price.mark_price * (1 + stop_pct)
        take_profit = price.mark_price * (1 - stop_pct * reward_multiple)
    stop_loss = (
        round(calculated_stop_loss, 4)
        if leverage >= 10
        else None
    )
    max_loss_usdc = round(max_loss, 2) if stop_loss is not None else 0.0

    rationale = (
        f"Testnet-only {side.value} proposal for {request.asset} based on the risk profile "
        f"and the latest research thesis. Mark price source: {price.source}."
    )
    if stop_loss is None:
        rationale = (
            f"{rationale} No stop-loss is attached because leverage is below 10x; "
            "the plan relies on active monitoring, thesis invalidation, and take-profit."
        )
    if research:
        rationale = f"{rationale} Thesis: {research.thesis[:260]}"

    invalidation = [
        "The agent cannot verify current market structure or source quality.",
        "The monitored thesis invalidates or the trade is no longer expected to close intraday.",
        "Portfolio beta or drawdown exceeds the guardrails from the risk profile.",
    ]
    if research:
        invalidation.extend(research.why_not_invest[:2])

    return TradePlan(
        asset=request.asset,
        side=side,
        size_usdc=round(size_usdc, 2),
        entry_price=round(price.mark_price, 4),
        stop_loss=stop_loss,
        take_profit=round(take_profit, 4),
        max_loss_usdc=max_loss_usdc,
        leverage=round(leverage, 2),
        profile_id=profile.id,
        research_id=research.id if research else None,
        rationale=rationale,
        invalidation_criteria=invalidation,
    )
