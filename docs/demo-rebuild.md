# Rebuild Guide: HyperClaude

This guide recreates the demo from a clean clone. The demo is Hyperliquid-only and defaults
to guarded mainnet proposals. Real execution remains behind explicit environment enablement
and manual confirmation.

Use this document as implementation context for a coding agent. The companion
workshop prompt is [workshop/initial-goal-prompt.md](../workshop/initial-goal-prompt.md)
and the product target is [workshop/design.md](../workshop/design.md).

## Integration Map For Coding Agents

The demo is a FastAPI + static UI + Typer CLI application. It should be built as
an observable product workflow, not as a single prompt wrapper.

### Claude Managed Agents

Role in the product:

- Owns the agent session loop and reasoning trace.
- Calls tools for runtime settings, market context, wallet state, plan creation,
  validation, and pending execution actions.
- Produces structured, reviewable draft plans rather than direct trading advice.
- Emits events that the UI can show in the robot/debug log.

Environment contract:

```bash
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_AGENT_ID=
ANTHROPIC_ENVIRONMENT_ID=
ANTHROPIC_CHAT_MODEL=
ANTHROPIC_CHAT_AUTO_BOOTSTRAP=true
ANTHROPIC_CHAT_MAX_OUTCOME_ITERATIONS=5
ANTHROPIC_CHAT_VAULT_IDS=
ANTHROPIC_CHAT_MCP_SERVERS=
ANTHROPIC_CHAT_ENABLE_DREAMS=false
```

Implementation targets:

- `demo/src/hyper_demo/adapters/anthropic_managed.py`
- `demo/src/hyper_demo/services/managed_chat.py`
- `demo/src/hyper_demo/services/trading_agent.py`

Clean-project behavior:

- Start by setting only `ANTHROPIC_API_KEY`.
- Leave agent and environment IDs blank unless reusing resources from a
  rehearsal.
- If MCP servers or vault resources are available, wire them through
  `ANTHROPIC_CHAT_MCP_SERVERS` and `ANTHROPIC_CHAT_VAULT_IDS`.
- Bootstrap must be idempotent. Before creating any Claude Managed Agents
  Platform resource, first check configured IDs, then search/list existing
  resources by stable demo names. Reuse safe matches, persist discovered IDs in
  local state or documented environment values, and create new resources only
  when no unambiguous existing match is found.
- Re-running `setup-check`, chat bootstrap, or a rehearsal must not create
  duplicate agents, environments, vault entries, tool resources, or MCP server
  registrations.

### Hyperliquid Prodnet

Role in the product:

- Provides prodnet market data, mark prices, wallet/account state, open
  positions, and order submission.
- Enforces the product's runtime boundaries: known URLs only, allowlisted
  assets, max notional, leverage bounds, sufficient margin, and confirmation.
- Never receives a main wallet private key. Execution uses an API/agent wallet
  authorized for the main account.

Environment contract:

```bash
DEMO_TRADING_MODE=mainnet_guarded
HYPERLIQUID_BASE_URL=https://api.hyperliquid.xyz
HYPERLIQUID_WS_URL=wss://api.hyperliquid.xyz/ws
HYPERLIQUID_MAINNET_ENABLED=true
HYPERLIQUID_ACCOUNT_ADDRESS=0x_your_main_wallet
HYPERLIQUID_API_WALLET_PRIVATE_KEY=0x_your_api_wallet_private_key
HYPERLIQUID_MAX_ORDER_USDC=25
HYPERLIQUID_ALLOWED_ASSETS=BTC,ETH,SOL,HYPE
DEMO_REQUIRE_CONFIRMATION=true
```

Implementation targets:

- `demo/src/hyper_demo/adapters/hyperliquid.py`
- `demo/src/hyper_demo/services/market.py`
- `demo/src/hyper_demo/services/formal_validation.py`
- `demo/src/hyper_demo/services/risk.py`

Safety invariants:

- Prodnet execution is never automatic.
- `DEMO_REQUIRE_CONFIRMATION=true` is required for the workshop.
- `ui_mode=robot` can prepare and validate actions but cannot bypass approval.
- Arbitrary exchange URLs must be rejected.

### Privy

Role in the product:

- Optional browser login and optional server-managed wallet path.
- Can create/register a Hyperliquid agent wallet and route execution through
  that wallet when enabled.

Environment contract:

```bash
PRIVY_APP_ID=
PRIVY_CLIENT_ID=
PRIVY_APP_SECRET=
PRIVY_EXECUTION_ENABLED=false
```

Implementation targets:

- `demo/src/hyper_demo/static/privy.js`
- `demo/src/hyper_demo/adapters/privy_hyperliquid.py`
- `demo/scripts/privy_hyperliquid.mjs`

Safety invariant: `PRIVY_APP_SECRET` is server-side only.

### Perplexity

Role in the product:

- Optional finance-search enrichment for market context.
- Optional MCP server for Claude Managed Agents when exposed through an HTTPS
  URL.

Environment contract:

```bash
PERPLEXITY_API_KEY=
PERPLEXITY_BASE_URL=https://api.perplexity.ai/v1
PERPLEXITY_MCP_SERVER_URL=
PERPLEXITY_MODEL=perplexity/sonar
```

