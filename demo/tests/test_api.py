from fastapi.testclient import TestClient

from hyper_demo.api import app
from hyper_demo.models import OrderRecord, PrivyAgentWallet, RuntimeSettings, TradePlan
from hyper_demo.services.hypertracker import MarketIntelligence
from hyper_demo.services.market import MarketAsset
from hyper_demo.services.perplexity import FinanceContext
from hyper_demo.storage import JsonStore


def test_agent_analyze_creates_trade_proposal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    client = TestClient(app)

    response = client.post("/api/agent/analyze", json={"asset": "BTC"})

    assert response.status_code == 200
    plan = response.json()["plan"]
    analysis = response.json()["analysis"]
    assert plan["asset"] == "BTC"
    assert plan["network"] == "prodnet"
    assert plan["size_usdc"] <= 100
    assert plan["execution_decision"] == "proposed"
    assert response.json()["order_id"] is None
    assert analysis["asset"] == "BTC"
    assert analysis["best_candidate"]["side"] in {"long", "short"}
    assert len(analysis["timeframes"]) == 4
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


def test_agent_analyze_adds_perplexity_finance_context(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "token")

    def fake_context(self, asset):
        return FinanceContext(
            asset=asset,
            evidence=["Perplexity finance brief: BTC proxy risk appetite improved."],
            risks=["Perplexity finance_search coverage is partial for crypto perps."],
            assumptions=[],
            sources=["https://www.perplexity.ai/finance/BTC"],
            available=True,
        )

    monkeypatch.setattr(
        "hyper_demo.services.trading_agent.PerplexityFinanceClient.context_for_asset",
        fake_context,
    )
    client = TestClient(app)

    response = client.post("/api/agent/analyze", json={"asset": "BTC"})

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert any("Perplexity finance brief" in item for item in plan["evidence"])
    events = client.get("/api/agent/events").json()
    assert any("Perplexity finance_search context added" in event["message"] for event in events)


