import io
import json
import urllib.error

from hyper_demo.config import Settings
from hyper_demo.services.hypertracker import HyperTrackerClient


class FakeResponse:
    def __init__(self, payload) -> None:
        self.payload = payload

    def __enter__(self):
        return io.BytesIO(json.dumps(self.payload).encode("utf-8"))

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None


def test_hypertracker_client_sends_bearer_token_and_summarizes(monkeypatch) -> None:
    requested_urls: list[str] = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        assert request.get_header("Authorization") == "Bearer test-token"
        assert timeout == 6
        if "/position-metrics/coin/BTC" in request.full_url:
            return FakeResponse(
                {
                    "metrics": [
                        {
                            "totalPositionValue": 125_000_000,
                            "longPositionValue": 75_000_000,
                            "shortPositionValue": 50_000_000,
                            "positionCount": 2400,
                            "sumUpnl": 1_250_000,
                        }
                    ]
                }
            )
        return FakeResponse(
            {
                "items": [
                    {
                        "address": "0x1234567890abcdef1234567890abcdef12345678",
                        "totalEquity": 1_200_000,
                        "perpPnl": 85_000,
                        "openValue": 4_500_000,
                        "perpBias": 3.2,
                    }
                ]
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    intelligence = HyperTrackerClient(
        Settings(HYPERTRACKER_API_KEY="test-token")
    ).intelligence_for_asset("BTC")

    assert intelligence.available
    assert len(requested_urls) == 2
    assert any("/api/external/position-metrics/coin/BTC" in url for url in requested_urls)
    assert any("/api/external/leaderboards/perp-pnl" in url for url in requested_urls)
    assert any("aggregate BTC perpetual exposure" in item for item in intelligence.evidence)
    assert any("long/short positioning" in item for item in intelligence.evidence)
    assert any("top 24h perp PnL wallet" in item for item in intelligence.evidence)
    assert intelligence.sources


def test_hypertracker_client_is_unavailable_without_key() -> None:
    intelligence = HyperTrackerClient(Settings(HYPERTRACKER_API_KEY="")).intelligence_for_asset(
        "BTC"
    )

    assert not intelligence.available
    assert intelligence.evidence == []
    assert "API key is not configured" in intelligence.assumptions[0]


def test_hypertracker_client_falls_back_on_http_error(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            429,
            "rate limited",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    intelligence = HyperTrackerClient(
        Settings(HYPERTRACKER_API_KEY="test-token")
    ).intelligence_for_asset("BTC")

    assert not intelligence.available
    assert intelligence.evidence == []
    assert any("unavailable" in item for item in intelligence.assumptions)
