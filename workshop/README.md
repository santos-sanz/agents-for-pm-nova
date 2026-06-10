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
cd ..
make workshop
```

Open <http://127.0.0.1:8123/workshop>.

During the workshop, keep the UI on `prodnet`, keep confirmation enabled, and
show the approval boundary before any exchange-changing action.

## Build Prompt Assets

- `initial-goal-prompt.md`: one-shot prompt for a coding agent using `/goal` and
  `/plan`.
- `design.md`: product/design target the coding agent should implement against.
- `../docs/demo-rebuild.md`: integration and implementation context for the
  coding agent.
