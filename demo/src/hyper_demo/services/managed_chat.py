from __future__ import annotations

import asyncio
import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from anthropic.lib import files_from_dir

from hyper_demo.config import Settings, get_settings
from hyper_demo.models import (
    ManagedChatCredentialStatus,
    ManagedChatEvent,
    ManagedChatResources,
    ManagedChatSession,
    utc_now,
)
from hyper_demo.storage import JsonStore

CHAT_RESOURCE_ID = "managed_chat_resources"
CHAT_AGENT_RUN_LABEL = "managed-chat"
API_KEY_TOOL_NAMES = {"hypertracker", "perplexity"}
ALLOWED_NETWORK_HOSTS = [
    "api.hyperliquid.xyz",
    "api.hyperliquid-testnet.xyz",
    "ht-api.coinmarketman.com",
    "api.perplexity.ai",
]


ToolRunner = Callable[[ManagedChatSession, dict[str, Any]], dict[str, Any]]


CUSTOM_TOOLS: list[dict[str, Any]] = [
    {
        "type": "custom",
        "name": "trading_market_snapshot",
        "description": (
            "Return a non-secret trading snapshot: runtime, setup status, wallet summary, "
            "orders, positions, portfolio metrics, current mark price, and recent candles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset": {"type": "string", "description": "Optional Hyperliquid asset."},
                "interval": {"type": "string", "enum": ["15m", "1h", "4h", "1d"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "custom",
        "name": "trading_create_plan",
        "description": (
            "Create a guarded trade plan through the same validation used by the order ticket. "
            "This stores a proposal only and never submits an exchange order."
        ),
        "input_schema": {
            "type": "object",
            "required": ["asset", "side", "size_usdc"],
            "properties": {
                "asset": {"type": "string"},
                "side": {"type": "string", "enum": ["long", "short"]},
                "size_usdc": {"type": "number", "minimum": 1},
                "entry_type": {"type": "string", "enum": ["market", "limit"]},
                "entry_price": {"type": "number"},
                "stop_loss": {"type": "number"},
                "take_profit": {"type": "number"},
                "leverage": {"type": "number", "minimum": 1, "maximum": 10},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "custom",
        "name": "trading_execute_plan",
        "description": (
            "Submit an already stored trade plan. The backend still requires explicit "
            "confirmation and all Hyperliquid guardrails to pass."
        ),
        "input_schema": {
            "type": "object",
            "required": ["plan_id", "confirmed"],
            "properties": {
                "plan_id": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "custom",
        "name": "trading_hypertracker_intelligence",
        "description": (
            "Fetch HyperTracker positioning intelligence through the backend proxy. "
            "The API key never appears in tool input or output."
        ),
        "input_schema": {
            "type": "object",
            "required": ["asset"],
            "properties": {"asset": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "type": "custom",
        "name": "trading_perplexity_context",
        "description": (
            "Fetch Perplexity finance_search context through a backend proxy. "
            "The API key never appears in tool input or output."
        ),
        "input_schema": {
            "type": "object",
            "required": ["asset"],
            "properties": {"asset": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "type": "custom",
        "name": "trading_close_position",
        "description": (
            "Close an open position through the guarded backend reduce-only flow. "
            "Requires confirmed=true and existing Privy execution guardrails."
        ),
        "input_schema": {
            "type": "object",
            "required": ["asset", "confirmed"],
            "properties": {
                "asset": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "custom",
        "name": "trading_set_protection",
        "description": (
            "Set take-profit and/or stop-loss protection through the guarded backend "
            "reduce-only trigger flow. Requires confirmed=true."
        ),
        "input_schema": {
            "type": "object",
            "required": ["asset", "confirmed"],
            "properties": {
                "asset": {"type": "string"},
                "confirmed": {"type": "boolean"},
                "take_profit": {"type": "number"},
                "stop_loss": {"type": "number"},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "custom",
        "name": "trading_memory_note",
        "description": (
            "Record a non-secret note for the local audit trail. Durable Claude memory "
            "should still be written by the agent to the read-write memory store."
        ),
        "input_schema": {
            "type": "object",
            "required": ["note"],
            "properties": {
                "note": {"type": "string"},
                "category": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "custom",
        "name": "trading_runtime_get_settings",
        "description": "Return current runtime guardrails, watchlist, network, and setup status.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "custom",
        "name": "trading_runtime_update_settings",
        "description": (
            "Update only safe runtime settings: network, max order size, allowed assets, "
            "watchlist, and sync behavior. Exchange URLs and secrets cannot be changed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "network": {"type": "string", "enum": ["testnet", "prodnet"]},
                "max_order_usdc": {"type": "number", "minimum": 1},
                "allowed_assets": {"type": "array", "items": {"type": "string"}},
                "watchlist": {"type": "array", "items": {"type": "string"}},
                "sync_asset_lists": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "custom",
        "name": "trading_skill_proposal",
        "description": (
            "Record a proposed new skill or improvement. The host may create safe skills, "
            "but no host code is executed from this proposal."
        ),
        "input_schema": {
            "type": "object",
            "required": ["title", "body"],
            "properties": {
                "title": {"type": "string"},
                "body": {"type": "string"},
                "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "custom",
        "name": "trading_tool_proposal",
        "description": (
            "Record a proposed new host tool interface. The proposal is reviewable and "
            "does not execute arbitrary host code."
        ),
        "input_schema": {
            "type": "object",
            "required": ["name", "description"],
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "input_schema": {"type": "object"},
                "risk_controls": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
    },
]


SKILL_SPECS: dict[str, tuple[str, str]] = {
    "hyperliquid-safety": (
        "Hyperliquid Trading Safety",
        """# Hyperliquid Trading Safety

Use this skill before proposing, executing, closing, or protecting a Hyperliquid trade.

- Treat testnet as the default operating mode.
- Treat prodnet as guarded: explicit environment enablement and UI confirmation are required.
- Never ask for, store, print, or infer private keys, cookies, API keys, or seed phrases.
- Use only configured allowlisted assets and the runtime max order size.
- Validate entry direction, stop loss, take profit, leverage, minimum order value, and margin.
- If risk is ambiguous, propose a smaller plan or ask for confirmation instead of executing.
- Explain blocked actions plainly and preserve the audit trail.
""",
    ),
    "source-quality": (
        "Market Source Quality",
        """# Market Source Quality

Use this skill when researching catalysts, positioning, or macro context.

- Separate live market data, source-backed research, model inference, and user preference.
- Prefer Hyperliquid market data for price-sensitive claims.
- Prefer HyperTracker for positioning and wallet-flow signals when available.
- Prefer Perplexity finance_search for sourced public-market context when available.
- Cite sources by product or URL and state coverage gaps for crypto perps or HIP-3 assets.
- Penalize stale, circular, unsourced, or narrative-only evidence.
""",
    ),
    "hypertracker-cli": (
        "HyperTracker CLI Workflow",
        """# HyperTracker CLI Workflow

Use this skill when the agent needs HyperTracker positioning intelligence from the local demo CLI.

Primary command:

```bash
cd demo && uv run demo hypertracker --asset BTC
```

Operating rules:

- Use uppercase Hyperliquid asset symbols such as BTC, ETH, SOL, or HYPE.
- Never pass `HYPERTRACKER_API_KEY` on the command line, in chat, or in a tool argument.
- Let the backend load credentials from `.env`, backend env, or Managed Agents Vault/MCP binding.
- Treat the command output as JSON with `asset`, `available`, `evidence`, `risks`,
  `assumptions`, and `sources`.
- If `available` is false, preserve the assumptions and do not invent HyperTracker data.
- If a key is missing, tell the user HyperTracker is unavailable instead of asking for the key.
- Use HyperTracker for positioning, long/short crowding, aggregate exposure, funding impact,
  open-position count, and leaderboard wallet-flow clues.
- Do not treat HyperTracker as a standalone buy/sell signal. Cross-check with
  `trading_market_snapshot`, current price/candles, risk limits, and source-backed research.
- Include HyperTracker findings as evidence or risk inputs in the trade plan rationale.
- If shell access to the local repo is not available inside the Claude sandbox, call the
  `trading_hypertracker_intelligence` custom tool instead.
- For MCP-backed HyperTracker, prefer the MCP tool only when its Vault status is connected;
  otherwise use the backend CLI/custom-tool path.

Decision rubric:

- Crowded long positioning increases downside squeeze risk and should reduce long confidence.
- Crowded short positioning increases upside squeeze risk and should reduce short confidence.
- Large aggregate exposure without confirming price action should be treated as risk, not proof.
- Partial endpoint failures must lower confidence and be recorded in assumptions.
""",
    ),
    "trade-validation": (
        "Trade Plan Validation",
        """# Trade Plan Validation

Use this skill before creating a trade plan.

- Convert a thesis into a bounded plan: asset, side, size, entry type, entry price, leverage,
  stop loss, take profit, invalidation, confidence, and monitoring cadence.
- Keep leverage integer and at or below the asset maximum.
- Reject plans that exceed runtime max order USDC or are outside the allowlist.
- Reject plans where TP/SL are on the wrong side of entry/current price.
- Prefer plans that are easy to explain and easy to cancel.
""",
    ),
    "self-improvement": (
        "Trading Self Improvement",
        """# Trading Self Improvement

Use this skill throughout the conversation.

- Track rejected ideas, user corrections, false positives, and post-trade lessons.
- Propose new skills or tools when repeated gaps appear.
- Do not mutate host code. Use skill/tool proposal custom tools for reviewable improvements.
- Write durable learning only to the read-write memory store and never write secrets.
- Use outcomes and rubrics for high-stakes analyses before proposing action.
""",
    ),
}


SKILL_DESCRIPTIONS: dict[str, str] = {
    "hyperliquid-safety": (
        "Use before proposing, executing, closing, or protecting Hyperliquid trades."
    ),
    "source-quality": (
        "Use when researching market catalysts, positioning, macro context, or source quality."
    ),
    "hypertracker-cli": (
        "Use when collecting and interpreting HyperTracker intelligence through the demo CLI."
    ),
    "trade-validation": "Use before converting a thesis into a bounded trade plan.",
    "self-improvement": (
        "Use throughout trading conversations to capture lessons and propose safe improvements."
    ),
}


SUBAGENT_SPECS: dict[str, tuple[str, str]] = {
    "research": (
        "HyperClaude Research Agent",
        "Find source-backed catalysts, macro context, positioning, and coverage gaps.",
    ),
    "risk": (
        "HyperClaude Risk Sentinel",
        "Stress-test every plan against liquidation, sizing, execution, and operational risk.",
    ),
    "execution": (
        "HyperClaude Execution Planner",
        "Convert validated theses into order-ticket-compatible plans without bypassing guardrails.",
    ),
    "auditor": (
        "HyperClaude Outcome Auditor",
        "Grade reasoning quality, evidence, safety, and auditability before actions are proposed.",
    ),
    "toolsmith": (
        "HyperClaude Toolsmith",
        "Identify missing skills/tools and record reviewable improvement proposals.",
    ),
}


COORDINATOR_SYSTEM = """You are HyperClaude Chat, an autonomous Claude Managed Agents coordinator
for a guarded Hyperliquid trading demo.

Operate with maximum autonomy inside the Claude Managed Agents sandbox: research, calculate, write
scratch files, use web tools, delegate to subagents, use memory, create outcome loops, and call the
provided custom tools. You may self-improve during the conversation by proposing skills and tools.

Hard boundaries:
- Do not request, reveal, infer, or persist secrets.
- Do not invent exchange access or arbitrary URLs.
- Host-side trading actions are only available through custom tools and existing guardrails.
- Prodnet execution requires explicit environment enablement and UI confirmation.
- Testnet execution must still pass validation, sizing, leverage, margin, and asset allowlist
  checks.

Default workflow:
1. Gather runtime, wallet, market, HyperTracker, and Perplexity context when relevant.
   Use the HyperTracker CLI Workflow skill before relying on HyperTracker positioning data.
2. Delegate research, risk, execution, auditor, or toolsmith work when it improves quality.
3. Use outcomes/rubrics for high-stakes or uncertain plans.
4. Create reviewable trade plans before execution.
5. Record what should be remembered, improved, or rejected for future sessions.
"""


class ManagedTradingChatService:
    def __init__(
        self,
        settings: Settings | None = None,
        store: JsonStore | None = None,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.store = store or JsonStore(self.settings)
        self.client_factory = client_factory

    def state(self) -> dict[str, Any]:
        resources = self.resources()
        sessions = sorted(
            self.store.list("managed_chat_sessions"),
            key=lambda item: item.created_at,
            reverse=True,
        )
        return {
            "resources": resources,
            "sessions": sessions,
            "latest_events": self.store.list("managed_chat_events")[-50:],
            "capabilities": {
                "managed_agents": self.settings.has_anthropic_credentials,
                "auto_bootstrap": self.settings.anthropic_chat_auto_bootstrap,
                "dreams": self.settings.anthropic_chat_enable_dreams,
                "max_outcome_iterations": self.settings.anthropic_chat_max_outcome_iterations,
                "custom_tools": [tool["name"] for tool in CUSTOM_TOOLS],
            },
        }

    def resources(self) -> ManagedChatResources:
        return self.store.get(
            "managed_chat_resources",
            CHAT_RESOURCE_ID,
        ) or self._disabled_resources()

    async def bootstrap(self, force: bool = False) -> ManagedChatResources:
        if not force:
            current = self.store.get("managed_chat_resources", CHAT_RESOURCE_ID)
            if current and current.status == "ready":
                return current
        if not self.settings.has_anthropic_credentials:
            resources = self._disabled_resources("ANTHROPIC_API_KEY is missing.")
            return self.store.save("managed_chat_resources", resources)
        try:
            return await asyncio.to_thread(self._bootstrap_remote)
        except Exception as exc:  # pragma: no cover - beta API failures are environment-specific.
            resources = ManagedChatResources(
                status="error",
                disabled_reason="Managed Agents bootstrap failed.",
                credentials=self._credential_statuses(),
                vault_ids=self.settings.managed_chat_vault_ids,
                mcp_servers=self.settings.managed_chat_mcp_servers,
                custom_tools=[tool["name"] for tool in CUSTOM_TOOLS],
                error=str(exc),
            )
            return self.store.save("managed_chat_resources", resources)

    async def create_session(self, title: str | None = None) -> ManagedChatSession:
        resources = self.resources()
        if resources.status != "ready":
            session = ManagedChatSession(
                title=title or "Local Chat",
                status="disabled",
                vault_ids=resources.vault_ids,
                memory_store_ids=resources.memory_store_ids,
                last_error=resources.disabled_reason or resources.error,
            )
            self.store.save("managed_chat_sessions", session)
            self.append_event(
                session.id,
                "session.disabled",
                "Managed Agents are not ready. Configure ANTHROPIC_API_KEY and bootstrap Chat.",
                level="warning",
                role="system",
            )
            return session
        return await asyncio.to_thread(self._create_remote_session, resources, title)

    async def send_message(
        self,
        session_id: str,
        message: str,
        tool_runner: ToolRunner | None = None,
    ) -> ManagedChatSession:
        session = self._session_or_404(session_id)
        self.append_event(session.id, "user.message", message, role="user")
        if session.status == "disabled" or not session.claude_session_id:
            self.append_event(
                session.id,
                "agent.message",
                (
                    "Managed Agents Chat is disabled. Add ANTHROPIC_API_KEY, optional Vault/MCP "
                    "configuration, then rebuild resources."
                ),
                role="agent",
            )
            return session
        return await asyncio.to_thread(self._send_remote_message, session, message, tool_runner)

    async def define_outcome(
        self,
        session_id: str,
        description: str,
        rubric: str,
        max_iterations: int | None = None,
        tool_runner: ToolRunner | None = None,
    ) -> ManagedChatSession:
        session = self._session_or_404(session_id)
        max_iterations = min(
            max_iterations or self.settings.anthropic_chat_max_outcome_iterations,
            self.settings.anthropic_chat_max_outcome_iterations,
            20,
        )
        self.append_event(
            session.id,
            "user.define_outcome",
            description,
            role="user",
            payload={"rubric": rubric, "max_iterations": max_iterations},
        )
        if session.status == "disabled" or not session.claude_session_id:
            self.append_event(
                session.id,
                "session.error",
                "Managed Agents are disabled; outcome loops require a Claude session.",
                level="warning",
                role="system",
            )
            return session
        return await asyncio.to_thread(
            self._send_remote_outcome,
            session,
            description,
            rubric,
            max_iterations,
            tool_runner,
        )

    async def confirm_tool(
        self,
        session_id: str,
        tool_use_id: str,
        allow: bool,
        deny_message: str | None = None,
    ) -> ManagedChatSession:
        session = self._session_or_404(session_id)
        if not session.claude_session_id:
            self.append_event(
                session.id,
                "user.tool_confirmation",
                "Tool confirmation recorded locally.",
                role="user",
                payload={"tool_use_id": tool_use_id, "result": "allow" if allow else "deny"},
            )
            return session
        client = self._client()
        event: dict[str, Any] = {
            "type": "user.tool_confirmation",
            "tool_use_id": tool_use_id,
            "result": "allow" if allow else "deny",
        }
        if not allow and deny_message:
            event["deny_message"] = deny_message
        await asyncio.to_thread(
            client.beta.sessions.events.send,
            session.claude_session_id,
            events=[event],
        )
        self.append_event(
            session.id,
            "user.tool_confirmation",
            "Tool confirmation sent.",
            role="user",
            payload={"tool_use_id": tool_use_id, "result": event["result"]},
        )
        return session

    def interrupt(self, session_id: str) -> ManagedChatSession:
        session = self._session_or_404(session_id)
        if session.claude_session_id:
            client = self._client()
            client.beta.sessions.events.send(
                session.claude_session_id,
                events=[{"type": "user.interrupt"}],
            )
        session.status = "idle"
        session.updated_at = utc_now()
        self.store.save("managed_chat_sessions", session)
        self.append_event(session.id, "user.interrupt", "Interrupt requested.", role="user")
        return session

    def archive(self, session_id: str) -> ManagedChatSession:
        session = self._session_or_404(session_id)
        if session.claude_session_id:
            try:
                self._client().beta.sessions.update(session.claude_session_id, archived=True)
            except Exception:
                pass
        session.status = "terminated"
        session.updated_at = utc_now()
        self.store.save("managed_chat_sessions", session)
        self.append_event(session.id, "session.archived", "Chat session archived.", role="system")
        return session

    def events(self, session_id: str) -> list[ManagedChatEvent]:
        self._session_or_404(session_id)
        return [
            event
            for event in self.store.list("managed_chat_events")
            if event.session_id == session_id
        ]

    def append_event(
        self,
        session_id: str,
        event_type: str,
        text: str | None = None,
        *,
        level: str = "info",
        role: str | None = None,
        payload: dict[str, Any] | None = None,
        requires_action: bool = False,
    ) -> ManagedChatEvent:
        event = ManagedChatEvent(
            session_id=session_id,
            type=event_type,
            level=level,
            role=role,
            text=text,
            payload=_safe_payload(payload or {}),
            requires_action=requires_action,
        )
        return self.store.save("managed_chat_events", event)

    def _bootstrap_remote(self) -> ManagedChatResources:
        client = self._client()
        environment = client.beta.environments.create(
            name="hyperclaude-trading-chat-env",
            description="Sandbox for autonomous HyperClaude trading chat sessions.",
            config={
                "type": "cloud",
                "networking": {
                    "type": "limited",
                    "allowed_hosts": self._allowed_network_hosts(),
                    "allow_package_managers": True,
                    "allow_mcp_servers": True,
                },
                "packages": {
                    "type": "packages",
                    "pip": ["numpy", "pandas", "scipy", "requests"],
                    "npm": ["typescript"],
                },
            },
            metadata={"app": "hyperclaude", "component": CHAT_AGENT_RUN_LABEL},
        )
        skill_ids, skill_versions = self._create_skills(client)
        memory_store_ids = self._create_memory_stores(client)
        vault_ids, credentials = self._prepare_vaults(client)
        mcp_servers = self.settings.managed_chat_mcp_servers
        tools = self._agent_tools(mcp_servers)
        skills = [{"type": "custom", "skill_id": skill_id} for skill_id in skill_ids.values()]

        subagent_ids: dict[str, str] = {}
        for slug, (name, role) in SUBAGENT_SPECS.items():
            agent = client.beta.agents.create(
                name=name,
                model=self.settings.managed_chat_model,
                description=role,
                system=f"{role}\n\n{COORDINATOR_SYSTEM}",
                tools=tools[:1],
                skills=skills,
                metadata={"app": "hyperclaude", "role": slug},
            )
            subagent_ids[slug] = _object_id(agent)

        coordinator = client.beta.agents.create(
            name="HyperClaude Chat Coordinator",
            model=self.settings.managed_chat_model,
            description=(
                "Autonomous Managed Agents trading coordinator with guarded custom tools, "
                "Vault-backed MCP support, memory, outcomes, and subagents."
            ),
            system=COORDINATOR_SYSTEM,
            tools=tools,
            mcp_servers=mcp_servers,
            skills=skills,
            multiagent={"type": "coordinator", "agents": list(subagent_ids.values())},
            metadata={"app": "hyperclaude", "role": "coordinator"},
        )

        resources = ManagedChatResources(
            status="ready",
            environment_id=_object_id(environment),
            coordinator_agent_id=_object_id(coordinator),
            coordinator_agent_version=_object_version(coordinator),
            subagent_ids=subagent_ids,
            skill_ids=skill_ids,
            skill_versions=skill_versions,
            memory_store_ids=memory_store_ids,
            vault_ids=vault_ids,
            credentials=credentials,
            mcp_servers=mcp_servers,
            custom_tools=[tool["name"] for tool in CUSTOM_TOOLS],
        )
        return self.store.save("managed_chat_resources", resources)

    def _create_remote_session(
        self,
        resources: ManagedChatResources,
        title: str | None,
    ) -> ManagedChatSession:
        client = self._client()
        session = client.beta.sessions.create(
            agent=resources.coordinator_agent_id or "",
            environment_id=resources.environment_id or "",
            title=title or "HyperClaude Chat",
            metadata={"app": "hyperclaude", "component": CHAT_AGENT_RUN_LABEL},
            resources=self._session_resources(resources),
            vault_ids=resources.vault_ids,
        )
        record = ManagedChatSession(
            title=title or "HyperClaude Chat",
            claude_session_id=_object_id(session),
            status="idle",
            vault_ids=resources.vault_ids,
            memory_store_ids=resources.memory_store_ids,
        )
        self.store.save("managed_chat_sessions", record)
        self.append_event(
            record.id,
            "session.created",
            "Claude Managed Agents session created.",
            role="system",
            payload={
                "claude_session_id": record.claude_session_id,
                "vault_ids": record.vault_ids,
                "memory_store_ids": record.memory_store_ids,
            },
        )
        return record

    def _send_remote_message(
        self,
        session: ManagedChatSession,
        message: str,
        tool_runner: ToolRunner | None,
    ) -> ManagedChatSession:
        client = self._client()
        session.status = "running"
        session.updated_at = utc_now()
        self.store.save("managed_chat_sessions", session)
        with client.beta.sessions.events.stream(session.claude_session_id) as stream:
            client.beta.sessions.events.send(
                session.claude_session_id,
                events=[{"type": "user.message", "content": [{"type": "text", "text": message}]}],
            )
            self._consume_stream(client, session, stream, tool_runner)
        session.updated_at = utc_now()
        self.store.save("managed_chat_sessions", session)
        return session

    def _send_remote_outcome(
        self,
        session: ManagedChatSession,
        description: str,
        rubric: str,
        max_iterations: int,
        tool_runner: ToolRunner | None,
    ) -> ManagedChatSession:
        client = self._client()
        session.status = "running"
        session.updated_at = utc_now()
        self.store.save("managed_chat_sessions", session)
        with client.beta.sessions.events.stream(session.claude_session_id) as stream:
            client.beta.sessions.events.send(
                session.claude_session_id,
                events=[
                    {
                        "type": "user.define_outcome",
                        "description": description,
                        "rubric": {"type": "text", "content": rubric},
                        "max_iterations": max_iterations,
                    }
                ],
            )
            self._consume_stream(client, session, stream, tool_runner)
        session.updated_at = utc_now()
        self.store.save("managed_chat_sessions", session)
        return session

    def _consume_stream(
        self,
        client: Any,
        session: ManagedChatSession,
        stream: Any,
        tool_runner: ToolRunner | None,
    ) -> None:
        for raw_event in stream:
            event = _event_dict(raw_event)
            event_type = event.get("type", "unknown")
            text = _event_text(event)
            requires_action = event_type in {
                "agent.custom_tool_use",
                "agent.tool_use",
                "agent.mcp_tool_use",
            }
            self.append_event(
                session.id,
                event_type,
                text,
                level="error" if event_type == "session.error" else "info",
                role=_event_role(event_type),
                payload=event,
                requires_action=requires_action,
            )
            if event_type == "agent.custom_tool_use" and tool_runner:
                self._handle_custom_tool(client, session, event, tool_runner)
            if event_type == "session.status_running":
                session.status = "running"
            if event_type == "session.status_idle":
                session.status = "waiting_action" if _requires_action(event) else "idle"
                if not _requires_action(event):
                    break
            if event_type == "session.status_terminated":
                session.status = "terminated"
                break
            if event_type == "session.error":
                session.status = "error"
                session.last_error = text or "Claude session error."
                break
        self.store.save("managed_chat_sessions", session)

    def _handle_custom_tool(
        self,
        client: Any,
        session: ManagedChatSession,
        event: dict[str, Any],
        tool_runner: ToolRunner,
    ) -> None:
        tool_use_id = str(event.get("id") or event.get("custom_tool_use_id") or "")
        try:
            result = tool_runner(session, event)
            is_error = False
        except Exception as exc:
            result = {"error": str(exc)}
            is_error = True
        text = json.dumps(_safe_payload(result), indent=2)
        self.append_event(
            session.id,
            "user.custom_tool_result",
            f"Custom tool result for {event.get('name') or 'tool'}.",
            role="tool",
            level="error" if is_error else "info",
            payload={"custom_tool_use_id": tool_use_id, "result": result, "is_error": is_error},
        )
        if tool_use_id:
            client.beta.sessions.events.send(
                session.claude_session_id,
                events=[
                    {
                        "type": "user.custom_tool_result",
                        "custom_tool_use_id": tool_use_id,
                        "content": [{"type": "text", "text": text}],
                        "is_error": is_error,
                    }
                ],
            )

    def _create_skills(self, client: Any) -> tuple[dict[str, str], dict[str, int]]:
        skill_ids: dict[str, str] = {}
        skill_versions: dict[str, int] = {}
        build_suffix = f"{CHAT_AGENT_RUN_LABEL}-{uuid4().hex[:8]}"
        with tempfile.TemporaryDirectory(prefix="hyperclaude-skills-") as tmp:
            root = Path(tmp)
            for slug, (title, body) in SKILL_SPECS.items():
                skill_dir = root / slug
                skill_dir.mkdir()
                skill_path = skill_dir / "SKILL.md"
                content = _skill_markdown(slug, body)
                skill_path.write_text(content, encoding="utf-8")
                skill = client.beta.skills.create(
                    display_title=f"{title} ({build_suffix})",
                    files=files_from_dir(skill_dir),
                )
                skill_ids[slug] = _object_id(skill)
                version = _object_version(skill)
                if version is not None:
                    skill_versions[slug] = version
        return skill_ids, skill_versions

    def _create_memory_stores(self, client: Any) -> dict[str, str]:
        canon = client.beta.memory_stores.create(
            name="HyperClaude Trading Canon",
            description=(
                "Read-only operating canon: guardrails, allowed exchange boundaries, "
                "and trading safety principles."
            ),
            metadata={"app": "hyperclaude", "kind": "canon"},
        )
        learning = client.beta.memory_stores.create(
            name="HyperClaude Conversation Learning",
            description=(
                "Read-write user preferences, rejected ideas, post-trade lessons, "
                "and proposed process improvements. Never store secrets."
            ),
            metadata={"app": "hyperclaude", "kind": "learning"},
        )
        ids = {"canon": _object_id(canon), "learning": _object_id(learning)}
        self._seed_memory(
            client,
            ids["canon"],
            "/canon/safety.md",
            SKILL_SPECS["hyperliquid-safety"][1],
        )
        self._seed_memory(
            client,
            ids["learning"],
            "/learning/README.md",
            (
                "# Conversation Learning\n\n"
                "Store user preferences, repeated mistakes, rejected setups, and post-trade "
                "lessons here. Do not store API keys, private keys, cookies, or credentials.\n"
            ),
        )
        return ids

    def _seed_memory(self, client: Any, store_id: str, path: str, content: str) -> None:
        try:
            client.beta.memory_stores.memories.create(store_id, path=path, content=content)
        except Exception:
            return

    def _prepare_vaults(
        self,
        client: Any,
    ) -> tuple[list[str], list[ManagedChatCredentialStatus]]:
        vault_ids = list(self.settings.managed_chat_vault_ids)
        statuses = self._credential_statuses()
        mcp_servers = self.settings.managed_chat_mcp_servers
        credential_jobs = self._mcp_credential_jobs(statuses, mcp_servers)
        managed_statuses = [
            status
            for status in statuses
            if status.name in API_KEY_TOOL_NAMES and status.configured
        ]
        managed_vault_id = ""
        if managed_statuses:
            managed_vault_id = self._managed_vault_id(client)
            if managed_vault_id:
                vault_ids.append(managed_vault_id)
                for status in managed_statuses:
                    if any(job_status is status for job_status, _, _ in credential_jobs):
                        continue
                    status.kind = "vault"
                    status.status = "unavailable"
                    status.vault_id = managed_vault_id
                    status.message = (
                        "Managed Agents Vault created for this API-key tool, but Claude can "
                        "only inject the credential into a declared MCP server. Set "
                        f"{status.name.upper()}_MCP_SERVER_URL or ANTHROPIC_CHAT_MCP_SERVERS "
                        "to bind the API key to an MCP server. The backend proxy remains "
                        "active without exposing the key."
                    )
        if credential_jobs:
            for status, token, server_url in credential_jobs:
                vault_id = managed_vault_id or self._managed_vault_id(client)
                if vault_id and vault_id not in vault_ids:
                    vault_ids.append(vault_id)
                try:
                    credential = client.beta.vaults.credentials.create(
                        vault_id,
                        display_name=f"{status.name} bearer token",
                        auth={
                            "type": "static_bearer",
                            "token": token,
                            "mcp_server_url": server_url,
                        },
                        metadata={"app": "hyperclaude", "tool": status.name},
                    )
                    status.kind = "vault"
                    status.status = "connected"
                    status.vault_id = vault_id
                    status.credential_id = _object_id(credential)
                    status.message = "Credential stored in Managed Agents Vault."
                except Exception as exc:
                    message = str(exc)
                    status.kind = "vault"
                    status.vault_id = vault_id
                    if "409" in message or "already" in message.lower():
                        status.status = "connected"
                        status.message = (
                            "Managed Agents Vault already has an active credential for this "
                            "MCP server URL. Secrets are write-only, so the existing token was "
                            "not read back."
                        )
                    else:
                        status.status = "error"
                        status.message = f"Vault credential creation failed: {exc}"
        if self.settings.managed_chat_vault_ids:
            statuses.append(
                ManagedChatCredentialStatus(
                    name="external-vaults",
                    kind="vault",
                    configured=True,
                    status="connected",
                    message="Vault IDs provided via ANTHROPIC_CHAT_VAULT_IDS.",
                )
            )
        return _unique(vault_ids), statuses

    def _managed_vault_id(self, client: Any) -> str:
        existing = self._existing_managed_vault_id()
        if existing:
            return existing
        vault = client.beta.vaults.create(
            display_name="HyperClaude API-Key Tools",
            metadata={"app": "hyperclaude", "component": CHAT_AGENT_RUN_LABEL},
        )
        return _object_id(vault)

    def _existing_managed_vault_id(self) -> str:
        resources = self.store.get("managed_chat_resources", CHAT_RESOURCE_ID)
        if not resources:
            return ""
        external_vault_ids = set(self.settings.managed_chat_vault_ids)
        for credential in resources.credentials:
            if credential.name in API_KEY_TOOL_NAMES and credential.vault_id:
                return credential.vault_id
        for vault_id in resources.vault_ids:
            if vault_id not in external_vault_ids:
                return vault_id
        return ""

    def _credential_statuses(self) -> list[ManagedChatCredentialStatus]:
        return [
            ManagedChatCredentialStatus(
                name="hypertracker",
                kind="backend_env",
                configured=self.settings.has_hypertracker_credentials,
                status="connected" if self.settings.has_hypertracker_credentials else "missing",
                message=(
                    "Backend proxy can call HyperTracker without exposing the API key. "
                    "Configure ANTHROPIC_CHAT_MCP_SERVERS to store this credential in a "
                    "Managed Agents Vault."
                    if self.settings.has_hypertracker_credentials
                    else "HYPERTRACKER_API_KEY is not configured."
                ),
            ),
            ManagedChatCredentialStatus(
                name="perplexity",
                kind="backend_env",
                configured=self.settings.has_perplexity_credentials,
                status="connected" if self.settings.has_perplexity_credentials else "missing",
                message=(
                    "Backend proxy can call Perplexity without exposing the API key. "
                    "Configure ANTHROPIC_CHAT_MCP_SERVERS to store this credential in a "
                    "Managed Agents Vault."
                    if self.settings.has_perplexity_credentials
                    else "PERPLEXITY_API_KEY is not configured."
                ),
            ),
        ]

    def _mcp_credential_jobs(
        self,
        statuses: list[ManagedChatCredentialStatus],
        mcp_servers: list[dict[str, Any]],
    ) -> list[tuple[ManagedChatCredentialStatus, str, str]]:
        jobs: list[tuple[ManagedChatCredentialStatus, str, str]] = []
        for status in statuses:
            if not status.configured:
                continue
            server = _matching_mcp_server(status.name, mcp_servers)
            if not server:
                continue
            token = ""
            if status.name == "hypertracker" and self.settings.hypertracker_api_key:
                token = self.settings.hypertracker_api_key.get_secret_value()
            if status.name == "perplexity" and self.settings.perplexity_api_key:
                token = self.settings.perplexity_api_key.get_secret_value()
            if not token:
                continue
            status.mcp_server = server["name"]
            jobs.append((status, token, server["url"]))
        return jobs

    def _agent_tools(self, mcp_servers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = [
            {
                "type": "agent_toolset_20260401",
                "default_config": {
                    "enabled": True,
                    "permission_policy": {"type": "always_allow"},
                },
            },
            *CUSTOM_TOOLS,
        ]
        for server in mcp_servers:
            tools.append(
                {
                    "type": "mcp_toolset",
                    "mcp_server_name": server["name"],
                    "default_config": {
                        "enabled": True,
                        "permission_policy": {"type": "always_allow"},
                    },
                }
            )
        return tools

    def _allowed_network_hosts(self) -> list[str]:
        hosts = list(ALLOWED_NETWORK_HOSTS)
        for server in self.settings.managed_chat_mcp_servers:
            hostname = urlparse(str(server.get("url") or "")).hostname
            if hostname and hostname not in hosts:
                hosts.append(hostname)
        return hosts

    def _session_resources(self, resources: ManagedChatResources) -> list[dict[str, Any]]:
        attached = []
        canon = resources.memory_store_ids.get("canon")
        if canon:
            attached.append(
                {
                    "type": "memory_store",
                    "memory_store_id": canon,
                    "access": "read_only",
                    "instructions": "Use as immutable trading safety canon.",
                }
            )
        learning = resources.memory_store_ids.get("learning")
        if learning:
            attached.append(
                {
                    "type": "memory_store",
                    "memory_store_id": learning,
                    "access": "read_write",
                    "instructions": (
                        "Store non-secret user preferences, rejected setups, post-trade lessons, "
                        "and process improvements."
                    ),
                }
            )
        return attached

    def _client(self) -> Any:
        if self.client_factory:
            return self.client_factory()
        from anthropic import Anthropic

        api_key = self.settings.anthropic_api_key
        return Anthropic(api_key=api_key.get_secret_value() if api_key else None)

    def _disabled_resources(self, reason: str | None = None) -> ManagedChatResources:
        return ManagedChatResources(
            status="disabled",
            disabled_reason=reason or "Managed Agents resources have not been bootstrapped.",
            credentials=self._credential_statuses(),
            vault_ids=self.settings.managed_chat_vault_ids,
            mcp_servers=self.settings.managed_chat_mcp_servers,
            custom_tools=[tool["name"] for tool in CUSTOM_TOOLS],
        )

    def _session_or_404(self, session_id: str) -> ManagedChatSession:
        session = self.store.get("managed_chat_sessions", session_id)
        if not session:
            raise KeyError("Chat session not found.")
        return session


def _event_dict(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        return _safe_payload(event)
    if hasattr(event, "model_dump"):
        return _safe_payload(event.model_dump(mode="json"))
    payload = {
        key: value
        for key, value in vars(event).items()
        if not key.startswith("_")
    }
    if "type" not in payload and hasattr(event, "type"):
        payload["type"] = event.type
    return _safe_payload(payload)


def _event_text(event: dict[str, Any]) -> str | None:
    content = event.get("content")
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))
        if parts:
            return "\n".join(parts)
    for key in ("text", "message", "error"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    if event.get("type") == "agent.custom_tool_use":
        return f"Custom tool requested: {event.get('name') or 'tool'}"
    return None


def _event_role(event_type: str) -> str | None:
    if event_type.startswith("user."):
        return "user"
    if event_type.startswith("agent."):
        return "agent"
    if "tool" in event_type:
        return "tool"
    if event_type.startswith("session.") or event_type.startswith("span."):
        return "system"
    return None


def _requires_action(event: dict[str, Any]) -> bool:
    stop_reason = event.get("stop_reason")
    if not isinstance(stop_reason, dict):
        return False
    return stop_reason.get("type") == "requires_action" or bool(stop_reason.get("event_ids"))


def _skill_markdown(slug: str, body: str) -> str:
    description = SKILL_DESCRIPTIONS[slug]
    frontmatter = (
        "---\n"
        f"name: {slug}\n"
        f"description: {description}\n"
        "---\n\n"
    )
    return frontmatter + body.lstrip()


def _safe_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _safe_payload(item)
            for key, item in value.items()
            if "secret" not in key.lower()
            and "private" not in key.lower()
            and "api_key" not in key.lower()
            and key.lower() not in {"token", "authorization", "cookie"}
        }
    if isinstance(value, list):
        return [_safe_payload(item) for item in value]
    return value


def _object_id(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or "")
    return str(getattr(value, "id", "") or "")


def _object_version(value: Any) -> int | None:
    if isinstance(value, dict):
        version = value.get("version")
    else:
        version = getattr(value, "version", None)
    try:
        return int(version)
    except (TypeError, ValueError):
        return None


def _matching_mcp_server(name: str, servers: list[dict[str, Any]]) -> dict[str, Any] | None:
    needle = name.lower()
    return next(
        (
            server
            for server in servers
            if needle in str(server.get("name", "")).lower()
            or needle in str(server.get("url", "")).lower()
        ),
        None,
    )


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
