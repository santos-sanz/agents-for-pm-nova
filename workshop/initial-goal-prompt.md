# Initial Coding Agent Prompt

Use this as the first prompt in a clean Claude Managed Agents project. It is
designed to work with `/goal`, `/plan`, `workshop/design.md`, and the
integration context in `docs/demo-rebuild.md`.

Asset availability was checked on 2026-06-10 against Hyperliquid's public
`/info` endpoint using `perpDexs`, `metaAndAssetCtxs`, and `allMids`. The app
must re-check availability at runtime because HIP-3 markets can be added,
renamed, halted, or delisted.

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
- Use the Apple-style workshop/design.md reference: photography-first surfaces, restrained chrome, SF/system typography, a single Action Blue interactive color, no decorative gradients, no card shadows, and no oversized marketing hero.
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

Requested but not currently eligible as active allocation assets:
- `CORN-USDC`: `xyz:CORN` exists but is delisted; do not allocate until it is active again.
- `SUGAR-USDC`, `COFFEE-USDC`, `COTTON-USDC`, `SODIUM-USDC`, and `WOC-USDC`: no active matching Hyperliquid market was found.
- `TRADETECH-USDC`: no exact active market was found. Treat it as a research-only theme unless the user explicitly approves an active substitute such as `vntl:INFOTECH`, `vntl:MAG7`, `vntl:SEMIS`, `km:USTECH`, or `xyz:XYZ100`.

Risk-profile mapping:
- `0-35` capital preservation: minimum USDC 40%, max single asset 12%, max BTC 5%, max total equity-index exposure 30%, max total commodity exposure 45%.
- `36-70` balanced conservative: minimum USDC 25%, max single asset 18%, max BTC 8%, max total equity-index exposure 45%, max total commodity exposure 55%.
- `71-100` guarded growth: minimum USDC 10%, max single asset 25%, max BTC 12%, max total equity-index exposure 60%, max total commodity exposure 65%.
- The risk agent may increase cash above these minimums whenever macro, funding, liquidity, or volatility conditions deteriorate.

Required implementation:
- FastAPI backend serving a static browser UI.
- Static browser UI with risk slider onboarding, portfolio dashboard, asset universe, allocation proposal, validation status, research sources, agent chat/workflow, and event logs.
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
- The first interaction, if no profile exists, is one slider question only.
- Show the current risk profile, USDC cash target, total portfolio risk, confidence, and source freshness above the allocation.
- Show target allocation and current wallet allocation side by side when wallet data exists.
- Show each asset's canonical market ID, display label, category, active/delisted status, mark price, funding, open interest, max leverage, allocation cap, and final target percentage.
- Show why the agent increased or decreased cash.
- Show blocked assets separately with the reason they are blocked.
- Use explicit statuses: `draft`, `validated`, `blocked`, `pending_approval`, `submitted`, `failed`.
- Keep copy concise and educational; avoid "buy", "sell", or guaranteed-return language.

Validation requirements:
- Re-check Hyperliquid availability at app startup and before every proposal.
- Block delisted, missing, halted, unsupported, or non-allowlisted markets.
- Block arbitrary exchange URLs.
- Ensure allocation percentages sum to 100%.
- Enforce the minimum USDC cash percentage for the user's risk profile.
- Enforce single-asset, category, BTC, notional, leverage, and funding-cost caps.
- Validate account state and available margin before any rebalance order.
- Require explicit confirmation before submitting any order.
- Never ask for, log, store, or expose private keys, credentials, cookies, browser data, or wallet secrets.

/plan Before editing, inspect the project structure and read workshop/design.md, workshop/initial-goal-prompt.md, and docs/demo-rebuild.md. Then implement in small vertical slices:
1. Update the design target if needed so workshop/design.md matches the Apple-design-analysis reference and the portfolio-manager product.
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
- `uv run demo setup-check` reports required configuration and guarded prodnet posture.
- `uv run demo verify-assets` re-checks the active universe and reports blocked/missing requested assets.
- Re-running setup/bootstrap does not duplicate Claude Managed Agents Platform resources; it reuses pinned IDs or previously discovered resources.
- `uv run pytest` passes.
- `uv run ruff check .` passes.
- The browser dashboard opens locally, asks exactly one risk-slider question when needed, and then shows portfolio allocation, USDC cash, active/blocked assets, research sources, validation, and event logs.
- Allocation output always sums to 100% and respects the selected risk profile.
- Exchange-changing prodnet actions require explicit confirmation and cannot be triggered by robot mode alone.
- No secrets, `.env` files, runtime state, caches, or generated build outputs are committed.
- The final response includes changed files, validation commands, asset verification results, and any live-network steps that were not executed.
```
