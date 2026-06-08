from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from hyper_demo.config import Settings, get_settings
from hyper_demo.models import normalize_asset_symbol

FALLBACK_PRICES = {
    "BTC": 106_000.0,
    "ETH": 3_850.0,
    "SOL": 172.0,
    "HYPE": 32.0,
}

COMMON_ASSETS = ("BTC", "ETH", "SOL", "HYPE")


@dataclass(frozen=True)
class MarketPrice:
    asset: str
    mark_price: float
    source: str


@dataclass(frozen=True)
class MarketAsset:
    symbol: str
    max_leverage: int
    sz_decimals: int
    mark_price: float | None
    delisted: bool
    icon_url: str
    dex: str | None = None


class MarketDataClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._last_source = "hyperliquid"

    def all_mids(self) -> dict[str, float]:
        return self._all_mids_for({})

    def _all_mids_for(self, extra: dict[str, str]) -> dict[str, float]:
        payload = json.dumps({"type": "allMids", **extra}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.settings.hyperliquid_base_url}/info",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
            self._last_source = "hyperliquid"
            return {str(asset).upper(): float(price) for asset, price in data.items()}
        except (TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            self._last_source = "fallback"
            return FALLBACK_PRICES.copy()

    def available_assets(self) -> list[MarketAsset]:
        assets = self._available_assets_from({}, "https://api.hyperliquid.xyz")
        for dex in self._perp_dexes("https://api.hyperliquid.xyz"):
            assets.extend(self._available_assets_from({"dex": dex}, "https://api.hyperliquid.xyz"))
        if assets:
            seen: set[str] = set()
            unique = []
            for asset in assets:
                if asset.symbol in seen:
                    continue
                seen.add(asset.symbol)
                unique.append(asset)
            return unique
        return [
            MarketAsset(
                symbol=symbol,
                max_leverage=0,
                sz_decimals=0,
                mark_price=FALLBACK_PRICES.get(symbol),
                delisted=False,
                icon_url=asset_icon_url(symbol),
            )
            for symbol in COMMON_ASSETS
        ]

    def _available_assets_from(self, extra: dict[str, str], base_url: str) -> list[MarketAsset]:
        payload = json.dumps({"type": "metaAndAssetCtxs", **extra}).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/info",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
            if not isinstance(data, list) or len(data) < 2:
                return []
            meta = data[0] if isinstance(data[0], dict) else {}
            contexts = data[1] if isinstance(data[1], list) else []
            universe = meta.get("universe", []) if isinstance(meta, dict) else []
            dex = extra.get("dex")
            return [
                _market_asset_from_meta(item, contexts[index] if index < len(contexts) else {}, dex)
                for index, item in enumerate(universe)
                if isinstance(item, dict) and item.get("name")
            ]
        except (TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            return []

    def _perp_dexes(self, base_url: str) -> list[str]:
        payload = json.dumps({"type": "perpDexs"}).encode("utf-8")
        request = urllib.request.Request(
            f"{base_url}/info",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
            if not isinstance(data, list):
                return []
            return [
                str(item["name"])
                for item in data
                if isinstance(item, dict) and item.get("name")
            ]
        except (TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            return []

    def mark_price(self, asset: str) -> MarketPrice:
        normalized = normalize_asset_symbol(asset)
        dex, _ = split_dex_symbol(normalized)
        mids = self._all_mids_for({"dex": dex}) if dex else self.all_mids()
        if normalized in mids:
            return MarketPrice(
                asset=normalized,
                mark_price=mids[normalized],
                source=self._last_source,
            )
        fallback = FALLBACK_PRICES.get(normalized, 100.0)
        return MarketPrice(asset=normalized, mark_price=fallback, source="fallback")


def asset_icon_url(symbol: str) -> str:
    normalized = normalize_asset_symbol(symbol)
    _, base_symbol = split_dex_symbol(normalized)
    aliases = {
        "HYPE": "hyperliquid",
        "PURR": "purr",
        "WIF": "dogwifhat",
        "KPEPE": "pepe",
        "KFLOKI": "floki",
        "KBONK": "bonk",
        "KSHIB": "shib",
        "KNEIRO": "neiro",
        "KDOGS": "dogs",
        "UBTC": "btc",
        "UETH": "eth",
        "GOOGL": "googl",
    }
    icon_symbol = aliases.get(base_symbol, base_symbol).lower()
    return f"https://assets.coincap.io/assets/icons/{icon_symbol}@2x.png"


def split_dex_symbol(value: str) -> tuple[str | None, str]:
    normalized = normalize_asset_symbol(value)
    if ":" not in normalized:
        return None, normalized
    dex, symbol = normalized.split(":", 1)
    return dex, symbol


def _ctx_mark_price(context: dict[str, Any]) -> float | None:
    for key in ("markPx", "midPx", "oraclePx", "prevDayPx"):
        try:
            value = context.get(key)
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _market_asset_from_meta(
    item: dict[str, Any],
    context: dict[str, Any],
    dex: str | None,
) -> MarketAsset:
    symbol = normalize_asset_symbol(str(item["name"]))
    return MarketAsset(
        symbol=symbol,
        max_leverage=int(item.get("maxLeverage") or 0),
        sz_decimals=int(item.get("szDecimals") or 0),
        mark_price=_ctx_mark_price(context),
        delisted=bool(item.get("isDelisted")),
        icon_url=asset_icon_url(symbol),
        dex=dex,
    )
