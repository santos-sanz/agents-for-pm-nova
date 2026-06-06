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
        self._last_source = "hyperliquid"

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
            self._last_source = "hyperliquid"
            return {str(asset).upper(): float(price) for asset, price in data.items()}
        except (TimeoutError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            self._last_source = "fallback"
            return FALLBACK_PRICES.copy()

    def mark_price(self, asset: str) -> MarketPrice:
        normalized = asset.upper().replace("-PERP", "")
        mids = self.all_mids()
        if normalized in mids:
            return MarketPrice(
                asset=normalized,
                mark_price=mids[normalized],
                source=self._last_source,
            )
        fallback = FALLBACK_PRICES.get(normalized, 100.0)
        return MarketPrice(asset=normalized, mark_price=fallback, source="fallback")
