import json
import urllib.request
from contextlib import contextmanager

from fastapi.testclient import TestClient

from hyper_demo.api import app


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> None:
        return None


def test_perplexity_mcp_initializes_and_lists_tools() -> None:
    client = TestClient(app)

    init = client.post(
        "/mcp/perplexity",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
    )
    tools = client.post(
        "/mcp/perplexity",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )

    assert init.status_code == 200
    assert init.json()["result"]["serverInfo"]["name"] == "hyperclaude-perplexity-mcp"
    assert tools.status_code == 200
    tool_names = {tool["name"] for tool in tools.json()["result"]["tools"]}
    assert tool_names == {
        "perplexity_search",
        "perplexity_ask",
        "perplexity_research",
        "perplexity_reason",
    }


def test_perplexity_mcp_tool_call_requires_vault_bearer() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/perplexity",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "perplexity_search", "arguments": {"query": "BTC"}},
        },
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32001
    assert "Vault" in response.json()["error"]["message"]


def test_perplexity_mcp_search_uses_bearer_without_returning_it(monkeypatch) -> None:
    captured = {}

    @contextmanager
    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        captured["authorization"] = request.headers["Authorization"]
        yield FakeResponse(
            {
                "id": "search_123",
                "results": [
                    {
                        "title": "BTC market structure improves",
                        "url": "https://example.com/btc",
                        "snippet": "Bitcoin liquidity and ETF flows improved.",
                    }
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = TestClient(app)

    response = client.post(
        "/mcp/perplexity",
        headers={"Authorization": "Bearer ppx-test-token"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "perplexity_search",
                "arguments": {"query": "BTC ETF flows", "max_results": 3},
            },
        },
    )

    assert response.status_code == 200, response.json()
    payload = response.json()
    dumped = json.dumps(payload)
    assert captured["url"] == "https://api.perplexity.ai/search"
    assert captured["authorization"] == "Bearer ppx-test-token"
    assert captured["body"] == {"query": "BTC ETF flows", "max_results": 3}
    assert "BTC market structure improves" in payload["result"]["content"][0]["text"]
    assert "ppx-test-token" not in dumped


def test_perplexity_mcp_reason_calls_sonar_and_strips_thinking(monkeypatch) -> None:
    captured = {}

    @contextmanager
    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        captured["authorization"] = request.headers["Authorization"]
        yield FakeResponse(
            {
                "id": "sonar_123",
                "model": "sonar-reasoning-pro",
                "choices": [
                    {
                        "message": {
                            "content": (
                                "<think>internal chain</think> "
                                "Prefer no trade until volume confirms."
                            )
                        }
                    }
                ],
                "citations": ["https://example.com/volume"],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = TestClient(app)

    response = client.post(
        "/mcp/perplexity",
        headers={"Authorization": "Bearer ppx-test-token"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "perplexity_reason",
                "arguments": {
                    "problem": "Should the agent enter BTC now?",
                    "context": "Momentum is mixed.",
                    "strip_thinking": True,
                },
            },
        },
    )

    assert response.status_code == 200, response.json()
    dumped = json.dumps(response.json())
    assert captured["url"] == "https://api.perplexity.ai/v1/sonar"
    assert captured["authorization"] == "Bearer ppx-test-token"
    assert captured["body"]["model"] == "sonar-reasoning-pro"
    assert "Momentum is mixed" in captured["body"]["messages"][0]["content"]
    assert "Prefer no trade" in dumped
    assert "<think>" not in dumped
    assert "ppx-test-token" not in dumped
