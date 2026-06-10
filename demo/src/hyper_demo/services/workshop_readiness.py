from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from hyper_demo.adapters.hyperliquid import HyperliquidAdapter
from hyper_demo.adapters.privy_hyperliquid import PrivyHyperliquidAdapter
from hyper_demo.config import Settings, get_settings
from hyper_demo.models import ManagedChatResources, utc_now
from hyper_demo.services.hypertracker import HyperTrackerClient
from hyper_demo.services.managed_chat import ManagedTradingChatService
from hyper_demo.services.market import MarketDataClient
from hyper_demo.services.perplexity import PerplexityFinanceClient
from hyper_demo.storage import JsonStore

WORKSHOP_ROOT = Path(__file__).resolve().parents[4] / "workshop"
WORKSHOP_REQUIRED_FILES = ("design.md", "initial-goal-prompt.md", "index.html")


class WorkshopIntegrationCheck(BaseModel):
    name: str
    status: Literal["ready", "warning", "blocked"]
    configured: bool
    required: bool = True
    detail: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkshopReadiness(BaseModel):
    generated_at: str
    status: Literal["ready", "warning", "blocked"]
    workspace: dict[str, Any]
    anthropic_workspace: dict[str, Any]
    checks: list[WorkshopIntegrationCheck]
    warnings: list[str]


def workshop_readiness(store: JsonStore | None = None) -> WorkshopReadiness:
    settings = _settings_for_workshop(get_settings())
    store = store or JsonStore(settings)
    warnings: list[str] = []
    resources = ManagedTradingChatService(settings, store).resources()
    checks = [
        _workshop_files_check(),
        _workshop_tradeable_assets_check(settings),
        _anthropic_check(settings, resources),
        _hyperliquid_market_check(settings),
        _wallet_balance_check(settings, store),
        _perplexity_check(settings),
        _hypertracker_check(settings),
        _privy_check(settings),
    ]
    warnings.extend(_setup_warnings(settings))
    return WorkshopReadiness(
        generated_at=utc_now().isoformat(),
        status=_rollup_status(checks),
        workspace={
            "name": "workshop",
            "path": str(WORKSHOP_ROOT),
            "exists": WORKSHOP_ROOT.exists(),
            "design_path": str(WORKSHOP_ROOT / "design.md"),
            "prompt_path": str(WORKSHOP_ROOT / "initial-goal-prompt.md"),
            "runtime_source": "workshop_environment",
            "workshop_tradeable_assets": settings.workshop_allowed_assets_list,
            "demo_tradeable_assets": settings.allowed_assets_list,
            "assets_distinct_from_demo": set(settings.workshop_allowed_assets_list)
            != set(settings.allowed_assets_list),
        },
        anthropic_workspace=_anthropic_workspace(settings, resources),
        checks=checks,
        warnings=warnings,
    )


def _settings_for_workshop(settings: Settings) -> Settings:
    if settings.has_workshop_anthropic_credentials:
        return settings.model_copy(
            update={"anthropic_api_key": settings.workshop_anthropic_api_key}
        )
    return settings


def _workshop_tradeable_assets_check(settings: Settings) -> WorkshopIntegrationCheck:
    workshop_assets = settings.workshop_allowed_assets_list
    demo_assets = settings.allowed_assets_list
    distinct = set(workshop_assets) != set(demo_assets)
    if not workshop_assets:
        status: Literal["ready", "warning", "blocked"] = "blocked"
        detail = "WORKSHOP_HYPERLIQUID_ALLOWED_ASSETS is empty."
    elif not distinct:
        status = "blocked"
        detail = (
            "Workshop tradeable assets match the demo allowed assets. "
            "Use a separate workshop universe."
        )
    else:
        status = "ready"
        detail = (
            f"{len(workshop_assets)} workshop tradeable assets are configured separately "
            "from the demo."
        )
    return WorkshopIntegrationCheck(
        name="Workshop tradeable assets",
        status=status,
        configured=bool(workshop_assets) and distinct,
        required=True,
        detail=detail,
        metadata={
            "configured_assets": workshop_assets,
            "demo_configured_assets": demo_assets,
            "distinct_from_demo_assets": distinct,
        },
    )


