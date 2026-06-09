SHELL := /bin/bash

SLIDEV_HOST ?= 127.0.0.1
SLIDEV_PORT ?= 3030
DEMO_HOST ?= 127.0.0.1
DEMO_PORT ?= 8001

.PHONY: help install presentation demo dev build test lint validate

help:
	@printf "Available targets:\n"
	@printf "  make install       Install root npm deps and demo uv deps\n"
	@printf "  make presentation  Start the Slidev presentation on %s:%s\n" "$(SLIDEV_HOST)" "$(SLIDEV_PORT)"
	@printf "  make demo          Start the FastAPI demo on %s:%s\n" "$(DEMO_HOST)" "$(DEMO_PORT)"
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
