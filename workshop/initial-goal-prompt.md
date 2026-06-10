# Initial Coding Agent Prompt

Use this as the first prompt in a clean Claude Managed Agents project. It is
designed to work with `/goal`, `/plan`, `workshop/design.md`, and the
integration context in `docs/demo-rebuild.md`.

Asset availability was checked on 2026-06-10 against Hyperliquid's public
`/info` endpoint using `perpDexs`, `metaAndAssetCtxs`, and `allMids`. The app
must use only the active markets listed below and must re-check availability at
runtime because HIP-3 markets can be added, renamed, halted, or delisted.

```text
/goal Build Nova Wealth Guard: a conservative, agentic portfolio manager for a Hyperliquid USDC portfolio.

The final result must match workshop/design.md and use docs/demo-rebuild.md as the implementation and integration context. Build the actual working portfolio manager, not a mock landing page.

Product goal:
- Create a more conservative wealth-management experience, not an intraday trading cockpit.
- A team of agents researches the eligible asset universe, evaluates the global macro/market situation, and proposes a target allocation across active assets plus cash.
- Cash is USDC and can be any percentage from 0% to 100%.
- The final allocation must always sum to 100%.
- The product must preserve capital first, diversify second, and seek moderate upside third.
- The product must not present output as personal financial advice.

Context:
- The first screen is the working portfolio dashboard, not a marketing page.
- Before building the full portfolio workflow, create a workshop readiness page that only verifies required integrations and shows which Anthropic Managed Agents workspace/environment is being used for this `workshop/` project.
- The workshop Claude workspace is `wrkspc_01Ja4EK3nFQXQqKUgf8dcLu7` (`https://platform.claude.com/workspaces/wrkspc_01Ja4EK3nFQXQqKUgf8dcLu7/sessions`) and must remain distinct from any demo workspace configured through `ANTHROPIC_WORKSPACE_ID`.
- When `WORKSHOP_ANTHROPIC_API_KEY` is configured, use it for workshop Anthropic checks and Managed Agents bootstrap instead of the generic demo `ANTHROPIC_API_KEY`; show only the key source name in readiness output.
- The existing `demo/` app is the finished reference demo. The workshop builds a separate portfolio-manager product and must use workshop-specific configuration instead of inheriting demo runtime choices.
- The workshop tradeable universe comes from `WORKSHOP_HYPERLIQUID_ALLOWED_ASSETS` and must remain distinct from `HYPERLIQUID_ALLOWED_ASSETS`, which belongs to the finished demo.
- Use workshop/design.md as the design target: photography-first surfaces, restrained chrome, system typography, a single blue action color, no decorative gradients, no card shadows, and no oversized marketing hero.
- The app must ask the user one initial risk-profile question only: a single slider from "capital preservation" to "growth". Convert it to `risk_score` from 0 to 100 and persist it.
- Default behavior is conservative even when the slider is high because the instruments are perpetual futures.
- The portfolio is long-only by default. Do not use short exposure unless a future operator setting explicitly enables it.
- Use low or no leverage by default; validate funding costs, liquidity, open interest, available margin, and concentration before any rebalance.
- The system must be comfortable recommending 100% USDC when evidence is weak or conditions are hostile.
- Execution-changing actions require explicit host/user confirmation and cannot be triggered by robot mode alone.

Agent team:
- Research agent: uses Perplexity Finance, Hyperliquid market data, and optional intelligence APIs to summarize macro conditions, asset signals, liquidity, funding, and data freshness.
- Portfolio agent: applies the user's risk score, portfolio constraints, diversification rules, and cash policy to produce a 100% target allocation across eligible assets and USDC.
- Safety agent: verifies active/non-delisted markets, validates allocation math and risk caps, blocks unsafe execution, keeps secrets server-side, and labels output as educational/non-advisory.

Data sources:
- Perplexity Finance for market and macro context.
- Hyperliquid public and authenticated APIs for quotes, metadata, candles, funding, open interest, account state, and order validation.
- Claude Managed Agents tools for structured reasoning, tool traces, and optional web/search/fetch intelligence.
- Optional intelligence APIs such as HyperTracker or other configured adapters behind environment variables.
- Every allocation must include source summaries, timestamps, and coverage gaps.

Verified active asset universe:
Use these canonical Hyperliquid market IDs for quotes, validation, and execution. The UI may show the friendly `*-USDC` labels, but internal logic must use the canonical IDs.