def _setup_warnings(settings: Settings) -> list[str]:
    warnings: list[str] = []
    if not settings.has_anthropic_credentials:
        warnings.append("ANTHROPIC_API_KEY is missing; research will use fallback output.")
    if not settings.workshop_anthropic_workspace_id:
        warnings.append(
            "WORKSHOP_ANTHROPIC_WORKSPACE_ID is missing; the workshop Claude workspace "
            "cannot be verified."
        )
    if (
        settings.anthropic_workspace_id
        and settings.workshop_anthropic_workspace_id
        and settings.anthropic_workspace_id == settings.workshop_anthropic_workspace_id
    ):
        warnings.append(
            "The workshop Claude workspace matches ANTHROPIC_WORKSPACE_ID; configure a "
            "separate demo workspace before the workshop."
        )
    if not settings.has_hypertracker_credentials:
        warnings.append("HYPERTRACKER_API_KEY is missing; market intelligence enrichment disabled.")
    if not settings.has_perplexity_credentials:
        warnings.append("PERPLEXITY_API_KEY is missing; finance_search enrichment disabled.")
    if not settings.has_hyperliquid_credentials and not (
        settings.privy_execution_enabled and settings.has_privy_server_credentials
    ):
        warnings.append("Hyperliquid credentials are missing; exchange execution is blocked.")
    if settings.is_mainnet_mode and not settings.hyperliquid_mainnet_enabled:
        warnings.append(
            "Mainnet selected for market data. Execution remains blocked until "
            "HYPERLIQUID_MAINNET_ENABLED=true."
        )
    if settings.is_mainnet_mode and not settings.demo_require_confirmation:
        warnings.append("Mainnet mode should keep DEMO_REQUIRE_CONFIRMATION=true.")
    if settings.privy_execution_enabled and not settings.has_privy_server_credentials:
        warnings.append("Privy execution is enabled, but PRIVY_APP_SECRET is missing.")
    return warnings


def _rollup_status(
    checks: list[WorkshopIntegrationCheck],
) -> Literal["ready", "warning", "blocked"]:
    if any(check.required and check.status == "blocked" for check in checks):
        return "blocked"
    if any(check.status != "ready" for check in checks):
        return "warning"
    return "ready"


def _workshop_files_check() -> WorkshopIntegrationCheck:
    files = []
    missing = []
    for name in WORKSHOP_REQUIRED_FILES:
        path = WORKSHOP_ROOT / name
        exists = path.exists()
        files.append(
            {
                "name": name,
                "path": str(path),
                "exists": exists,
                "size_bytes": path.stat().st_size if exists else None,
            }
        )
        if not exists:
            missing.append(name)
    status: Literal["ready", "warning", "blocked"] = "ready" if not missing else "blocked"
    detail = (
        "Workshop prompt assets are present."
        if not missing
        else f"Missing workshop files: {', '.join(missing)}."
    )
    return WorkshopIntegrationCheck(
        name="Workshop assets",
        status=status,
        configured=not missing,
        required=True,
        detail=detail,
        metadata={"files": files},
    )


