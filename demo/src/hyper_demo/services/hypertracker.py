from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from hyper_demo.config import Settings, get_settings
from hyper_demo.models import normalize_asset_symbol


@dataclass(frozen=True)
class MarketIntelligence:
    asset: str
    evidence: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    available: bool = False


class HyperTrackerClient:
    def __init__(self, settings: Settings | None = None, timeout: int = 6) -> None:
        self.settings = settings or get_settings()
        self.timeout = timeout

    def intelligence_for_asset(self, asset: str) -> MarketIntelligence:
        normalized = normalize_asset_symbol(asset)
        if not self.settings.has_hypertracker_credentials:
            return MarketIntelligence(
                asset=normalized,
                assumptions=["HyperTracker API key is not configured."],
            )

        position_metrics = self._get(
            f"/api/external/position-metrics/coin/{urllib.parse.quote(normalized)}",
            _recent_window_params(limit=24),
        )
        leaderboard = self._get(
            "/api/external/leaderboards/perp-pnl",
            {
                "limit": 25,
                "offset": 0,
                "order": "desc",
                "orderBy": "pnlDay",
                "rankBy": "pnlDay",
            },
        )

        evidence: list[str] = []
        risks: list[str] = []
        assumptions: list[str] = []

        metrics_summary = _summarize_position_metrics(normalized, position_metrics)
        wallet_summary = _summarize_wallets(leaderboard)
        if metrics_summary:
            evidence.extend(metrics_summary[:3])
        if wallet_summary:
            evidence.extend(wallet_summary)

        if position_metrics is None or leaderboard is None:
            assumptions.append(
                "HyperTracker enrichment is partial because at least one endpoint was unavailable."
            )
        if not evidence:
            assumptions.append("HyperTracker returned no usable market intelligence rows.")

        long_short_risk = _long_short_concentration_risk(normalized, position_metrics)
        if long_short_risk:
            risks.append(long_short_risk)

        available = bool(evidence)
        return MarketIntelligence(
            asset=normalized,
            evidence=evidence[:4],
            risks=risks[:2],
            assumptions=assumptions[:2],
            sources=(
                [
                    "HyperTracker /api/external/position-metrics/coin/{asset}",
                    "HyperTracker /api/external/leaderboards/perp-pnl",
                ]
                if available
                else []
            ),
            available=available,
        )

    def _get(self, path: str, params: dict[str, Any]) -> Any | None:
        query = urllib.parse.urlencode(params)
        url = f"{self.settings.hypertracker_base_url}{path}"
        if query:
            url = f"{url}?{query}"
        api_key = self.settings.hypertracker_api_key
        token = api_key.get_secret_value() if api_key else ""
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (
            TimeoutError,
            urllib.error.HTTPError,
            urllib.error.URLError,
            ValueError,
            json.JSONDecodeError,
        ):
            return None


def enrich_research_with_market_intelligence(
    report,
    intelligence: MarketIntelligence,
):
    if intelligence.available:
        report.evidence = [*report.evidence, *intelligence.evidence]
        report.risks = [*report.risks, *intelligence.risks]
        report.sources = [*report.sources, *intelligence.sources]
    report.assumptions = [*report.assumptions, *intelligence.assumptions]
    return report


def _recent_window_params(limit: int) -> dict[str, Any]:
    end = datetime.now(UTC)
    start = end - timedelta(hours=24)
    return {
        "limit": limit,
        "start": start.isoformat().replace("+00:00", "Z"),
        "end": end.isoformat().replace("+00:00", "Z"),
    }


