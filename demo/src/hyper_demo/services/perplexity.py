from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from hyper_demo.config import Settings, get_settings
from hyper_demo.models import ResearchReport, normalize_asset_symbol


@dataclass(frozen=True)
class FinanceContext:
    asset: str
    evidence: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    available: bool = False
    raw_response_id: str | None = None


class PerplexityFinanceClient:
    def __init__(self, settings: Settings | None = None, timeout: int = 12) -> None:
        self.settings = settings or get_settings()
        self.timeout = timeout

    def context_for_asset(self, asset: str) -> FinanceContext:
        normalized = normalize_asset_symbol(asset)
        if not self.settings.has_perplexity_credentials:
            return FinanceContext(
                asset=normalized,
                assumptions=["PERPLEXITY_API_KEY is not configured."],
            )

        payload = self._post_agent(normalized)
        if not payload:
            return FinanceContext(
                asset=normalized,
                assumptions=["Perplexity finance_search returned no usable response."],
            )

        evidence, sources = _extract_finance_context(payload)
        assumptions = []
        if not evidence:
            assumptions.append(
                "Perplexity finance_search did not return source-backed finance context "
                "for this asset."
            )
        return FinanceContext(
            asset=normalized,
            evidence=evidence[:4],
            risks=[
                (
                    "Perplexity finance_search coverage is strongest for public equities and ETFs; "
                    "crypto perpetual context may be partial or unavailable."
                )
            ],
            assumptions=assumptions,
            sources=sources[:8],
            available=bool(evidence),
            raw_response_id=str(payload.get("id") or "") or None,
        )

    def _post_agent(self, asset: str) -> dict[str, Any] | None:
        api_key = self.settings.perplexity_api_key
        token = api_key.get_secret_value() if api_key else ""
        body = json.dumps(
            {
                "model": self.settings.perplexity_model,
                "input": (
                    f"Create a concise, source-backed finance brief for {asset}. "
                    "Prioritize live quote context, valuation or ETF/public-equity proxies when "
                    "available, recent market catalysts, and explicit coverage limitations. "
                    "If this is a crypto perpetual or HIP-3 asset, say when finance_search has no "
                    "direct coverage instead of inventing data."
                ),
                "tools": [{"type": "finance_search"}],
                "max_steps": 1,
                "max_output_tokens": 1024,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.settings.perplexity_base_url}/agent",
            data=body,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (
            TimeoutError,
            urllib.error.HTTPError,
            urllib.error.URLError,
            ValueError,
            json.JSONDecodeError,
        ):
            return None


def enrich_research_with_finance_context(
    report: ResearchReport,
    context: FinanceContext,
) -> ResearchReport:
    if context.available:
        report.evidence = [*report.evidence, *context.evidence]
        report.risks = [*report.risks, *context.risks]
        report.sources = [*report.sources, *context.sources]
    report.assumptions = [*report.assumptions, *context.assumptions]
    return report


def finance_context_prompt(context: FinanceContext) -> str:
    if context.available:
        return "\n".join(
            [
                "Perplexity finance_search context:",
                *[f"- {item}" for item in context.evidence],
                *[f"- Risk: {item}" for item in context.risks],
                *[f"- Source: {item}" for item in context.sources[:4]],
            ]
        )
    return "Perplexity finance_search context unavailable: " + "; ".join(context.assumptions)


def _extract_finance_context(payload: dict[str, Any]) -> tuple[list[str], list[str]]:
    evidence: list[str] = []
    sources: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "finance_results":
            for result in item.get("results", []):
                if not isinstance(result, dict):
                    continue
                category = str(result.get("category") or "finance")
                content = _clean_text(str(result.get("content") or ""))
                if content:
                    evidence.append(f"Perplexity finance_search {category}: {content}")
                sources.extend(_as_strings(result.get("sources")))
        if item.get("type") == "message":
            for block in item.get("content", []):
                if not isinstance(block, dict):
                    continue
                text = _clean_text(str(block.get("text") or ""))
                if text:
                    evidence.append(f"Perplexity finance brief: {text}")
                for annotation in block.get("annotations", []):
                    if isinstance(annotation, dict) and annotation.get("url"):
                        sources.append(str(annotation["url"]))
    return _unique(evidence), _unique(sources)


def _clean_text(value: str) -> str:
    return " ".join(value.replace("|", " ").split())[:700]


def _as_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result