def _anthropic_check(
    settings: Settings,
    resources: ManagedChatResources,
) -> WorkshopIntegrationCheck:
    workspace_metadata = _anthropic_workspace(settings, resources)
    if not settings.has_anthropic_credentials:
        return WorkshopIntegrationCheck(
            name="Anthropic Managed Agents",
            status="blocked",
            configured=False,
            required=True,
            detail="ANTHROPIC_API_KEY is missing.",
            metadata=workspace_metadata,
        )
    if not settings.workshop_anthropic_workspace_id:
        return WorkshopIntegrationCheck(
            name="Anthropic Managed Agents",
            status="blocked",
            configured=False,
            required=True,
            detail="WORKSHOP_ANTHROPIC_WORKSPACE_ID is missing.",
            metadata=workspace_metadata,
        )
    if (
        settings.anthropic_workspace_id
        and settings.anthropic_workspace_id == settings.workshop_anthropic_workspace_id
    ):
        return WorkshopIntegrationCheck(
            name="Anthropic Managed Agents",
            status="blocked",
            configured=False,
            required=True,
            detail=(
                "The workshop Claude workspace is the same as the demo workspace. "
                "Use a distinct workspace for workshop Managed Agents resources."
            ),
            metadata=workspace_metadata,
        )
    if resources.status == "ready":
        detail = "Managed Agents resources are ready for the configured workshop Claude workspace."
        if not settings.anthropic_workspace_id:
            detail = (
                "Managed Agents resources are ready for the workshop Claude workspace. "
                "Demo workspace comparison is skipped because ANTHROPIC_WORKSPACE_ID is not set."
            )
        return WorkshopIntegrationCheck(
            name="Anthropic Managed Agents",
            status="ready",
            configured=True,
            required=True,
            detail=detail,
            metadata=workspace_metadata,
        )
    status: Literal["ready", "warning", "blocked"] = "warning"
    detail = resources.disabled_reason or resources.error or (
        "Managed Agents are configured but have not been bootstrapped yet."
    )
    if resources.status == "error":
        status = "blocked"
    return WorkshopIntegrationCheck(
        name="Anthropic Managed Agents",
        status=status,
        configured=True,
        required=True,
        detail=detail,
        metadata=workspace_metadata,
    )


def _anthropic_workspace(
    settings: Settings,
    resources: ManagedChatResources,
) -> dict[str, Any]:
    environment_id = resources.environment_id or settings.anthropic_environment_id
    agent_id = resources.coordinator_agent_id or settings.anthropic_agent_id
    workshop_workspace_id = settings.workshop_anthropic_workspace_id
    demo_workspace_id = settings.anthropic_workspace_id
    demo_workspace_url = (
        f"https://platform.claude.com/workspaces/{demo_workspace_id}/sessions"
        if demo_workspace_id
        else None
    )
    distinct_from_demo_workspace: bool | None
    if workshop_workspace_id and demo_workspace_id:
        distinct_from_demo_workspace = workshop_workspace_id != demo_workspace_id
    else:
        distinct_from_demo_workspace = None
    if resources.environment_id:
        source = "persisted_managed_agents_resources"
    elif settings.anthropic_environment_id or settings.anthropic_agent_id:
        source = "environment_variables"
    else:
        source = "not_bootstrapped"
    return {
        "local_workspace": str(WORKSHOP_ROOT),
        "expected_workspace_id": workshop_workspace_id,
        "expected_workspace_url": settings.workshop_anthropic_workspace_url,
        "demo_workspace_id": demo_workspace_id,
        "demo_workspace_url": demo_workspace_url,
        "distinct_from_demo_workspace": distinct_from_demo_workspace,
        "api_key_source": settings.workshop_anthropic_api_key_source,
        "resource_status": resources.status,
        "source": source,
        "model": settings.managed_chat_model,
        "auto_bootstrap": settings.anthropic_chat_auto_bootstrap,
        "environment_id": environment_id,
        "coordinator_agent_id": agent_id,
        "subagent_ids": resources.subagent_ids,
        "vault_ids": resources.vault_ids,
        "mcp_servers": resources.mcp_servers,
        "custom_tools": resources.custom_tools,
        "error": resources.error,
    }


