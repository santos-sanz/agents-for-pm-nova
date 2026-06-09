# AGENTS.md - agents-for-pm-nova

## Remote Synchronization

- Before making any repository change, make sure the local branches are updated from the remote.
- Treat the remote repository as the source of truth.
- The first command to run before editing files is:

```bash
git pull
```

## Repository Structure

- Root: Slidev presentation and talk materials managed with npm/Node.js.
- `docs/`: Markdown source for storyline, speaker profile, research, demo script, handout, rebuild notes, and supporting PM/agent material.
- `demo/`: Python 3.12+ Hyperliquid trading-agent demo managed with `uv`.
- `demo/src/hyper_demo/static/`: Browser UI assets served by the FastAPI demo.

Generated outputs and local runtime files are not source of truth: `dist/`, `.slidev/`, `node_modules/`, `.npm-cache/`, `demo/.venv/`, `demo/.demo_state/`, `demo/.ruff_cache/`, and `demo/.pytest_cache/`.

## Root Slidev App

### Commands

```bash
npm install
npm run dev
npm run build
npm run export
```

- `npm run dev`: opens the Slidev deck locally.
- `npm run build`: validates the static Slidev site.
- `npm run export`: exports `dist/agents-for-pm-nova.pdf`; requires Playwright Chromium.

### Key Files

- `slides.md`: presentation source and speaker notes.
- `style.css`: global Slidev styling.
- `package.json` / `package-lock.json`: Node dependency and script definitions.
- `README.md`: public overview of the talk and repository.
- `docs/storyline.md`: 60-minute narrative, timing, and transitions.
- `docs/demo-script.md`: demo runbook and fallback path.
- `docs/demo-rebuild.md`: instructions to recreate the demo.
- `docs/research.md`, `docs/speaker-profile.md`, `docs/handout.md`, `docs/testing-pyramid.md`, `docs/coding-agent-prompts.md`: supporting talk material.

## Demo App

### Setup

```bash
cd demo
uv sync
npm install
cp .env.example .env
uv run demo setup-check
```

Fill `demo/.env` with Anthropic and Hyperliquid credentials. Use only a Hyperliquid API/agent wallet private key. Never use or store the main wallet private key in this project.

### CLI Commands

```bash
uv run demo analyze --asset BTC
uv run demo scan
uv run demo execute --plan <id> --confirm
uv run demo wallet
```

- `analyze`: reactive single-asset analysis.
- `scan`: proactive watchlist scan.
- `execute`: submit a stored plan after guardrail checks and confirmation.
- `wallet`: show configured wallet/account state.

### Browser UI

```bash
cd demo
uv run uvicorn hyper_demo.api:app --reload
```

Open `http://127.0.0.1:8000`. The FastAPI app serves the static UI from `demo/src/hyper_demo/static/`.

### Architecture Notes

- Entrypoints: `demo/src/hyper_demo/cli.py` for Typer CLI and `demo/src/hyper_demo/api.py` for FastAPI.
- Config: `demo/src/hyper_demo/config.py` loads `.env` / `.env.local` through Pydantic Settings.
- Models: `demo/src/hyper_demo/models.py`.
- Persistence: `demo/src/hyper_demo/storage.py` writes JSON state under `demo/.demo_state/`.
- Agent adapter: `demo/src/hyper_demo/adapters/anthropic_managed.py`.
- Exchange adapter: `demo/src/hyper_demo/adapters/hyperliquid.py`.
- Domain services: `demo/src/hyper_demo/services/market.py`, `metrics.py`, `monitoring.py`, `proposals.py`, `risk.py`, and `trading_agent.py`.
- Tests: `demo/tests/`; fixtures in `demo/tests/conftest.py` mock network calls.

## Runtime Modes And Safety

- Default mode is `testnet`.
- `testnet`: auto-execution is allowed only when credentials and guardrails pass.
- `prodnet`: guarded; requires browser UI confirmation and explicit environment enablement.
- Browser runtime settings live in `demo/.demo_state/runtime.json`.
- CLI settings come from environment variables and `.env` files.
- `HYPERLIQUID_MAINNET_ENABLED=true` is required before prodnet execution can be enabled.
- Testnet/prodnet URL allowlists are enforced internally; do not add arbitrary exchange URLs.

Never commit `.env`, `.env.*` except `.env.example`, `.demo_state/`, private keys, credentials, browser data, cookies, local caches, or generated dependency/build directories.

## Validation

Run root validation from the repository root:

```bash
npm run build
```

Run demo validation from `demo/`:

```bash
uv run pytest
uv run ruff check .
```

For focused checks:

```bash
uv run pytest tests/test_config.py::test_settings_accept_testnet_urls
```

## Change Guidelines

- Treat Markdown files, `slides.md`, `style.css`, and `demo/src/` as primary source.
- Keep generated build output out of reviews unless the user explicitly asks for exported artifacts.
- Preserve the demo's trading safety model: testnet by default, prodnet only with explicit environment enablement and UI confirmation.
- Prefer small, focused edits and run the relevant validation command for the area changed.