def _rows(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("metrics", "items", "data", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _latest_row(payload: Any) -> dict[str, Any]:
    rows = _rows(payload)
    return rows[-1] if rows else {}


def _number(row: dict[str, Any], *names: str) -> float | None:
    for name in names:
        value = row.get(name)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _summarize_position_metrics(asset: str, payload: Any) -> list[str]:
    row = _latest_row(payload)
    if not row:
        return []

    total_value = _number(row, "totalPositionValue", "positionValue", "openInterest", "value")
    long_value = _number(
        row,
        "totalPositionValueLong",
        "longPositionValue",
        "longValue",
        "longOpenInterest",
    )
    total_size = _number(row, "totalPositionSize")
    long_size = _number(row, "totalPositionSizeLong")
    short_value = _number(row, "shortPositionValue", "shortValue", "shortOpenInterest")
    if short_value is None and total_value is not None and long_value is not None:
        short_value = total_value - long_value
    position_count = _number(row, "positionCount", "totalPositions", "count")
    unrealized_pnl = _number(
        row,
        "totalUnrealizedPnl",
        "sumUpnl",
        "unrealizedPnl",
    )
    funding = _number(row, "totalFunding", "funding", "cumFunding")

    evidence: list[str] = []
    if total_value is not None:
        evidence.append(
            f"HyperTracker shows aggregate {asset} perpetual exposure near "
            f"{_compact_usd(total_value)} in the latest 24h snapshot."
        )
    if long_value is not None and short_value is not None and long_value + short_value > 0:
        long_share = long_value / (long_value + short_value) * 100
        evidence.append(
            f"HyperTracker long/short positioning is {long_share:.0f}% long and "
            f"{100 - long_share:.0f}% short by notional."
        )
    elif total_size is not None and long_size is not None and total_size > 0:
        long_share = long_size / total_size * 100
        evidence.append(
            f"HyperTracker long/short positioning is {long_share:.0f}% long and "
            f"{100 - long_share:.0f}% short by position size."
        )
    if position_count is not None:
        evidence.append(
            f"HyperTracker counts about {position_count:,.0f} open {asset} positions "
            "in the latest market snapshot."
        )
    if unrealized_pnl is not None:
        evidence.append(
            f"HyperTracker aggregate unrealized PnL for {asset} is "
            f"{_compact_usd(unrealized_pnl)}."
        )
    if funding is not None:
        evidence.append(
            f"HyperTracker reports aggregate funding impact near {_compact_usd(funding)}."
        )
    return evidence


def _summarize_wallets(payload: Any) -> list[str]:
    rows = _rows(payload)
    if not rows:
        return []
    top = rows[0]
    address = str(top.get("address") or "top wallet")
    profile = top.get("profile") if isinstance(top.get("profile"), dict) else {}
    equity = _number(top, "perpEquity", "totalEquity") or _number(profile, "totalEquity")
    pnl = _number(top, "pnlDay", "perpPnl", "pnl") or _number(profile, "perpPnl")
    open_value = _number(top, "openValue")
    bias = _number(top, "bias", "exposureRatio", "perpBias")

    metrics: list[str] = []
    if equity is not None:
        metrics.append(f"equity {_compact_usd(equity)}")
    if pnl is not None:
        metrics.append(f"24h perp PnL {_compact_usd(pnl)}")
    if open_value is not None:
        metrics.append(f"open value {_compact_usd(open_value)}")
    if bias is not None:
        metrics.append(f"bias {bias:.2f}x")

    if not metrics:
        return []
    return [
        f"HyperTracker top 24h perp PnL wallet {_mask_address(address)} shows "
        f"{', '.join(metrics)}."
    ]


def _long_short_concentration_risk(asset: str, payload: Any) -> str | None:
    row = _latest_row(payload)
    long_value = _number(
        row,
        "totalPositionValueLong",
        "longPositionValue",
        "longValue",
        "longOpenInterest",
    )
    total_value = _number(row, "totalPositionValue", "positionValue", "openInterest", "value")
    short_value = _number(row, "shortPositionValue", "shortValue", "shortOpenInterest")
    if short_value is None and total_value is not None and long_value is not None:
        short_value = total_value - long_value
    if long_value is None or short_value is None or long_value + short_value <= 0:
        return None
    long_share = long_value / (long_value + short_value)
    if long_share >= 0.7:
        return f"HyperTracker positioning is crowded long on {asset}, raising squeeze risk."
    if long_share <= 0.3:
        return f"HyperTracker positioning is crowded short on {asset}, raising squeeze risk."
    return None


def _compact_usd(value: float) -> str:
    sign = "-" if value < 0 else ""
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{sign}${absolute / 1_000_000_000:.2f}B"
    if absolute >= 1_000_000:
        return f"{sign}${absolute / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{sign}${absolute / 1_000:.2f}K"
    return f"{sign}${absolute:.2f}"


def _mask_address(address: str) -> str:
    if len(address) <= 12:
        return address
    return f"{address[:6]}...{address[-4:]}"
