# Coding Agent Prompt Runbook

Use these prompts step by step in the coding agent to rebuild or extend the demo.
For a clean Claude Managed Agents project, start with
[`workshop/initial-goal-prompt.md`](../workshop/initial-goal-prompt.md) and
[`workshop/design.md`](../workshop/design.md); this file is for follow-up
extensions.

## 1. Inspect The Existing Demo

```text
Read the repository and explain the current Hyperliquid demo architecture.
Identify API entrypoints, CLI commands, state storage, safety checks, and tests.
Do not edit files yet.
```

## 2. Add The Multi-Agent Investment Committee

```text
Add a multi-agent investment committee layer to the demo.
It must include a search tool facade, a quant trading tool, and investor-style skills inspired by public principles from Ray Dalio, Warren Buffett, Jim Simons, and Peter Lynch.
Do not impersonate those people; encode review heuristics, veto rules, required checks, and prompt text.
Expose the result through a FastAPI endpoint and a CLI command.
```

## 3. Add Reviewable Quant Signals

```text
Create deterministic quant signals for the demo: trend score, volatility score, carry score, liquidity score, recommendation, and explanation.
Use existing market-data clients and keep all outputs educational, reviewable, and guarded for prodnet.
Add unit tests that do not call live networks.
```

## 4. Wire The Browser Demo

```text
Add an Agent Team view to the browser UI.
The view should run the multi-agent debate, show consensus, show each agent stance, and expose the raw JSON for presenters.
Keep the existing visual design and do not modify the slides.
```

## 5. Build The Testing Pyramid

```text
Create a testing pyramid for the demo.
Add unit tests for pure scoring and skills, integration tests for FastAPI endpoints, CLI smoke tests, and manual browser rehearsal checks.
Document which tests run in CI and which tests are live-demo rehearsal only.
```

## 6. Validate End To End

```text
Run formatting, linting, and tests for the demo.
Start the local API server, open the browser demo, and verify the Agent Team flow with fallback mode.
Report commands run, pass/fail status, and any live-network steps not executed.
```

## 7. Demo Script For Presenter

```text
Write a concise presenter script:
1. Create risk profile.
2. Run research.
3. Create proposal.
4. Run multi-agent debate.
5. Execute paper trade.
6. Monitor metrics and events.
Include fallback instructions and safety language.
```
