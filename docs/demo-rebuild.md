# Rebuild Guide: Hyperliquid Testnet Investment Agent Demo

This guide recreates the demo from a clean clone. The demo is English-only and defaults to testnet.

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
HYPERLIQUID_MAX_ORDER_USDC=100
HYPERLIQUID_ALLOWED_ASSETS=BTC,ETH,SOL
HYPERLIQUID_MAINNET_ENABLED=false
DEMO_TRADING_MODE=testnet
DEMO_REQUIRE_CONFIRMATION=true
```

For mainnet, use only a Hyperliquid API/agent wallet private key, never the main wallet
private key. `.env` and `.env.*` are already ignored by Git.

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
uv run demo skills
uv run demo debate --asset BTC
uv run demo paper --plan <plan_id> --confirm
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
4. Run Agent Team to review search cards, quant signals, and investor-style skills.
5. Review the stop-loss, take-profit, max loss, consensus, and invalidation criteria.
6. Confirm and run paper trading first.
7. Submit to Hyperliquid only if credentials are configured and the presenter opts in.
8. Monitor metrics and events.

## 5. Optional Mainnet Guarded Mode

Use this only for a controlled live-wallet demo. `HYPERLIQUID_ACCOUNT_ADDRESS` is the main
Dreamcash/Hyperliquid wallet address used for read-only account state. The private key must
belong to a Hyperliquid API/agent wallet authorized for that account.

```bash
DEMO_TRADING_MODE=mainnet_guarded
HYPERLIQUID_MAINNET_ENABLED=true
HYPERLIQUID_BASE_URL=https://api.hyperliquid.xyz
HYPERLIQUID_WS_URL=wss://api.hyperliquid.xyz/ws
HYPERLIQUID_ACCOUNT_ADDRESS=0x_your_main_wallet
HYPERLIQUID_API_WALLET_PRIVATE_KEY=0x_your_api_wallet_private_key
HYPERLIQUID_MAX_ORDER_USDC=100
HYPERLIQUID_ALLOWED_ASSETS=BTC,ETH,SOL
DEMO_REQUIRE_CONFIRMATION=true
```

The browser and CLI both require explicit confirmation. Mainnet also requires the exact phrase
`CONFIRM MAINNET ORDER`.

Optional websocket smoke test:

```bash
curl http://127.0.0.1:8000/api/market/BTC/ws-sample
```

## 6. Safety Boundaries

- Mainnet Hyperliquid URLs are rejected unless `mainnet_guarded` and
  `HYPERLIQUID_MAINNET_ENABLED=true` are both set.
- The execution endpoint refuses orders without explicit confirmation.
- Mainnet orders require `CONFIRM MAINNET ORDER`.
- Missing Hyperliquid credentials block execution instead of silently trading.
- Orders above `HYPERLIQUID_MAX_ORDER_USDC` or outside `HYPERLIQUID_ALLOWED_ASSETS` are blocked.
- Fallback replay never sends exchange requests.
- All outputs are educational analysis, not financial advice.

## 7. Validation

```bash
uv run pytest
uv run ruff check .
```

For rehearsal, also run the browser UI and load the fallback replay once before the session.
The full coding-agent prompt runbook is in `docs/coding-agent-prompts.md`; the test strategy is in
`docs/testing-pyramid.md`.
