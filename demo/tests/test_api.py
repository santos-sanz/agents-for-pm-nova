from fastapi.testclient import TestClient

from hyper_demo.api import app
from hyper_demo.models import OrderRecord, TradePlan
from hyper_demo.storage import JsonStore


def test_profile_research_proposal_and_guarded_execution(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid-testnet.xyz")
    monkeypatch.setenv("HYPERLIQUID_WS_URL", "wss://api.hyperliquid-testnet.xyz/ws")
    client = TestClient(app)

    profile_response = client.post(
        "/api/profile",
        json={
            "horizon_days": 30,
            "max_drawdown_pct": 8,
            "leverage_tolerance": "low",
            "asset_preference": "BTC",
            "capital_at_risk_usdc": 100,
            "stop_loss_pct": 4,
        },
    )
    assert profile_response.status_code == 200

    research_response = client.post("/api/research", json={"asset": "BTC"})
    assert research_response.status_code == 200
    assert research_response.json()["fallback_used"] is True

    proposal_response = client.post("/api/proposals", json={"asset": "BTC"})
    assert proposal_response.status_code == 200
    plan_id = proposal_response.json()["id"]

    blocked_response = client.post(
        "/api/orders/testnet", json={"plan_id": plan_id, "confirmed": False}
    )
    assert blocked_response.status_code == 400


def test_metrics_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)
    response = client.get("/api/portfolio/metrics")
    assert response.status_code == 200
    assert "alpha" in response.json()


def test_agent_team_endpoint_returns_consensus(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)

    response = client.post("/api/agents/debate", json={"asset": "BTC"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset"] == "BTC"
    assert payload["consensus"] in {"approve_paper_trade", "revise_plan", "reject_trade"}
    assert len(payload["opinions"]) == 4


def test_replay_rejects_path_traversal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)
    response = client.post("/api/replay/bad.name")
    assert response.status_code == 400


def test_paper_order_creates_debug_events(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    store = JsonStore()
    plan = TradePlan(
        asset="BTC",
        side="long",
        size_usdc=100,
        entry_price=100,
        stop_loss=95,
        take_profit=110,
        max_loss_usdc=5,
        rationale="test",
        invalidation_criteria=[],
    )
    store.save("plans", plan)
    client = TestClient(app)

    response = client.post("/api/orders/paper", json={"plan_id": plan.id, "confirmed": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["order"]["exchange"] == "paper-coinbase"
    events = client.get(f"/api/runs/{payload['run']['id']}/events")
    assert events.status_code == 200
    assert len(events.json()) == 3


def test_metrics_use_paper_fill_price(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))

    class FakeResponse:
        def __enter__(self):
            import io
            import json

            return io.BytesIO(json.dumps({"price": "105"}).encode("utf-8"))

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: FakeResponse())
    store = JsonStore()
    plan = TradePlan(
        asset="BTC",
        side="long",
        size_usdc=100,
        entry_price=100,
        stop_loss=95,
        take_profit=110,
        max_loss_usdc=5,
        rationale="test",
        invalidation_criteria=[],
    )
    order = OrderRecord(
        plan_id=plan.id,
        exchange="paper-coinbase",
        asset="BTC",
        side="long",
        size_usdc=100,
        raw_response={"fill": {"fill_price": 100, "notional_usdc": 100}},
        status="simulated",
        message="paper",
    )
    store.save("plans", plan)
    store.save("orders", order)
    client = TestClient(app)

    response = client.get("/api/portfolio/metrics")

    assert response.status_code == 200
    assert response.json()["unrealized_pnl_usdc"] == 5.0