def test_agent_opportunities_are_ambitious_and_runtime_aware(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("HYPERTRACKER_API_KEY", "token")
    client = TestClient(app)
    runtime = client.post(
        "/api/settings/runtime",
        json={"network": "prodnet", "allowed_assets": ["BTC", "xyz:SPCX"]},
    )
    assert runtime.status_code == 200

    response = client.get("/api/agent/opportunities")

    assert response.status_code == 200
    opportunities = response.json()
    assert len(opportunities) >= 6
    assert {item["horizon"] for item in opportunities} == {"now", "next", "moonshot"}
    assert any("xyz:SPCX" in item["owner_loop"] for item in opportunities)
    assert any("HyperTracker positioning" in item["tools"] for item in opportunities)
    assert any("CONFIRM MAINNET ORDER" in item["human_gate"] for item in opportunities)


def test_agent_opportunities_use_testnet_gate_when_selected(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)
    runtime = client.post("/api/settings/runtime", json={"network": "testnet"})
    assert runtime.status_code == 200

    response = client.get("/api/agent/opportunities")

    assert response.status_code == 200
    assert any("testnet" in item["human_gate"].lower() for item in response.json())


def test_setup_check_reflects_hypertracker_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("HYPERTRACKER_API_KEY", "")
    client = TestClient(app)

    response = client.get("/api/setup-check")

    assert response.status_code == 200
    setup = response.json()
    assert setup["hypertracker_configured"] is False
    assert any("market intelligence enrichment disabled" in item for item in setup["warnings"])


def test_setup_check_reflects_perplexity_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PERPLEXITY_API_KEY", "")
    client = TestClient(app)

    response = client.get("/api/setup-check")

    assert response.status_code == 200
    setup = response.json()
    assert setup["perplexity_configured"] is False
    assert any("finance_search enrichment disabled" in item for item in setup["warnings"])


def test_state_bootstraps_runtime_assets_from_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("HYPERLIQUID_ALLOWED_ASSETS", "BTC,xyz:SPCX")
    client = TestClient(app)

    response = client.get("/api/state")

    assert response.status_code == 200
    runtime = response.json()["runtime"]
    assert runtime["allowed_assets"] == ["BTC", "xyz:SPCX"]
    assert runtime["watchlist"] == ["BTC", "xyz:SPCX"]


def test_setup_check_uses_persisted_runtime_assets_over_env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("HYPERLIQUID_ALLOWED_ASSETS", "BTC")
    store = JsonStore()
    store.save(
        "runtime",
        RuntimeSettings(
            allowed_assets=["BTC", "ETH", "SOL", "HYPE", "xyz:SPCX"],
            watchlist=["BTC", "ETH", "SOL", "HYPE", "xyz:SPCX"],
        ),
    )
    client = TestClient(app)

    response = client.get("/api/setup-check")

    assert response.status_code == 200
    setup = response.json()
    assert setup["hyperliquid_allowed_assets"] == ["BTC", "ETH", "HYPE", "SOL", "xyz:SPCX"]


def test_market_candles_endpoint_does_not_require_analysis(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)

    response = client.get("/api/market/BTC/candles?interval=1h&limit=24")

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset"] == "BTC"
    assert payload["interval"] == "1h"
    assert len(payload["candles"]) == 24
    state = client.get("/api/state").json()
    assert state["analysis"] is None
    assert state["plan"] is None


def test_market_candles_endpoint_supports_hip3_asset_without_analysis(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)

    response = client.get("/api/market/xyz%3ASPCX/candles?interval=1h&limit=24")

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset"] == "xyz:SPCX"
    assert payload["interval"] == "1h"
    assert len(payload["candles"]) == 24
    state = client.get("/api/state").json()
    assert state["analysis"] is None
    assert state["plan"] is None


def test_manual_market_plan_can_be_created_without_agent_proposal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/api/trades/manual-plan",
        json={
            "asset": "BTC",
            "side": "long",
            "entry_type": "market",
            "size_usdc": 25,
            "leverage": 2,
        },
    )

    assert response.status_code == 200
    plan = response.json()
    assert plan["asset"] == "BTC"
    assert plan["entry_type"] == "market"
    assert plan["stop_loss"] is None
    assert plan["take_profit"] is None
    assert plan["max_loss_usdc"] == 0
    assert plan["leverage"] == 2
    assert plan["source"] == "manual"
    state = client.get("/api/state").json()
    assert state["analysis"] is None
    assert state["plan"]["id"] == plan["id"]


def test_manual_limit_plan_accepts_optional_exits(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/api/trades/manual-plan",
        json={
            "asset": "BTC",
            "side": "short",
            "entry_type": "limit",
            "entry_price": 100,
            "stop_loss": 104,
            "take_profit": 92,
            "size_usdc": 50,
            "leverage": 1.5,
        },
    )

    assert response.status_code == 200
    plan = response.json()
    assert plan["side"] == "short"
    assert plan["entry_price"] == 100
    assert plan["stop_loss"] == 104
    assert plan["take_profit"] == 92
    assert plan["max_loss_usdc"] == 2
    assert plan["source"] == "manual"


def test_manual_spcx_short_market_plan_with_one_percent_tp(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))

    def fake_mark(self, asset):
        from hyper_demo.services.market import MarketPrice

        return MarketPrice(asset=asset, mark_price=155.0, source="test")

    monkeypatch.setattr("hyper_demo.api.MarketDataClient.mark_price", fake_mark)
    client = TestClient(app)
    runtime = client.post(
        "/api/settings/runtime",
        json={"allowed_assets": ["BTC", "xyz:SPCX"], "watchlist": ["BTC", "xyz:SPCX"]},
    )
    assert runtime.status_code == 200

    response = client.post(
        "/api/trades/manual-plan",
        json={
            "asset": "xyz:SPCX",
            "side": "short",
            "entry_type": "market",
            "size_usdc": 25,
            "take_profit": 153.45,
            "leverage": 3,
        },
    )

    assert response.status_code == 200
    plan = response.json()
    assert plan["source"] == "manual"
    assert plan["asset"] == "xyz:SPCX"
    assert plan["side"] == "short"
    assert plan["entry_type"] == "market"
    assert plan["entry_price"] == 155
    assert plan["stop_loss"] is None
    assert plan["take_profit"] == 153.45
    assert plan["leverage"] == 3


