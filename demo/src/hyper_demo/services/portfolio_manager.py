from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hyper_demo.adapters.hyperliquid import ExecutionBlocked, HyperliquidAdapter
from hyper_demo.config import Settings, get_settings
from hyper_demo.models import (
    OrderRecord,
    RunEvent,
    TradeSide,
    WorkshopAllocationPosition,
    WorkshopAllocationProposal,
    WorkshopAssetSnapshot,
    WorkshopAssetVerification,
    WorkshopResearchBrief,
    WorkshopRiskBand,
    WorkshopRiskProfile,
    normalize_asset_symbol,
    utc_now,
)
from hyper_demo.services.formal_validation import HYPERLIQUID_MIN_NOTIONAL_BUFFER_USDC
from hyper_demo.services.hypertracker import HyperTrackerClient
from hyper_demo.services.market import MarketAsset, MarketDataClient
from hyper_demo.services.perplexity import PerplexityFinanceClient
from hyper_demo.storage import JsonStore

WORKSHOP_RUN_ID = "workshop_portfolio"
WORKSHOP_MIN_REBALANCE_ORDER_USDC = 10.0 + HYPERLIQUID_MIN_NOTIONAL_BUFFER_USDC


@dataclass(frozen=True)
class WorkshopAssetDefinition:
    canonical_id: str
    display_label: str
    category: str
    description: str


WORKSHOP_ASSETS: tuple[WorkshopAssetDefinition, ...] = (
    WorkshopAssetDefinition("xyz:CL", "CL-USDC", "commodity", "WTI crude oil perpetual"),
    WorkshopAssetDefinition("xyz:BRENTOIL", "BRENT-USDC", "commodity", "Brent crude oil perpetual"),
    WorkshopAssetDefinition("xyz:GOLD", "XAU-USDC", "commodity", "Gold perpetual"),
    WorkshopAssetDefinition("xyz:SILVER", "XAG-USDC", "commodity", "Silver perpetual"),
    WorkshopAssetDefinition("xyz:SP500", "US500-USDC", "equity_index", "S&P 500 perpetual"),
    WorkshopAssetDefinition("flx:USA100", "US100-USDC", "equity_index", "NASDAQ 100 perpetual"),
    WorkshopAssetDefinition("xyz:COPPER", "COPPER-USDC", "commodity", "Copper perpetual"),
    WorkshopAssetDefinition("vntl:WHEAT", "WHEAT-USDC", "commodity", "Wheat perpetual"),
    WorkshopAssetDefinition("xyz:NATGAS", "NATGAS-USDC", "commodity", "Natural gas perpetual"),
    WorkshopAssetDefinition("BTC", "BTC-USDC", "crypto", "Bitcoin perpetual"),
)
WORKSHOP_ASSET_BY_ID = {asset.canonical_id: asset for asset in WORKSHOP_ASSETS}
EQUITY_CATEGORIES = {"equity_index"}
COMMODITY_CATEGORIES = {"commodity"}


def risk_band_for_score(risk_score: int) -> WorkshopRiskBand:
    if risk_score <= 35:
        return WorkshopRiskBand.capital_preservation
    if risk_score <= 70:
        return WorkshopRiskBand.balanced_conservative
    return WorkshopRiskBand.guarded_growth


def constraints_for_score(risk_score: int) -> dict[str, Any]:
    band = risk_band_for_score(risk_score)
    if band == WorkshopRiskBand.capital_preservation:
        return {
            "band": band.value,
            "min_cash_pct": 40.0,
            "max_single_asset_pct": 12.0,
            "max_btc_pct": 5.0,
            "max_equity_index_pct": 30.0,
            "max_commodity_pct": 45.0,
        }
    if band == WorkshopRiskBand.balanced_conservative:
        return {
            "band": band.value,
            "min_cash_pct": 25.0,
            "max_single_asset_pct": 18.0,
            "max_btc_pct": 8.0,
            "max_equity_index_pct": 45.0,
            "max_commodity_pct": 55.0,
        }
    return {
        "band": band.value,
        "min_cash_pct": 10.0,
        "max_single_asset_pct": 25.0,
        "max_btc_pct": 12.0,
        "max_equity_index_pct": 60.0,
        "max_commodity_pct": 65.0,
    }


