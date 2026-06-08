# HyperClaude

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
To enable the browser wallet login, also set `PRIVY_APP_ID` and `PRIVY_CLIENT_ID`
from the Privy Dashboard. Do not put the Privy app secret in the browser demo.
To execute through Privy-managed Hyperliquid agent wallets, install the Node helper
dependencies and enable the server-side Privy secret:

```bash
npm install
```

```bash
PRIVY_APP_ID=...
PRIVY_CLIENT_ID=...
PRIVY_APP_SECRET=...
PRIVY_EXECUTION_ENABLED=true
```

With `PRIVY_EXECUTION_ENABLED=true`, connect/create a Privy wallet in the browser, then use
`Initialize agent` before execution. When the browser SDK provides a wallet ID, that wallet
is used as the master wallet; otherwise the backend creates a Privy master wallet. The app
then creates a Privy agent wallet, registers the agent on Hyperliquid, and routes trading
orders through that registered agent.

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
