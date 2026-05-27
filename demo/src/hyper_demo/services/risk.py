from __future__ import annotations

from hyper_demo.models import (
    InvestorProfile,
    LeverageTolerance,
    RiskCategory,
    RiskProfileInput,
)

LEVERAGE_CAPS = {
    LeverageTolerance.none: 1.0,
    LeverageTolerance.low: 1.5,
    LeverageTolerance.moderate: 2.5,
    LeverageTolerance.high: 4.0,
}


def score_risk_profile(inputs: RiskProfileInput) -> int:
    horizon_score = min(inputs.horizon_days / 180, 1.0) * 20
    drawdown_score = min(inputs.max_drawdown_pct / 40, 1.0) * 35
    leverage_score = {
        LeverageTolerance.none: 0,
        LeverageTolerance.low: 12,
        LeverageTolerance.moderate: 24,
        LeverageTolerance.high: 35,
    }[inputs.leverage_tolerance]
    stop_score = max(0.0, min((inputs.stop_loss_pct - 1) / 19, 1.0)) * 10
    return round(horizon_score + drawdown_score + leverage_score + stop_score)


def categorize_score(score: int) -> RiskCategory:
    if score < 35:
        return RiskCategory.conservative
    if score < 70:
        return RiskCategory.balanced
    return RiskCategory.aggressive


def build_investor_profile(inputs: RiskProfileInput) -> InvestorProfile:
    score = score_risk_profile(inputs)
    category = categorize_score(score)
    leverage_cap = LEVERAGE_CAPS[inputs.leverage_tolerance]
    stop_loss_fraction = inputs.stop_loss_pct / 100
    risk_budget = inputs.capital_at_risk_usdc
    max_position = min(risk_budget / stop_loss_fraction, risk_budget * leverage_cap * 8)
    max_position = round(max(10.0, max_position), 2)

    guardrails = [
        "Use Hyperliquid testnet only; mainnet trading is disabled for this demo.",
        "Require explicit user confirmation before submitting any order.",
        f"Do not exceed {inputs.capital_at_risk_usdc:.2f} USDC of planned loss.",
        f"Attach a stop-loss no wider than {inputs.stop_loss_pct:.2f}% from entry.",
        "Treat all outputs as educational analysis, not financial advice.",
    ]

    summary = (
        f"{category.value.title()} testnet profile for {inputs.asset_preference}: "
        f"{inputs.horizon_days} day horizon, {inputs.max_drawdown_pct:.1f}% drawdown tolerance, "
        f"{inputs.leverage_tolerance.value} leverage tolerance."
    )

    return InvestorProfile(
        inputs=inputs,
        risk_score=score,
        category=category,
        max_position_notional_usdc=max_position,
        recommended_leverage_cap=leverage_cap,
        summary=summary,
        guardrails=guardrails,
    )
