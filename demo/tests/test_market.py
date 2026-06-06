import io
import json
import urllib.error

from hyper_demo.config import Settings
from hyper_demo.services.market import MarketDataClient


class FakeResponse:
    def __init__(self, payload: dict[str, str]) -> None:
        self.payload = payload

    def __enter__(self):
        return io.BytesIO(json.dumps(self.payload).encode("utf-8"))

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


def test_hyperliquid_all_mids(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        assert request.full_url == "https://api.hyperliquid-testnet.xyz/info"
        assert timeout == 8
        return FakeResponse({"BTC": "102.50"})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    price = MarketDataClient(Settings()).mark_price("BTC")

    assert price.mark_price == 102.5
    assert price.source == "hyperliquid"


def test_hyperliquid_market_falls_back(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    price = MarketDataClient(Settings()).mark_price("BTC")

    assert price.mark_price == 106_000.0
    assert price.source == "fallback"
