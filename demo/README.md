# Hyperliquid Testnet Investment Agent Demo

English-language demo app for a Claude Managed Agents investment workflow with Hyperliquid testnet execution.

The app has two entrypoints:

- Browser UI: `uv run uvicorn hyper_demo.api:app --reload`
- CLI: `uv run demo setup-check`
- Paper trading: `uv run demo paper --plan <plan_id> --confirm`
- Agent team review: `uv run demo debate --asset BTC`

The demo is educational. It is not financial advice. Mainnet trading is intentionally out of scope.

## Setup

```bash
cd demo
uv sync
cp .env.example .env
```

Fill `.env` with Claude and Hyperliquid **testnet** credentials only.
The default model is `claude-haiku-4-5-20251001` for low-cost, low-latency demo runs.
Paper trading uses the public Coinbase Exchange ticker API and does not require trading
credentials.

```bash
uv run demo setup-check
uv run demo profile
uv run demo research --asset BTC
uv run demo propose --asset BTC
uv run demo skills
uv run demo debate --asset BTC
uv run demo paper --plan <plan_id> --confirm
uv run uvicorn hyper_demo.api:app --reload
```

Open <http://127.0.0.1:8000>.

## Safety Defaults

- `DEMO_TRADING_MODE` must be `testnet`.
- `DEMO_REQUIRE_CONFIRMATION` defaults to `true`.
- Mainnet Hyperliquid URLs are rejected by configuration validation.
- The execution endpoint refuses to submit an order unless the request is explicitly confirmed.
- Paper trading calls the public Coinbase Exchange market-data API, simulates entry, stop-loss,
  and take-profit orders, and stores a debug trace in the run events and order raw response.
- The multi-agent review combines search cards, deterministic quant signals, and skills inspired
  by public investing principles without impersonating any investor.
- If live services are unavailable, use `uv run demo replay --fixture fallback`.
