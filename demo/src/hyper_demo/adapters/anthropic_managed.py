from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from hyper_demo.config import Settings, get_settings
from hyper_demo.models import (
    InvestorProfile,
    ManagedAgentResearchResources,
    ResearchReport,
    utc_now,
)
from hyper_demo.storage import JsonStore

RESEARCH_RESOURCE_ID = "managed_agent_research_resources"
RESEARCH_ENVIRONMENT_NAME = "hyperliquid-investment-demo-env"
RESEARCH_AGENT_NAME = "hyperliquid-investment-demo-agent"
CHAT_ENVIRONMENT_NAME = "hyperclaude-trading-chat-env"
CHAT_AGENT_NAMES = [
    "HyperClaude Research Agent",
    "HyperClaude Risk Sentinel",
    "HyperClaude Execution Planner",
    "HyperClaude Outcome Auditor",
    "HyperClaude Toolsmith",
    "HyperClaude Chat Coordinator",
]

SYSTEM_PROMPT = """You are an educational investment analysis agent for a live demo.

You may use web search and web fetch to gather current public context. Think beyond a
single trade call: act like the research desk inside a broader trading operating system.
You must not provide personal financial advice. You must not claim certainty. You must
return reviewable analysis for a human presenter.
Use Hyperliquid mainnet/testnet language only. Describe mainnet as guarded and human-confirmed.

Return only JSON with these keys:
thesis: string
evidence: string[] (include catalysts, market structure, directional bias, portfolio impact,
execution quality, and monitoring signals)
risks: string[] (include leverage, liquidity, invalidation, operational, compliance, and
automation risks)
assumptions: string[] (include which managed-agent loops would need human gates)
why_not_invest: string[]
sources: string[]
"""