def save_workshop_risk_profile(
    risk_score: int,
    store: JsonStore,
) -> WorkshopRiskProfile:
    band = risk_band_for_score(risk_score)
    profile = WorkshopRiskProfile(
        risk_score=risk_score,
        band=band,
        summary=_risk_summary(band),
    )
    store.save("workshop_risk_profiles", profile)
    store.append_event(
        RunEvent(
            run_id=WORKSHOP_RUN_ID,
            message=f"Risk profile set to {risk_score}/100 ({band.value}).",
            payload={"risk_score": risk_score, "band": band.value},
        )
    )
    return profile


def latest_or_default_profile(store: JsonStore) -> WorkshopRiskProfile:
    profile = store.get("workshop_risk_profiles", "workshop_risk_profile")
    if profile is not None:
        return profile
    return save_workshop_risk_profile(25, store)


def verify_workshop_assets(
    settings: Settings | None = None,
    store: JsonStore | None = None,
) -> WorkshopAssetVerification:
    settings = settings or get_settings()
    store = store or JsonStore(settings)
    configured = settings.workshop_allowed_assets_list
    allowed = set(WORKSHOP_ASSET_BY_ID)
    invalid = [asset for asset in configured if asset not in allowed]
    configured = [asset for asset in configured if asset in allowed]
    market = MarketDataClient(settings)
    available_assets = market.available_assets()
    snapshots = [
        _snapshot_asset(asset_id, available_assets)
        for asset_id in configured
    ]
    unavailable = [snapshot.canonical_id for snapshot in snapshots if not snapshot.active]
    status = "blocked" if invalid or unavailable else "validated"
    if invalid:
        unavailable.extend(invalid)
    verification = WorkshopAssetVerification(
        status=status,
        assets=snapshots,
        unavailable_assets=unavailable,
        source="hyperliquid" if status == "validated" else "hyperliquid_with_gaps",
    )
    store.save("workshop_asset_verifications", verification)
    store.append_event(
        RunEvent(
            run_id=WORKSHOP_RUN_ID,
            level="warning" if status == "blocked" else "info",
            message=(
                "Workshop asset verification blocked some markets."
                if status == "blocked"
                else "Workshop asset universe verified."
            ),
            payload=verification.model_dump(mode="json"),
        )
    )
    return verification


def research_workshop_portfolio(
    risk_score: int,
    settings: Settings | None = None,
    store: JsonStore | None = None,
) -> WorkshopResearchBrief:
    settings = settings or get_settings()
    store = store or JsonStore(settings)
    configured_assets = settings.workshop_allowed_assets_list
    evidence: list[str] = []
    sources: list[dict[str, Any]] = []
    gaps: list[str] = []
    confidence = 0.58

    perplexity = PerplexityFinanceClient(settings, timeout=20).context_for_asset("BTC")
    if perplexity.available:
        evidence.extend(perplexity.evidence[:3])
        sources.extend(
            {"name": "Perplexity Finance", "url": source, "checked_at": utc_now().isoformat()}
            for source in perplexity.sources[:5]
        )
        confidence += 0.12
    else:
        gaps.append("Perplexity Finance context unavailable; using local conservative fallback.")

    hypertracker = HyperTrackerClient(settings, timeout=6).intelligence_for_asset("BTC")
    if hypertracker.available:
        evidence.extend(hypertracker.evidence[:2])
        sources.extend(
            {"name": "HyperTracker", "url": source, "checked_at": utc_now().isoformat()}
            for source in hypertracker.sources[:4]
        )
        confidence += 0.08
    else:
        gaps.append("HyperTracker positioning context unavailable.")

    if not evidence:
        evidence = [
            (
                "Live optional intelligence was unavailable; capital preservation rules "
                "increased cash."
            ),
            "Portfolio construction is limited to configured active Hyperliquid markets and USDC.",
        ]
        confidence = 0.42
    asset_signals = {
        asset_id: _asset_signal(asset_id, risk_score, bool(gaps))
        for asset_id in configured_assets
        if asset_id in WORKSHOP_ASSET_BY_ID
    }
    brief = WorkshopResearchBrief(
        risk_score=risk_score,
        macro_summary=" ".join(evidence[:3]),
        asset_signals=asset_signals,
        sources=sources
        or [
            {
                "name": "Local workshop policy",
                "url": "docs/demo-rebuild.md",
                "checked_at": utc_now().isoformat(),
            }
        ],
        coverage_gaps=gaps,
        confidence=round(min(confidence, 0.82), 2),
    )
    store.save("workshop_research", brief)
    store.append_event(
        RunEvent(
            run_id=WORKSHOP_RUN_ID,
            message="Research brief generated for the workshop allocation.",
            payload={"confidence": brief.confidence, "coverage_gaps": brief.coverage_gaps},
        )
    )
    return brief


