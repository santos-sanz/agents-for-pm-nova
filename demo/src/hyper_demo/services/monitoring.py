from __future__ import annotations

import asyncio
import json
from typing import Any

import websockets

from hyper_demo.config import Settings, get_settings
from hyper_demo.models import normalize_asset_symbol
from hyper_demo.services.market import FALLBACK_PRICES, MarketPrice


class HyperliquidWebsocketMonitor:
    """Minimal websocket monitor for Hyperliquid testnet market ticks."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @staticmethod
    def all_mids_subscription() -> dict[str, Any]:
        return {"method": "subscribe", "subscription": {"type": "allMids"}}

    @staticmethod
    def parse_all_mids_message(message: str, asset: str) -> MarketPrice | None:
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return None
        if payload.get("channel") != "allMids":
            return None
        mids = payload.get("data", {}).get("mids", {})
        normalized = normalize_asset_symbol(asset)
        if normalized not in mids:
            return None
        return MarketPrice(asset=normalized, mark_price=float(mids[normalized]), source="websocket")

    async def sample_mark_price(self, asset: str, timeout_seconds: float = 5.0) -> MarketPrice:
        normalized = normalize_asset_symbol(asset)
        try:
            async with websockets.connect(self.settings.hyperliquid_ws_url) as websocket:
                await websocket.send(json.dumps(self.all_mids_subscription()))
                deadline = asyncio.get_running_loop().time() + timeout_seconds
                while asyncio.get_running_loop().time() < deadline:
                    remaining = max(0.1, deadline - asyncio.get_running_loop().time())
                    message = await asyncio.wait_for(websocket.recv(), timeout=remaining)
                    price = self.parse_all_mids_message(str(message), normalized)
                    if price:
                        return price
        except (OSError, TimeoutError, websockets.WebSocketException):
            pass
        return MarketPrice(
            asset=normalized,
            mark_price=FALLBACK_PRICES.get(normalized, 100.0),
            source="fallback",
        )