def test_manual_plan_rejects_leverage_above_asset_max(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))

    def fake_assets(self):
        return [
            MarketAsset(
                symbol="BTC",
                max_leverage=3,
                sz_decimals=5,
                mark_price=100,
                delisted=False,
                icon_url="",
            )
        ]

    monkeypatch.setattr("hyper_demo.api.MarketDataClient.available_assets", fake_assets)
    client = TestClient(app)

    response = client.post(
        "/api/trades/manual-plan",
        json={
            "asset": "BTC",
            "side": "long",
            "entry_type": "market",
            "size_usdc": 25,
            "leverage": 4,
        },
    )

    assert response.status_code == 400
    assert "between 1x and 3x" in response.json()["detail"]


def test_proactive_scan_generates_event_and_plan(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)

    response = client.post("/api/agent/proactive-scan")

    assert response.status_code == 200
    assert response.json()["plan"]["asset"] in {"BTC", "ETH", "SOL", "HYPE"}
    assert response.json()["analysis"]["asset"] == response.json()["plan"]["asset"]
    events = client.get("/api/agent/events").json()
    assert any("Proactive scan selected" in event["message"] for event in events)


def test_testnet_analysis_does_not_auto_execute(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))

    def fake_execute(self, plan, confirmed, confirmation_phrase=None):
        raise AssertionError("analysis must not execute orders")

    monkeypatch.setattr(
        "hyper_demo.services.trading_agent.HyperliquidAdapter.execute_plan",
        fake_execute,
    )
    client = TestClient(app)
    runtime = client.post("/api/settings/runtime", json={"network": "testnet"})
    assert runtime.status_code == 200

    response = client.post("/api/agent/analyze", json={"asset": "BTC"})

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["execution_decision"] == "proposed"
    assert response.json()["order_id"] is None


def test_prodnet_analysis_still_only_proposes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("HYPERLIQUID_MAINNET_ENABLED", "true")
    client = TestClient(app)

    runtime = client.post("/api/settings/runtime", json={"network": "prodnet"})
    assert runtime.status_code == 200

    response = client.post("/api/agent/analyze", json={"asset": "BTC"})

    assert response.status_code == 200
    assert response.json()["plan"]["execution_decision"] == "proposed"
    assert response.json()["plan"]["network"] == "prodnet"


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


def test_runtime_accepts_prodnet_selection_when_execution_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("HYPERLIQUID_MAINNET_ENABLED", "false")
    client = TestClient(app)

    response = client.post("/api/settings/runtime", json={"network": "prodnet"})

    assert response.status_code == 200
    assert response.json()["network"] == "prodnet"
    state = client.get("/api/state").json()
    assert any("Execution remains blocked" in item for item in state["setup"]["warnings"])


def test_runtime_syncs_asset_lists_when_enabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/api/settings/runtime",
        json={
            "sync_asset_lists": True,
            "allowed_assets": ["BTC", "xyz:SPCX"],
            "watchlist": ["ETH"],
        },
    )

    assert response.status_code == 200
    runtime = response.json()
    assert runtime["allowed_assets"] == ["BTC", "xyz:SPCX"]
    assert runtime["watchlist"] == ["BTC", "xyz:SPCX"]


def test_connected_privy_wallet_is_saved_in_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/api/wallet/connected",
        json={
            "address": "0x0000000000000000000000000000000000000000",
            "user_id": "privy-user",
            "email": "pm@example.com",
        },
    )

    assert response.status_code == 200
    state = client.get("/api/state").json()
    assert state["connected_wallet"]["address"] == "0x0000000000000000000000000000000000000000"
    assert state["connected_wallet"]["source"] == "privy"


