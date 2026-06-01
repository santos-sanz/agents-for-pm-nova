from __future__ import annotations

from hyper_demo.models import (
    AgentOpinion,
    InvestorProfile,
    InvestorSkill,
    MultiAgentDecision,
    QuantSignal,
    ResearchReport,
    SearchResult,
    TradePlan,
)
from hyper_demo.services.market import MarketDataClient

INVESTOR_SKILLS: tuple[InvestorSkill, ...] = (
    InvestorSkill(
        id="dalio_macro",
        display_name="Macro Risk Parity",
        inspired_by="Ray Dalio public principles",
        decision_style="Balance growth, liquidity, correlation, and drawdown before sizing.",
        must_check=[
            "Macro liquidity and dollar conditions",
            "Correlation with BTC and ETH benchmarks",
            "Portfolio drawdown against stated max drawdown",
        ],
        veto_rules=[
            "Reject if downside is not explicitly bounded.",
            "Reject if the trade increases correlated exposure without a hedge.",
        ],
        prompt=(
            "Act as a macro risk-parity reviewer inspired by Ray Dalio's public principles. "
            "Do not impersonate him. Stress-test correlations, leverage, liquidity, "
            "and regime risk."
        ),
    ),
    InvestorSkill(
        id="buffett_quality",
        display_name="Quality and Margin of Safety",
        inspired_by="Warren Buffett public principles",
        decision_style="Prefer understandable assets, durable economics, and a margin of safety.",
        must_check=[
            "Whether the asset thesis is understandable",
            "Whether price offers enough margin of safety",
            "Whether the presenter can explain why not to trade",
        ],
        veto_rules=[
            "Reject if the thesis depends only on short-term narrative.",
            "Reject if risk/reward is not at least 1.5 to 1 after fees and slippage.",
        ],
        prompt=(
            "Act as a quality and margin-of-safety reviewer inspired by Warren Buffett's public "
            "principles. Do not impersonate him. Challenge narratives that lack intrinsic logic."
        ),
    ),
    InvestorSkill(
        id="simons_quant",
        display_name="Statistical Edge",
        inspired_by="Jim Simons public principles",
        decision_style="Demand measurable signal quality, repeatability, and execution discipline.",
        must_check=[
            "Trend, volatility, carry, and liquidity signal agreement",
            "Whether the signal can be tested independently",
            "Whether execution rules are deterministic",
        ],
        veto_rules=[
            "Reject if the plan is not expressible as rules.",
            "Reject if signal and risk controls conflict.",
        ],
        prompt=(
            "Act as a systematic quant reviewer inspired by Jim Simons' public principles. "
            "Do not impersonate him. Convert the idea into measurable signals and "
            "falsifiable rules."
        ),
    ),
    InvestorSkill(
        id="lynch_clarity",
        display_name="Plain-English Thesis",
        inspired_by="Peter Lynch public principles",
        decision_style="Only proceed when the thesis is simple enough to explain plainly.",
        must_check=[
            "One-sentence thesis clarity",
            "Catalyst and invalidation clarity",
            "Position size relative to uncertainty",
        ],
        veto_rules=[
            "Reject if the thesis cannot be explained without jargon.",
            "Reject if invalidation criteria are vague.",
        ],
        prompt=(
            "Act as a plain-English thesis reviewer inspired by Peter Lynch's public principles. "
            "Do not impersonate him. Force clarity on what must happen and what would "
            "prove it wrong."
        ),
    ),
)


class LocalSearchTool:
    """Credential-free search facade for the demo.

    Live Managed Agents research uses web_search/web_fetch upstream. This local tool turns the
    latest report into reviewable source cards and falls back when no report exists.
    """

    def search(self, asset: str, research: ResearchReport | None) -> list[SearchResult]:
        if research and research.sources:
            evidence = research.evidence
            return [
                SearchResult(
                    title=f"{asset} source {index}",
                    url=source,
                    snippet=evidence[index - 1] if index <= len(evidence) else research.thesis,
                    source="local-research",
                )
                for index, source in enumerate(research.sources[:5], start=1)
            ]
        return [
            SearchResult(
                title=f"{asset} local fallback research",
                url="local://fallback-research",
                snippet=(
                    "No live web-backed report is available; use fallback output only "
                    "for demo flow."
                ),
                source="fallback",
            )
        ]


