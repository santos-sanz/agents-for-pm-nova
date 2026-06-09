from hyper_demo.models import ResearchReport, RiskProfileInput, RuntimeSettings
from hyper_demo.services.market import MarketDataClient, fallback_candles
from hyper_demo.services.risk import build_investor_profile
from hyper_demo.services.technical_analysis import (
    analyze_timeframe,
    build_agent_trade_analysis,
)


class StaticMarket(MarketDataClient):
    def candles(self, asset: str, interval: str, limit: int = 120):
        return fallback_candles(asset, interval, limit)

    def available_assets(self):
        return []


def test_analyze_timeframe_scores_fallback_trend() -> None:
    signal = analyze_timeframe("1h", fallback_candles("BTC", "1h", 48))

    assert signal.interval == "1h"
    assert signal.direction in {"bullish", "neutral"}
    assert signal.support < signal.resistance
    assert signal.atr_pct > 0


def test_agent_trade_analysis_ranks_candidates_inside_limits() -> None:
    runtime = RuntimeSettings(max_order_usdc=75, allowed_assets=["BTC"])
    profile = build_investor_profile(
        RiskProfileInput(
            asset_preference="BTC",
            capital_at_risk_usdc=75,
            stop_loss_pct=4,
        )
    )
    report = ResearchReport(
        asset="BTC",
        thesis="Momentum and adoption trend remain constructive.",
        evidence=["trend strength", "breakout momentum"],
        risks=["volatility"],
        assumptions=["testnet"],
        why_not_invest=["invalid if structure flips bearish"],
    )

    analysis = build_agent_trade_analysis("BTC", runtime, profile, report, StaticMarket())

    assert analysis.best_candidate.size_usdc <= 75
    assert analysis.best_candidate.leverage <= 10
    assert len(analysis.candidates) >= 4
    assert {candidate.side for candidate in analysis.candidates} == {"long", "short"}
    assert {signal.interval for signal in analysis.timeframes} == {"15m", "1h", "4h", "1d"}