def allocate_workshop_portfolio(
    risk_score: int,
    settings: Settings | None = None,
    store: JsonStore | None = None,
) -> WorkshopAllocationProposal:
    settings = settings or get_settings()
    store = store or JsonStore(settings)
    profile = save_workshop_risk_profile(risk_score, store)
    verification = verify_workshop_assets(settings, store)
    brief = research_workshop_portfolio(risk_score, settings, store)
    constraints = constraints_for_score(risk_score)
    active_assets = [asset for asset in verification.assets if asset.active and not asset.delisted]
    cash_pct = _cash_target(constraints, brief)
    investable_pct = round(100.0 - cash_pct, 2)
    positions = _allocate_positions(active_assets, investable_pct, constraints)
    positions, cash_pct = _fix_rounding(positions, cash_pct)
    validation_status = "validated" if verification.status == "validated" else "blocked"
    explanations = [
        profile.summary,
        f"USDC cash is {cash_pct:.2f}% because minimum cash is "
        f"{constraints['min_cash_pct']:.0f}% and source confidence is {brief.confidence:.0%}.",
        "Output is educational and non-advisory; execution requires explicit host confirmation.",
    ]
    if brief.coverage_gaps:
        explanations.append("Coverage gaps increased cash above the profile minimum.")
    if verification.unavailable_assets:
        explanations.append(
            "Unavailable configured markets were excluded: "
            + ", ".join(verification.unavailable_assets)
            + "."
        )
    proposal = WorkshopAllocationProposal(
        risk_score=risk_score,
        cash_pct=cash_pct,
        positions=positions,
        constraints=constraints,
        research_sources=brief.sources,
        confidence=brief.confidence,
        validation_status=validation_status,
        explanations=explanations,
        coverage_gaps=brief.coverage_gaps,
        current_wallet_allocation=_wallet_allocation(settings),
    )
    store.save("workshop_allocations", proposal)
    store.append_event(
        RunEvent(
            run_id=WORKSHOP_RUN_ID,
            level="warning" if validation_status == "blocked" else "info",
            message=f"Allocation proposal {proposal.id} generated as {validation_status}.",
            payload=proposal.model_dump(mode="json"),
        )
    )
    return proposal


