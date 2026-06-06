# Hyperliquid Claude Trading Agent Demo

English-language demo app for a Claude Managed Agents trading cockpit on Hyperliquid.

The app supports:

- Reactive analysis: ask for a trade idea on any Hyperliquid asset.
- Proactive scan: scan the configured watchlist and propose the strongest demo candidate.
- Testnet auto-execution: guarded auto-submit when credentials and guardrails pass.
- Prodnet guarded execution: never automatic; requires UI confirmation and `CONFIRM MAINNET ORDER`.

## Setup

```bash
cd demo
uv sync
cp .env.example .env
```

Fill `.env` with Claude and Hyperliquid credentials. Use a Hyperliquid API/agent wallet
private key only. Never put the private key for the main wallet in this project.

```bash
uv run demo setup-check
uv run demo analyze --asset BTC
uv run demo scan
uv run uvicorn hyper_demo.api:app --reload
```

Open <http://127.0.0.1:8000>.

## Runtime Modes

The browser UI stores local runtime settings in `.demo_state/runtime.json`:

- `network`: `testnet` or `prodnet`
- `execution_policy`: `auto_testnet_confirm_prodnet`
- `ui_mode`: `human` or `robot`
- `watchlist`, `allowed_assets`, and `max_order_usdc`

The UI never accepts arbitrary exchange URLs. Testnet/prodnet URLs are derived internally.

## Prodnet Guardrails

Default mode is testnet. To allow guarded prodnet execution:

```bash
HYPERLIQUID_MAINNET_ENABLED=true
HYPERLIQUID_ACCOUNT_ADDRESS=0x_your_main_wallet
HYPERLIQUID_API_WALLET_PRIVATE_KEY=0x_your_api_wallet_private_key
HYPERLIQUID_MAX_ORDER_USDC=100
HYPERLIQUID_ALLOWED_ASSETS=BTC,ETH,SOL
DEMO_REQUIRE_CONFIRMATION=true
```

Prodnet execution still requires both the confirmation checkbox and the exact phrase
`CONFIRM MAINNET ORDER`.

## Validation

```bash
uv run pytest
uv run ruff check .
```
