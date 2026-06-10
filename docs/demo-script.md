# HyperClaude Happy Path Demo Script

## Demo Goal

Show PMs how a managed agent becomes a controllable product surface:

- contract and boundaries;
- runtime settings and guardrails;
- session loop and event stream;
- tool-backed trade planning;
- formal validation before execution;
- human confirmation for tiny mainnet execution;
- close/reduce loop after the proof.

This is an educational systems demo. It is not financial advice and it is not a buy, sell, or hold recommendation.

## Safety Framing

Say this before the demo:

> This is an educational demo of agentic systems with guarded execution. It is not an investment recommendation. The point is to inspect the workflow: what the agent can do, what it cannot do, what it must validate, and where the human approves.

## Happy Path

### 1. Explain The Agent Contract

Before using the UI, state the contract:

- HyperClaude synthesizes market context and proposes reviewable plans.
- It does not own the investment decision.
- It can use allowed tools and runtime context.
- It must respect allowlisted assets, max order size, wallet margin, and execution policy.
- On mainnet, execution needs explicit human approval.

### 2. Show Settings As Product Surface

Open `http://localhost:8001/`, then show Settings.

Confirm:

- network is `prodnet`;
- UI mode is `robot`;
- max order is `100 USDC`;
- allowed assets and watchlist are synced;
- Managed Agents resources are `ready`;
- Privy server execution is configured;
- mainnet execution is enabled but still guarded by confirmation.

The PM takeaway: the agent is not just a prompt. It is a configured product surface with tools, resources, memory, deployment, and guardrails.

### 3. Start A Clean Chat Session

Create a new Chat session and use this prompt:

```text
Analyze the allowed assets, use the available context, and propose several intraday trades without executing any of them.

Use runtime settings, wallet state, open positions, allowed assets, mark prices, and market context.
Create stored trade plans only for proposals that are formally coherent and likely to pass validation.
End with a compact ranked list and say which plan should be reviewed next.
```

While it runs, point to:

- runtime settings request;
- market snapshot;
- tool calls;
- plan creation;
- validation result;
- any pending human approval gate.

Key line:

> Here the PM sees the loop, not just the final answer.

### 4. Inspect The Plan

Choose an ETH or BTC plan with:

- notional around `10.5-12 USDC`;
- `4x` leverage;
- take profit present;
- no stop loss below `10x`, using active monitoring and thesis invalidation instead;
- status still `draft`;
- formal validation passing.

Explain the validation checklist:

- asset is allowlisted;
- network matches runtime;
- notional clears Hyperliquid minimum plus buffer;
- order is under runtime max;
- leverage is within market max;
- take profit is directionally valid;
- wallet margin is sufficient;
- no conflicting open position exists.

### 5. Execute Tiny Mainnet

Before clicking, say:

> I am about to submit a real tiny mainnet order. The notional is intentionally small, and it has passed formal validation. This is the human approval gate.

Click the guarded execution action only if validation is green.

Do not execute if:

- `valid=false`;
- wallet state is unavailable;
- plan is no longer `draft`;
- order size is above the planned tiny amount;
- the UI shows any guardrail error.

Expected success signal:

- order status is `submitted`;
- message mentions the Privy Hyperliquid agent wallet;
- Orders & positions updates.

### 6. Close The Loop

Open Orders & positions.

If a position remains open, use the close-position action to submit a reduce-only market close. The position card marks this as the happy path close step.

Close with:

> The value is not that the agent placed a tiny order. The value is that the system made work observable, reviewable, validated, and governed before it acted.

## Fallback Plan

If the live API, network, or Managed Agents service fails:

1. Show Settings and explain the intended contract.
2. Open a saved Chat session with tool requests and results.
3. Show a stored plan and the formal validation checklist.
4. Explain where human approval would have occurred.
5. Do not execute.

Fallback line:

> The live implementation detail failed, which is exactly why the product loop matters. We can still inspect the contract, events, validation, and approval boundary.

## Rehearsal Checklist

- Run `git pull`.
- Start the app on `http://localhost:8001/`.
- Verify `curl http://localhost:8001/api/setup-check`.
- Verify Managed Agents resources are `ready`.
- Verify Privy server execution is configured.
- Verify mainnet is enabled and confirmation is required.
- Run a Chat session without executing.
- Validate one tiny ETH or BTC plan.
- Confirm formal validation returns `valid=true`.
- Confirm the selected plan is around `10.5-12 USDC` notional.
- Rehearse the fallback path once.
- Keep secrets, private keys, browser data, and wallet credentials out of prompts and screenshots.