def guarded_rebalance_preview(
    allocation_id: str,
    confirmed: bool,
    settings: Settings | None = None,
    store: JsonStore | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    store = store or JsonStore(settings)
    proposal = store.get("workshop_allocations", allocation_id)
    if proposal is None:
        raise ExecutionBlocked("Allocation proposal was not found.")
    if proposal.validation_status not in {"validated", "pending_approval"}:
        raise ExecutionBlocked("Only validated or pending allocation proposals can be prepared.")
    orders = _rebalance_order_preview(proposal)
    if not confirmed:
        pending = proposal.model_copy(update={"validation_status": "pending_approval"})
        store.save("workshop_allocations", pending)
        store.append_event(
            RunEvent(
                run_id=WORKSHOP_RUN_ID,
                message="Rebalance preview prepared for human approval.",
                payload={"allocation_id": proposal.id, "orders": orders},
            )
        )
        return {
            "status": "pending_approval",
            "allocation_id": proposal.id,
            "message": "Rebalance is prepared for review only. Explicit confirmation is required.",
            "orders": orders,
        }

    submitted_orders = _execute_rebalance_orders(proposal, settings, store)
    next_status = "submitted" if submitted_orders else "approved"
    approved = proposal.model_copy(update={"validation_status": next_status})
    store.save("workshop_allocations", approved)
    environment_label = "mainnet" if settings.is_mainnet_mode else "testnet"
    store.append_event(
        RunEvent(
            run_id=WORKSHOP_RUN_ID,
            message=(
                f"Human approval recorded and {len(submitted_orders)} rebalance "
                f"order(s) submitted to Hyperliquid {environment_label}."
                if submitted_orders
                else "Human approval recorded; no rebalance deltas cleared execution thresholds."
            ),
            payload={
                "allocation_id": proposal.id,
                "orders": orders,
                "submitted_order_ids": [order.id for order in submitted_orders],
                "executable": True,
            },
        )
    )
    return {
        "status": next_status,
        "allocation_id": proposal.id,
        "message": (
            f"Submitted {len(submitted_orders)} rebalance order(s) to Hyperliquid "
            f"{environment_label}."
            if submitted_orders
            else "Human approval recorded. No rebalance tickets cleared execution thresholds."
        ),
        "orders": orders,
        "submitted_orders": [order.model_dump(mode="json") for order in submitted_orders],
        "executable": True,
    }


def reject_rebalance_preview(
    allocation_id: str,
    store: JsonStore | None = None,
) -> dict[str, Any]:
    store = store or JsonStore()
    proposal = store.get("workshop_allocations", allocation_id)
    if proposal is None:
        raise ExecutionBlocked("Allocation proposal was not found.")
    if proposal.validation_status != "pending_approval":
        raise ExecutionBlocked("Only pending rebalance previews can be rejected.")
    rejected = proposal.model_copy(update={"validation_status": "rejected"})
    store.save("workshop_allocations", rejected)
    store.append_event(
        RunEvent(
            run_id=WORKSHOP_RUN_ID,
            level="warning",
            message="Human operator rejected the rebalance preview.",
            payload={"allocation_id": proposal.id},
        )
    )
    return {
        "status": "rejected",
        "allocation_id": proposal.id,
        "message": "Rebalance preview rejected. Run agents again before approval.",
        "orders": _rebalance_order_preview(rejected),
    }


def _execute_rebalance_orders(
    proposal: WorkshopAllocationProposal,
    settings: Settings,
    store: JsonStore,
) -> list[OrderRecord]:
    if not settings.has_hyperliquid_credentials:
        raise ExecutionBlocked(
            "Hyperliquid credentials are missing. Configure .env.local or use replay mode."
        )
    if settings.is_mainnet_mode and not settings.hyperliquid_mainnet_enabled:
        raise ExecutionBlocked(
            "Mainnet is disabled. Set HYPERLIQUID_MAINNET_ENABLED=true to proceed."
        )
    adapter = HyperliquidAdapter(settings)
    wallet = adapter.wallet_state()
    collateral = float(wallet.get("collateral_usdc") or 0)
    if collateral <= 0:
        raise ExecutionBlocked("Wallet collateral is unavailable; rebalance execution is blocked.")
    open_positions = wallet.get("open_positions") or []
    current_by_id = _current_position_snapshot(open_positions)
    market_assets = MarketDataClient(settings).available_assets()
    submitted: list[OrderRecord] = []

    for target in _rebalance_targets(proposal):
        canonical_id = str(target["canonical_id"])
        if canonical_id == "USDC":
            continue
        current = current_by_id.get(canonical_id, {})
        target_usdc = collateral * float(target["target_pct"]) / 100.0
        current_usdc = float(current.get("position_value_usdc") or 0)
        delta_usdc = round(target_usdc - current_usdc, 4)
        if abs(delta_usdc) < WORKSHOP_MIN_REBALANCE_ORDER_USDC:
            continue
        if abs(delta_usdc) > settings.hyperliquid_max_order_usdc:
            raise ExecutionBlocked(
                f"Rebalance ticket for {canonical_id} is {abs(delta_usdc):.2f} USDC, "
                f"above the max order cap {settings.hyperliquid_max_order_usdc:.2f} USDC."
            )
        market_asset = _find_market_asset(canonical_id, market_assets)
        if market_asset is None or market_asset.mark_price is None or market_asset.delisted:
            raise ExecutionBlocked(f"{canonical_id} is not active in Hyperliquid metadata.")
        if delta_usdc > 0:
            order = adapter.submit_rebalance_order(
                allocation_id=proposal.id,
                asset=canonical_id,
                side=TradeSide.long,
                size_usdc=delta_usdc,
                mark_price=market_asset.mark_price,
                size_decimals=market_asset.sz_decimals,
                reduce_only=False,
                confirmed=True,
            )
        else:
            if current_usdc <= 0:
                raise ExecutionBlocked(f"No open {canonical_id} position is available to trim.")
            order = adapter.submit_rebalance_order(
                allocation_id=proposal.id,
                asset=canonical_id,
                side=TradeSide.short,
                size_usdc=min(abs(delta_usdc), current_usdc),
                mark_price=market_asset.mark_price,
                size_decimals=market_asset.sz_decimals,
                reduce_only=True,
                confirmed=True,
            )
        store.save("orders", order)
        submitted.append(order)
    return submitted


def _rebalance_order_preview(proposal: WorkshopAllocationProposal) -> list[dict[str, Any]]:
    target_rows = _rebalance_targets(proposal)
    current_by_id = {
        str(item.get("canonical_id") or ""): float(item.get("target_pct") or 0)
        for item in proposal.current_wallet_allocation
    }
    has_wallet_snapshot = bool(current_by_id)
    target_ids = {str(row["canonical_id"]) for row in target_rows}
    target_rows.extend(
        {
            "canonical_id": current_id,
            "display_label": current_id,
            "category": "outside_target",
            "target_pct": 0.0,
            "rationale": "Existing wallet exposure is outside the approved target allocation.",
            "constraints": ["trim to target allocation"],
        }
        for current_id in current_by_id
        if current_id and current_id not in target_ids
    )
    orders: list[dict[str, Any]] = []
    for row in target_rows:
        current_pct = (
            round(current_by_id.get(str(row["canonical_id"]), 0.0), 2)
            if has_wallet_snapshot
            else None
        )
        target_pct = round(float(row["target_pct"]), 2)
        delta_pct = round(target_pct - current_pct, 2) if current_pct is not None else None
        action = _rebalance_action(str(row["canonical_id"]), delta_pct)
        orders.append(
            {
                "canonical_id": row["canonical_id"],
                "display_label": row["display_label"],
                "category": row["category"],
                "action": action,
                "current_pct": current_pct,
                "target_pct": target_pct,
                "delta_pct": delta_pct,
                "rationale": row["rationale"],
                "constraints": row["constraints"],
                "requires_confirmation": True,
            }
        )
    return orders


def _rebalance_targets(proposal: WorkshopAllocationProposal) -> list[dict[str, Any]]:
    target_rows: list[dict[str, Any]] = [
        {
            "canonical_id": "USDC",
            "display_label": "USDC",
            "category": "cash",
            "target_pct": proposal.cash_pct,
            "rationale": "Capital reserve after rebalance.",
            "constraints": ["cash reserve"],
        }
    ]
    target_rows.extend(
        {
            "canonical_id": position.canonical_id,
            "display_label": position.display_label,
            "category": position.category,
            "target_pct": position.target_pct,
            "rationale": position.rationale,
            "constraints": position.constraints,
        }
        for position in proposal.positions
    )
    return target_rows


def _current_position_snapshot(open_positions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for position in open_positions:
        asset = normalize_asset_symbol(str(position.get("asset") or position.get("coin") or ""))
        if not asset:
            continue
        size = float(position.get("size") or position.get("szi") or 0)
        entry_price = float(position.get("entry_price") or position.get("entryPx") or 0)
        value = float(position.get("position_value_usdc") or position.get("positionValue") or 0)
        if value <= 0 and entry_price > 0 and size:
            value = abs(size * entry_price)
        snapshot[asset] = {
            "size": size,
            "position_value_usdc": abs(value),
            "entry_price": entry_price,
        }
    return snapshot


def _rebalance_action(canonical_id: str, delta_pct: float | None) -> str:
    if delta_pct is None:
        return "reserve" if canonical_id == "USDC" else "stage"
    if abs(delta_pct) < 0.01:
        return "hold"
    if canonical_id == "USDC":
        return "raise cash" if delta_pct > 0 else "deploy cash"
    return "increase" if delta_pct > 0 else "trim"


def _snapshot_asset(
    canonical_id: str,
    available_assets: list[MarketAsset],
) -> WorkshopAssetSnapshot:
    definition = WORKSHOP_ASSET_BY_ID[canonical_id]
    matched = _find_market_asset(canonical_id, available_assets)
    issues: list[str] = []
    if matched is None:
        issues.append("Market was not found in Hyperliquid metadata.")
    elif matched.delisted:
        issues.append("Market is marked delisted.")
    active = matched is not None and not matched.delisted and matched.mark_price is not None
    cap = 0.0
    if active:
        cap = 12.0 if canonical_id == "BTC" else 18.0
    return WorkshopAssetSnapshot(
        canonical_id=canonical_id,
        display_label=definition.display_label,
        category=definition.category,  # type: ignore[arg-type]
        description=definition.description,
        active=active,
        delisted=bool(matched.delisted) if matched else False,
        mark_price=matched.mark_price if matched else None,
        max_leverage=matched.max_leverage if matched else 0,
        allocation_cap_pct=cap,
        quote_source="hyperliquid" if active else "unavailable",
        issues=issues,
    )


def _find_market_asset(canonical_id: str, assets: list[MarketAsset]) -> MarketAsset | None:
    normalized = normalize_asset_symbol(canonical_id)
    for asset in assets:
        symbol = normalize_asset_symbol(asset.symbol)
        dex_qualified = f"{str(asset.dex).lower()}:{symbol}" if asset.dex else symbol
        if symbol == normalized or dex_qualified == normalized:
            return asset
    return None


def _allocate_positions(
    assets: list[WorkshopAssetSnapshot],
    investable_pct: float,
    constraints: dict[str, Any],
) -> list[WorkshopAllocationPosition]:
    if investable_pct <= 0 or not assets:
        return []
    weights = {asset.canonical_id: _base_weight(asset) for asset in assets}
    total_weight = sum(weights.values()) or 1.0
    raw = {
        asset.canonical_id: investable_pct * weights[asset.canonical_id] / total_weight
        for asset in assets
    }
    positions: list[WorkshopAllocationPosition] = []
    commodity_used = 0.0
    equity_used = 0.0
    for asset in assets:
        max_pct = float(constraints["max_single_asset_pct"])
        if asset.canonical_id == "BTC":
            max_pct = min(max_pct, float(constraints["max_btc_pct"]))
        if asset.category in COMMODITY_CATEGORIES:
            remaining_commodity = float(constraints["max_commodity_pct"]) - commodity_used
            max_pct = min(max_pct, max(0.0, remaining_commodity))
        if asset.category in EQUITY_CATEGORIES:
            max_pct = min(
                max_pct,
                max(0.0, float(constraints["max_equity_index_pct"]) - equity_used),
            )
        target = round(min(raw[asset.canonical_id], max_pct), 2)
        if target <= 0:
            continue
        if asset.category in COMMODITY_CATEGORIES:
            commodity_used += target
        if asset.category in EQUITY_CATEGORIES:
            equity_used += target
        positions.append(
            WorkshopAllocationPosition(
                canonical_id=asset.canonical_id,
                display_label=asset.display_label,
                category=asset.category,
                target_pct=target,
                rationale=_position_rationale(asset),
                constraints=[
                    f"single asset cap {constraints['max_single_asset_pct']:.0f}%",
                    f"max leverage observed {asset.max_leverage}x; target assumes no leverage",
                ],
            )
        )
    return positions


def _fix_rounding(
    positions: list[WorkshopAllocationPosition],
    cash_pct: float,
) -> tuple[list[WorkshopAllocationPosition], float]:
    invested = round(sum(position.target_pct for position in positions), 2)
    cash_pct = round(100.0 - invested, 2)
    return positions, cash_pct


def _cash_target(constraints: dict[str, Any], brief: WorkshopResearchBrief) -> float:
    cash = float(constraints["min_cash_pct"])
    if brief.confidence < 0.5:
        cash += 20
    elif brief.confidence < 0.65:
        cash += 10
    if brief.coverage_gaps:
        cash += min(15, len(brief.coverage_gaps) * 5)
    return round(min(100.0, cash), 2)


def _wallet_allocation(settings: Settings) -> list[dict[str, Any]]:
    if not settings.has_hyperliquid_credentials:
        return []
    try:
        wallet = HyperliquidAdapter(settings).wallet_state()
    except ExecutionBlocked:
        return []
    collateral = float(wallet.get("collateral_usdc") or 0)
    if collateral <= 0:
        return []
    positions = wallet.get("open_positions") or []
    allocation = [
        {
            "canonical_id": str(position.get("asset") or ""),
            "target_pct": round(
                float(position.get("position_value_usdc") or 0) / collateral * 100,
                2,
            ),
        }
        for position in positions
    ]
    used = sum(item["target_pct"] for item in allocation)
    allocation.append({"canonical_id": "USDC", "target_pct": round(max(0.0, 100 - used), 2)})
    return allocation


def _base_weight(asset: WorkshopAssetSnapshot) -> float:
    if asset.canonical_id == "BTC":
        return 0.45
    if asset.category == "equity_index":
        return 0.85
    if asset.canonical_id in {"xyz:GOLD", "xyz:SILVER"}:
        return 1.05
    return 0.75


def _asset_signal(asset_id: str, risk_score: int, has_gaps: bool) -> str:
    definition = WORKSHOP_ASSET_BY_ID.get(asset_id)
    if definition is None:
        return "Excluded because the asset is outside the verified workshop universe."
    if has_gaps:
        return "Eligible but capped because external source coverage is incomplete."
    if risk_score <= 35:
        return "Eligible at a low target weight under capital-preservation constraints."
    return "Eligible under conservative caps with USDC retained as the primary buffer."


def _position_rationale(asset: WorkshopAssetSnapshot) -> str:
    if asset.canonical_id == "BTC":
        return "Small capped crypto exposure for moderate upside without short exposure."
    if asset.category == "equity_index":
        return "Diversified index exposure capped by the selected risk profile."
    if asset.canonical_id in {"xyz:GOLD", "xyz:SILVER"}:
        return "Precious-metals exposure supports defensive diversification."
    return "Commodity exposure is included only within conservative category caps."


def _risk_summary(band: WorkshopRiskBand) -> str:
    if band == WorkshopRiskBand.capital_preservation:
        return "Capital preservation profile: high USDC reserve and tight per-market caps."
    if band == WorkshopRiskBand.balanced_conservative:
        return "Balanced conservative profile: diversified exposure with USDC as primary buffer."
    return "Guarded growth profile: higher investable range while preserving low leverage and caps."
