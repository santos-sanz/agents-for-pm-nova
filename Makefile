SHELL := /bin/bash

SLIDEV_HOST ?= 127.0.0.1
SLIDEV_PORT ?= 3030
DEMO_HOST ?= 127.0.0.1
DEMO_PORT ?= 8001
WORKSHOP_HOST ?= $(DEMO_HOST)
WORKSHOP_PORT ?= 8123
WORKSHOP_ANTHROPIC_WORKSPACE_ID ?= wrkspc_01Ja4EK3nFQXQqKUgf8dcLu7
WORKSHOP_HYPERLIQUID_ALLOWED_ASSETS ?= xyz:CL,xyz:BRENTOIL,xyz:GOLD,xyz:SILVER,xyz:SP500,flx:USA100,xyz:COPPER,vntl:WHEAT,xyz:NATGAS,BTC

.PHONY: help install presentation demo workshop dev build test lint validate

help:
	@printf "Available targets:\n"
	@printf "  make install       Install root npm deps and demo uv deps\n"
	@printf "  make presentation  Start the Slidev presentation on %s:%s\n" "$(SLIDEV_HOST)" "$(SLIDEV_PORT)"
	@printf "  make demo          Start the FastAPI demo on %s:%s\n" "$(DEMO_HOST)" "$(DEMO_PORT)"
	@printf "  make workshop      Start the workshop readiness app on http://%s:%s/workshop\n" "$(WORKSHOP_HOST)" "$(WORKSHOP_PORT)"
	@printf "  make dev           Start presentation and demo together\n"
	@printf "  make build         Build the Slidev presentation\n"
	@printf "  make test          Run demo pytest suite\n"
	@printf "  make lint          Run demo ruff checks\n"
	@printf "  make validate      Run build, tests, and lint\n"

install:
	npm install
	cd demo && uv sync

presentation:
	npm run dev -- --host $(SLIDEV_HOST) --port $(SLIDEV_PORT)

demo:
	cd demo && uv run uvicorn hyper_demo.api:app --host $(DEMO_HOST) --port $(DEMO_PORT)

workshop:
	@printf "Workshop readiness app: http://%s:%s/workshop\n" "$(WORKSHOP_HOST)" "$(WORKSHOP_PORT)"
	@printf "Workshop Claude workspace: %s\n" "$(WORKSHOP_ANTHROPIC_WORKSPACE_ID)"
	@printf "Workshop tradeable assets: %s\n" "$(WORKSHOP_HYPERLIQUID_ALLOWED_ASSETS)"
	cd demo && WORKSHOP_ANTHROPIC_WORKSPACE_ID=$(WORKSHOP_ANTHROPIC_WORKSPACE_ID) WORKSHOP_HYPERLIQUID_ALLOWED_ASSETS=$(WORKSHOP_HYPERLIQUID_ALLOWED_ASSETS) uv run uvicorn hyper_demo.workshop:app --host $(WORKSHOP_HOST) --port $(WORKSHOP_PORT)

dev:
	@trap 'kill 0' EXIT; \
	(cd demo && uv run uvicorn hyper_demo.api:app --host $(DEMO_HOST) --port $(DEMO_PORT)) & \
	npm run dev -- --host $(SLIDEV_HOST) --port $(SLIDEV_PORT) & \
	wait

build:
	npm run build

test:
	cd demo && uv run pytest

lint:
	cd demo && uv run ruff check .

validate: build test lint