class ManagedAgentResearchClient:
    def __init__(self, settings: Settings | None = None, store: JsonStore | None = None) -> None:
        self.settings = settings or get_settings()
        self.store = store or JsonStore(self.settings)

    async def research(
        self,
        asset: str,
        profile: InvestorProfile | None = None,
        external_context: str | None = None,
    ) -> ResearchReport:
        if not self.settings.has_anthropic_credentials:
            return self._fallback_report(
                asset,
                profile,
                reason="ANTHROPIC_API_KEY is not configured.",
                external_context=external_context,
            )
        try:
            return await asyncio.to_thread(
                self._research_with_managed_agents,
                asset,
                profile,
                external_context,
            )
        except Exception as exc:  # pragma: no cover - exercised manually against the beta API.
            return self._fallback_report(
                asset,
                profile,
                reason=f"Managed Agents unavailable: {exc}",
                external_context=external_context,
            )

    def _research_with_managed_agents(
        self,
        asset: str,
        profile: InvestorProfile | None = None,
        external_context: str | None = None,
    ) -> ResearchReport:
        from anthropic import Anthropic

        api_key = self.settings.anthropic_api_key
        client = Anthropic(api_key=api_key.get_secret_value() if api_key else None)
        resources = self._research_resources(client)
        environment_id = resources.environment_id
        agent_id = resources.agent_id
        if not environment_id or not agent_id:
            raise RuntimeError("Managed Agents research resources are not ready.")

        session = client.beta.sessions.create(agent=agent_id, environment_id=environment_id)
        prompt = self._prompt(asset, profile, external_context)
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

    def _research_resources(self, client: Any) -> ManagedAgentResearchResources:
        configured_environment_id = self.settings.anthropic_environment_id
        configured_agent_id = self.settings.anthropic_agent_id
        if configured_environment_id and configured_agent_id:
            return self._save_resources(
                environment_id=configured_environment_id,
                agent_id=configured_agent_id,
            )

        current = self.store.get("managed_agent_research_resources", RESEARCH_RESOURCE_ID)
        environment_id = configured_environment_id or (current.environment_id if current else None)
        agent_id = configured_agent_id or (current.agent_id if current else None)
        agent_version = current.agent_version if current else None

        if not environment_id:
            environment = self._find_latest_named(
                client.beta.environments,
                RESEARCH_ENVIRONMENT_NAME,
            )
            if not environment:
                environment = client.beta.environments.create(
                    name=RESEARCH_ENVIRONMENT_NAME,
                    description="Sandbox for the HyperClaude one-shot research agent.",
                    config={"type": "cloud", "networking": {"type": "unrestricted"}},
                    metadata={"app": "hyperclaude", "component": "research"},
                )
            environment_id = _object_id(environment)

        if not agent_id:
            agent = self._find_latest_named(client.beta.agents, RESEARCH_AGENT_NAME)
            if not agent:
                agent = client.beta.agents.create(
                    name=RESEARCH_AGENT_NAME,
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
                    description=(
                        "Educational trading operating-system agent for guarded Hyperliquid "
                        "research, risk, monitoring, and execution review."
                    ),
                    metadata={"app": "hyperclaude", "component": "research"},
                )
            agent_id = _object_id(agent)
            agent_version = _object_version(agent)

        return self._save_resources(
            environment_id=environment_id,
            agent_id=agent_id,
            agent_version=agent_version,
        )

    def _save_resources(
        self,
        *,
        environment_id: str,
        agent_id: str,
        agent_version: int | None = None,
    ) -> ManagedAgentResearchResources:
        existing = self.store.get("managed_agent_research_resources", RESEARCH_RESOURCE_ID)
        resources = ManagedAgentResearchResources(
            created_at=existing.created_at if existing else utc_now(),
            updated_at=utc_now(),
            status="ready",
            environment_id=environment_id,
            agent_id=agent_id,
            agent_version=agent_version,
        )
        return self.store.save("managed_agent_research_resources", resources)

    def _find_latest_named(self, api: Any, name: str) -> Any | None:
        matches = [item for item in _list_all(api) if getattr(item, "name", None) == name]
        if not matches:
            return None
        return sorted(matches, key=_created_sort_key)[-1]

    def cleanup_duplicate_resources(self, keep: int = 1, dry_run: bool = True) -> dict[str, Any]:
        if keep < 1:
            raise ValueError("keep must be at least 1.")
        if not self.settings.has_anthropic_credentials:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured.")

        from anthropic import Anthropic

        api_key = self.settings.anthropic_api_key
        client = Anthropic(api_key=api_key.get_secret_value() if api_key else None)
        all_agents = _list_all(client.beta.agents)
        all_environments = _list_all(client.beta.environments)
        research_agents = _duplicates_to_remove(all_agents, RESEARCH_AGENT_NAME, keep)
        chat_agents = [
            item
            for name in CHAT_AGENT_NAMES
            for item in _duplicates_to_remove(all_agents, name, keep)
        ]
        research_environments = _duplicates_to_remove(
            all_environments,
            RESEARCH_ENVIRONMENT_NAME,
            keep,
        )
        chat_environments = _duplicates_to_remove(all_environments, CHAT_ENVIRONMENT_NAME, keep)
        result: dict[str, Any] = {
            "dry_run": dry_run,
            "keep": keep,
            "research_agents": [_object_id(item) for item in research_agents],
            "chat_agents": [_object_id(item) for item in chat_agents],
            "research_environments": [_object_id(item) for item in research_environments],
            "chat_environments": [_object_id(item) for item in chat_environments],
        }
        if dry_run:
            return result

        for agent in [*research_agents, *chat_agents]:
            client.beta.agents.archive(_object_id(agent))
        for environment in [*research_environments, *chat_environments]:
            environment_id = _object_id(environment)
            try:
                client.beta.environments.delete(environment_id)
            except Exception:
                client.beta.environments.archive(environment_id)
        return result

    def _prompt(
        self,
        asset: str,
        profile: InvestorProfile | None,
        external_context: str | None = None,
    ) -> str:
        profile_text = (
            profile.summary
            if profile
            else "No saved risk profile; assume balanced guarded-mainnet demo."
        )
        return f"""Research {asset}-PERP for an educational guarded Hyperliquid mainnet demo.

Risk profile: {profile_text}

External source-backed context to consider:
{external_context or "None supplied."}

Use web search/fetch for current context. Return only JSON with:
thesis, evidence, risks, assumptions, why_not_invest, sources.
Evidence should include catalysts, directional bias, market structure, portfolio impact,
execution quality, and post-trade monitoring signals when available.
Assumptions should name any managed-agent loops that would need human gates.
Do not recommend personal trading decisions. Treat any mainnet output as a proposal requiring
human confirmation and the configured guardrails. Do not provide personal financial advice.
"""

    def _fallback_report(
        self,
        asset: str,
        profile: InvestorProfile | None = None,
        reason: str | None = None,
        external_context: str | None = None,
    ) -> ResearchReport:
        risk_note = profile.category.value if profile else "balanced"
        return ResearchReport(
            asset=asset,
            profile_id=profile.id if profile else None,
            thesis=(
                f"{asset} has enough liquidity and narrative relevance for a guarded "
                "mainnet workflow, "
                f"but the live thesis must be treated as provisional because this fallback did not "
                "perform web research."
            ),
            evidence=[
                "Hyperliquid mainnet market data supports realistic order-review "
                "and monitoring mechanics.",
                (
                    f"Fallback directional bias for {asset} is mildly constructive until "
                    "local signals disagree."
                ),
                f"The saved profile is {risk_note}, so sizing should prioritize bounded downside.",
                (
                    "The demo can show trend discovery, proposal review, TP/SL placement, "
                    "and monitoring."
                ),
                (
                    "A broader Managed Agents deployment could own market briefing, "
                    "risk sentinel, portfolio allocation, execution review, and incident "
                    "reporting loops."
                ),
            ],
            risks=[
                "Fallback research may be stale and should not drive real capital decisions.",
                "Perpetual futures can move sharply and liquidation risk increases with leverage.",
                (
                    "TP/SL orders can fail or become misaligned if the parent order only "
                    "partially fills."
                ),
                (
                    "Ambitious automation needs explicit human gates for capital allocation, "
                    "leverage, hedging, and production policy changes."
                ),
            ],
            assumptions=[
                "The presenter wants an educational, English-language demo.",
                (
                    "Execution remains guarded and requires explicit human approval."
                ),
                (
                    "Managed Agents can expand from one-shot research into a reviewable "
                    "operating loop with memory, tools, sessions, and event inspection."
                ),
                reason or "Managed Agents fallback path selected.",
                (
                    "External context supplied to the fallback path: "
                    f"{external_context[:240]}"
                    if external_context
                    else "No external context was supplied to the fallback path."
                ),
            ],
            why_not_invest=[
                "No live source-backed catalyst was verified in fallback mode.",
                "Fallback mode does not validate slippage, liquidity, or real execution quality.",
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


def _object_id(obj: Any) -> str:
    return str(getattr(obj, "id", "") or "")


def _object_version(obj: Any) -> int | None:
    version = getattr(obj, "version", None)
    return int(version) if version is not None else None


def _created_sort_key(obj: Any) -> str:
    return str(getattr(obj, "created_at", "") or "")


def _list_all(api: Any) -> list[Any]:
    page = api.list(limit=100)
    if hasattr(page, "data"):
        return list(page.data)
    return list(page)


def _duplicates_to_remove(items: list[Any], name: str, keep: int) -> list[Any]:
    named = [item for item in items if getattr(item, "name", None) == name]
    sorted_items = sorted(named, key=_created_sort_key, reverse=True)
    return sorted_items[keep:]
