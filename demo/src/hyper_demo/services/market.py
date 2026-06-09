from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from hyper_demo.config import Settings, get_settings
from hyper_demo.models import Candle, normalize_asset_symbol

FALLBACK_PRICES = {
    "BTC": 106_000.0,
    "ETH": 3_850.0,
    "SOL": 172.0,
    "HYPE": 32.0,
}

COMMON_ASSETS = ("BTC", "ETH", "SOL", "HYPE")
SUPPORTED_CANDLE_INTERVALS = {"15m", "1h", "4h", "1d"}
INTERVAL_DELTAS = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


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

    def candles(self, asset: str, interval: str, limit: int = 120) -> list[Candle]:
        if interval not in SUPPORTED_CANDLE_INTERVALS:
            raise ValueError(f"Unsupported candle interval: {interval}")
        normalized = normalize_asset_symbol(asset)
        limit = max(10, min(limit, 500))
        delta = INTERVAL_DELTAS[interval]
        end = datetime.now(UTC)
        start = end - delta * limit
        payload = json.dumps(
            {
                "type": "candleSnapshot",
                "req": {
                    "coin": normalized,
                    "interval": interval,
                    "startTime": int(start.timestamp() * 1000),
                    "endTime": int(end.timestamp() * 1000),
                },
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.settings.hyperliquid_base_url}/info",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
            candles = [
                _candle_from_payload(normalized, interval, item)
                for item in data
                if isinstance(item, dict)
            ]
            if candles:
                self._last_source = "hyperliquid"
                return candles[-limit:]
        except (TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            pass
        self._last_source = "fallback"
        return fallback_candles(normalized, interval, limit)


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


def fallback_candles(asset: str, interval: str, limit: int = 120) -> list[Candle]:
    normalized = normalize_asset_symbol(asset)
    _, base_symbol = split_dex_symbol(normalized)
    base = FALLBACK_PRICES.get(normalized, FALLBACK_PRICES.get(base_symbol, 100.0))
    delta = INTERVAL_DELTAS.get(interval, timedelta(hours=1))
    start = datetime.now(UTC) - delta * limit
    candles: list[Candle] = []
    price = base * 0.965
    for index in range(limit):
        trend = 1 + (index / max(limit, 1)) * 0.07
        wave = ((index % 9) - 4) / 900
        open_price = price
        close = base * trend * (1 + wave)
        spread = max(close * 0.0045, 0.01)
        high = max(open_price, close) + spread
        low = max(0.0001, min(open_price, close) - spread)
        candles.append(
            Candle(
                asset=normalized,
                interval=interval,  # type: ignore[arg-type]
                opened_at=start + delta * index,
                open=round(open_price, 6),
                high=round(high, 6),
                low=round(low, 6),
                close=round(close, 6),
                volume=round(1_000 + index * 13.7, 4),
                source="fallback",
            )
        )
        price = close
    return candles


def _candle_from_payload(asset: str, interval: str, item: dict[str, Any]) -> Candle:
    opened_at = datetime.fromtimestamp(float(item.get("t") or item.get("T") or 0) / 1000, UTC)
    return Candle(
        asset=asset,
        interval=interval,  # type: ignore[arg-type]
        opened_at=opened_at,
        open=float(item.get("o") or item.get("open")),
        high=float(item.get("h") or item.get("high")),
        low=float(item.get("l") or item.get("low")),
        close=float(item.get("c") or item.get("close")),
        volume=float(item.get("v") or item.get("volume") or 0),
        source="hyperliquid",
    )


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