Implementation targets:

- `demo/src/hyper_demo/services/perplexity.py`
- `demo/src/hyper_demo/services/perplexity_mcp.py`

### HyperTracker / CoinMarketMan

Role in the product:

- Optional market intelligence enrichment.
- Optional MCP server for Claude Managed Agents when exposed through an HTTPS
  URL.

Environment contract:

```bash
HYPERTRACKER_API_KEY=
HYPERTRACKER_BASE_URL=https://ht-api.coinmarketman.com
HYPERTRACKER_MCP_SERVER_URL=
```

Implementation target:

- `demo/src/hyper_demo/services/hypertracker.py`

### Browser UI

Role in the product:

- First screen is the cockpit, not a landing page.
- Shows runtime settings, Managed Agents status, chat/workflow, plans,
  validation, execution controls, orders/positions, and robot logs.
- Makes the prodnet approval boundary visible before any exchange-changing
  action.

Implementation targets:

- `demo/src/hyper_demo/static/index.html`
- `demo/src/hyper_demo/static/app.js`
- `demo/src/hyper_demo/static/styles.css`

### Persistence And Runtime State

Role in the product:

- Stores sessions, plans, events, runtime settings, and wallet metadata under
  `.demo_state/`.
- Runtime settings can adjust allowlist, watchlist, max order size, UI mode, and
  network selection, but must not inject arbitrary exchange URLs.

Implementation targets:

- `demo/src/hyper_demo/storage.py`
- `demo/src/hyper_demo/models.py`
- `demo/src/hyper_demo/config.py`

## 1. Install

```bash
cd demo
uv sync
npm install
cp .env.example .env
```

The browser UI serves TradingView Lightweight Charts from the demo npm dependencies.
For the instructor-led workshop, use the shorter preset instead:

```bash
cp ../workshop/.env.example .env
```

Then follow [Instructor Workshop Kit](../workshop/README.md) to use the guarded
prodnet workshop path, change only the Claude Managed Agents values, and review
the integration map in this guide.

Fill `.env` with Claude and Hyperliquid values:

```bash
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
HYPERLIQUID_ACCOUNT_ADDRESS=...
HYPERLIQUID_API_WALLET_PRIVATE_KEY=...
HYPERLIQUID_MAX_ORDER_USDC=100
HYPERLIQUID_ALLOWED_ASSETS=BTC,ETH,SOL,HYPE
HYPERLIQUID_MAINNET_ENABLED=true
DEMO_TRADING_MODE=mainnet_guarded
DEMO_REQUIRE_CONFIRMATION=true
```

## 2. Check Setup

```bash
uv run demo setup-check
```

Expected:

- Trading mode is `mainnet_guarded`.
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

1. Keep `prodnet` selected and `Human` mode active.
2. Enter an asset and run reactive analysis.
3. Show the proposal, risk, invalidation, and execution decision.
4. Switch to `Robot logs` to show raw state and Managed Agent/event traces.
5. Run a proactive scan from the watchlist.
6. Show that prodnet execution waits for explicit confirmation.

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

The browser requires the confirmation checkbox before prodnet execution.

## 6. Cloud Deployment Access

Give the Claude deployment only server-side environment variables and scoped
wallet access. Do not paste private keys into prompts, chat messages, browser
local storage, or source files.

For cloud workshop deployment, use guarded prodnet and keep exchange-changing
actions behind explicit host approval:

```bash
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_CHAT_AUTO_BOOTSTRAP=true
DEMO_TRADING_MODE=mainnet_guarded
DEMO_REQUIRE_CONFIRMATION=true
HYPERLIQUID_BASE_URL=https://api.hyperliquid.xyz
HYPERLIQUID_WS_URL=wss://api.hyperliquid.xyz/ws
HYPERLIQUID_ACCOUNT_ADDRESS=0x_your_main_wallet
HYPERLIQUID_API_WALLET_PRIVATE_KEY=0x_your_api_wallet_private_key
HYPERLIQUID_MAX_ORDER_USDC=25
HYPERLIQUID_ALLOWED_ASSETS=BTC,ETH,SOL,HYPE
HYPERLIQUID_MAINNET_ENABLED=true
```

If using Privy server wallets instead of a raw Hyperliquid API wallet, set:

```bash
PRIVY_APP_ID=...
PRIVY_APP_SECRET=...
PRIVY_EXECUTION_ENABLED=true
```

Then initialize the agent wallet from the browser UI or via
`POST /api/privy/agent-wallet` for the selected network. The deployment can use
the stored agent wallet record after it exists.

For the workshop, prodnet remains guarded:

```bash
DEMO_TRADING_MODE=mainnet_guarded
HYPERLIQUID_MAINNET_ENABLED=true
DEMO_REQUIRE_CONFIRMATION=true
HYPERLIQUID_MAX_ORDER_USDC=25
```

In prodnet, Managed Chat tools can create and validate plans, read wallet state,
and prepare pending tool actions, but exchange-changing actions require explicit
host human approval. `ui_mode=robot` is not a bypass for prodnet execution.

## 7. Validation

```bash
uv run pytest
uv run ruff check .
```
