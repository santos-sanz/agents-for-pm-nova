from fastapi.testclient import TestClient

from hyper_demo.api import app


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


def test_replay_rejects_path_traversal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)
    response = client.post("/api/replay/bad.name")
    assert response.status_code == 400