def _hyperliquid_market_check(settings: Settings) -> WorkshopIntegrationCheck:
    configured_assets = settings.workshop_allowed_assets_list
    probe_asset = (
        "BTC" if "BTC" in configured_assets else (configured_assets[0] if configured_assets else "")
    )
    if not probe_asset:
        return WorkshopIntegrationCheck(
            name="Hyperliquid market data",
            status="blocked",
            configured=False,
            required=True,
            detail="No workshop assets are configured for Hyperliquid verification.",
            metadata={
                "base_url": settings.hyperliquid_base_url,
                "ws_url": settings.hyperliquid_ws_url,
                "configured_assets": configured_assets,
            },
        )
    try:
        market = MarketDataClient(settings)
        probe_price = market.mark_price(probe_asset)
        available_assets = market.available_assets()
    except Exception as exc:  # pragma: no cover - network failures are environment-specific.
        return WorkshopIntegrationCheck(
            name="Hyperliquid market data",
            status="blocked",
            configured=False,
            required=True,
            detail=f"Could not verify Hyperliquid market data: {exc}",
            metadata={
                "base_url": settings.hyperliquid_base_url,
                "ws_url": settings.hyperliquid_ws_url,
                "configured_assets": configured_assets,
                "demo_configured_assets": settings.allowed_assets_list,
            },
        )
    active_symbols = {asset.symbol for asset in available_assets if not asset.delisted}
    missing = [asset for asset in configured_assets if asset not in active_symbols]
    status: Literal["ready", "warning", "blocked"] = "ready"
    if probe_price.source != "hyperliquid":
        status = "blocked"
    elif missing:
        status = "blocked"
    detail = (
        f"{len(configured_assets)} workshop markets verified on Hyperliquid."
        if status == "ready"
        else "Hyperliquid responded, but one or more workshop markets could not be verified."
    )
    return WorkshopIntegrationCheck(
        name="Hyperliquid market data",
        status=status,
        configured=status == "ready",
        required=True,
        detail=detail,
        metadata={
            "environment": settings.hyperliquid_environment,
            "base_url": settings.hyperliquid_base_url,
            "ws_url": settings.hyperliquid_ws_url,
            "probe_asset": probe_asset,
            "probe_mark_price": probe_price.mark_price,
            "probe_source": probe_price.source,
            "configured_assets": configured_assets,
            "demo_configured_assets": settings.allowed_assets_list,
            "distinct_from_demo_assets": set(configured_assets)
            != set(settings.allowed_assets_list),
            "missing_or_inactive_assets": missing,
        },
    )


def _wallet_balance_check(settings: Settings, store: JsonStore) -> WorkshopIntegrationCheck:
    if not settings.hyperliquid_account_address:
        agent = _privy_agent_wallet(settings, store)
        if agent is not None:
            try:
                wallet = PrivyHyperliquidAdapter(settings).wallet_state(agent)
            except Exception as exc:  # pragma: no cover - environment-specific.
                return WorkshopIntegrationCheck(
                    name="Hyperliquid wallet balance",
                    status="warning",
                    configured=True,
                    required=False,
                    detail=f"Could not fetch Privy Hyperliquid wallet balance: {exc}",
                    metadata={
                        "source": "privy_agent_wallet",
                        "environment": agent.network.value,
                        "account_address": _mask_address(agent.master_wallet_address),
                        "agent_address": _mask_address(agent.agent_wallet_address),
                    },
                )
            return _wallet_balance_ready_check(
                settings=settings,
                wallet=wallet,
                source="privy_agent_wallet",
                environment=agent.network.value,
            )
        return WorkshopIntegrationCheck(
            name="Hyperliquid wallet balance",
            status="warning",
            configured=False,
            required=False,
            detail="HYPERLIQUID_ACCOUNT_ADDRESS is missing; wallet balance was not fetched.",
            metadata={
                "environment": settings.hyperliquid_environment,
                "base_url": settings.hyperliquid_base_url,
            },
        )
    try:
        wallet = HyperliquidAdapter(settings).wallet_state()
    except Exception as exc:  # pragma: no cover - network failures are environment-specific.
        return WorkshopIntegrationCheck(
            name="Hyperliquid wallet balance",
            status="warning",
            configured=True,
            required=False,
            detail=f"Could not fetch Hyperliquid wallet balance: {exc}",
            metadata={
                "environment": settings.hyperliquid_environment,
                "base_url": settings.hyperliquid_base_url,
                "account_address": _mask_address(settings.hyperliquid_account_address),
            },
        )
    return _wallet_balance_ready_check(
        settings=settings,
        wallet=wallet,
        source="hyperliquid_account_address",
        environment=settings.hyperliquid_environment,
    )


