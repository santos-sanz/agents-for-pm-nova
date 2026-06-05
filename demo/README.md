# Hyperliquid Testnet Investment Agent Demo

English-language demo app for a Claude Managed Agents investment workflow with Hyperliquid guarded execution.

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

Fill `.env` with Claude and Hyperliquid credentials. Use a Hyperliquid API/agent wallet
private key only. Never put the private key for the main Dreamcash/Hyperliquid wallet in
this project.
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

## Dreamcash / Hyperliquid Mainnet Wallet

Default mode remains testnet. To connect a real Hyperliquid wallet read-only, set
`HYPERLIQUID_ACCOUNT_ADDRESS` to the main wallet address. The app uses that address for
account state and never treats the API wallet address as the account owner.

To allow guarded mainnet execution, generate or connect a Hyperliquid API/agent wallet and
store only that API wallet private key in `.env.local`:

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

Mainnet execution requires both the confirmation checkbox and the exact phrase
`CONFIRM MAINNET ORDER`. Revoke the API wallet in Hyperliquid when the demo is over if you
do not want it to remain usable.

## Safety Defaults

- `DEMO_TRADING_MODE` defaults to `testnet`.
- `mainnet_guarded` requires `HYPERLIQUID_MAINNET_ENABLED=true`.
- `DEMO_REQUIRE_CONFIRMATION` defaults to `true`.
- Mainnet Hyperliquid URLs are rejected unless guarded mainnet mode is explicitly enabled.
- The execution endpoint refuses to submit an order unless the request is explicitly confirmed.
- Mainnet execution also requires `CONFIRM MAINNET ORDER`.
- Orders above `HYPERLIQUID_MAX_ORDER_USDC` or outside `HYPERLIQUID_ALLOWED_ASSETS` are blocked.
- Paper trading calls the public Coinbase Exchange market-data API, simulates entry, stop-loss,
  and take-profit orders, and stores a debug trace in the run events and order raw response.
- The multi-agent review combines search cards, deterministic quant signals, and skills inspired
  by public investing principles without impersonating any investor.
- If live services are unavailable, use `uv run demo replay --fixture fallback`.
