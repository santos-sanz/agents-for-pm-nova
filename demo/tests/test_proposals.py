import pytest

from hyper_demo.models import ProposalRequest, ResearchReport, RiskProfileInput
from hyper_demo.services.market import MarketPrice
from hyper_demo.services.proposals import build_trade_plan
from hyper_demo.services.risk import build_investor_profile


class StaticMarket:
    def mark_price(self, asset: str) -> MarketPrice:
        return MarketPrice(asset=asset, mark_price=100.0, source="test")


def test_build_trade_plan_omits_stop_loss_below_10x() -> None:
    profile = build_investor_profile(RiskProfileInput(stop_loss_pct=5, capital_at_risk_usdc=100))
    research = ResearchReport(
        asset="BTC",
        thesis="Momentum and adoption trend remain constructive.",
        evidence=["growth", "trend"],
        risks=["volatility"],
        assumptions=["testnet"],
        why_not_invest=["stop-loss missing"],
    )

    plan = build_trade_plan(ProposalRequest(asset="BTC"), profile, research, StaticMarket())

    assert plan.side == "long"
    assert plan.entry_type == "limit"
    assert plan.stop_loss is None
    assert plan.entry_price < plan.take_profit
    assert plan.max_loss_usdc == 0
    assert "No stop-loss is attached because leverage is below 10x" in plan.rationale


def test_invalid_trade_plan_exit_shape_is_rejected() -> None:
    with pytest.raises(ValueError):
        from hyper_demo.models import TradePlan

        TradePlan(
            asset="BTC",
            side="long",
            size_usdc=100,
            entry_price=100,
            stop_loss=105,
            take_profit=110,
            max_loss_usdc=10,
            rationale="bad exits",
            invalidation_criteria=[],
        )