def _privy_agent_wallet(settings: Settings, store: JsonStore):
    if not (settings.privy_execution_enabled and settings.has_privy_server_credentials):
        return None
    for item_id in (
        "privy_agent_wallet_prodnet",
        "privy_agent_wallet_testnet",
        "privy_agent_wallet",
    ):
        agent = store.get("privy_agent_wallet", item_id)
        if agent is not None:
            return agent
    return None


def _wallet_balance_ready_check(
    settings: Settings,
    wallet: dict[str, Any],
    source: str,
    environment: str,
) -> WorkshopIntegrationCheck:
    collateral = _rounded_usdc(wallet.get("collateral_usdc"))
    withdrawable = _rounded_usdc(wallet.get("withdrawable_usdc"))
    margin_used = _rounded_usdc(wallet.get("total_margin_used_usdc"))
    exposure = _rounded_usdc(wallet.get("exposure_usdc"))
    open_positions = wallet.get("open_positions") or []
    metadata = {
        "source": source,
        "environment": environment,
        "base_url": settings.hyperliquid_base_url,
        "account_address": _mask_address(str(wallet.get("account_address") or "")),
        "agent_address": _mask_address(str(wallet.get("agent_address") or "")),
        "withdrawable_usdc": withdrawable,
        "collateral_usdc": collateral,
        "total_margin_used_usdc": margin_used,
        "exposure_usdc": exposure,
        "open_positions_count": len(open_positions),
    }
    return WorkshopIntegrationCheck(
        name="Hyperliquid wallet balance",
        status="ready",
        configured=True,
        required=False,
        detail=(
            f"Wallet balance fetched from {source}: {withdrawable:.2f} USDC "
            f"withdrawable, {collateral:.2f} USDC collateral."
        ),
        metadata={key: value for key, value in metadata.items() if value is not None},
    )


def _perplexity_check(settings: Settings) -> WorkshopIntegrationCheck:
    configured = settings.has_perplexity_credentials
    if configured:
        try:
            context = PerplexityFinanceClient(settings, timeout=35).context_for_asset("BTC")
        except Exception as exc:  # pragma: no cover - network failures are environment-specific.
            return WorkshopIntegrationCheck(
                name="Perplexity Finance",
                status="warning",
                configured=True,
                required=False,
                detail=f"Perplexity Finance test call failed: {exc}",
                metadata={
                    "base_url": settings.perplexity_base_url,
                    "model": settings.perplexity_model,
                    "mcp_server_configured": bool(settings.perplexity_mcp_server_url),
                    "test_asset": "BTC",
                    "test_call": "failed",
                },
            )
        status: Literal["ready", "warning", "blocked"] = "ready" if context.available else "warning"
        return WorkshopIntegrationCheck(
            name="Perplexity Finance",
            status=status,
            configured=True,
            required=False,
            detail=(
                "Perplexity Finance test call returned source-backed context."
                if context.available
                else "Perplexity Finance test call completed but returned no usable context."
            ),
            metadata={
                "base_url": settings.perplexity_base_url,
                "model": settings.perplexity_model,
                "mcp_server_configured": bool(settings.perplexity_mcp_server_url),
                "test_asset": context.asset,
                "test_call": "executed",
                "available": context.available,
                "evidence_count": len(context.evidence),
                "source_count": len(context.sources),
                "raw_response_id": context.raw_response_id,
                "assumptions": context.assumptions,
                "sample_evidence": context.evidence[:2],
                "sample_sources": context.sources[:4],
            },
        )
    return WorkshopIntegrationCheck(
        name="Perplexity Finance",
        status="warning",
        configured=configured,
        required=False,
        detail=(
            "PERPLEXITY_API_KEY is configured for finance context."
            if configured
            else "PERPLEXITY_API_KEY is missing; finance context will be disabled."
        ),
        metadata={
            "base_url": settings.perplexity_base_url,
            "model": settings.perplexity_model,
            "mcp_server_configured": bool(settings.perplexity_mcp_server_url),
            "test_asset": "BTC",
            "test_call": "skipped",
        },
    )


