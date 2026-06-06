# Rebuild Guide: Hyperliquid Claude Trading Agent Demo

This guide recreates the demo from a clean clone. The demo is Hyperliquid-only and defaults
to testnet auto-execution when credentials and guardrails pass.

## 1. Install

```bash
cd demo
uv sync
cp .env.example .env
```

Fill `.env` with Claude and Hyperliquid values:

```bash
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
HYPERLIQUID_ACCOUNT_ADDRESS=...
HYPERLIQUID_API_WALLET_PRIVATE_KEY=...
HYPERLIQUID_MAX_ORDER_USDC=100
HYPERLIQUID_ALLOWED_ASSETS=BTC,ETH,SOL,HYPE
HYPERLIQUID_MAINNET_ENABLED=false
DEMO_TRADING_MODE=testnet
DEMO_REQUIRE_CONFIRMATION=true
```

## 2. Check Setup

```bash
uv run demo setup-check
```

Expected:

- Trading mode is `testnet`.
- Claude is configured if `ANTHROPIC_API_KEY` is present.
- Hyperliquid is configured if account address and API wallet key are present.

## 3. Run the CLI Demo

```bash
uv run demo analyze --asset BTC
uv run demo scan
uv run demo execute --plan <plan_id> --confirm
uv run demo wallet
```

## 4. Run the Browser Demo

```bash
uv run uvicorn hyper_demo.api:app --reload
```

Open <http://127.0.0.1:8000>.

Suggested live flow:

1. Keep `testnet` selected and `Human` mode active.
2. Enter an asset and run reactive analysis.
3. Show the proposal, risk, invalidation, and execution decision.
4. Switch to `Robot logs` to show raw state and Managed Agent/event traces.
5. Run a proactive scan from the watchlist.
6. Optionally switch to prodnet to show that execution waits for confirmation.

## 5. Optional Prodnet Guarded Mode

Use only for a controlled live-wallet demo. The account address is the main Hyperliquid
wallet used for read-only account state. The private key must belong to a Hyperliquid
API/agent wallet authorized for that account.

```bash
HYPERLIQUID_MAINNET_ENABLED=true
HYPERLIQUID_ACCOUNT_ADDRESS=0x_your_main_wallet
HYPERLIQUID_API_WALLET_PRIVATE_KEY=0x_your_api_wallet_private_key
HYPERLIQUID_MAX_ORDER_USDC=100
HYPERLIQUID_ALLOWED_ASSETS=BTC,ETH,SOL,HYPE
DEMO_REQUIRE_CONFIRMATION=true
```

The browser requires the confirmation checkbox and the exact phrase
`CONFIRM MAINNET ORDER` before prodnet execution.

## 6. Validation

```bash
uv run pytest
uv run ruff check .
```
