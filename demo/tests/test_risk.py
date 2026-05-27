from hyper_demo.models import LeverageTolerance, RiskProfileInput
from hyper_demo.services.risk import build_investor_profile, score_risk_profile


def test_risk_profile_scores_and_guardrails() -> None:
    conservative = RiskProfileInput(
        horizon_days=14,
        max_drawdown_pct=5,
        leverage_tolerance=LeverageTolerance.none,
        capital_at_risk_usdc=100,
        stop_loss_pct=2,
    )
    aggressive = RiskProfileInput(
        horizon_days=180,
        max_drawdown_pct=30,
        leverage_tolerance=LeverageTolerance.high,
        capital_at_risk_usdc=1000,
        stop_loss_pct=10,
    )

    assert score_risk_profile(aggressive) > score_risk_profile(conservative)

    profile = build_investor_profile(conservative)
    assert profile.category == "conservative"
    assert profile.recommended_leverage_cap == 1.0
    assert any("testnet" in guardrail.lower() for guardrail in profile.guardrails)