def _hypertracker_check(settings: Settings) -> WorkshopIntegrationCheck:
    configured = settings.has_hypertracker_credentials
    if configured:
        try:
            intelligence = HyperTrackerClient(settings, timeout=6).intelligence_for_asset("BTC")
        except Exception as exc:  # pragma: no cover - network failures are environment-specific.
            return WorkshopIntegrationCheck(
                name="HyperTracker",
                status="warning",
                configured=True,
                required=False,
                detail=f"HyperTracker test call failed: {exc}",
                metadata={
                    "base_url": settings.hypertracker_base_url,
                    "mcp_server_configured": bool(settings.hypertracker_mcp_server_url),
                    "test_asset": "BTC",
                    "test_call": "failed",
                },
            )
        status: Literal["ready", "warning", "blocked"] = (
            "ready" if intelligence.available else "warning"
        )
        return WorkshopIntegrationCheck(
            name="HyperTracker",
            status=status,
            configured=True,
            required=False,
            detail=(
                "HyperTracker test call returned market intelligence."
                if intelligence.available
                else "HyperTracker test call completed but returned no usable intelligence."
            ),
            metadata={
                "base_url": settings.hypertracker_base_url,
                "mcp_server_configured": bool(settings.hypertracker_mcp_server_url),
                "test_asset": intelligence.asset,
                "test_call": "executed",
                "available": intelligence.available,
                "evidence_count": len(intelligence.evidence),
                "source_count": len(intelligence.sources),
                "assumptions": intelligence.assumptions,
                "sample_evidence": intelligence.evidence[:2],
                "sample_sources": intelligence.sources[:4],
            },
        )
    return WorkshopIntegrationCheck(
        name="HyperTracker",
        status="warning",
        configured=configured,
        required=False,
        detail=(
            "HYPERTRACKER_API_KEY is configured."
            if configured
            else "HYPERTRACKER_API_KEY is missing; positioning intelligence is disabled."
        ),
        metadata={
            "base_url": settings.hypertracker_base_url,
            "mcp_server_configured": bool(settings.hypertracker_mcp_server_url),
            "test_asset": "BTC",
            "test_call": "skipped",
        },
    )


def _privy_check(settings: Settings) -> WorkshopIntegrationCheck:
    configured = settings.has_privy_config
    server_ready = settings.has_privy_server_credentials
    if not settings.privy_execution_enabled:
        status: Literal["ready", "warning", "blocked"] = "warning"
        detail = "Privy execution is disabled for this workshop run."
    elif configured and server_ready:
        status = "ready"
        detail = "Privy public and server credentials are configured."
    else:
        status = "blocked"
        detail = "Privy execution is enabled but required Privy values are missing."
    return WorkshopIntegrationCheck(
        name="Privy wallet execution",
        status=status,
        configured=configured and (server_ready or not settings.privy_execution_enabled),
        required=False,
        detail=detail,
        metadata={
            "app_configured": configured,
            "server_configured": server_ready,
            "execution_enabled": settings.privy_execution_enabled,
        },
    )


def _rounded_usdc(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _mask_address(address: str) -> str | None:
    if not address:
        return None
    if len(address) <= 12:
        return address
    return f"{address[:6]}...{address[-4:]}"
