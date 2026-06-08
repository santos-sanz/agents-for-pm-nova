import io
import json
import urllib.error

from hyper_demo.config import Settings
from hyper_demo.services.market import MarketDataClient


class FakeResponse:
    def __init__(self, payload) -> None:
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


def test_available_assets_includes_hip3_dex_markets(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        assert request.full_url == "https://api.hyperliquid.xyz/info"
        body = json.loads(request.data.decode("utf-8"))
        assert body["type"] in {"metaAndAssetCtxs", "perpDexs"}
        if body["type"] == "perpDexs":
            return FakeResponse([None, {"name": "xyz", "fullName": "XYZ"}])
        if body.get("dex") == "xyz":
            return FakeResponse(
                [
                    {
                        "universe": [
                            {"name": "xyz:SPCX", "maxLeverage": 5, "szDecimals": 2},
                            {"name": "xyz:GOOGL", "maxLeverage": 10, "szDecimals": 3},
                        ]
                    },
                    [{"markPx": "163.5"}, {"markPx": "363.0"}],
                ]
            )
        return FakeResponse(
            [
                {"universe": [{"name": "BTC", "maxLeverage": 40, "szDecimals": 5}]},
                [{"markPx": "63000"}],
            ]
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assets = MarketDataClient(Settings()).available_assets()

    by_symbol = {asset.symbol: asset for asset in assets}
    assert by_symbol["BTC"].mark_price == 63_000
    assert by_symbol["xyz:SPCX"].dex == "xyz"
    assert by_symbol["xyz:SPCX"].mark_price == 163.5
    assert by_symbol["xyz:GOOGL"].max_leverage == 10
