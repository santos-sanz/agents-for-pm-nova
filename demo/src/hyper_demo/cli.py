from __future__ import annotations

import asyncio
import json
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from hyper_demo.adapters.hyperliquid import ExecutionBlocked
from hyper_demo.api import setup_check
from hyper_demo.config import get_settings, settings_for_runtime
from hyper_demo.services.metrics import compute_portfolio_metrics
from hyper_demo.services.trading_agent import (
    analyze_trade,
    manual_execute_trade,
    run_proactive_scan,
)
from hyper_demo.storage import JsonStore

app = typer.Typer(help="HyperClaude trading agent demo CLI.")
console = Console()


@app.command("setup-check")
def setup_check_command() -> None:
    check = setup_check(get_settings())
    table = Table(title="Demo Setup")
    table.add_column("Item")
    table.add_column("Value")
    table.add_row("Trading mode", check.trading_mode)
    table.add_row("Requires confirmation", str(check.require_confirmation))
    table.add_row("Anthropic configured", str(check.anthropic_configured))
    table.add_row("Hyperliquid configured", str(check.hyperliquid_configured))
    table.add_row("Hyperliquid HTTP", check.hyperliquid_base_url)
    table.add_row("Hyperliquid WS", check.hyperliquid_ws_url)
    table.add_row("Hyperliquid environment", check.hyperliquid_environment)
    table.add_row("Mainnet enabled", str(check.hyperliquid_mainnet_enabled))
    table.add_row("Max order USDC", str(check.hyperliquid_max_order_usdc))
    table.add_row("Allowed assets", ", ".join(check.hyperliquid_allowed_assets))
    table.add_row("Account address", check.hyperliquid_account_address or "missing")
    console.print(table)
    for warning in check.warnings:
        console.print(f"[yellow]warning:[/] {warning}")


@app.command("analyze")
def analyze_command(
    asset: Annotated[str, typer.Option("--asset")] = "BTC",
    context: Annotated[str | None, typer.Option("--context")] = None,
) -> None:
    store = JsonStore(get_settings())
    runtime = store.runtime_settings()
    result = asyncio.run(analyze_trade(asset, runtime, store, context))
    console.print(Panel(result.plan.rationale, title=f"Trade Idea {result.plan.id}"))
    console.print_json(result.plan.model_dump_json(indent=2))


@app.command("scan")
def scan_command() -> None:
    store = JsonStore(get_settings())
    runtime = store.runtime_settings()
    result = asyncio.run(run_proactive_scan(runtime, store))
    console.print(Panel(result.plan.rationale, title=f"Proactive Trade Idea {result.plan.id}"))
    console.print_json(result.plan.model_dump_json(indent=2))


@app.command("execute")
def execute_command(
    plan: Annotated[str, typer.Option("--plan")],
    confirm: Annotated[bool, typer.Option("--confirm")] = False,
    confirmation_phrase: Annotated[
        str | None,
        typer.Option(
            "--confirmation-phrase",
            help="Deprecated; order execution now uses explicit confirmation only.",
        ),
    ] = None,
) -> None:
    store = JsonStore(get_settings())
    trade_plan = store.get("plans", plan)
    if not trade_plan:
        raise typer.BadParameter(f"Plan not found: {plan}")
    runtime = store.runtime_settings()
    try:
        result = manual_execute_trade(
            trade_plan,
            runtime,
            store,
            confirmed=confirm,
            confirmation_phrase=confirmation_phrase,
        )
    except ExecutionBlocked as exc:
        console.print(f"[red]blocked:[/] {exc}")
        raise typer.Exit(code=1) from exc
    console.print_json(
        json.dumps(
            {
                "plan": result.plan.model_dump(mode="json"),
                "order_id": result.order_id,
                "run_id": result.run_id,
            }
        )
    )


@app.command("wallet")
def wallet_command() -> None:
    runtime = JsonStore(get_settings()).runtime_settings()
    try:
        from hyper_demo.adapters.hyperliquid import HyperliquidAdapter

        wallet = HyperliquidAdapter(settings_for_runtime(runtime)).wallet_state()
    except ExecutionBlocked as exc:
        console.print(f"[red]blocked:[/] {exc}")
        raise typer.Exit(code=1) from exc
    console.print_json(json.dumps(wallet))


@app.command("monitor")
def monitor_command(run: Annotated[str, typer.Option("--run")]) -> None:
    store = JsonStore(get_settings())
    demo_run = store.get("runs", run)
    if not demo_run:
        raise typer.BadParameter(f"Run not found: {run}")
    events = store.events_for_run(run)
    metrics = compute_portfolio_metrics(
        equity_curve=[10_000, 10_040, 10_015, 10_120, 10_090, 10_180],
        btc_benchmark=[100, 101.2, 100.4, 102.8, 101.9, 103.1],
        eth_benchmark=[100, 100.7, 99.8, 101.6, 101.1, 102.0],
        positions=[],
    )
    console.print(Panel(f"Run status: {demo_run.status}", title=demo_run.id))
    for event in events:
        console.print(f"[{event.level}] {event.created_at.isoformat()} {event.message}")
    console.print_json(metrics.model_dump_json(indent=2))


if __name__ == "__main__":
    app()
