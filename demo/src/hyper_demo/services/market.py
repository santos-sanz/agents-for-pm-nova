from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from hyper_demo.config import Settings, get_settings

FALLBACK_PRICES = {
    "BTC": 106_000.0,
    "ETH": 3_850.0,
    "SOL": 172.0,
    "HYPE": 32.0,
}


@dataclass(frozen=True)
class MarketPrice:
    asset: str
    mark_price: float
    source: str


class MarketDataClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def all_mids(self) -> dict[str, float]:
        payload = json.dumps({"type": "allMids"}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.settings.hyperliquid_base_url}/info",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
            return {str(asset).upper(): float(price) for asset, price in data.items()}
        except (TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            return FALLBACK_PRICES.copy()

    def mark_price(self, asset: str) -> MarketPrice:
        normalized = asset.upper().replace("-PERP", "")
        mids = self.all_mids()
        if normalized in mids:
            return MarketPrice(asset=normalized, mark_price=mids[normalized], source="hyperliquid")
        fallback = FALLBACK_PRICES.get(normalized, 100.0)
        return MarketPrice(asset=normalized, mark_price=fallback, source="fallback")


class CoinbasePublicMarketDataClient:
    """Public, credential-free market data for paper trading fills."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def product_id(self, asset: str) -> str:
        return f"{asset.upper().replace('-PERP', '')}-USD"

    def mark_price(self, asset: str) -> MarketPrice:
        normalized = asset.upper().replace("-PERP", "")
        product_id = self.product_id(normalized)
        request = urllib.request.Request(
            f"{self.settings.paper_market_base_url}/products/{product_id}/ticker",
            headers={"Accept": "application/json", "User-Agent": "hyper-demo-paper-trading/0.1"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8"))
            price = float(data["price"])
            if price <= 0:
                raise ValueError("Coinbase ticker returned a non-positive price.")
            return MarketPrice(
                asset=normalized,
                mark_price=price,
                source=f"coinbase:{product_id}",
            )
        except (TimeoutError, urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError):
            fallback = FALLBACK_PRICES.get(normalized, 100.0)
            return MarketPrice(asset=normalized, mark_price=fallback, source="fallback")
