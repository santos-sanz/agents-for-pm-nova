import json
import urllib.request
from contextlib import contextmanager

from hyper_demo.config import Settings
from hyper_demo.models import ResearchReport
from hyper_demo.services.perplexity import (
    PerplexityFinanceClient,
    enrich_research_with_finance_context,
    finance_context_prompt,
)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> None:
        return None


def test_perplexity_finance_context_parses_finance_results(monkeypatch) -> None:
    captured = {}

    @contextmanager
    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        captured["authorization"] = request.headers["Authorization"]
        yield FakeResponse(
            {
                "id": "resp_123",
                "output": [
                    {
                        "type": "finance_results",
                        "results": [
                            {
                                "category": "quote",
                                "content": "## NVDA Quote\nprice 200.23 pe 40.86",
                                "sources": ["https://www.perplexity.ai/finance/NVDA"],
                            }
                        ],
                    },
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "NVIDIA is trading near $200 with elevated valuation.",
                                "annotations": [
                                    {
                                        "url": "https://www.perplexity.ai/finance/NVDA/historical-data"
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    context = PerplexityFinanceClient(
        Settings(PERPLEXITY_API_KEY="token"),
    ).context_for_asset("nvda")

    assert context.available is True
    assert context.asset == "NVDA"
    assert context.raw_response_id == "resp_123"
    assert captured["url"] == "https://api.perplexity.ai/v1/agent"
    assert captured["authorization"] == "Bearer token"
    assert captured["body"]["tools"] == [{"type": "finance_search"}]
    assert any("finance_search quote" in item for item in context.evidence)
    assert any("NVIDIA is trading" in item for item in context.evidence)
    assert "https://www.perplexity.ai/finance/NVDA" in context.sources


def test_perplexity_finance_context_falls_back_without_key() -> None:
    context = PerplexityFinanceClient(Settings(PERPLEXITY_API_KEY="")).context_for_asset("BTC")

    assert context.available is False
    assert context.assumptions == ["PERPLEXITY_API_KEY is not configured."]


def test_finance_context_enriches_research_report() -> None:
    context = PerplexityFinanceClient(Settings(PERPLEXITY_API_KEY="")).context_for_asset("BTC")
    report = ResearchReport(
        asset="BTC",
        thesis="Base thesis.",
        evidence=["Local evidence."],
        risks=[],
        assumptions=[],
        why_not_invest=[],
    )

    enriched = enrich_research_with_finance_context(report, context)

    assert enriched.evidence == ["Local evidence."]
    assert "PERPLEXITY_API_KEY is not configured." in enriched.assumptions
    assert "Perplexity finance_search context unavailable" in finance_context_prompt(context)
