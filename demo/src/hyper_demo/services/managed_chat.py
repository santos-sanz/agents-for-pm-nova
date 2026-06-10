from __future__ import annotations

import asyncio
import json
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from anthropic.lib import files_from_dir

from hyper_demo.config import Settings, get_settings
from hyper_demo.models import (
    ManagedChatCredentialStatus,
    ManagedChatDeployment,
    ManagedChatEvent,
    ManagedChatResources,
    ManagedChatSession,
    UIMode,
    utc_now,
)
from hyper_demo.storage import JsonStore

CHAT_RESOURCE_ID = "managed_chat_resources"
CHAT_DEPLOYMENT_ID = "managed_chat_deployment"
CHAT_AGENT_RUN_LABEL = "nova-wealth-guard"
CHAT_APP_METADATA = "nova-wealth-guard"
CHAT_ENVIRONMENT_NAME = "nova-wealth-guard-managed-env"
CHAT_COORDINATOR_NAME = "Nova Wealth Guard Coordinator"
CHAT_DEFAULT_TITLE = "Nova Wealth Guard"
ANTHROPIC_API_VERSION = "2023-06-01"
MANAGED_AGENTS_BETA = "managed-agents-2026-04-01"
ANTHROPIC_API_BASE_URL = "https://api.anthropic.com/v1"
API_KEY_TOOL_NAMES = {"hypertracker", "perplexity"}
HUMAN_APPROVAL_CUSTOM_TOOLS = {
    "trading_execute_plan",
    "trading_close_position",
    "trading_set_protection",
}
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
        "name": "nova_portfolio_snapshot",
        "description": (
            "Return the current non-secret Nova Wealth Guard snapshot: risk profile, "
            "asset verification, research brief, allocation, readiness, and event log."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "type": "custom",
        "name": "nova_set_risk_profile",
        "description": (
            "Persist the user's single slider risk profile as a risk_score from 0 to 100."
        ),
        "input_schema": {
            "type": "object",
            "required": ["risk_score"],
            "properties": {
                "risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "custom",
        "name": "nova_verify_assets",
        "description": (
            "Re-check every configured workshop Hyperliquid market against metadata before "
            "research, allocation, or rebalance preparation."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "custom",
        "name": "nova_research_portfolio",
        "description": (
            "Generate a source-backed portfolio research brief using Perplexity Finance, "
            "Hyperliquid market data, and optional intelligence adapters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "custom",
        "name": "nova_allocate_portfolio",
        "description": (
            "Produce and persist a 100% long-only target allocation across active eligible "
            "markets plus USDC, enforcing the user's risk profile and cash policy."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "custom",
        "name": "nova_prepare_rebalance",
        "description": (
            "Prepare a rebalance preview for an already validated allocation. With confirmed=true "
            "and explicit host approval, submit guarded rebalance orders through the host runtime."
        ),
        "input_schema": {
            "type": "object",
            "required": ["allocation_id"],
            "properties": {
                "allocation_id": {"type": "string"},
                "confirmed": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "type": "custom",
        "name": "nova_hypertracker_intelligence",
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
        "name": "nova_perplexity_context",
        "description": (
            "Fetch Perplexity Finance context through a backend proxy. "
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
        "name": "nova_memory_note",
        "description": (
            "Record a non-secret portfolio-management lesson, rejected allocation idea, "
            "coverage gap, or process improvement for the local audit trail."
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
        "name": "nova_runtime_get_settings",
        "description": (
            "Return current non-secret runtime guardrails, workshop asset universe, "
            "network posture, and setup status."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "type": "custom",
        "name": "nova_runtime_update_settings",
        "description": (
            "Update only safe runtime settings: network, max order size, and display "
            "asset lists. Exchange URLs, workshop canonical markets, and secrets cannot be changed."
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
        "name": "nova_skill_proposal",
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
        "name": "nova_tool_proposal",
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
        "Nova Wealth Guard Safety",
        """# Nova Wealth Guard Safety

Use this skill before researching, allocating, validating, or preparing a Hyperliquid
portfolio rebalance.

- Preserve capital first, diversify second, seek moderate upside third.
- Treat every output as educational and non-advisory.
- Use USDC as cash and allow cash to be 0% to 100%.
- Keep allocations long-only, non-negative, rounded consistently, and summing to 100%.
- Use low or no leverage by default because eligible instruments are perpetual futures.
- Treat prodnet as guarded: explicit environment enablement and UI confirmation are required.
- Never ask for, store, print, or infer private keys, cookies, API keys, or seed phrases.
- Use only the configured workshop canonical market IDs plus USDC.
- Exclude missing, halted, delisted, stale, or non-allowlisted markets.
- Increase USDC when confidence is low, sources are stale, volatility is elevated, funding is
  punitive, liquidity is thin, or agents disagree.
- Rebalance preparation is not execution. Any exchange-changing action requires explicit host
  confirmation and must not be triggered by robot mode alone.
- Explain blocked actions plainly and preserve the audit trail.
""",
    ),
    "source-quality": (
        "Nova Source Quality",
        """# Market Source Quality

Use this skill when researching macro conditions, eligible markets, source freshness,
liquidity, funding, open interest, or portfolio confidence.

- Separate live market data, source-backed research, model inference, and user preference.
- Prefer Hyperliquid market data for price-sensitive claims.
- Prefer Perplexity Finance for sourced macro and public-market context when available.
- Prefer HyperTracker for optional positioning and wallet-flow signals when available.
- Cite sources by product or URL and include timestamps or freshness notes.
- State coverage gaps for HIP-3 commodities, equity-index perps, funding, open interest, and
  wallet data.
- Penalize stale, circular, unsourced, or narrative-only evidence.
""",
    ),
    "hypertracker-cli": (
        "Nova Intelligence Workflow",
        """# Nova Intelligence Workflow

Use this skill when the agent needs optional intelligence from local/backend adapters.

Primary local commands:

```bash
cd demo && uv run demo verify-assets
cd demo && uv run demo hypertracker --asset BTC
cd demo && uv run demo allocate --risk-score 70
```

Operating rules:

- Use canonical workshop market IDs for portfolio construction.
- Never pass `HYPERTRACKER_API_KEY` on the command line, in chat, or in a tool argument.
- Let the backend load credentials from `.env`, backend env, or Managed Agents Vault/MCP binding.
- Treat the command output as JSON with `asset`, `available`, `evidence`, `risks`,
  `assumptions`, and `sources`.
- If `available` is false, preserve the assumptions and do not invent HyperTracker data.
- If a key is missing, tell the user HyperTracker is unavailable instead of asking for the key.
- Use HyperTracker for optional positioning, crowding, aggregate exposure, funding impact,
  open-position count, and leaderboard wallet-flow clues.
- Do not treat HyperTracker as a standalone allocation signal. Cross-check with
  `nova_portfolio_snapshot`, Hyperliquid metadata, risk limits, and source-backed research.
- Include HyperTracker findings as evidence or risk inputs in the allocation explanation.
- If shell access to the local repo is not available inside the Claude sandbox, call the
  `nova_hypertracker_intelligence` custom tool instead.
- For MCP-backed HyperTracker, prefer the MCP tool only when its Vault status is connected;
  otherwise use the backend CLI/custom-tool path.

Decision rubric:

- Thin liquidity, punitive funding, stale context, or large source gaps increase USDC.
- Crowded exposure reduces confidence unless independent evidence supports the risk.
- Partial endpoint failures must lower confidence and be recorded in coverage gaps.
""",
    ),
    "trade-validation": (
        "Portfolio Allocation Rules",
        """# Portfolio Allocation Rules

Use this skill before producing a target allocation.

- Map the slider directly to `risk_score` from 0 to 100.
- Risk score 0-35: minimum USDC 40%, max single asset 12%, max BTC 5%,
  max equity-index exposure 30%, max commodity exposure 45%.
- Risk score 36-70: minimum USDC 25%, max single asset 18%, max BTC 8%,
  max equity-index exposure 45%, max commodity exposure 55%.
- Risk score 71-100: minimum USDC 10%, max single asset 25%, max BTC 12%,
  max equity-index exposure 60%, max commodity exposure 65%.
- The safety agent may increase cash above the minimum.
- Apply single-asset, category, BTC, leverage, liquidity, open-interest, and funding caps.
- If evidence is weak or hostile, recommending 100% USDC is acceptable.
""",
    ),
    "formal-order-validation": (
        "Rebalance Approval Boundary",
        """# Rebalance Approval Boundary

Use this skill before preparing or discussing a rebalance.

- First create a validated allocation with `nova_allocate_portfolio`.
- Use `nova_prepare_rebalance` for a pending-approval preview first. Submit with
  `confirmed=true` only when the host has explicitly confirmed the action.
- Do not submit or simulate exchange-changing actions from prose, background jobs, chat, or
  robot mode alone.
- Validate active markets, account state, current positions, available margin, minimum order
  sizes, expected slippage, and rebalance deltas before order construction.
- Block arbitrary exchange URLs, non-allowlisted canonical IDs, delisted markets, missing
  credentials, unsafe leverage, and any proposal that cannot be fully validated.
- If credentials are missing, keep the allocation useful but mark it non-executable.
""",
    ),
    "self-improvement": (
        "Nova Process Improvement",
        """# Nova Process Improvement

Use this skill throughout the conversation.

- Track rejected ideas, user corrections, source gaps, validation failures, and rehearsal lessons.
- Propose new skills or tools when repeated gaps appear.
- Do not mutate host code. Use skill/tool proposal custom tools for reviewable improvements.
- Write durable learning only to the read-write memory store and never write secrets.
- Use outcomes and rubrics for high-stakes portfolio analyses before proposing action.
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
    "formal-order-validation": (
        "Use before preparing a rebalance or discussing exchange-changing actions."
    ),
    "self-improvement": (
        "Use throughout Nova conversations to capture lessons and propose safe improvements."
    ),
}


SUBAGENT_SPECS: dict[str, tuple[str, str]] = {
    "research": (
        "Nova Wealth Guard Research Agent",
        "Summarize macro context, asset signals, liquidity, funding, and coverage gaps.",
    ),
    "portfolio": (
        "Nova Wealth Guard Portfolio Agent",
        "Apply risk score, diversification rules, cash policy, and allocation math.",
    ),
    "safety": (
        "Nova Wealth Guard Safety Agent",
        "Validate active markets, caps, long-only math, credentials, and approval gates.",
    ),
    "auditor": (
        "Nova Wealth Guard Source Auditor",
        "Grade source freshness, evidence quality, coverage gaps, and non-advisory language.",
    ),
    "toolsmith": (
        "Nova Wealth Guard Toolsmith",
        "Identify missing skills/tools and record reviewable improvement proposals.",
    ),
}


COORDINATOR_SYSTEM = """You are Nova Wealth Guard, a Claude Managed Agents coordinator for a
conservative, educational Hyperliquid USDC portfolio manager.

Operate with maximum autonomy inside the Claude Managed Agents sandbox: research, calculate, write
scratch files, use web tools, delegate to subagents, use memory, create outcome loops, and call the
provided custom tools. You may self-improve by proposing skills and tools, but host code changes
must remain reviewable.

Product intent:
- Preserve capital first, diversify second, seek moderate upside third.
- Build 100% target allocations across USDC plus active eligible Hyperliquid markets.
- Ask for only one initial risk input: a 0-100 score derived from the user's slider.
- Default conservative even when the risk score is high because the instruments are perpetuals.
- Be comfortable recommending 100% USDC when evidence is weak or conditions are hostile.
- Never present output as personal financial advice.

Hard boundaries:
- Do not request, reveal, infer, or persist secrets.
- Do not invent exchange access or arbitrary URLs.
- Always respond in English, even when the user writes in another language.
- Use only the verified workshop canonical market IDs plus USDC.
- Keep allocations long-only, non-negative, rounded consistently, and summing exactly to 100%.
- Re-check Hyperliquid metadata before allocation and before rebalance preparation.
- Prodnet execution requires explicit environment enablement and UI confirmation. Robot mode,
  chat messages, and background jobs are not approval.
- Keep private keys, API keys, cookies, browser data, raw wallet payloads, and generated local
  state out of responses.

Default workflow:
1. Call `nova_portfolio_snapshot` to understand current local state.
2. If the user provides risk as x/10, convert it to risk_score=x*10 and call
   `nova_set_risk_profile`.
3. Call `nova_verify_assets` before research/allocation.
4. Call `nova_research_portfolio` to collect source summaries and coverage gaps.
5. Call `nova_allocate_portfolio` to produce the structured 100% allocation.
6. Delegate research, portfolio, safety, auditor, or toolsmith work when it improves quality.
7. Use `nova_prepare_rebalance` first for a pending-approval preview. Use `confirmed=true`
   only when explicit host/user confirmation is present and all guardrails pass.
8. After each run, use `nova_memory_note` and the learning memory store to record non-secret
   lessons from source gaps, validation failures, rejected allocations, and missed assumptions.
"""


class ManagedTradingChatService:
    def __init__(
        self,
        settings: Settings | None = None,
        store: JsonStore | None = None,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        base_settings = settings or get_settings()
        self.settings = (
            base_settings.model_copy(
                update={"anthropic_api_key": base_settings.workshop_anthropic_api_key}
            )
            if base_settings.has_workshop_anthropic_credentials
            else base_settings
        )
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
            "deployment": self.deployment(),
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

    def deployment(self) -> ManagedChatDeployment:
        return self.store.get(
            "managed_chat_deployments",
            CHAT_DEPLOYMENT_ID,
        ) or self._default_deployment()

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

    async def create_deployment(
        self,
        name: str | None = None,
        cron_expression: str | None = None,
        timezone: str | None = None,
        initial_prompt: str | None = None,
    ) -> ManagedChatDeployment:
        resources = self.resources()
        deployment = self._deployment_from_inputs(name, cron_expression, timezone, initial_prompt)
        if resources.status != "ready":
            deployment.status = "error"
            deployment.last_error = (
                resources.disabled_reason or resources.error or "Resources not ready."
            )
            return self.store.save("managed_chat_deployments", deployment)
        if not self.settings.has_anthropic_credentials:
            deployment.status = "error"
            deployment.last_error = "ANTHROPIC_API_KEY is missing."
            return self.store.save("managed_chat_deployments", deployment)
        try:
            return await asyncio.to_thread(self._create_remote_deployment, resources, deployment)
        except Exception as exc:  # pragma: no cover - beta API failures are environment-specific.
            deployment.status = "error"
            deployment.last_error = str(exc)
            deployment.updated_at = utc_now()
            return self.store.save("managed_chat_deployments", deployment)

    async def run_deployment(self) -> ManagedChatDeployment:
        deployment = self.deployment()
        if not deployment.anthropic_deployment_id:
            deployment.status = "error"
            deployment.last_error = "Create the Claude deployment before running it."
            deployment.updated_at = utc_now()
            return self.store.save("managed_chat_deployments", deployment)
        if not self.settings.has_anthropic_credentials:
            deployment.status = "error"
            deployment.last_error = "ANTHROPIC_API_KEY is missing."
            deployment.updated_at = utc_now()
            return self.store.save("managed_chat_deployments", deployment)
        try:
            return await asyncio.to_thread(self._run_remote_deployment, deployment)
        except Exception as exc:  # pragma: no cover - beta API failures are environment-specific.
            deployment.status = "error"
            deployment.last_error = str(exc)
            deployment.updated_at = utc_now()
            return self.store.save("managed_chat_deployments", deployment)

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
        tool_runner: ToolRunner | None = None,
    ) -> ManagedChatSession:
        session = self._session_or_404(session_id)
        pending_custom_tool = self._pending_custom_tool_event(session_id, tool_use_id)
        if pending_custom_tool:
            pending_custom_tool.requires_action = False
            self.store.save("managed_chat_events", pending_custom_tool)
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
            if not allow:
                result = {"error": deny_message or "Trade execution denied by human operator."}
                self._send_custom_tool_result(
                    client,
                    session,
                    pending_custom_tool.payload,
                    result,
                    is_error=True,
                )
                session.status = "idle"
                session.updated_at = utc_now()
                self.store.save("managed_chat_sessions", session)
                return session
            if not tool_runner:
                self._send_custom_tool_result(
                    client,
                    session,
                    pending_custom_tool.payload,
                    {"error": "No backend tool runner is available for this approval."},
                    is_error=True,
                )
                session.status = "error"
                session.last_error = "No backend tool runner is available for this approval."
                session.updated_at = utc_now()
                self.store.save("managed_chat_sessions", session)
                return session
            approved_event = dict(pending_custom_tool.payload)
            payload = approved_event.get("input")
            if not isinstance(payload, dict):
                payload = {}
            payload = dict(payload)
            payload["confirmed"] = True
            approved_event["input"] = payload
            approved_event["host_human_approved"] = True
            self._handle_custom_tool(client, session, approved_event, tool_runner)
            session.status = "idle"
            session.updated_at = utc_now()
            self.store.save("managed_chat_sessions", session)
            return session
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

    def _pending_custom_tool_event(
        self,
        session_id: str,
        tool_use_id: str,
    ) -> ManagedChatEvent | None:
        for event in self.events(session_id):
            if not event.requires_action or event.type != "agent.custom_tool_use":
                continue
            payload = event.payload
            candidate_id = str(payload.get("id") or payload.get("custom_tool_use_id") or "")
            if candidate_id == tool_use_id:
                return event
        return None

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
        environment = _find_latest_named_resource(
            client.beta.environments,
            CHAT_ENVIRONMENT_NAME,
            metadata={"app": CHAT_APP_METADATA, "component": CHAT_AGENT_RUN_LABEL},
        )
        if not environment:
            environment = client.beta.environments.create(
                name=CHAT_ENVIRONMENT_NAME,
                description="Sandbox for autonomous Nova Wealth Guard portfolio sessions.",
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
                metadata={"app": CHAT_APP_METADATA, "component": CHAT_AGENT_RUN_LABEL},
            )
        skill_ids, skill_versions = self._create_skills(client)
        memory_store_ids = self._create_memory_stores(client)
        vault_ids, credentials = self._prepare_vaults(client)
        mcp_servers = self.settings.managed_chat_mcp_servers
        tools = self._agent_tools(mcp_servers)
        skills = [{"type": "custom", "skill_id": skill_id} for skill_id in skill_ids.values()]

        subagent_ids: dict[str, str] = {}
        for slug, (name, role) in SUBAGENT_SPECS.items():
            agent = _find_latest_named_resource(
                client.beta.agents,
                name,
                metadata={"app": CHAT_APP_METADATA, "role": slug},
            )
            if not agent:
                agent = client.beta.agents.create(
                    name=name,
                    model=self.settings.managed_chat_model,
                    description=role,
                    system=f"{role}\n\n{COORDINATOR_SYSTEM}",
                    tools=tools[:1],
                    skills=skills,
                    metadata={"app": CHAT_APP_METADATA, "role": slug},
                )
            subagent_ids[slug] = _object_id(agent)

        coordinator = _find_latest_named_resource(
            client.beta.agents,
            CHAT_COORDINATOR_NAME,
            metadata={"app": CHAT_APP_METADATA, "role": "coordinator"},
        )
        if not coordinator:
            coordinator = client.beta.agents.create(
                name=CHAT_COORDINATOR_NAME,
                model=self.settings.managed_chat_model,
                description=(
                    "Autonomous Managed Agents portfolio coordinator with guarded custom tools, "
                    "Vault-backed MCP support, memory, outcomes, and a "
                    "research/portfolio/safety team."
                ),
                system=COORDINATOR_SYSTEM,
                tools=tools,
                mcp_servers=mcp_servers,
                skills=skills,
                multiagent={"type": "coordinator", "agents": list(subagent_ids.values())},
                metadata={"app": CHAT_APP_METADATA, "role": "coordinator"},
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
            title=title or CHAT_DEFAULT_TITLE,
            metadata={"app": CHAT_APP_METADATA, "component": CHAT_AGENT_RUN_LABEL},
            resources=self._session_resources(resources),
            vault_ids=resources.vault_ids,
        )
        record = ManagedChatSession(
            title=title or CHAT_DEFAULT_TITLE,
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

    def _create_remote_deployment(
        self,
        resources: ManagedChatResources,
        deployment: ManagedChatDeployment,
    ) -> ManagedChatDeployment:
        payload = {
            "name": deployment.name,
            "agent": resources.coordinator_agent_id or "",
            "environment_id": resources.environment_id or "",
            "initial_events": [_user_message_event(deployment.initial_prompt)],
            "schedule": {
                "type": "cron",
                "expression": deployment.cron_expression,
                "timezone": deployment.timezone,
            },
            "resources": self._session_resources(resources),
            "vault_ids": resources.vault_ids,
            "metadata": {"app": CHAT_APP_METADATA, "component": CHAT_AGENT_RUN_LABEL},
        }
        result = self._anthropic_json_request("POST", "/deployments", payload)
        deployment.anthropic_deployment_id = str(result.get("id") or "")
        deployment.status = _deployment_status(result)
        deployment.paused_reason = result.get("paused_reason")
        deployment.agent_id = resources.coordinator_agent_id
        deployment.environment_id = resources.environment_id
        deployment.upcoming_runs_at = _upcoming_runs(result)
        deployment.raw_response = _safe_payload(result)
        deployment.last_error = None
        deployment.updated_at = utc_now()
        return self.store.save("managed_chat_deployments", deployment)

    def _run_remote_deployment(
        self,
        deployment: ManagedChatDeployment,
    ) -> ManagedChatDeployment:
        result = self._anthropic_json_request(
            "POST",
            f"/deployments/{deployment.anthropic_deployment_id}/run",
            {},
        )
        deployment.last_run_id = str(result.get("id") or deployment.last_run_id or "")
        deployment.last_session_id = str(
            result.get("session_id") or deployment.last_session_id or ""
        )
        deployment.raw_response = _safe_payload(result)
        deployment.last_error = _deployment_run_error(result)
        deployment.updated_at = utc_now()
        return self.store.save("managed_chat_deployments", deployment)

    def _anthropic_json_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        api_key = self.settings.anthropic_api_key
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is missing.")
        body = json.dumps(payload or {}).encode("utf-8")
        request = urllib.request.Request(
            f"{ANTHROPIC_API_BASE_URL}{path}",
            data=body,
            method=method,
            headers={
                "anthropic-version": ANTHROPIC_API_VERSION,
                "anthropic-beta": MANAGED_AGENTS_BETA,
                "x-api-key": api_key.get_secret_value(),
                "content-type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Anthropic deployment API error {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Anthropic deployment API unavailable: {exc.reason}") from exc
        parsed = json.loads(data) if data else {}
        if not isinstance(parsed, dict):
            raise RuntimeError("Anthropic deployment API returned an unexpected payload.")
        return parsed

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
        pending_local_action = False
        for raw_event in stream:
            event = _event_dict(raw_event)
            event_type = event.get("type", "unknown")
            text = _event_text(event)
            requires_action = self._custom_tool_requires_human_approval(event_type, event)
            pending_local_action = pending_local_action or requires_action
            self.append_event(
                session.id,
                event_type,
                text,
                level="error" if event_type == "session.error" else "info",
                role=_event_role(event_type),
                payload=event,
                requires_action=requires_action,
            )
            if event_type == "agent.custom_tool_use" and tool_runner and not requires_action:
                self._handle_custom_tool(client, session, event, tool_runner)
            if event_type == "session.status_running":
                session.status = "running"
            if event_type == "session.status_idle":
                session.status = "waiting_action" if pending_local_action else "idle"
                if not _requires_action(event) or not pending_local_action:
                    break
            if event_type == "session.status_terminated":
                session.status = "terminated"
                break
            if event_type == "session.error":
                session.status = "error"
                session.last_error = text or "Claude session error."
                break
        self.store.save("managed_chat_sessions", session)

    def _custom_tool_requires_human_approval(
        self,
        event_type: str,
        event: dict[str, Any],
    ) -> bool:
        if event_type != "agent.custom_tool_use":
            return False
        if str(event.get("name") or "") not in HUMAN_APPROVAL_CUSTOM_TOOLS:
            return False
        return self.store.runtime_settings().ui_mode == UIMode.human

    def _handle_custom_tool(
        self,
        client: Any,
        session: ManagedChatSession,
        event: dict[str, Any],
        tool_runner: ToolRunner,
    ) -> None:
        try:
            result = tool_runner(session, event)
            is_error = False
        except Exception as exc:
            result = {"error": str(exc)}
            is_error = True
        self._send_custom_tool_result(client, session, event, result, is_error=is_error)

    def _send_custom_tool_result(
        self,
        client: Any,
        session: ManagedChatSession,
        event: dict[str, Any],
        result: dict[str, Any],
        *,
        is_error: bool,
    ) -> None:
        tool_use_id = str(event.get("id") or event.get("custom_tool_use_id") or "")
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
        with tempfile.TemporaryDirectory(prefix="nova-wealth-guard-skills-") as tmp:
            root = Path(tmp)
            for slug, (title, body) in SKILL_SPECS.items():
                skill = _find_latest_titled_resource(client.beta.skills, title)
                if not skill:
                    skill_dir = root / slug
                    skill_dir.mkdir()
                    skill_path = skill_dir / "SKILL.md"
                    content = _skill_markdown(slug, body)
                    skill_path.write_text(content, encoding="utf-8")
                    skill = client.beta.skills.create(
                        display_title=title,
                        files=files_from_dir(skill_dir),
                    )
                skill_ids[slug] = _object_id(skill)
                version = _object_version(skill)
                if version is not None:
                    skill_versions[slug] = version
        return skill_ids, skill_versions

    def _create_memory_stores(self, client: Any) -> dict[str, str]:
        canon, canon_created = self._ensure_memory_store(
            client,
            name="Nova Wealth Guard Canon",
            description=(
                "Read-only operating canon: portfolio guardrails, allowed market boundaries, "
                "cash policy, and safety principles."
            ),
            kind="canon",
        )
        learning, learning_created = self._ensure_memory_store(
            client,
            name="Nova Wealth Guard Conversation Learning",
            description=(
                "Read-write user preferences, rejected allocations, source-gap lessons, "
                "and proposed process improvements. Never store secrets."
            ),
            kind="learning",
        )
        ids = {"canon": _object_id(canon), "learning": _object_id(learning)}
        if canon_created:
            self._seed_memory(
                client,
                ids["canon"],
                "/canon/safety.md",
                SKILL_SPECS["hyperliquid-safety"][1],
            )
        if learning_created:
            self._seed_memory(
                client,
                ids["learning"],
                "/learning/README.md",
                (
                    "# Conversation Learning\n\n"
                    "Store user preferences, repeated mistakes, rejected allocations, source-gap "
                    "lessons here. Do not store API keys, private keys, cookies, or credentials.\n"
                ),
            )
        return ids

    def _ensure_memory_store(
        self,
        client: Any,
        *,
        name: str,
        description: str,
        kind: str,
    ) -> tuple[Any, bool]:
        store = _find_latest_named_resource(
            client.beta.memory_stores,
            name,
            metadata={"app": CHAT_APP_METADATA, "kind": kind},
        )
        if store:
            return store, False
        return (
            client.beta.memory_stores.create(
                name=name,
                description=description,
                metadata={"app": CHAT_APP_METADATA, "kind": kind},
            ),
            True,
        )

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
                        metadata={"app": CHAT_APP_METADATA, "tool": status.name},
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
        remote = _find_latest_named_resource(
            client.beta.vaults,
            "Nova Wealth Guard API-Key Tools",
            metadata={"app": CHAT_APP_METADATA, "component": CHAT_AGENT_RUN_LABEL},
        )
        if remote:
            return _object_id(remote)
        vault = client.beta.vaults.create(
            display_name="Nova Wealth Guard API-Key Tools",
            metadata={"app": CHAT_APP_METADATA, "component": CHAT_AGENT_RUN_LABEL},
        )
        return _object_id(vault)

    def _existing_managed_vault_id(self) -> str:
        # Vault IDs are workspace-scoped and may be write-only or inaccessible when the
        # workshop API key points at a different Claude workspace. Always re-discover by
        # stable Nova Vault name before reusing a locally persisted ID.
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
                    "instructions": "Use as immutable Nova Wealth Guard safety canon.",
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
                        "Store non-secret user preferences, rejected allocations, source gaps, "
                        "and process improvements."
                    ),
                }
            )
        return attached

    def _default_deployment(self) -> ManagedChatDeployment:
        return ManagedChatDeployment(
            id=CHAT_DEPLOYMENT_ID,
            name="Nova Wealth Guard portfolio watch",
            cron_expression="*/30 * * * *",
            timezone="Europe/Madrid",
            initial_prompt=_default_deployment_prompt(),
        )

    def _deployment_from_inputs(
        self,
        name: str | None,
        cron_expression: str | None,
        timezone: str | None,
        initial_prompt: str | None,
    ) -> ManagedChatDeployment:
        existing = self.deployment()
        deployment = ManagedChatDeployment(
            id=CHAT_DEPLOYMENT_ID,
            name=(name or existing.name).strip(),
            cron_expression=(cron_expression or existing.cron_expression).strip(),
            timezone=(timezone or existing.timezone).strip(),
            initial_prompt=(initial_prompt or existing.initial_prompt).strip(),
        )
        if not deployment.name:
            raise ValueError("Deployment name is required.")
        if not _valid_cron_expression(deployment.cron_expression):
            raise ValueError("Deployment cron expression must have five POSIX fields.")
        if not deployment.timezone or "/" not in deployment.timezone:
            raise ValueError("Deployment timezone must be an IANA timezone such as Europe/Madrid.")
        if not deployment.initial_prompt:
            raise ValueError("Deployment initial prompt is required.")
        return deployment

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


def _user_message_event(text: str) -> dict[str, Any]:
    return {
        "type": "user.message",
        "content": [{"type": "text", "text": text}],
    }


def _default_deployment_prompt() -> str:
    return (
        "Run the scheduled Nova Wealth Guard portfolio watch. Gather the saved risk profile, "
        "workshop asset verification, Hyperliquid market context, Perplexity/HyperTracker "
        "coverage, source freshness, and current allocation. Produce or refresh a 100% "
        "educational target allocation only when the eligible market universe validates. Keep "
        "USDC high when evidence is weak or hostile. Do not submit or modify exchange orders "
        "without explicit host human approval. Record non-secret lessons from source gaps, "
        "failed validations, rejected allocations, and missed assumptions."
    )


def _valid_cron_expression(value: str) -> bool:
    return len([part for part in value.split() if part]) == 5


def _deployment_status(payload: dict[str, Any]) -> str:
    raw_status = str(payload.get("status") or "").lower()
    if raw_status in {"active", "paused", "archived", "error"}:
        return raw_status
    if payload.get("paused_reason"):
        return "paused"
    return "active" if payload.get("id") else "error"


def _upcoming_runs(payload: dict[str, Any]) -> list[str]:
    schedule = payload.get("schedule")
    if not isinstance(schedule, dict):
        return []
    runs = schedule.get("upcoming_runs_at")
    if not isinstance(runs, list):
        return []
    return [str(item) for item in runs]


def _deployment_run_error(payload: dict[str, Any]) -> str | None:
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    message = error.get("message") or error.get("type")
    return str(message) if message else "Deployment run failed."


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


def _find_latest_named_resource(
    api: Any,
    name: str,
    *,
    metadata: dict[str, str] | None = None,
) -> Any | None:
    matches = [
        item
        for item in _list_resource_page(api)
        if _resource_name(item) == name and _metadata_matches(item, metadata or {})
    ]
    if not matches:
        return None
    return sorted(matches, key=_created_sort_key)[-1]


def _find_latest_titled_resource(api: Any, title: str) -> Any | None:
    matches = [
        item
        for item in _list_resource_page(api)
        if _resource_name(item) == title or _resource_name(item).startswith(f"{title} (")
    ]
    if not matches:
        return None
    return sorted(matches, key=_created_sort_key)[-1]


def _list_resource_page(api: Any) -> list[Any]:
    page = api.list(limit=100)
    if hasattr(page, "data"):
        return list(page.data)
    return list(page)


def _resource_name(item: Any) -> str:
    for attr in ("name", "display_name", "display_title", "title"):
        value = getattr(item, attr, None)
        if value:
            return str(value)
    return ""


def _metadata_matches(item: Any, expected: dict[str, str]) -> bool:
    metadata = getattr(item, "metadata", None) or {}
    return all(str(metadata.get(key) or "") == value for key, value in expected.items())


def _created_sort_key(item: Any) -> str:
    return str(getattr(item, "created_at", "") or "")


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
