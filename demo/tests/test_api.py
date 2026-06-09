import json

from fastapi.testclient import TestClient

from hyper_demo.api import app, run_chat_custom_tool
from hyper_demo.models import (
    ManagedChatDeployment,
    ManagedChatEvent,
    ManagedChatResources,
    ManagedChatSession,
    OrderRecord,
    PrivyAgentWallet,
    ResearchReport,
    RuntimeSettings,
    TradePlan,
)
from hyper_demo.services.hypertracker import MarketIntelligence
from hyper_demo.services.managed_chat import ManagedTradingChatService
from hyper_demo.services.market import MarketAsset, MarketPrice
from hyper_demo.services.perplexity import FinanceContext
from hyper_demo.storage import JsonStore


class FakeManagedObject:
    def __init__(self, item_id: str, version: int | None = None, **kwargs) -> None:
        self.id = item_id
        self.version = version
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeManagedStream:
    def __init__(self, events):
        self.events = events

    def __enter__(self):
        return iter(self.events)

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeManagedEvents:
    def __init__(self) -> None:
        self.sent = []
        self.stream_events = [
            {
                "type": "agent.message",
                "content": [{"type": "text", "text": "Ready."}],
            },
            {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
        ]

    def stream(self, session_id):
        return FakeManagedStream(self.stream_events)

    def send(self, session_id, *, events):
        self.sent.append({"session_id": session_id, "events": events})
        return FakeManagedObject("sent")


class FakeManagedAnthropic:
    def __init__(self) -> None:
        self.beta = self
        self.environments = self
        self.skills = self
        self.agents = self
        self.sessions = self
        self.vaults = self
        self.credentials = self
        self.memory_stores = self
        self.memories = self
        self.events = FakeManagedEvents()
        self.created_environments = []
        self.created_sessions = []
        self.created_agents = []
        self.created_skills = []
        self.created_vaults = []
        self.created_credentials = []
        self._skill_count = 0
        self._agent_count = 0
        self._memory_count = 0
        self._credential_count = 0

    def create(self, *args, **kwargs):
        if "environment" in kwargs.get("name", "").lower() or kwargs.get("config"):
            self.created_environments.append(kwargs)
            return FakeManagedObject("env_chat")
        if kwargs.get("files") is not None:
            self._skill_count += 1
            self.created_skills.append(kwargs)
            return FakeManagedObject(f"skill_{self._skill_count}", version=1)
        if kwargs.get("model") is not None:
            self._agent_count += 1
            self.created_agents.append(kwargs)
            return FakeManagedObject(f"agent_{self._agent_count}", version=1)
        if kwargs.get("agent") is not None:
            self.created_sessions.append(kwargs)
            return FakeManagedObject("sess_chat")
        if kwargs.get("display_name") and "bearer" not in kwargs.get("display_name", ""):
            self.created_vaults.append(kwargs)
            return FakeManagedObject("vault_chat")
        if kwargs.get("auth") is not None:
            self._credential_count += 1
            self.created_credentials.append({"args": args, "kwargs": kwargs})
            return FakeManagedObject(f"cred_{self._credential_count}")
        if kwargs.get("name") is not None:
            self._memory_count += 1
            return FakeManagedObject(f"mem_{self._memory_count}")
        return FakeManagedObject("created")

    def update(self, *args, **kwargs):
        return FakeManagedObject("updated")

    def list(self, *args, **kwargs):
        return FakeManagedObject("list", data=[])


class FakeHttpResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_agent_analyze_creates_trade_proposal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    client = TestClient(app)

    response = client.post("/api/agent/analyze", json={"asset": "BTC"})

    assert response.status_code == 200, response.json()
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
    assert all(float(item["leverage"]).is_integer() for item in analysis["candidates"])
    events = client.get("/api/agent/events")
    assert events.status_code == 200
    event_payloads = [event.get("payload", {}) for event in events.json()]
    analysis_context = next(
        payload.get("context", "") for payload in event_payloads if "context" in payload
    )
    assert "Available trading input=" in analysis_context
    assert "BTC max supported leverage=" in analysis_context
    assert len(events.json()) >= 2


def test_agent_chat_auto_uses_managed_chat_service(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    captured: dict[str, str] = {}
    session = ManagedChatSession(
        title="Trading Auto intraday - BTC",
        claude_session_id="sess_chat",
    )
    plan = TradePlan(
        asset="BTC",
        side="short",
        size_usdc=12,
        entry_price=62000,
        take_profit=61000,
        leverage=3,
        rationale="test",
        invalidation_criteria=["test"],
    ).model_dump(mode="json")
    events = [
        ManagedChatEvent(
            session_id=session.id,
            type="user.custom_tool_result",
            role="tool",
            payload={"result": {"plan": plan}},
        ),
        ManagedChatEvent(
            session_id=session.id,
            type="agent.message",
            role="agent",
            text="Ranked intraday proposals are ready.",
        ),
    ]

    class FakeChatService:
        def resources(self):
            return ManagedChatResources(status="ready")

        async def create_session(self, title=None):
            captured["title"] = title
            return session

        async def send_message(self, session_id, message, tool_runner=None):
            captured["session_id"] = session_id
            captured["message"] = message
            captured["tool_runner"] = str(tool_runner is not None)
            return session

        def events(self, session_id):
            captured["events_session_id"] = session_id
            return events

    monkeypatch.setattr("hyper_demo.api.get_chat_service", lambda store=None: FakeChatService())
    client = TestClient(app)

    response = client.post(
        "/api/agent/chat-auto",
        json={"asset": "BTC", "risk_appetite": "balanced", "close_window": "1h"},
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["session"]["id"] == session.id
    assert payload["plans"][0]["asset"] == "BTC"
    assert payload["plan"]["id"] == plan["id"]
    assert captured["title"] == "Trading Auto intraday - BTC"
    assert "Risk appetite: balanced." in captured["message"]
    assert "Preferred close window: 1h." in captured["message"]
    assert "Do not execute any trade from this Auto request." in captured["message"]
    assert captured["tool_runner"] == "True"


def test_agent_chat_auto_requires_managed_chat_ready(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_CHAT_AUTO_BOOTSTRAP", "false")

    class FakeChatService:
        def resources(self):
            return ManagedChatResources(status="disabled", disabled_reason="not configured")

    monkeypatch.setattr("hyper_demo.api.get_chat_service", lambda store=None: FakeChatService())
    client = TestClient(app)

    response = client.post(
        "/api/agent/chat-auto",
        json={"asset": "BTC", "risk_appetite": "balanced", "close_window": "1h"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "not configured"


def test_agent_proposal_can_be_approved_as_valid_plan(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    client = TestClient(app)

    analysis_response = client.post(
        "/api/agent/analyze",
        json={
            "asset": "BTC",
            "risk_appetite": "balanced",
            "close_window": "1h",
        },
    )
    assert analysis_response.status_code == 200

    proposals = analysis_response.json()["analysis"]["candidates"]
    response = None
    for index in range(len(proposals)):
        response = client.post(f"/api/agent/proposals/{index}/approve")
        if response.status_code == 200:
            break

    assert response is not None
    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["plan"]["source"] == "agent"
    assert payload["plan"]["id"] == payload["analysis"]["plan_id"]
    assert float(payload["plan"]["leverage"]).is_integer()


def test_agent_market_proposal_approval_uses_live_entry_price(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    client = TestClient(app)

    analysis_response = client.post("/api/agent/analyze", json={"asset": "BTC"})
    assert analysis_response.status_code == 200
    proposals = analysis_response.json()["analysis"]["candidates"]
    market_index, market_proposal = next(
        (index, proposal)
        for index, proposal in enumerate(proposals)
        if proposal["entry_type"] == "market"
    )
    stale_entry = float(market_proposal["entry_price"])
    live_mark = stale_entry * 1.03

    def fake_mark(self, asset):
        return MarketPrice(asset=asset, mark_price=live_mark, source="test")

    monkeypatch.setattr("hyper_demo.api.MarketDataClient.mark_price", fake_mark)

    response = client.post(f"/api/agent/proposals/{market_index}/approve")

    assert response.status_code == 200, response.json()
    plan = response.json()["plan"]
    assert plan["entry_type"] == "market"
    assert plan["entry_price"] == round(live_mark, 6)
    assert plan["entry_price"] != stale_entry
    if plan["side"] == "long":
        assert plan["take_profit"] > plan["entry_price"]
        if plan["stop_loss"] is None:
            assert plan["leverage"] < 10
        else:
            assert plan["stop_loss"] < plan["entry_price"]
    else:
        assert plan["take_profit"] < plan["entry_price"]
        if plan["stop_loss"] is None:
            assert plan["leverage"] < 10
        else:
            assert plan["stop_loss"] > plan["entry_price"]


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

    captured = {}

    async def fake_research(self, asset, profile=None, external_context=None):
        captured["external_context"] = external_context
        return ResearchReport(
            asset=asset,
            profile_id=profile.id if profile else None,
            thesis="Captured research input.",
            evidence=["Captured base evidence."],
            risks=[],
            assumptions=[],
            why_not_invest=[],
            sources=[],
            fallback_used=False,
        )

    monkeypatch.setattr(
        "hyper_demo.services.trading_agent.PerplexityFinanceClient.context_for_asset",
        fake_context,
    )
    monkeypatch.setattr(
        "hyper_demo.services.trading_agent.ManagedAgentResearchClient.research",
        fake_research,
    )
    client = TestClient(app)

    response = client.post(
        "/api/agent/analyze",
        json={
            "asset": "BTC",
            "context": "User wants auto proposals constrained by account inputs.",
            "available_usdc": 42,
            "max_leverage": 3,
        },
    )

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert any("Perplexity finance brief" in item for item in plan["evidence"])
    assert "User wants auto proposals" in captured["external_context"]
    assert "Available trading input=" in captured["external_context"]
    assert "BTC max supported leverage=" in captured["external_context"]
    assert "Perplexity finance_search context" in captured["external_context"]
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
    assert any("explicit mainnet enablement" in item["human_gate"] for item in opportunities)


def test_agent_opportunities_use_testnet_gate_when_selected(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)
    runtime = client.post("/api/settings/runtime", json={"network": "testnet"})
    assert runtime.status_code == 200

    response = client.get("/api/agent/opportunities")

    assert response.status_code == 200
    assert any("testnet" in item["human_gate"].lower() for item in response.json())


def test_chat_bootstrap_without_anthropic_key_is_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    client = TestClient(app)

    response = client.post("/api/chat/bootstrap", json={"force": True})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "disabled"
    assert "ANTHROPIC_API_KEY" in payload["disabled_reason"]
    session = client.post("/api/chat/sessions", json={"title": "Fallback"})
    assert session.status_code == 200
    assert session.json()["status"] == "disabled"


def test_chat_state_includes_default_deployment(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    client = TestClient(app)

    response = client.get("/api/chat/state")

    assert response.status_code == 200
    deployment = response.json()["deployment"]
    assert deployment["id"] == "managed_chat_deployment"
    assert deployment["status"] == "not_created"
    assert deployment["cron_expression"] == "*/30 * * * *"
    assert deployment["timezone"] == "Europe/Madrid"
    assert "explicit host human approval" in deployment["initial_prompt"]
    assert "Record non-secret lessons" in deployment["initial_prompt"]


def test_chat_create_deployment_posts_anthropic_payload(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-token")
    store = JsonStore()
    store.save(
        "managed_chat_resources",
        ManagedChatResources(
            status="ready",
            environment_id="env_chat",
            coordinator_agent_id="agent_chat",
            memory_store_ids={"canon": "mem_canon", "learning": "mem_learning"},
            vault_ids=["vault_chat"],
        ),
    )
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHttpResponse(
            {
                "id": "depl_chat",
                "status": "active",
                "paused_reason": None,
                "schedule": {
                    "type": "cron",
                    "expression": "*/15 * * * *",
                    "timezone": "Europe/Madrid",
                    "upcoming_runs_at": ["2026-06-09T22:15:00Z"],
                },
            }
        )

    monkeypatch.setattr("hyper_demo.services.managed_chat.urllib.request.urlopen", fake_urlopen)
    client = TestClient(app)

    response = client.post(
        "/api/chat/deployment",
        json={
            "name": "HyperClaude intraday watch",
            "cron_expression": "*/15 * * * *",
            "timezone": "Europe/Madrid",
            "initial_prompt": "Run a safe scheduled watch and do not execute in human mode.",
        },
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["anthropic_deployment_id"] == "depl_chat"
    assert payload["status"] == "active"
    assert payload["upcoming_runs_at"] == ["2026-06-09T22:15:00Z"]
    assert captured["url"] == "https://api.anthropic.com/v1/deployments"
    assert captured["timeout"] == 30
    headers = {key.lower(): value for key, value in captured["headers"].items()}
    assert headers["anthropic-beta"] == "managed-agents-2026-04-01"
    assert headers["x-api-key"] == "anthropic-token"
    body = captured["body"]
    assert body["agent"] == "agent_chat"
    assert body["environment_id"] == "env_chat"
    assert body["vault_ids"] == ["vault_chat"]
    assert body["schedule"] == {
        "type": "cron",
        "expression": "*/15 * * * *",
        "timezone": "Europe/Madrid",
    }
    assert body["initial_events"][0]["type"] == "user.message"
    assert body["resources"] == [
        {
            "type": "memory_store",
            "memory_store_id": "mem_canon",
            "access": "read_only",
            "instructions": "Use as immutable trading safety canon.",
        },
        {
            "type": "memory_store",
            "memory_store_id": "mem_learning",
            "access": "read_write",
            "instructions": (
                "Store non-secret user preferences, rejected setups, post-trade lessons, "
                "and process improvements."
            ),
        },
    ]


def test_chat_run_deployment_posts_run_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-token")
    store = JsonStore()
    store.save(
        "managed_chat_deployments",
        ManagedChatDeployment(
            id="managed_chat_deployment",
            name="HyperClaude intraday watch",
            status="active",
            anthropic_deployment_id="depl_chat",
            cron_expression="*/30 * * * *",
            timezone="Europe/Madrid",
            initial_prompt="Watch only.",
        ),
    )
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHttpResponse(
            {
                "id": "drun_chat",
                "deployment_id": "depl_chat",
                "session_id": "sesn_chat",
            }
        )

    monkeypatch.setattr("hyper_demo.services.managed_chat.urllib.request.urlopen", fake_urlopen)
    client = TestClient(app)

    response = client.post("/api/chat/deployment/run")

    assert response.status_code == 200, response.json()
    payload = response.json()
    assert payload["last_run_id"] == "drun_chat"
    assert payload["last_session_id"] == "sesn_chat"
    assert captured["url"] == "https://api.anthropic.com/v1/deployments/depl_chat/run"
    assert captured["body"] == {}


def test_chat_bootstrap_creates_managed_resources_and_vaults(tmp_path, monkeypatch) -> None:
    fake = FakeManagedAnthropic()
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-token")
    monkeypatch.setenv("HYPERTRACKER_API_KEY", "hypertracker-secret")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "perplexity-secret")
    monkeypatch.setenv(
        "ANTHROPIC_CHAT_MCP_SERVERS",
        json.dumps(
            [
                {"name": "hypertracker", "url": "https://mcp.example.com/hypertracker"},
                {"name": "perplexity", "url": "https://mcp.example.com/perplexity"},
            ]
        ),
    )
    monkeypatch.setattr(ManagedTradingChatService, "_client", lambda self: fake)
    client = TestClient(app)

    response = client.post("/api/chat/bootstrap", json={"force": True})

    assert response.status_code == 200, response.json()
    payload = response.json()
    dumped = json.dumps(payload)
    assert payload["status"] == "ready"
    assert payload["environment_id"] == "env_chat"
    assert payload["coordinator_agent_id"] == "agent_6"
    assert set(payload["skill_ids"]) == {
        "hyperliquid-safety",
        "source-quality",
        "hypertracker-cli",
        "trade-validation",
        "formal-order-validation",
        "self-improvement",
    }
    assert set(payload["memory_store_ids"]) == {"canon", "learning"}
    assert payload["vault_ids"] == ["vault_chat"]
    assert {item["name"] for item in payload["credentials"]} >= {"hypertracker", "perplexity"}
    credential_statuses = {item["name"]: item for item in payload["credentials"]}
    assert credential_statuses["hypertracker"]["kind"] == "vault"
    assert credential_statuses["hypertracker"]["status"] == "connected"
    assert credential_statuses["perplexity"]["kind"] == "vault"
    assert credential_statuses["perplexity"]["status"] == "connected"
    assert len(fake.created_vaults) == 1
    assert len(fake.created_credentials) == 2
    assert {
        item["kwargs"]["auth"]["mcp_server_url"] for item in fake.created_credentials
    } == {
        "https://mcp.example.com/hypertracker",
        "https://mcp.example.com/perplexity",
    }
    assert payload["mcp_servers"] == [
        {
            "name": "hypertracker",
            "type": "url",
            "url": "https://mcp.example.com/hypertracker",
        },
        {
            "name": "perplexity",
            "type": "url",
            "url": "https://mcp.example.com/perplexity",
        },
    ]
    environment_hosts = fake.created_environments[-1]["config"]["networking"]["allowed_hosts"]
    assert "mcp.example.com" in environment_hosts
    coordinator_agent = fake.created_agents[-1]
    assert coordinator_agent["mcp_servers"] == payload["mcp_servers"]
    assert {
        tool["mcp_server_name"]
        for tool in coordinator_agent["tools"]
        if tool["type"] == "mcp_toolset"
    } == {"hypertracker", "perplexity"}
    assert "trading_close_position" in payload["custom_tools"]
    assert "hypertracker-secret" not in dumped
    assert "perplexity-secret" not in dumped
    assert len(fake.created_skills) == 6
    skill_uploads = {
        files[0][0].split("/")[0]: files[0][1]
        for created_skill in fake.created_skills
        if (files := created_skill["files"])
    }
    assert b"uv run demo hypertracker --asset BTC" in skill_uploads["hypertracker-cli"]
    assert b"trading_hypertracker_intelligence" in skill_uploads["hypertracker-cli"]
    for created_skill in fake.created_skills:
        files = created_skill["files"]
        assert len(files) == 1
        uploaded_path, uploaded_body = files[0]
        assert uploaded_path.count("/") == 1
        assert uploaded_path.endswith("/SKILL.md")
        assert uploaded_body.startswith(b"---\nname: ")
        assert b"\ndescription: " in uploaded_body


def test_chat_bootstrap_creates_vault_for_api_key_tools_without_mcp(
    tmp_path,
    monkeypatch,
) -> None:
    fake = FakeManagedAnthropic()
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-token")
    monkeypatch.setenv("HYPERTRACKER_API_KEY", "hypertracker-secret")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "perplexity-secret")
    monkeypatch.setattr(ManagedTradingChatService, "_client", lambda self: fake)
    client = TestClient(app)

    response = client.post("/api/chat/bootstrap", json={"force": True})

    assert response.status_code == 200, response.json()
    payload = response.json()
    dumped = json.dumps(payload)
    assert payload["status"] == "ready"
    assert payload["vault_ids"] == ["vault_chat"]
    assert len(fake.created_vaults) == 1
    assert fake.created_credentials == []
    credential_statuses = {item["name"]: item for item in payload["credentials"]}
    assert credential_statuses["hypertracker"]["kind"] == "vault"
    assert credential_statuses["hypertracker"]["status"] == "unavailable"
    assert credential_statuses["hypertracker"]["vault_id"] == "vault_chat"
    assert "MCP_SERVER_URL" in credential_statuses["hypertracker"]["message"]
    assert credential_statuses["perplexity"]["kind"] == "vault"
    assert credential_statuses["perplexity"]["status"] == "unavailable"
    assert credential_statuses["perplexity"]["vault_id"] == "vault_chat"
    assert "hypertracker-secret" not in dumped
    assert "perplexity-secret" not in dumped

    session = client.post("/api/chat/sessions", json={"title": "Vault fallback"}).json()
    assert session["vault_ids"] == ["vault_chat"]


def test_chat_bootstrap_wires_perplexity_mcp_shortcut(tmp_path, monkeypatch) -> None:
    fake = FakeManagedAnthropic()
    mcp_url = "https://perplexity.tunnel.example.com/mcp"
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-token")
    monkeypatch.setenv("HYPERTRACKER_API_KEY", "")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "perplexity-secret")
    monkeypatch.setenv("PERPLEXITY_MCP_SERVER_URL", mcp_url)
    monkeypatch.setattr(ManagedTradingChatService, "_client", lambda self: fake)
    client = TestClient(app)

    response = client.post("/api/chat/bootstrap", json={"force": True})

    assert response.status_code == 200, response.json()
    payload = response.json()
    dumped = json.dumps(payload)
    assert payload["status"] == "ready"
    assert payload["mcp_servers"] == [
        {"name": "perplexity", "type": "url", "url": mcp_url},
    ]
    assert payload["vault_ids"] == ["vault_chat"]
    credentials = {item["name"]: item for item in payload["credentials"]}
    assert credentials["perplexity"]["kind"] == "vault"
    assert credentials["perplexity"]["status"] == "connected"
    assert credentials["perplexity"]["mcp_server"] == "perplexity"
    assert credentials["perplexity"]["credential_id"] == "cred_1"
    assert fake.created_credentials == [
        {
            "args": ("vault_chat",),
            "kwargs": {
                "display_name": "perplexity bearer token",
                "auth": {
                    "type": "static_bearer",
                    "token": "perplexity-secret",
                    "mcp_server_url": mcp_url,
                },
                "metadata": {"app": "hyperclaude", "tool": "perplexity"},
            },
        }
    ]
    environment_hosts = fake.created_environments[-1]["config"]["networking"]["allowed_hosts"]
    assert "perplexity.tunnel.example.com" in environment_hosts
    coordinator_agent = fake.created_agents[-1]
    assert coordinator_agent["mcp_servers"] == payload["mcp_servers"]
    assert any(
        tool["type"] == "mcp_toolset" and tool["mcp_server_name"] == "perplexity"
        for tool in coordinator_agent["tools"]
    )
    assert "perplexity-secret" not in dumped


def test_chat_session_attaches_vaults_and_memory_resources(tmp_path, monkeypatch) -> None:
    fake = FakeManagedAnthropic()
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-token")
    monkeypatch.setenv("ANTHROPIC_CHAT_VAULT_IDS", "vault_existing")
    monkeypatch.setenv("HYPERTRACKER_API_KEY", "")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "")
    monkeypatch.setattr(ManagedTradingChatService, "_client", lambda self: fake)
    client = TestClient(app)
    bootstrap = client.post("/api/chat/bootstrap", json={"force": True})
    assert bootstrap.status_code == 200

    response = client.post("/api/chat/sessions", json={"title": "Autonomous desk"})

    assert response.status_code == 200
    session = response.json()
    assert session["claude_session_id"] == "sess_chat"
    assert session["vault_ids"] == ["vault_existing"]
    created = fake.created_sessions[-1]
    assert created["vault_ids"] == ["vault_existing"]
    assert {resource["access"] for resource in created["resources"]} == {"read_only", "read_write"}


def test_chat_custom_tool_creates_valid_plan_without_leaking_secrets(
    tmp_path,
    monkeypatch,
) -> None:
    fake = FakeManagedAnthropic()
    fake.events.stream_events = [
        {
            "id": "custom_tool_1",
            "type": "agent.custom_tool_use",
            "name": "trading_create_plan",
            "input": {
                "asset": "BTC",
                "side": "long",
                "entry_type": "market",
                "size_usdc": 12,
                "leverage": 2,
            },
        },
        {"type": "session.status_idle", "stop_reason": {"type": "end_turn"}},
    ]
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-token")
    monkeypatch.setenv("HYPERTRACKER_API_KEY", "hypertracker-secret")
    monkeypatch.setattr(ManagedTradingChatService, "_client", lambda self: fake)
    client = TestClient(app)
    assert client.post("/api/chat/bootstrap", json={"force": True}).status_code == 200
    session = client.post("/api/chat/sessions", json={"title": "Tool test"}).json()

    response = client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"message": "Create a guarded BTC plan."},
    )

    assert response.status_code == 200, response.json()
    plan = client.get("/api/state").json()["plan"]
    assert plan["asset"] == "BTC"
    assert plan["source"] == "manual"
    events = client.get(f"/api/chat/sessions/{session['id']}/events").json()
    event_dump = json.dumps(events)
    assert any(event["type"] == "user.custom_tool_result" for event in events)
    assert not any(event["requires_action"] for event in events)
    assert "hypertracker-secret" not in event_dump
    sent_events = [
        event
        for request in fake.events.sent
        for event in request["events"]
        if event["type"] == "user.custom_tool_result"
    ]
    assert sent_events
    assert sent_events[0]["custom_tool_use_id"] == "custom_tool_1"


def test_chat_market_snapshot_serializes_dataclass_price(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    session = ManagedChatSession(title="Snapshot")

    payload = run_chat_custom_tool(
        session,
        {"name": "trading_market_snapshot", "input": {"asset": "BTC", "interval": "1h"}},
    )

    assert "market_error" not in payload
    assert payload["mark_price"]["asset"] == "BTC"
    assert payload["mark_price"]["mark_price"] > 0


def test_chat_formal_validation_blocks_unbuffered_minimum_order(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet", ui_mode="robot"))
    store.save(
        "privy_agent_wallet",
        PrivyAgentWallet(
            id="privy_agent_wallet_prodnet",
            network="prodnet",
            master_wallet_id="master-id",
            master_wallet_address="0x0000000000000000000000000000000000000000",
            agent_wallet_id="agent-id",
            agent_wallet_address="0x0000000000000000000000000000000000000001",
            registered=True,
        ),
    )
    plan = TradePlan(
        asset="ETH",
        side="long",
        size_usdc=10,
        entry_type="market",
        entry_price=100,
        stop_loss=98,
        take_profit=104,
        leverage=2,
        rationale="test",
        invalidation_criteria=[],
        network="prodnet",
    )
    store.save("plans", plan)

    def fake_wallet_state(self, agent):
        return {"withdrawable_usdc": 10.5, "open_positions": []}

    def fake_mark(self, asset):
        return MarketPrice(asset=asset, mark_price=100, source="test")

    monkeypatch.setattr("hyper_demo.api.PrivyHyperliquidAdapter.wallet_state", fake_wallet_state)
    monkeypatch.setattr("hyper_demo.api.MarketDataClient.mark_price", fake_mark)

    payload = run_chat_custom_tool(
        ManagedChatSession(title="Validator"),
        {"name": "trading_validate_plan", "input": {"plan_id": plan.id}},
    )

    assert payload["validation"]["valid"] is False
    assert any("10.25 USDC" in item for item in payload["validation"]["errors"])


def test_chat_formal_validation_allows_sub_10x_take_profit_without_stop_loss(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet"))
    store.save(
        "privy_agent_wallet",
        PrivyAgentWallet(
            id="privy_agent_wallet_prodnet",
            network="prodnet",
            master_wallet_id="master-id",
            master_wallet_address="0x0000000000000000000000000000000000000000",
            agent_wallet_id="agent-id",
            agent_wallet_address="0x0000000000000000000000000000000000000001",
            registered=True,
        ),
    )
    plan = TradePlan(
        asset="ETH",
        side="long",
        size_usdc=12,
        entry_type="market",
        entry_price=100,
        stop_loss=None,
        take_profit=104,
        leverage=3,
        rationale="test",
        invalidation_criteria=["Close manually if thesis invalidates."],
        network="prodnet",
    )
    store.save("plans", plan)

    def fake_wallet_state(self, agent):
        return {"withdrawable_usdc": 10, "open_positions": []}

    def fake_mark(self, asset):
        return MarketPrice(asset=asset, mark_price=100, source="test")

    monkeypatch.setattr("hyper_demo.api.PrivyHyperliquidAdapter.wallet_state", fake_wallet_state)
    monkeypatch.setattr("hyper_demo.api.MarketDataClient.mark_price", fake_mark)

    payload = run_chat_custom_tool(
        ManagedChatSession(title="Validator"),
        {"name": "trading_validate_plan", "input": {"plan_id": plan.id}},
    )

    assert payload["validation"]["valid"] is True
    assert any(
        "No stop_loss attached for sub-10x" in item
        for item in payload["validation"]["checks"]
    )


def test_chat_formal_validation_requires_stop_loss_at_10x(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet"))
    store.save(
        "privy_agent_wallet",
        PrivyAgentWallet(
            id="privy_agent_wallet_prodnet",
            network="prodnet",
            master_wallet_id="master-id",
            master_wallet_address="0x0000000000000000000000000000000000000000",
            agent_wallet_id="agent-id",
            agent_wallet_address="0x0000000000000000000000000000000000000001",
            registered=True,
        ),
    )
    plan = TradePlan(
        asset="ETH",
        side="long",
        size_usdc=12,
        entry_type="market",
        entry_price=100,
        stop_loss=None,
        take_profit=104,
        leverage=10,
        rationale="test",
        invalidation_criteria=["Close manually if thesis invalidates."],
        network="prodnet",
    )
    store.save("plans", plan)

    def fake_wallet_state(self, agent):
        return {"withdrawable_usdc": 10, "open_positions": []}

    def fake_mark(self, asset):
        return MarketPrice(asset=asset, mark_price=100, source="test")

    monkeypatch.setattr("hyper_demo.api.PrivyHyperliquidAdapter.wallet_state", fake_wallet_state)
    monkeypatch.setattr("hyper_demo.api.MarketDataClient.mark_price", fake_mark)

    payload = run_chat_custom_tool(
        ManagedChatSession(title="Validator"),
        {"name": "trading_validate_plan", "input": {"plan_id": plan.id}},
    )

    assert payload["validation"]["valid"] is False
    assert any(
        "10x leverage or higher require stop_loss" in item
        for item in payload["validation"]["errors"]
    )


def test_chat_autonomous_execution_requires_human_approval(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("HYPERLIQUID_MAINNET_ENABLED", "true")
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet"))
    store.save(
        "privy_agent_wallet",
        PrivyAgentWallet(
            id="privy_agent_wallet_prodnet",
            network="prodnet",
            master_wallet_id="master-id",
            master_wallet_address="0x0000000000000000000000000000000000000000",
            agent_wallet_id="agent-id",
            agent_wallet_address="0x0000000000000000000000000000000000000001",
            registered=True,
        ),
    )
    plan = TradePlan(
        asset="ETH",
        side="long",
        size_usdc=12,
        entry_type="market",
        entry_price=100,
        stop_loss=None,
        take_profit=104,
        leverage=2,
        rationale="test",
        invalidation_criteria=[],
        network="prodnet",
    )
    store.save("plans", plan)

    def fake_wallet_state(self, agent):
        return {"withdrawable_usdc": 10, "open_positions": []}

    def fake_mark(self, asset):
        return MarketPrice(asset=asset, mark_price=100, source="test")

    monkeypatch.setattr("hyper_demo.api.PrivyHyperliquidAdapter.wallet_state", fake_wallet_state)
    monkeypatch.setattr("hyper_demo.api.MarketDataClient.mark_price", fake_mark)

    try:
        run_chat_custom_tool(
            ManagedChatSession(title="Executor"),
            {
                "name": "trading_execute_plan",
                "input": {"plan_id": plan.id, "confirmed": True},
            },
        )
    except Exception as exc:
        assert "host human approval" in str(exc)
    else:
        raise AssertionError("human mode must block autonomous prodnet execution")


def test_chat_trade_action_tools_require_human_approval(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet", ui_mode="human"))

    try:
        run_chat_custom_tool(
            ManagedChatSession(title="Closer"),
            {
                "name": "trading_close_position",
                "input": {"asset": "BTC", "confirmed": True},
            },
        )
    except Exception as exc:
        assert "human approval" in str(exc)
    else:
        raise AssertionError("human mode must block autonomous prodnet close actions")


def test_chat_human_mode_only_requires_action_for_trade_execution(
    tmp_path,
    monkeypatch,
) -> None:
    fake = FakeManagedAnthropic()
    fake.events.stream_events = [
        {
            "id": "custom_tool_1",
            "type": "agent.custom_tool_use",
            "name": "trading_execute_plan",
            "input": {"plan_id": "plan_pending", "confirmed": True},
        },
        {"type": "session.status_idle", "stop_reason": {"type": "requires_action"}},
    ]
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-token")
    monkeypatch.setattr(ManagedTradingChatService, "_client", lambda self: fake)
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet", ui_mode="human"))
    client = TestClient(app)
    assert client.post("/api/chat/bootstrap", json={"force": True}).status_code == 200
    session = client.post("/api/chat/sessions", json={"title": "Pending execution"}).json()

    response = client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"message": "Execute the selected trade."},
    )

    assert response.status_code == 200, response.json()
    assert response.json()["status"] == "waiting_action"
    events = client.get(f"/api/chat/sessions/{session['id']}/events").json()
    pending = [event for event in events if event["requires_action"]]
    assert len(pending) == 1
    assert pending[0]["type"] == "agent.custom_tool_use"
    assert pending[0]["payload"]["name"] == "trading_execute_plan"
    assert not any(event["type"] == "user.custom_tool_result" for event in events)


def test_chat_human_approval_executes_pending_trade_once(
    tmp_path,
    monkeypatch,
) -> None:
    fake = FakeManagedAnthropic()
    fake.events.stream_events = [
        {
            "id": "custom_tool_1",
            "type": "agent.custom_tool_use",
            "name": "trading_execute_plan",
            "input": {"plan_id": "plan_human", "confirmed": False},
        },
        {"type": "session.status_idle", "stop_reason": {"type": "requires_action"}},
    ]
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-token")
    monkeypatch.setenv("HYPERLIQUID_MAINNET_ENABLED", "true")
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    monkeypatch.setattr(ManagedTradingChatService, "_client", lambda self: fake)
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet", ui_mode="human"))
    store.save(
        "privy_agent_wallet",
        PrivyAgentWallet(
            id="privy_agent_wallet_prodnet",
            network="prodnet",
            master_wallet_id="master-id",
            master_wallet_address="0x0000000000000000000000000000000000000000",
            agent_wallet_id="agent-id",
            agent_wallet_address="0x0000000000000000000000000000000000000001",
            registered=True,
        ),
    )
    plan = TradePlan(
        id="plan_human",
        asset="ETH",
        side="long",
        size_usdc=12,
        entry_type="market",
        entry_price=100,
        stop_loss=98,
        take_profit=104,
        leverage=2,
        rationale="test",
        invalidation_criteria=[],
        network="prodnet",
    )
    store.save("plans", plan)

    def fake_wallet_state(self, agent):
        return {"withdrawable_usdc": 10, "open_positions": []}

    def fake_mark(self, asset):
        return MarketPrice(asset=asset, mark_price=100, source="test")

    executions = []

    def fake_execute(self, submitted_plan, runtime_agent, confirmed, confirmation_phrase=None):
        executions.append(submitted_plan.id)
        assert confirmed is True
        return OrderRecord(
            plan_id=submitted_plan.id,
            exchange="hyperliquid-mainnet",
            asset=submitted_plan.asset,
            side=submitted_plan.side,
            size_usdc=submitted_plan.size_usdc,
            entry_order_id="entry-human",
            status="submitted",
            message="Submitted after human approval.",
        )

    monkeypatch.setattr("hyper_demo.api.PrivyHyperliquidAdapter.wallet_state", fake_wallet_state)
    monkeypatch.setattr("hyper_demo.api.MarketDataClient.mark_price", fake_mark)
    monkeypatch.setattr(
        "hyper_demo.services.trading_agent.PrivyHyperliquidAdapter.execute_plan",
        fake_execute,
    )
    client = TestClient(app)
    assert client.post("/api/chat/bootstrap", json={"force": True}).status_code == 200
    session = client.post("/api/chat/sessions", json={"title": "Human approval"}).json()
    response = client.post(
        f"/api/chat/sessions/{session['id']}/messages",
        json={"message": "Execute the selected trade."},
    )
    assert response.status_code == 200, response.json()

    approval = client.post(
        f"/api/chat/sessions/{session['id']}/tool-confirmations",
        json={"tool_use_id": "custom_tool_1", "allow": True},
    )

    assert approval.status_code == 200, approval.json()
    assert executions == ["plan_human"]
    events = client.get(f"/api/chat/sessions/{session['id']}/events").json()
    assert not any(event["requires_action"] for event in events)
    result = [event for event in events if event["type"] == "user.custom_tool_result"][-1]
    assert result["payload"]["is_error"] is False
    assert result["payload"]["custom_tool_use_id"] == "custom_tool_1"


def test_chat_robot_mode_prodnet_execution_waits_for_human_approval(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("HYPERLIQUID_MAINNET_ENABLED", "true")
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet", ui_mode="robot"))
    store.save(
        "privy_agent_wallet",
        PrivyAgentWallet(
            id="privy_agent_wallet_prodnet",
            network="prodnet",
            master_wallet_id="master-id",
            master_wallet_address="0x0000000000000000000000000000000000000000",
            agent_wallet_id="agent-id",
            agent_wallet_address="0x0000000000000000000000000000000000000001",
            registered=True,
        ),
    )
    plan = TradePlan(
        asset="ETH",
        side="long",
        size_usdc=12,
        entry_type="market",
        entry_price=100,
        stop_loss=None,
        take_profit=104,
        leverage=2,
        rationale="test",
        invalidation_criteria=[],
        network="prodnet",
    )
    store.save("plans", plan)

    def fake_wallet_state(self, agent):
        return {"withdrawable_usdc": 10, "open_positions": []}

    def fake_mark(self, asset):
        return MarketPrice(asset=asset, mark_price=100, source="test")

    monkeypatch.setattr("hyper_demo.api.PrivyHyperliquidAdapter.wallet_state", fake_wallet_state)
    monkeypatch.setattr("hyper_demo.api.MarketDataClient.mark_price", fake_mark)

    try:
        run_chat_custom_tool(
            ManagedChatSession(title="Executor"),
            {
                "name": "trading_execute_plan",
                "input": {"plan_id": plan.id, "confirmed": True},
            },
        )
    except Exception as exc:
        assert "host human approval" in str(exc)
    else:
        raise AssertionError("robot mode must not bypass prodnet human approval")


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

    def fake_mark(self, asset):
        from hyper_demo.services.market import MarketPrice

        return MarketPrice(asset=asset, mark_price=61000.0, source="test")

    monkeypatch.setattr("hyper_demo.api.MarketDataClient.mark_price", fake_mark)
    client = TestClient(app)

    response = client.post(
        "/api/trades/manual-plan",
        json={
            "asset": "BTC",
            "side": "short",
            "entry_type": "limit",
            "entry_price": 62000,
            "stop_loss": 63240,
            "take_profit": 60760,
            "size_usdc": 50,
            "leverage": 2,
        },
    )

    assert response.status_code == 200
    plan = response.json()
    assert plan["side"] == "short"
    assert plan["entry_price"] == 62000
    assert plan["stop_loss"] == 63240
    assert plan["take_profit"] == 60760
    assert plan["max_loss_usdc"] == 1
    assert plan["source"] == "manual"


def test_manual_plan_rejects_fractional_leverage(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/api/trades/manual-plan",
        json={
            "asset": "BTC",
            "side": "short",
            "entry_type": "market",
            "size_usdc": 25,
            "leverage": 2.5,
        },
    )

    assert response.status_code == 400
    assert "whole number" in response.json()["detail"]


def test_manual_plan_rejects_trigger_that_would_execute_immediately(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))

    def fake_mark(self, asset):
        from hyper_demo.services.market import MarketPrice

        return MarketPrice(asset=asset, mark_price=62000.0, source="test")

    monkeypatch.setattr("hyper_demo.api.MarketDataClient.mark_price", fake_mark)
    client = TestClient(app)

    response = client.post(
        "/api/trades/manual-plan",
        json={
            "asset": "BTC",
            "side": "short",
            "entry_type": "limit",
            "entry_price": 65000,
            "take_profit": 63000,
            "size_usdc": 25,
            "leverage": 2,
        },
    )

    assert response.status_code == 400
    assert "Take Profit would be invalid for this Short" in response.json()["detail"]


def test_manual_plan_rejects_stop_loss_beyond_liquidation(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))

    def fake_mark(self, asset):
        from hyper_demo.services.market import MarketPrice

        return MarketPrice(asset=asset, mark_price=100.0, source="test")

    monkeypatch.setattr("hyper_demo.api.MarketDataClient.mark_price", fake_mark)
    client = TestClient(app)

    response = client.post(
        "/api/trades/manual-plan",
        json={
            "asset": "BTC",
            "side": "short",
            "entry_type": "market",
            "stop_loss": 151,
            "size_usdc": 25,
            "leverage": 2,
        },
    )

    assert response.status_code == 400
    assert "beyond the estimated liquidation price" in response.json()["detail"]


def test_manual_limit_plan_rejects_price_far_from_reference(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/api/trades/manual-plan",
        json={
            "asset": "BTC",
            "side": "long",
            "entry_type": "limit",
            "entry_price": 1,
            "size_usdc": 25,
            "leverage": 1,
        },
    )

    assert response.status_code == 400
    assert "95% away" in response.json()["detail"]


def test_manual_plan_rejects_order_below_hyperliquid_minimum(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/api/trades/manual-plan",
        json={
            "asset": "BTC",
            "side": "short",
            "entry_type": "market",
            "size_usdc": 5,
            "leverage": 2,
        },
    )

    assert response.status_code == 400
    assert "minimum order value of 10 USDC" in response.json()["detail"]


def test_manual_plan_rejects_size_above_wallet_available(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet"))
    store.save(
        "privy_agent_wallet",
        PrivyAgentWallet(
            id="privy_agent_wallet_prodnet",
            network="prodnet",
            master_wallet_id="master-id",
            master_wallet_address="0x0000000000000000000000000000000000000000",
            agent_wallet_id="agent-id",
            agent_wallet_address="0x0000000000000000000000000000000000000001",
            registered=True,
        ),
    )

    def fake_wallet_state(self, agent):
        return {
            "account_address": agent.master_wallet_address,
            "agent_address": agent.agent_wallet_address,
            "withdrawable_usdc": 5,
        }

    monkeypatch.setattr(
        "hyper_demo.api.PrivyHyperliquidAdapter.wallet_state",
        fake_wallet_state,
    )
    client = TestClient(app)

    response = client.post(
        "/api/trades/manual-plan",
        json={
            "asset": "BTC",
            "side": "long",
            "entry_type": "market",
            "size_usdc": 12,
            "leverage": 2,
        },
    )

    assert response.status_code == 400
    assert "withdrawable balance" in response.json()["detail"]
    events = client.get("/api/agent/events").json()
    assert any(
        "Order margin exceeds wallet withdrawable balance" in item["message"]
        for item in events
    )


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


def test_manual_submit_creates_and_executes_in_one_request(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))

    def fake_mark(self, asset):
        from hyper_demo.services.market import MarketPrice

        return MarketPrice(asset=asset, mark_price=62000.0, source="test")

    def fake_execute(self, plan, confirmed, confirmation_phrase=None):
        assert confirmed is True
        assert confirmation_phrase is None
        return OrderRecord(
            plan_id=plan.id,
            exchange="hyperliquid-testnet",
            asset=plan.asset,
            side=plan.side,
            size_usdc=plan.size_usdc,
            entry_order_id="entry-fast",
            message="fast submitted",
        )

    monkeypatch.setattr("hyper_demo.api.MarketDataClient.mark_price", fake_mark)
    monkeypatch.setattr(
        "hyper_demo.services.trading_agent.HyperliquidAdapter.execute_plan",
        fake_execute,
    )
    client = TestClient(app)
    runtime = client.post("/api/settings/runtime", json={"network": "testnet"})
    assert runtime.status_code == 200

    response = client.post(
        "/api/trades/manual-submit",
        json={
            "asset": "BTC",
            "side": "long",
            "entry_type": "market",
            "size_usdc": 12,
            "leverage": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["status"] == "executed"
    assert payload["order"]["entry_order_id"] == "entry-fast"
    assert payload["order_id"] == payload["order"]["id"]


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


def test_prodnet_confirmation_executes_without_phrase(tmp_path, monkeypatch) -> None:
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

    def fake_execute(self, submitted_plan, confirmed, confirmation_phrase=None):
        assert submitted_plan.id == plan.id
        assert confirmed is True
        assert confirmation_phrase is None
        return OrderRecord(
            plan_id=submitted_plan.id,
            exchange="hyperliquid-mainnet",
            asset=submitted_plan.asset,
            side=submitted_plan.side,
            size_usdc=submitted_plan.size_usdc,
            status="submitted",
            message="Submitted test order.",
        )

    monkeypatch.setattr(
        "hyper_demo.services.trading_agent.HyperliquidAdapter.execute_plan",
        fake_execute,
    )
    client = TestClient(app)

    response = client.post(f"/api/trades/{plan.id}/execute", json={"confirmed": True})

    assert response.status_code == 200
    assert response.json()["plan"]["status"] == "executed"


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


def test_orders_endpoint_includes_wallet_positions_and_history(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet"))
    agent = PrivyAgentWallet(
        id="privy_agent_wallet_prodnet",
        master_wallet_id="master-id",
        master_wallet_address="0x0000000000000000000000000000000000000000",
        agent_wallet_id="agent-id",
        agent_wallet_address="0x0000000000000000000000000000000000000001",
        network="prodnet",
        registered=True,
    )
    store.save("privy_agent_wallet", agent)
    store.save(
        "orders",
        OrderRecord(
            plan_id="plan-id",
            exchange="hyperliquid-mainnet",
            asset="BTC",
            side="long",
            size_usdc=10,
            message="submitted",
        ),
    )

    def fake_wallet_state(self, runtime_agent):
        return {
            "account_address": runtime_agent.master_wallet_address,
            "agent_address": runtime_agent.agent_wallet_address,
            "withdrawable_usdc": 5,
            "total_margin_used_usdc": 5,
            "open_positions": [{"position": {"coin": "BTC", "szi": "0.00017"}}],
            "open_orders": [],
        }

    monkeypatch.setattr("hyper_demo.api.PrivyHyperliquidAdapter.wallet_state", fake_wallet_state)
    client = TestClient(app)

    response = client.get("/api/orders")

    assert response.status_code == 200
    payload = response.json()
    assert payload["positions"][0]["position"]["coin"] == "BTC"
    assert payload["orders"][0]["asset"] == "BTC"
    assert payload["wallet"]["withdrawable_usdc"] == 5


def test_close_position_uses_reduce_only_privy_adapter(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet"))
    agent = PrivyAgentWallet(
        id="privy_agent_wallet_prodnet",
        master_wallet_id="master-id",
        master_wallet_address="0x0000000000000000000000000000000000000000",
        agent_wallet_id="agent-id",
        agent_wallet_address="0x0000000000000000000000000000000000000001",
        network="prodnet",
        registered=True,
    )
    store.save("privy_agent_wallet", agent)
    captured = {}

    def fake_wallet_state(self, runtime_agent):
        return {
            "open_positions": [
                {
                    "position": {
                        "coin": "BTC",
                        "szi": "0.00017",
                        "positionValue": "10.5",
                    }
                }
            ],
            "open_orders": [],
        }

    def fake_close_position(self, **kwargs):
        captured.update(kwargs)
        return OrderRecord(
            plan_id="manual_position_close",
            exchange="hyperliquid-mainnet",
            asset=kwargs["asset"],
            side="short",
            size_usdc=kwargs["position_value_usdc"],
            entry_order_id="close-oid",
            message="close submitted",
        )

    monkeypatch.setattr("hyper_demo.api.PrivyHyperliquidAdapter.wallet_state", fake_wallet_state)
    monkeypatch.setattr(
        "hyper_demo.api.PrivyHyperliquidAdapter.close_position",
        fake_close_position,
    )
    client = TestClient(app)

    response = client.post("/api/positions/BTC/close", json={"confirmed": True})

    assert response.status_code == 200
    assert captured["asset"] == "BTC"
    assert captured["size"] == 0.00017
    assert captured["side"] == "long"
    assert response.json()["order"]["entry_order_id"] == "close-oid"


def test_set_position_protection_updates_plan_and_order(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet"))
    agent = PrivyAgentWallet(
        id="privy_agent_wallet_prodnet",
        master_wallet_id="master-id",
        master_wallet_address="0x0000000000000000000000000000000000000000",
        agent_wallet_id="agent-id",
        agent_wallet_address="0x0000000000000000000000000000000000000001",
        network="prodnet",
        registered=True,
    )
    store.save("privy_agent_wallet", agent)
    plan = store.save(
        "plans",
        TradePlan(
            asset="BTC",
            side="long",
            size_usdc=10,
            entry_type="market",
            entry_price=61792,
            rationale="manual",
            invalidation_criteria=[],
            source="manual",
            network="prodnet",
            status="executed",
        ),
    )
    order = store.save(
        "orders",
        OrderRecord(
            plan_id=plan.id,
            exchange="hyperliquid-mainnet",
            asset="BTC",
            side="long",
            size_usdc=10,
            entry_order_id="entry-oid",
            message="submitted",
        ),
    )
    captured = {}

    def fake_wallet_state(self, runtime_agent):
        return {
            "open_positions": [
                {
                    "position": {
                        "coin": "BTC",
                        "szi": "0.00017",
                        "entryPx": "61792",
                        "markPx": "62000",
                        "positionValue": "10.54",
                    }
                }
            ],
            "open_orders": [],
        }

    def fake_set_position_protection(self, **kwargs):
        captured.update(kwargs)
        return {
            "stopOrderId": "stop-oid",
            "takeProfitOrderId": "tp-oid",
            "stopLoss": {"status": "ok"},
            "takeProfit": {"status": "ok"},
        }

    monkeypatch.setattr("hyper_demo.api.PrivyHyperliquidAdapter.wallet_state", fake_wallet_state)
    monkeypatch.setattr(
        "hyper_demo.api.PrivyHyperliquidAdapter.set_position_protection",
        fake_set_position_protection,
    )
    client = TestClient(app)

    response = client.post(
        "/api/positions/BTC/protection",
        json={"confirmed": True, "take_profit": 63000, "stop_loss": 60000},
    )

    assert response.status_code == 200
    assert captured["asset"] == "BTC"
    assert captured["size"] == 0.00017
    assert captured["side"] == "long"
    assert captured["take_profit"] == 63000
    assert captured["stop_loss"] == 60000
    assert captured["remove_take_profit"] is False
    assert captured["remove_stop_loss"] is False
    updated_plan = store.get("plans", plan.id)
    assert updated_plan.take_profit == 63000
    assert updated_plan.stop_loss == 60000
    updated_order = store.get("orders", order.id)
    assert updated_order.take_profit_order_id == "tp-oid"
    assert updated_order.stop_order_id == "stop-oid"


def test_set_position_protection_can_remove_existing_stop_loss(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet"))
    store.save(
        "privy_agent_wallet",
        PrivyAgentWallet(
            id="privy_agent_wallet_prodnet",
            master_wallet_id="master-id",
            master_wallet_address="0x0000000000000000000000000000000000000000",
            agent_wallet_id="agent-id",
            agent_wallet_address="0x0000000000000000000000000000000000000001",
            network="prodnet",
            registered=True,
        ),
    )
    plan = TradePlan(
        asset="BTC",
        side="long",
        size_usdc=12,
        entry_price=61792,
        take_profit=63000,
        stop_loss=60000,
        leverage=3,
        rationale="test",
        invalidation_criteria=["test"],
        network="prodnet",
        status="executed",
    )
    store.save("plans", plan)
    order = store.save(
        "orders",
        OrderRecord(
            plan_id=plan.id,
            exchange="hyperliquid-mainnet",
            asset="BTC",
            side="long",
            size_usdc=12,
            entry_order_id="entry-oid",
            take_profit_order_id="tp-oid",
            stop_order_id="stop-oid",
            message="submitted",
        ),
    )
    captured = {}

    def fake_wallet_state(self, runtime_agent):
        return {
            "open_positions": [
                {
                    "position": {
                        "coin": "BTC",
                        "szi": "0.00017",
                        "entryPx": "61792",
                        "markPx": "62000",
                        "positionValue": "10.54",
                    }
                }
            ],
            "open_orders": [],
        }

    def fake_set_position_protection(self, **kwargs):
        captured.update(kwargs)
        return {
            "cancelled": {"status": "ok"},
            "stopOrderId": None,
            "takeProfitOrderId": "tp-new",
            "stopLoss": None,
            "takeProfit": {"status": "ok"},
        }

    monkeypatch.setattr("hyper_demo.api.PrivyHyperliquidAdapter.wallet_state", fake_wallet_state)
    monkeypatch.setattr(
        "hyper_demo.api.PrivyHyperliquidAdapter.set_position_protection",
        fake_set_position_protection,
    )
    client = TestClient(app)

    response = client.post(
        "/api/positions/BTC/protection",
        json={"confirmed": True, "take_profit": 63100, "remove_stop_loss": True},
    )

    assert response.status_code == 200
    assert captured["take_profit"] == 63100
    assert captured["stop_loss"] is None
    assert captured["remove_take_profit"] is False
    assert captured["remove_stop_loss"] is True
    updated_plan = store.get("plans", plan.id)
    assert updated_plan.take_profit == 63100
    assert updated_plan.stop_loss is None
    updated_order = store.get("orders", order.id)
    assert updated_order.take_profit_order_id == "tp-new"
    assert updated_order.stop_order_id is None


def test_set_position_protection_rejects_wrong_side_levels(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PRIVY_EXECUTION_ENABLED", "true")
    monkeypatch.setenv("PRIVY_APP_ID", "app")
    monkeypatch.setenv("PRIVY_APP_SECRET", "secret")
    store = JsonStore()
    store.save("runtime", RuntimeSettings(network="prodnet"))
    store.save(
        "privy_agent_wallet",
        PrivyAgentWallet(
            id="privy_agent_wallet_prodnet",
            master_wallet_id="master-id",
            master_wallet_address="0x0000000000000000000000000000000000000000",
            agent_wallet_id="agent-id",
            agent_wallet_address="0x0000000000000000000000000000000000000001",
            network="prodnet",
            registered=True,
        ),
    )

    def fake_wallet_state(self, runtime_agent):
        return {
            "open_positions": [
                {
                    "position": {
                        "coin": "BTC",
                        "szi": "0.00017",
                        "entryPx": "61792",
                        "markPx": "62000",
                    }
                }
            ],
            "open_orders": [],
        }

    monkeypatch.setattr("hyper_demo.api.PrivyHyperliquidAdapter.wallet_state", fake_wallet_state)
    client = TestClient(app)

    response = client.post(
        "/api/positions/BTC/protection",
        json={"confirmed": True, "take_profit": 61000},
    )

    assert response.status_code == 400
    assert "Long take profit must be above entry and current price" in response.json()["detail"]


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