- `xyz:CL` (display `CL-USDC`): WTI crude oil perpetual.
- `xyz:BRENTOIL` (display `BRENT-USDC`): Brent crude oil perpetual.
- `xyz:GOLD` (display `XAU-USDC`): gold perpetual.
- `xyz:SILVER` (display `XAG-USDC`): silver perpetual.
- `xyz:SP500` (display `US500-USDC`): S&P 500 perpetual by Trade[XYZ].
- `flx:USA100` (display `US100-USDC`): NASDAQ 100 / USA100-style technology index perpetual.
- `xyz:COPPER` (display `COPPER-USDC`): copper perpetual.
- `vntl:WHEAT` (display `WHEAT-USDC`): wheat perpetual.
- `xyz:NATGAS` (display `NATGAS-USDC`): natural gas perpetual.
- `BTC` (display `BTC-USDC`): Bitcoin perpetual.

Risk-profile mapping:
- `0-35` capital preservation: minimum USDC 40%, max single asset 12%, max BTC 5%, max total equity-index exposure 30%, max total commodity exposure 45%.
- `36-70` balanced conservative: minimum USDC 25%, max single asset 18%, max BTC 8%, max total equity-index exposure 45%, max total commodity exposure 55%.
- `71-100` guarded growth: minimum USDC 10%, max single asset 25%, max BTC 12%, max total equity-index exposure 60%, max total commodity exposure 65%.
- The risk agent may increase cash above these minimums whenever macro, funding, liquidity, or volatility conditions deteriorate.

Required implementation:
- Initial workshop readiness page at `/workshop` with no trading or allocation workflow. It must show integration status, required vs optional services, safe configuration details, and Anthropic workspace/environment IDs without exposing secrets.
- Readiness API endpoint that powers the page and checks workshop files, Anthropic Managed Agents resources, the expected workshop Claude workspace ID/URL, separation from the demo Claude workspace when `ANTHROPIC_WORKSPACE_ID` is configured, workshop tradeable assets distinct from demo assets, Hyperliquid market data, wallet USDC balance, real Perplexity Finance test-call status, real HyperTracker test-call status, optional Privy, and guarded execution posture.
- FastAPI backend serving a static browser UI.
- Static browser UI with risk slider onboarding, portfolio dashboard, asset universe, allocation proposal, validation status, research sources, agent chat/workflow, and event logs.
- Use `tradingview/lightweight-charts` (`lightweight-charts`) whenever the UI needs financial time-series visualization, such as market candles, allocation history, portfolio value, drawdown, or asset comparison charts. Do not hand-roll charting primitives for those cases.
- Typer CLI for setup-check, verify-assets, profile, research, allocate, rebalance, and wallet state.
- Pydantic settings from `.env` / `.env.local`.
- Claude Managed Agents integration for sessions, agent roles, tool use, structured allocation output, and event traces.
- Idempotent Claude Managed Agents bootstrap that avoids duplicate platform resources across reruns and rehearsals.
- Perplexity Finance integration for market/macro context behind environment variables.
- Hyperliquid integration for market metadata, mark prices, candles, funding/open-interest context, wallet/account state, formal validation, and guarded order submission.
- Optional intelligence integrations behind environment variables.
- Persistent JSON state under `.demo_state/` for risk profile, asset verification snapshots, research briefs, target allocations, proposals, validations, and events.
- Tests covering config, asset-universe verification, profile mapping, allocation math, services, adapters, API, storage, validation, and safety guardrails.
- Documentation showing setup, rehearsal, asset verification, data-source coverage, and the non-advisory posture.

Core UI requirements:
- The workshop readiness page is a separate initial page for the instructor. It only checks integrations and workspace identity; it must not ask risk questions, generate allocations, or submit exchange actions.
- On the readiness page, show the local `workshop/` path, expected workshop Claude workspace ID and URL, demo Claude workspace ID when configured, whether both workspaces are distinct, workshop tradeable assets, demo tradeable assets, whether both asset universes are distinct, Anthropic model, resource status, environment ID, coordinator agent ID, vault IDs, MCP servers, custom tools, Perplexity/HyperTracker test-call results, and masked wallet balance.
- The first interaction, if no profile exists, is one slider question only.
- Show the current risk profile, USDC cash target, total portfolio risk, confidence, and source freshness above the allocation.
- Show target allocation and current wallet allocation side by side when wallet data exists.
- Show each asset's canonical market ID, display label, category, active/delisted status, mark price, funding, open interest, max leverage, allocation cap, and final target percentage.
- Show why the agent increased or decreased cash.
- Show runtime verification failures separately only if a configured active asset becomes unavailable, halted, or delisted.
- Use explicit statuses: `draft`, `validated`, `blocked`, `pending_approval`, `submitted`, `failed`.
- Keep copy concise and educational; avoid "buy", "sell", or guaranteed-return language.

