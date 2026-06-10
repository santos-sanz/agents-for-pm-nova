# Instructor Workshop Kit

This folder is for the live instructor-led workshop. Attendees only watch the
build and demo flow; they do not need to follow along locally or edit code.

The existing `demo/` app is the finished reference demo for the talk. The
workshop is a separate product build that starts from the prompt, design target,
and readiness page in this folder.

## Environment Preset

Copy the workshop preset into the demo before rehearsal or the live session:

```bash
cp workshop/.env.example demo/.env
```

When starting from a clean Claude Managed Agents project, change only the Claude
Managed Agents values first:

```bash
ANTHROPIC_API_KEY=...
WORKSHOP_ANTHROPIC_API_KEY=...
```

The workshop readiness app expects the workshop Claude workspace to be:

```bash
WORKSHOP_ANTHROPIC_WORKSPACE_ID=wrkspc_01Ja4EK3nFQXQqKUgf8dcLu7
```

Set `ANTHROPIC_WORKSPACE_ID` only when you want the readiness page to compare
the workshop workspace against the separate demo workspace. These IDs must not
match.

When `WORKSHOP_ANTHROPIC_API_KEY` is set, the workshop readiness app uses it for
Anthropic checks instead of the generic `ANTHROPIC_API_KEY`. The readiness page
shows only the key source name, never the key value.

The workshop portfolio-manager asset universe is also separate from the demo
runtime:

```bash
WORKSHOP_HYPERLIQUID_ALLOWED_ASSETS=xyz:CL,xyz:BRENTOIL,xyz:GOLD,xyz:SILVER,xyz:SP500,flx:USA100,xyz:COPPER,vntl:WHEAT,xyz:NATGAS,BTC
```

Keep `HYPERLIQUID_ALLOWED_ASSETS` for the finished demo and use
`WORKSHOP_HYPERLIQUID_ALLOWED_ASSETS` for the product built during the workshop.

Leave these blank for a clean start unless you want to reuse resources from a
previous rehearsal:

```bash
ANTHROPIC_AGENT_ID=
ANTHROPIC_ENVIRONMENT_ID=
ANTHROPIC_CHAT_VAULT_IDS=
ANTHROPIC_CHAT_MCP_SERVERS=
```

The demo bootstrap should reuse existing Claude Managed Agents Platform
resources. If these IDs are blank, the code should discover matching resources
by stable demo names before creating anything new, then report or persist the
IDs for the next rehearsal.

If the workshop will include a guarded prodnet execution demo, the instructor
also preconfigures the host-managed execution values in `demo/.env`:

```bash
HYPERLIQUID_ACCOUNT_ADDRESS=0x_your_main_wallet
HYPERLIQUID_API_WALLET_PRIVATE_KEY=0x_your_api_wallet_private_key
HYPERLIQUID_MAX_ORDER_USDC=25
DEMO_TRADING_MODE=mainnet_guarded
HYPERLIQUID_MAINNET_ENABLED=true
DEMO_REQUIRE_CONFIRMATION=true
```

Use only a Hyperliquid API/agent wallet private key. Never use the main wallet
private key in this project, in prompts, in browser storage, or in screenshots.

## Rehearsal Commands

```bash
cd demo
uv sync
npm install
uv run demo setup-check
uv run demo verify-assets
uv run demo profile --risk-score 25
uv run demo research --risk-score 25
uv run demo allocate --risk-score 25
cd ..
make workshop
```

Open <http://127.0.0.1:8123/workshop>.

The instructor readiness page at `/workshop` checks only integrations and
workspace identity. The working portfolio product is served by the main FastAPI
app at `/`:

```bash
cd demo
uv run uvicorn hyper_demo.api:app --reload
```

Open <http://127.0.0.1:8000>. If no profile exists, Nova Wealth Guard asks one
question: a slider from capital preservation to growth. The app persists that
score, verifies the workshop asset universe, generates a research brief, and
produces a 100% allocation across USDC plus eligible active markets.

During the workshop, keep confirmation enabled and show the approval boundary
before any exchange-changing action. `uv run demo rebalance --allocation <id>`
prepares a pending-approval preview unless `--confirm` is supplied, and live
execution remains blocked when credentials or guardrails are missing.

## Asset Verification

`uv run demo verify-assets` re-checks the canonical workshop markets against
Hyperliquid metadata. The only eligible investment universe is:

- `xyz:CL` (`CL-USDC`)
- `xyz:BRENTOIL` (`BRENT-USDC`)
- `xyz:GOLD` (`XAU-USDC`)
- `xyz:SILVER` (`XAG-USDC`)
- `xyz:SP500` (`US500-USDC`)
- `flx:USA100` (`US100-USDC`)
- `xyz:COPPER` (`COPPER-USDC`)
- `vntl:WHEAT` (`WHEAT-USDC`)
- `xyz:NATGAS` (`NATGAS-USDC`)
- `BTC` (`BTC-USDC`)

If a configured market is missing, halted, delisted, or stale, the allocation
excludes it and records the runtime failure separately.

## Source Coverage And Posture

Perplexity Finance and HyperTracker are optional enrichments behind environment
variables. When they are unavailable, the allocation engine still produces an
educational target allocation, lowers confidence, records coverage gaps, and
raises USDC above the minimum cash rule.

Nova Wealth Guard is educational, not personal financial advice. It is long-only
by default, assumes no leverage for target allocation, requires every allocation
to sum to 100% including USDC, and keeps secrets server-side. Robot mode, chat
messages, and background jobs cannot submit exchange-changing actions without
explicit host/user confirmation.

## Build Prompt Assets

- `initial-goal-prompt.md`: one-shot prompt for a coding agent using `/goal` and
  `/plan`.
- `design.md`: product/design target the coding agent should implement against.
- `../docs/demo-rebuild.md`: integration and implementation context for the
  coding agent.