def test_setup_privy_agent_wallet_saves_agent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    monkeypatch.setenv("HYPERLIQUID_MAINNET_ENABLED", "true")

    def fake_setup(
        self,
        network,
        current=None,
        master_wallet_id=None,
        master_wallet_address=None,
    ):
        return PrivyAgentWallet(
            network=network,
            master_wallet_id="master-id",
            master_wallet_address="0x0000000000000000000000000000000000000000",
            agent_wallet_id="agent-id",
            agent_wallet_address="0x0000000000000000000000000000000000000001",
            registered=True,
        )

    monkeypatch.setattr(
        "hyper_demo.api.PrivyHyperliquidAdapter.setup_agent_wallet",
        fake_setup,
    )
    client = TestClient(app)

    response = client.post("/api/privy/agent-wallet")

    assert response.status_code == 200
    state = client.get("/api/state").json()
    assert state["privy_agent_wallet"]["agent_wallet_id"] == "agent-id"


def test_setup_privy_agent_wallet_is_scoped_by_network(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    monkeypatch.setenv("HYPERLIQUID_MAINNET_ENABLED", "true")

    def fake_setup(
        self,
        network,
        current=None,
        master_wallet_id=None,
        master_wallet_address=None,
    ):
        suffix = network.value
        return PrivyAgentWallet(
            network=network,
            master_wallet_id=f"master-{suffix}",
            master_wallet_address="0x0000000000000000000000000000000000000000",
            agent_wallet_id=f"agent-{suffix}",
            agent_wallet_address="0x0000000000000000000000000000000000000001",
            registered=True,
        )

    monkeypatch.setattr(
        "hyper_demo.api.PrivyHyperliquidAdapter.setup_agent_wallet",
        fake_setup,
    )
    client = TestClient(app)

    client.post("/api/settings/runtime", json={"network": "testnet"})
    testnet = client.post("/api/privy/agent-wallet")
    assert testnet.status_code == 200
    client.post("/api/settings/runtime", json={"network": "prodnet"})
    prodnet = client.post("/api/privy/agent-wallet")

    assert prodnet.status_code == 200
    store = JsonStore()
    testnet_agent = store.get("privy_agent_wallet", "privy_agent_wallet_testnet")
    prodnet_agent = store.get("privy_agent_wallet", "privy_agent_wallet_prodnet")
    active_agent = client.get("/api/state").json()["privy_agent_wallet"]

    assert testnet_agent.agent_wallet_id == "agent-testnet"
    assert prodnet_agent.agent_wallet_id == "agent-prodnet"
    assert active_agent["agent_wallet_id"] == "agent-prodnet"


def test_setup_privy_agent_wallet_blocks_mainnet_without_enable_flag(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    monkeypatch.setenv("HYPERLIQUID_MAINNET_ENABLED", "false")
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet"))
    client = TestClient(app)

    response = client.post("/api/privy/agent-wallet")

    assert response.status_code == 400
    assert "Prodnet agent registration is disabled" in response.json()["detail"]


def test_privy_execution_uses_privy_adapter(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="testnet"))
    agent = PrivyAgentWallet(
        master_wallet_id="master-id",
        master_wallet_address="0x0000000000000000000000000000000000000000",
        agent_wallet_id="agent-id",
        agent_wallet_address="0x0000000000000000000000000000000000000001",
        network="testnet",
        registered=True,
    )
    store.save("privy_agent_wallet", agent)

    def fake_execute(self, plan, runtime_agent, confirmed, confirmation_phrase=None):
        assert runtime_agent.agent_wallet_id == "agent-id"
        assert confirmed is True
        return OrderRecord(
            plan_id=plan.id,
            exchange="hyperliquid-testnet",
            asset=plan.asset,
            side=plan.side,
            size_usdc=plan.size_usdc,
            message="privy submitted",
        )

    monkeypatch.setattr(
        "hyper_demo.services.trading_agent.PrivyHyperliquidAdapter.execute_plan",
        fake_execute,
    )
    client = TestClient(app)

    analysis_response = client.post("/api/agent/analyze", json={"asset": "BTC"})
    assert analysis_response.status_code == 200
    plan_id = analysis_response.json()["plan"]["id"]
    response = client.post(f"/api/trades/{plan_id}/execute", json={"confirmed": True})

    assert response.status_code == 200
    assert response.json()["plan"]["execution_message"] == "privy submitted"


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