class QuantTradingTool:
    def __init__(self, market: MarketDataClient | None = None) -> None:
        self.market = market or MarketDataClient()

    def analyze(
        self,
        asset: str,
        research: ResearchReport | None,
        plan: TradePlan | None,
    ) -> QuantSignal:
        price = self.market.mark_price(asset)
        text = " ".join(
            [
                research.thesis if research else "",
                " ".join(research.evidence if research else []),
                " ".join(research.risks if research else []),
            ]
        ).lower()
        positive_terms = ("momentum", "trend", "breakout", "liquidity", "strength", "adoption")
        negative_terms = ("drawdown", "risk", "weak", "bear", "liquidation", "stress")
        positive = sum(text.count(term) for term in positive_terms)
        negative = sum(text.count(term) for term in negative_terms)
        denominator = max(positive + negative, 1)
        trend_score = max(min((positive - negative) / denominator, 1.0), -1.0)
        leverage_add = 0.25 if plan and plan.leverage > 1 else 0.15
        volatility_score = min(abs(trend_score) * 0.35 + leverage_add, 1.0)
        carry_score = 0.15 if plan and plan.side.value == "long" else -0.05
        liquidity_score = 0.85 if asset.upper() in {"BTC", "ETH", "SOL"} else 0.55
        if trend_score > 0.2 and volatility_score < 0.7:
            recommendation = "long_bias"
        elif trend_score < -0.25:
            recommendation = "short_bias"
        else:
            recommendation = "stand_aside"
        return QuantSignal(
            asset=asset.upper().replace("-PERP", ""),
            mark_price=price.mark_price,
            source=price.source,
            trend_score=round(trend_score, 3),
            volatility_score=round(volatility_score, 3),
            carry_score=round(carry_score, 3),
            liquidity_score=round(liquidity_score, 3),
            recommendation=recommendation,
            explanation=(
                "Rule-based demo signal from research wording, plan leverage, market-data source, "
                "and asset liquidity tier."
            ),
        )


def build_multi_agent_decision(
    asset: str,
    profile: InvestorProfile | None,
    research: ResearchReport | None,
    plan: TradePlan | None,
    search_tool: LocalSearchTool | None = None,
    quant_tool: QuantTradingTool | None = None,
) -> MultiAgentDecision:
    normalized = asset.upper().replace("-PERP", "")
    search_results = (search_tool or LocalSearchTool()).search(normalized, research)
    quant_signal = (quant_tool or QuantTradingTool()).analyze(normalized, research, plan)
    opinions = [
        _opinion_for_skill(skill, profile, research, plan, quant_signal)
        for skill in INVESTOR_SKILLS
    ]
    support = sum(1 for opinion in opinions if opinion.stance == "support")
    oppose = sum(1 for opinion in opinions if opinion.stance == "oppose")
    if oppose >= 2:
        consensus = "reject_trade"
    elif support >= 3 and plan:
        consensus = "approve_paper_trade"
    else:
        consensus = "revise_plan"
    return MultiAgentDecision(
        asset=normalized,
        search_results=search_results,
        quant_signal=quant_signal,
        opinions=opinions,
        consensus=consensus,
        next_actions=_next_actions(consensus, plan),
        safety_notes=[
            "Educational demo only; do not present output as personal financial advice.",
            "Keep Hyperliquid execution on testnet and prefer paper mode for live demos.",
            "Human confirmation is required before any simulated or testnet order is sent.",
        ],
    )


def _opinion_for_skill(
    skill: InvestorSkill,
    profile: InvestorProfile | None,
    research: ResearchReport | None,
    plan: TradePlan | None,
    quant_signal: QuantSignal,
) -> AgentOpinion:
    missing_checks: list[str] = []
    if not research or research.fallback_used:
        missing_checks.append("Replace fallback research with source-backed research.")
    if not plan:
        missing_checks.append("Create a bounded trade plan before approval.")
    if profile and plan and plan.max_loss_usdc > profile.inputs.capital_at_risk_usdc:
        missing_checks.append("Reduce max loss below capital-at-risk guardrail.")
    if quant_signal.recommendation == "stand_aside":
        missing_checks.append("Quant signal is neutral; require clearer edge.")

    if skill.id == "buffett_quality" and research and len(research.why_not_invest) < 2:
        missing_checks.append("Add explicit why-not-invest objections.")
    if skill.id == "simons_quant" and quant_signal.liquidity_score < 0.7:
        missing_checks.append("Liquidity tier is weak for a systematic demo.")
    if skill.id == "dalio_macro" and profile and profile.inputs.max_drawdown_pct < 5:
        missing_checks.append("Drawdown tolerance is too tight for perp volatility.")
    if skill.id == "lynch_clarity" and research and len(research.thesis) > 320:
        missing_checks.append("Shorten the thesis into one plain-English sentence.")

    if any("Reduce max loss" in check for check in missing_checks):
        stance = "oppose"
    elif len(missing_checks) >= 2:
        stance = "oppose"
    elif missing_checks:
        stance = "abstain"
    else:
        stance = "support"
    confidence = 0.78 if stance == "support" else 0.62 if stance == "abstain" else 0.72
    return AgentOpinion(
        skill_id=skill.id,
        display_name=skill.display_name,
        stance=stance,
        confidence=confidence,
        rationale=f"{skill.decision_style} Quant view: {quant_signal.recommendation}.",
        required_checks=missing_checks or skill.must_check[:2],
    )


def _next_actions(consensus: str, plan: TradePlan | None) -> list[str]:
    if consensus == "approve_paper_trade" and plan:
        return [
            f"Run paper execution for plan {plan.id}.",
            "Review generated run events and portfolio metrics.",
            "Only then decide whether testnet execution is worth demonstrating.",
        ]
    if consensus == "reject_trade":
        return [
            "Do not execute; update research and risk controls first.",
            "Ask the coding agent to add missing evidence, objections, or lower sizing.",
        ]
    return [
        "Revise the plan until at least three agents support it.",
        "Add source-backed research and rerun the quant signal.",
    ]
