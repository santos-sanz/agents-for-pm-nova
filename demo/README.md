# HyperClaude

English-language demo app for a Claude Managed Agents trading cockpit on Hyperliquid.

The app supports:

- Reactive analysis: ask for a trade idea on any Hyperliquid asset.
- Proactive scan: scan the configured watchlist and propose the strongest demo candidate.
- Prodnet guarded execution: never automatic; requires UI confirmation and explicit enablement.
- Reviewable execution controls: max order size, allowlisted assets, validation, and human approval.

## Setup

```bash
cd demo
uv sync
npm install
cp .env.example .env
```

For the workshop path, use the preset instead:

```bash
cp ../workshop/.env.example .env
```

Then change only the Claude Managed Agents values, starting with
`ANTHROPIC_API_KEY`. The workshop path always uses guarded prodnet, and
non-Claude execution credentials are host-managed. The full workshop guide and
integration map live in
`../workshop/README.md`.

Fill `.env` with Claude and Hyperliquid credentials. Use a Hyperliquid API/agent wallet
private key only. Never put the private key for the main wallet in this project.
The browser UI serves TradingView Lightweight Charts from `node_modules`, so keep the npm
dependencies installed before starting FastAPI.
To enable the browser wallet login, also set `PRIVY_APP_ID` and `PRIVY_CLIENT_ID`
from the Privy Dashboard. Do not put the Privy app secret in the browser demo.
To execute through Privy-managed Hyperliquid agent wallets, enable the server-side Privy secret:

```bash
PRIVY_APP_ID=...
PRIVY_CLIENT_ID=...
PRIVY_APP_SECRET=...
PRIVY_EXECUTION_ENABLED=true
PRIVY_EXTERNAL_WITHDRAWAL_ADDRESS=0xcF1D21Cd958C13aC24BA54506464E64AC80B4214
```

With `PRIVY_EXECUTION_ENABLED=true`, connect/create a Privy wallet in the browser, then use
`Initialize agent` before execution. When the browser SDK provides a wallet ID, that wallet
is used as the master wallet; otherwise the backend creates a Privy master wallet. The app
then creates a Privy agent wallet, registers the agent on Hyperliquid, and routes trading
orders through that registered agent.
For sponsored user-wallet transfers and external withdrawals, enable Privy identity tokens
in the dashboard under User management > Authentication > Advanced.

```bash
uv run demo setup-check
uv run demo analyze --asset BTC
uv run demo scan
uv run uvicorn hyper_demo.api:app --reload
```

Open <http://127.0.0.1:8000>.

## Runtime Modes

The browser UI stores local runtime settings in `.demo_state/runtime.json`:

- `network`: `prodnet` for the workshop path
- `ui_mode`: `human` or `robot`
- `watchlist`, `allowed_assets`, and `max_order_usdc`

The UI never accepts arbitrary exchange URLs. The workshop preset uses the known
Hyperliquid prodnet URLs and keeps execution behind explicit confirmation.

## Prodnet Guardrails

The workshop path uses guarded prodnet:

```bash
DEMO_TRADING_MODE=mainnet_guarded
HYPERLIQUID_MAINNET_ENABLED=true
HYPERLIQUID_ACCOUNT_ADDRESS=0x_your_main_wallet
HYPERLIQUID_API_WALLET_PRIVATE_KEY=0x_your_api_wallet_private_key
HYPERLIQUID_MAX_ORDER_USDC=100
HYPERLIQUID_ALLOWED_ASSETS=BTC,ETH,SOL
DEMO_REQUIRE_CONFIRMATION=true
```

Prodnet execution still requires the confirmation checkbox and explicit environment enablement.

## Validation

```bash
uv run pytest
uv run ruff check .
```
