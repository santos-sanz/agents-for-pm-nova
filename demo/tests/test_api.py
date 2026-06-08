from fastapi.testclient import TestClient

from hyper_demo.api import app
from hyper_demo.models import OrderRecord, RuntimeSettings, TradePlan
from hyper_demo.services.hypertracker import MarketIntelligence
from hyper_demo.storage import JsonStore


def test_agent_analyze_creates_trade_proposal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    client = TestClient(app)

    response = client.post("/api/agent/analyze", json={"asset": "BTC"})

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["asset"] == "BTC"
    assert plan["network"] == "testnet"
    assert plan["size_usdc"] <= 100
    assert plan["execution_decision"] in {"blocked", "auto_executed"}
    events = client.get("/api/agent/events")
    assert events.status_code == 200
    assert len(events.json()) >= 2


def test_agent_analyze_adds_hypertracker_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    def fake_intelligence(self, asset):
        return MarketIntelligence(
            asset=asset,
            evidence=["HyperTracker shows aggregate BTC perpetual exposure near $125.00M."],
            risks=["HyperTracker positioning is crowded long on BTC, raising squeeze risk."],
            assumptions=[],
            sources=["HyperTracker /api/external/position-metrics/coin/{asset}"],
            available=True,
        )

    monkeypatch.setattr(
        "hyper_demo.services.trading_agent.HyperTrackerClient.intelligence_for_asset",
        fake_intelligence,
    )
    client = TestClient(app)

    response = client.post("/api/agent/analyze", json={"asset": "BTC"})

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert any("HyperTracker shows aggregate BTC" in item for item in plan["evidence"])
    events = client.get("/api/agent/events").json()
    assert any("HyperTracker market intelligence added" in event["message"] for event in events)


def test_setup_check_reflects_hypertracker_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("HYPERTRACKER_API_KEY", "")
    client = TestClient(app)

    response = client.get("/api/setup-check")

    assert response.status_code == 200
    setup = response.json()
    assert setup["hypertracker_configured"] is False
    assert any("market intelligence enrichment disabled" in item for item in setup["warnings"])


def test_proactive_scan_generates_event_and_plan(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)

    response = client.post("/api/agent/proactive-scan")

    assert response.status_code == 200
    assert response.json()["plan"]["asset"] in {"BTC", "ETH", "SOL", "HYPE"}
    events = client.get("/api/agent/events").json()
    assert any("Proactive scan selected" in event["message"] for event in events)


def test_testnet_auto_execution_uses_hyperliquid_adapter(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))

    def fake_execute(self, plan, confirmed, confirmation_phrase=None):
        assert confirmed is True
        return OrderRecord(
            plan_id=plan.id,
            exchange="hyperliquid-testnet",
            asset=plan.asset,
            side=plan.side,
            size_usdc=plan.size_usdc,
            message="fake submitted",
        )

    monkeypatch.setattr(
        "hyper_demo.services.trading_agent.HyperliquidAdapter.execute_plan",
        fake_execute,
    )
    client = TestClient(app)

    response = client.post("/api/agent/analyze", json={"asset": "BTC"})

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["execution_decision"] == "auto_executed"
    assert response.json()["order_id"]


def test_prodnet_analysis_waits_for_confirmation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("HYPERLIQUID_MAINNET_ENABLED", "true")
    client = TestClient(app)

    runtime = client.post("/api/settings/runtime", json={"network": "prodnet"})
    assert runtime.status_code == 200

    response = client.post("/api/agent/analyze", json={"asset": "BTC"})

    assert response.status_code == 200
    assert response.json()["plan"]["execution_decision"] == "waiting_confirmation"


def test_prodnet_confirmation_requires_phrase(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("HYPERLIQUID_MAINNET_ENABLED", "true")
    monkeypatch.setenv("HYPERLIQUID_ACCOUNT_ADDRESS", "0x0000000000000000000000000000000000000000")
    monkeypatch.setenv(
        "HYPERLIQUID_API_WALLET_PRIVATE_KEY",
        "0x0000000000000000000000000000000000000000000000000000000000000001",
    )
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet"))
    plan = TradePlan(
        asset="BTC",
        side="long",
        size_usdc=25,
        entry_price=100,
        stop_loss=95,
        take_profit=110,
        max_loss_usdc=5,
        rationale="test",
        invalidation_criteria=[],
        network="prodnet",
    )
    store.save("plans", plan)
    client = TestClient(app)

    response = client.post(f"/api/trades/{plan.id}/execute", json={"confirmed": True})

    assert response.status_code == 400
    assert "CONFIRM MAINNET ORDER" in response.json()["detail"]


def test_runtime_rejects_prodnet_when_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("HYPERLIQUID_MAINNET_ENABLED", "false")
    client = TestClient(app)

    response = client.post("/api/settings/runtime", json={"network": "prodnet"})

    assert response.status_code == 400


def test_metrics_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)
    response = client.get("/api/portfolio/metrics")
    assert response.status_code == 200
    assert "alpha" in response.json()


def test_legacy_workflow_routes_are_removed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)

    for path in [
        "/api/profile",
        "/api/research",
        "/api/proposals",
        "/api/orders/testnet",
        "/api/agents/debate",
        "/api/replay/fallback",
    ]:
        response = client.post(path, json={})
        assert response.status_code == 404

    for path in ["/profile", "/research", "/proposal", "/agents", "/execution", "/settings"]:
        response = client.get(path)
        assert response.status_code == 404
