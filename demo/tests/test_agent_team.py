from hyper_demo.models import ProposalRequest, ResearchReport, RiskProfileInput
from hyper_demo.services.agent_team import (
    INVESTOR_SKILLS,
    QuantTradingTool,
    build_multi_agent_decision,
)
from hyper_demo.services.market import MarketPrice
from hyper_demo.services.proposals import build_trade_plan
from hyper_demo.services.risk import build_investor_profile


class StaticMarket:
    def mark_price(self, asset: str) -> MarketPrice:
        return MarketPrice(asset=asset, mark_price=100.0, source="test")


def test_investor_skills_are_promptable_and_reviewable() -> None:
    assert {skill.id for skill in INVESTOR_SKILLS} == {
        "dalio_macro",
        "buffett_quality",
        "simons_quant",
        "lynch_clarity",
    }
    assert all("Do not impersonate" in skill.prompt for skill in INVESTOR_SKILLS)
    assert all(skill.must_check and skill.veto_rules for skill in INVESTOR_SKILLS)


def test_quant_tool_returns_long_bias_for_constructive_research() -> None:
    research = ResearchReport(
        asset="BTC",
        thesis="Momentum trend and liquidity strength are constructive.",
        evidence=["breakout trend", "adoption growth"],
        risks=["volatility"],
        assumptions=["testnet"],
        why_not_invest=["invalidated below stop"],
    )

    signal = QuantTradingTool(StaticMarket()).analyze("BTC", research, None)

    assert signal.recommendation == "long_bias"
    assert signal.mark_price == 100
    assert signal.source == "test"


def test_multi_agent_decision_approves_source_backed_paper_trade() -> None:
    profile = build_investor_profile(RiskProfileInput(stop_loss_pct=4, capital_at_risk_usdc=100))
    research = ResearchReport(
        asset="BTC",
        thesis="Momentum trend and liquidity strength support a bounded testnet demo.",
        evidence=["breakout trend", "adoption growth", "liquidity strength"],
        risks=["volatility"],
        assumptions=["testnet only"],
        why_not_invest=["stop loss missing", "source quality degrades"],
        sources=["https://example.com/btc"],
    )
    plan = build_trade_plan(ProposalRequest(asset="BTC"), profile, research, StaticMarket())

    decision = build_multi_agent_decision(
        "BTC",
        profile,
        research,
        plan,
        quant_tool=QuantTradingTool(StaticMarket()),
    )

    assert decision.consensus == "approve_paper_trade"
    assert len(decision.opinions) == 4
    assert decision.search_results[0].source == "local-research"