Validation requirements:
- Treat the verified active asset universe above as the only eligible investment universe. Do not invent assets, use placeholders, or silently substitute similar markets.
- Re-check Hyperliquid metadata at startup, before every allocation proposal, and immediately before any rebalance. If a configured market is missing, halted, delisted, or has stale quote data, exclude it from allocation and explain the exclusion.
- Produce a structured allocation object with `generated_at`, `risk_score`, `cash_pct`, `positions`, `constraints`, `research_sources`, `confidence`, `validation_status`, and `explanations`.
- Ensure the allocation is long-only, non-negative, rounded consistently, and sums to exactly 100% including USDC after rounding.
- Enforce the minimum USDC cash percentage for the user's risk profile, then enforce single-asset, category, BTC, notional, leverage, liquidity, open-interest, and funding-cost caps.
- Increase USDC automatically when market confidence is low, sources are stale, volatility is elevated, funding is punitive, liquidity is thin, or the agents disagree.
- Block arbitrary exchange URLs, non-allowlisted canonical IDs, delisted markets, missing credentials, unsafe leverage, and any proposal that cannot be fully validated.
- Block workshop readiness if the workshop Claude workspace ID is missing or matches the configured demo Claude workspace ID.
- Block workshop readiness if `WORKSHOP_HYPERLIQUID_ALLOWED_ASSETS` is empty or matches the configured demo asset universe.
- Validate account state, current positions, available margin, minimum order size, expected slippage, and rebalance deltas before preparing orders.
- Require explicit user confirmation before submitting any order; robot mode, chat messages, or background jobs must never execute a rebalance by themselves.
- Never ask for, log, store, render, or expose private keys, credentials, cookies, browser data, access tokens, or wallet secrets.
- The app must remain useful without credentials: it should still verify assets, collect the risk profile, research markets, and produce a non-executable target allocation.

/plan Before editing, inspect the project structure and read workshop/design.md, workshop/initial-goal-prompt.md, and docs/demo-rebuild.md. Then implement in small vertical slices:
1. Confirm workshop/design.md is the current neutral design target and build the portfolio-manager product against it.
2. Settings, models, storage, asset-universe verification, and safety contracts.
3. Hyperliquid market/account adapter with prodnet URL allowlists and HIP-3 canonical market IDs.
4. Perplexity Finance and optional intelligence adapters.
5. Claude Managed Agents adapter, agent-role prompts, managed chat/session loop, and idempotent resource discovery/bootstrap.
6. Risk-profile slider, profile persistence, and allocation constraints.
7. Research brief, risk scoring, allocation proposal, formal validation, and guarded rebalance policy.
8. FastAPI routes and static UI dashboard.
9. CLI commands.
10. Tests and validation.
11. Browser verification of the complete portfolio workflow.

Use these quality plugins/capabilities when available:
- Browser plugin: open the local app, verify the dashboard loads, complete the risk slider, run a research/allocation flow, and capture console/network issues.
- JavaScript/TypeScript guidance: keep browser code maintainable and avoid brittle UI state.
- Backend/API guidance: keep FastAPI routes explicit, typed, and testable.
- Security review guidance: verify secrets stay server-side, execution remains gated, and arbitrary exchange URLs are rejected.
- GitHub/CI capabilities if publishing: run checks, summarize diff, and keep generated artifacts out of the PR.

Definition of done:
- `/workshop` opens locally and shows integration readiness plus the Anthropic workspace/environment used by this workshop.
- The readiness output shows `wrkspc_01Ja4EK3nFQXQqKUgf8dcLu7` as the expected workshop Claude workspace and does not mark it as the same workspace as the demo.
- `/api/workshop/readiness` returns structured readiness JSON without secrets.
- `uv run demo setup-check` reports required configuration and guarded prodnet posture.
- `uv run demo verify-assets` re-checks every configured active market and reports any unavailable, halted, delisted, or stale market.
- Re-running setup/bootstrap does not duplicate Claude Managed Agents Platform resources; it reuses pinned IDs or previously discovered resources.
- `uv run pytest` passes.
- `uv run ruff check .` passes.
- The browser dashboard opens locally, asks exactly one risk-slider question when needed, and then shows portfolio allocation, USDC cash, configured active assets, research sources, validation, and event logs.
- Allocation output always sums to 100% and respects the selected risk profile.
- The app can produce a complete target allocation without exchange credentials and clearly marks it as non-executable until credentials and confirmation are present.
- Exchange-changing prodnet actions require explicit confirmation and cannot be triggered by robot mode alone.
- No secrets, `.env` files, runtime state, caches, or generated build outputs are committed.
- The final response includes changed files, validation commands, asset verification results, and any live-network steps that were not executed.
```
