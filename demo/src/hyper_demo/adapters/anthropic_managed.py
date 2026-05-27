from __future__ import annotations

import json
import re
from typing import Any

from hyper_demo.config import Settings, get_settings
from hyper_demo.models import InvestorProfile, ResearchReport

SYSTEM_PROMPT = """You are an educational investment analysis agent for a live demo.

You may use web search and web fetch to gather current public context. You must not provide
personal financial advice. You must not claim certainty. You must return reviewable analysis
for a human presenter.

Return only JSON with these keys:
thesis: string
evidence: string[]
risks: string[]
assumptions: string[]
why_not_invest: string[]
sources: string[]
"""


class ManagedAgentResearchClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def research(self, asset: str, profile: InvestorProfile | None = None) -> ResearchReport:
        if not self.settings.has_anthropic_credentials:
            return self._fallback_report(
                asset,
                profile,
                reason="ANTHROPIC_API_KEY is not configured.",
            )
        try:
            return self._research_with_managed_agents(asset, profile)
        except Exception as exc:  # pragma: no cover - exercised manually against the beta API.
            return self._fallback_report(
                asset,
                profile,
                reason=f"Managed Agents unavailable: {exc}",
            )

    def _research_with_managed_agents(
        self, asset: str, profile: InvestorProfile | None = None
    ) -> ResearchReport:
        from anthropic import Anthropic

        api_key = self.settings.anthropic_api_key
        client = Anthropic(api_key=api_key.get_secret_value() if api_key else None)
        environment_id = self.settings.anthropic_environment_id
        if not environment_id:
            environment = client.beta.environments.create(
                name="hyperliquid-investment-demo-env",
                config={"type": "cloud", "networking": {"type": "unrestricted"}},
            )
            environment_id = environment.id

        agent_id = self.settings.anthropic_agent_id
        if not agent_id:
            agent = client.beta.agents.create(
                name="hyperliquid-investment-demo-agent",
                model=self.settings.anthropic_model,
                system=SYSTEM_PROMPT,
                tools=[
                    {
                        "type": "agent_toolset_20260401",
                        "default_config": {"enabled": False},
                        "configs": [
                            {"name": "web_search", "enabled": True},
                            {"name": "web_fetch", "enabled": True},
                        ],
                    }
                ],
                description="Educational market research agent for a Hyperliquid testnet demo.",
            )
            agent_id = agent.id

        session = client.beta.sessions.create(agent=agent_id, environment_id=environment_id)
        prompt = self._prompt(asset, profile)
        chunks: list[str] = []
        with client.beta.sessions.events.stream(session.id) as stream:
            client.beta.sessions.events.send(
                session.id,
                events=[{"type": "user.message", "content": [{"type": "text", "text": prompt}]}],
            )
            for event in stream:
                event_type = getattr(event, "type", "")
                if event_type == "agent.message":
                    for block in getattr(event, "content", []) or []:
                        text = getattr(block, "text", None)
                        if text:
                            chunks.append(text)
                if event_type == "session.status_idle":
                    stop_reason = getattr(event, "stop_reason", None)
                    stop_type = getattr(stop_reason, "type", None)
                    if stop_type in {None, "end_turn"}:
                        break

        raw = "\n".join(chunks).strip()
        parsed = _parse_jsonish(raw)
        return ResearchReport(
            asset=asset,
            profile_id=profile.id if profile else None,
            thesis=parsed.get("thesis") or f"Research completed for {asset}.",
            evidence=_as_list(parsed.get("evidence")),
            risks=_as_list(parsed.get("risks")),
            assumptions=_as_list(parsed.get("assumptions")),
            why_not_invest=_as_list(parsed.get("why_not_invest")),
            sources=_as_list(parsed.get("sources")),
            raw_agent_output=raw,
            agent_session_id=getattr(session, "id", None),
            fallback_used=False,
        )

    def _prompt(self, asset: str, profile: InvestorProfile | None) -> str:
        profile_text = (
            profile.summary
            if profile
            else "No saved risk profile; assume balanced testnet demo."
        )
        return f"""Research {asset}-PERP for an educational Hyperliquid testnet demo.

Risk profile: {profile_text}

Use web search/fetch for current context. Return only JSON with:
thesis, evidence, risks, assumptions, why_not_invest, sources.
Do not recommend mainnet trading. Do not provide personal financial advice.
"""

    def _fallback_report(
        self, asset: str, profile: InvestorProfile | None = None, reason: str | None = None
    ) -> ResearchReport:
        risk_note = profile.category.value if profile else "balanced"
        return ResearchReport(
            asset=asset,
            profile_id=profile.id if profile else None,
            thesis=(
                f"{asset} has enough liquidity and narrative relevance for a testnet workflow, "
                f"but the live thesis must be treated as provisional because this fallback did not "
                "perform web research."
            ),
            evidence=[
                "Hyperliquid testnet supports realistic order-entry and monitoring mechanics.",
                f"The saved profile is {risk_note}, so sizing should prioritize bounded downside.",
                (
                    "The demo can show trend discovery, proposal review, TP/SL placement, "
                    "and monitoring."
                ),
            ],
            risks=[
                "Fallback research may be stale and should not drive real capital decisions.",
                "Perpetual futures can move sharply and liquidation risk increases with leverage.",
                (
                    "TP/SL orders can fail or become misaligned if the parent order only "
                    "partially fills."
                ),
            ],
            assumptions=[
                "The presenter wants an educational, English-language demo.",
                "Execution remains on Hyperliquid testnet only.",
                reason or "Managed Agents fallback path selected.",
            ],
            why_not_invest=[
                "No live source-backed catalyst was verified in fallback mode.",
                "A testnet fill does not validate slippage, liquidity, or real execution quality.",
                "The thesis should be rejected if stop-loss placement cannot be confirmed.",
            ],
            sources=["local fallback fixture"],
            raw_agent_output=reason,
            fallback_used=True,
        )


def _parse_jsonish(text: str) -> dict[str, Any]:
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]
