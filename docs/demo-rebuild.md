# Rebuild Guide: Hyperliquid Testnet Investment Agent Demo

This guide recreates the demo from a clean clone. The demo is English-only, educational, and testnet-only.

## 1. Install

```bash
cd demo
uv sync
cp .env.example .env
```

Fill `.env` with Claude and Hyperliquid testnet values:

```bash
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
HYPERLIQUID_BASE_URL=https://api.hyperliquid-testnet.xyz
HYPERLIQUID_WS_URL=wss://api.hyperliquid-testnet.xyz/ws
HYPERLIQUID_ACCOUNT_ADDRESS=...
HYPERLIQUID_API_WALLET_PRIVATE_KEY=...
DEMO_TRADING_MODE=testnet
DEMO_REQUIRE_CONFIRMATION=true
```

Do not use a mainnet wallet. `.env` and `.env.*` are already ignored by Git.

## 2. Check Setup

```bash
uv run demo setup-check
```

Expected:

- Trading mode is `testnet`.
- Confirmation is `true`.
- Claude is configured if `ANTHROPIC_API_KEY` is present.
- Hyperliquid is configured if the testnet account address and API wallet key are present.

## 3. Run the CLI Demo

```bash
uv run demo profile --asset BTC --horizon-days 30 --max-drawdown-pct 8 --leverage low --capital-at-risk-usdc 100 --stop-loss-pct 4
uv run demo research --asset BTC
uv run demo propose --asset BTC
```

To execute on Hyperliquid testnet after reviewing the plan:

```bash
uv run demo execute --plan <plan_id> --confirm
uv run demo monitor --run <run_id>
```

If the live API path fails:

```bash
uv run demo replay --fixture fallback
```

## 4. Run the Browser Demo

```bash
uv run uvicorn hyper_demo.api:app --reload
```

Open <http://127.0.0.1:8000>.

Suggested live flow:

1. Create a risk profile.
2. Run research.
3. Create a proposal.
4. Review the stop-loss, take-profit, max loss, and invalidation criteria.
5. Confirm and submit only if Hyperliquid testnet credentials are configured.
6. Monitor metrics and events.

Optional websocket smoke test:

```bash
curl http://127.0.0.1:8000/api/market/BTC/ws-sample
```

## 5. Safety Boundaries

- Mainnet Hyperliquid URLs are rejected by config validation.
- The execution endpoint refuses orders without explicit confirmation.
- Missing Hyperliquid credentials block execution instead of silently trading.
- Fallback replay never sends exchange requests.
- All outputs are educational analysis, not financial advice.

## 6. Validation

```bash
uv run pytest
uv run ruff check .
```

For rehearsal, also run the browser UI and load the fallback replay once before the session.
