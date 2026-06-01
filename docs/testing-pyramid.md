# Demo Testing Pyramid

The demo uses a small but explicit pyramid so the live presentation can fail safely.

## Unit Tests

Fast, deterministic tests with no network calls:

- investor skill registry includes promptable, non-impersonating skills;
- quant signal scoring produces bounded values and clear recommendations;
- proposal exits satisfy directional constraints;
- risk profile sizing respects user guardrails;
- metrics math handles empty and active portfolios.

Command:

```bash
cd demo
uv run pytest tests/test_agent_team.py tests/test_proposals.py tests/test_risk.py tests/test_metrics.py
```

## Integration Tests

API and storage tests using temporary local state:

- profile, research fallback, proposal, guarded execution;
- paper order creation and run events;
- agent team consensus endpoint;
- replay fixture path validation;
- portfolio metrics with paper fill prices.

Command:

```bash
cd demo
uv run pytest tests/test_api.py tests/test_storage.py tests/test_paper_adapter.py
```

## CLI Smoke Tests

Presenter workflow checks:

- setup validation renders;
- profile and fallback replay work;
- skills and debate commands render;
- paper trading command simulates an order with confirmation.

Command:

```bash
cd demo
uv run pytest tests/test_cli.py
```

## Static Quality Gate

Run before presenting or opening a PR:

```bash
cd demo
uv run ruff check .
uv run pytest
```

## Manual Rehearsal

These checks intentionally touch the browser or optional live services:

1. Start `uv run uvicorn hyper_demo.api:app --reload`.
2. Open `http://127.0.0.1:8000`.
3. Create a risk profile.
4. Run research; fallback is acceptable if no API key is configured.
5. Create a proposal.
6. Run Agent Team and verify consensus plus four agent opinions.
7. Run Paper Trading with confirmation.
8. Open Monitor and update metrics/events.
9. Only test Hyperliquid execution with testnet credentials and explicit confirmation.

Live-network calls are rehearsal-only, not required for CI.
