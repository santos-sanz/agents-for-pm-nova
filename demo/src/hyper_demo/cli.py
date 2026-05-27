from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from hyper_demo.adapters.anthropic_managed import ManagedAgentResearchClient
from hyper_demo.adapters.hyperliquid import ExecutionBlocked, HyperliquidTestnetAdapter
from hyper_demo.api import setup_check
from hyper_demo.config import get_settings
from hyper_demo.models import (
    DemoRun,
    LeverageTolerance,
    ProposalRequest,
    RiskProfileInput,
    RunEvent,
)
from hyper_demo.services.market import MarketDataClient
from hyper_demo.services.metrics import compute_portfolio_metrics
from hyper_demo.services.proposals import build_trade_plan
from hyper_demo.services.risk import build_investor_profile
from hyper_demo.storage import JsonStore

app = typer.Typer(help="Hyperliquid testnet investment agent demo CLI.")
console = Console()
ROOT = Path(__file__).resolve().parents[2]


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
    console.print(table)
    for warning in check.warnings:
        console.print(f"[yellow]warning:[/] {warning}")


@app.command("profile")
def profile_command(
    horizon_days: Annotated[int, typer.Option("--horizon-days")] = 30,
    max_drawdown_pct: Annotated[float, typer.Option("--max-drawdown-pct")] = 8.0,
    leverage_tolerance: Annotated[
        LeverageTolerance, typer.Option("--leverage")
    ] = LeverageTolerance.low,
    asset_preference: Annotated[str, typer.Option("--asset")] = "BTC",
    capital_at_risk_usdc: Annotated[float, typer.Option("--capital-at-risk-usdc")] = 100.0,
    stop_loss_pct: Annotated[float, typer.Option("--stop-loss-pct")] = 4.0,
) -> None:
    inputs = RiskProfileInput(
        horizon_days=horizon_days,
        max_drawdown_pct=max_drawdown_pct,
        leverage_tolerance=leverage_tolerance,
        asset_preference=asset_preference,
        capital_at_risk_usdc=capital_at_risk_usdc,
        stop_loss_pct=stop_loss_pct,
    )
    profile = build_investor_profile(inputs)
    JsonStore(get_settings()).save("profiles", profile)
    console.print(Panel(profile.summary, title=f"Risk Profile {profile.id}"))
    console.print_json(profile.model_dump_json(indent=2))


@app.command("research")
def research_command(
    asset: Annotated[str, typer.Option("--asset")] = "BTC",
    profile_id: Annotated[str | None, typer.Option("--profile-id")] = None,
) -> None:
    store = JsonStore(get_settings())
    profile = store.get("profiles", profile_id) if profile_id else store.latest("profiles")
    report = asyncio.run(
        ManagedAgentResearchClient(get_settings()).research(asset.upper(), profile)
    )
    store.save("research", report)
    console.print(Panel(report.thesis, title=f"Research {report.id}"))
    console.print_json(report.model_dump_json(indent=2))


@app.command("propose")
def propose_command(
    asset: Annotated[str, typer.Option("--asset")] = "BTC",
    profile_id: Annotated[str | None, typer.Option("--profile-id")] = None,
    research_id: Annotated[str | None, typer.Option("--research-id")] = None,
) -> None:
    store = JsonStore(get_settings())
    profile = store.get("profiles", profile_id) if profile_id else store.latest("profiles")
    if not profile:
        profile = build_investor_profile(RiskProfileInput(asset_preference=asset))
        store.save("profiles", profile)
    research = store.get("research", research_id) if research_id else store.latest("research")
    plan = build_trade_plan(
        ProposalRequest(
            asset=asset,
            profile_id=profile.id,
            research_id=research.id if research else None,
        ),
        profile,
        research,
        MarketDataClient(get_settings()),
    )
    store.save("plans", plan)
    console.print(Panel(plan.rationale, title=f"Trade Plan {plan.id}"))
    console.print_json(plan.model_dump_json(indent=2))


@app.command("execute")
def execute_command(
    plan: Annotated[str, typer.Option("--plan")],
    confirm: Annotated[bool, typer.Option("--confirm")] = False,
) -> None:
    store = JsonStore(get_settings())
    trade_plan = store.get("plans", plan)
    if not trade_plan:
        raise typer.BadParameter(f"Plan not found: {plan}")
    try:
        order = HyperliquidTestnetAdapter(get_settings()).execute_plan(trade_plan, confirm)
    except ExecutionBlocked as exc:
        console.print(f"[red]blocked:[/] {exc}")
        raise typer.Exit(code=1) from exc
    store.save("orders", order)
    run = DemoRun(
        profile_id=trade_plan.profile_id,
        research_id=trade_plan.research_id,
        plan_id=trade_plan.id,
        order_id=order.id,
        status="executed",
    )
    store.save("runs", run)
    store.append_event(
        RunEvent(run_id=run.id, message="CLI submitted Hyperliquid testnet order set.")
    )
    console.print_json(
        json.dumps(
            {
                "run": run.model_dump(mode="json"),
                "order": order.model_dump(mode="json"),
            }
        )
    )


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


@app.command("replay")
def replay_command(fixture: Annotated[str, typer.Option("--fixture")] = "fallback") -> None:
    fixture_path = ROOT / "fixtures" / f"{fixture}.json"
    if not fixture_path.exists():
        raise typer.BadParameter(f"Fixture not found: {fixture}")
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    store = JsonStore(get_settings())
    saved = []
    for collection, model_name in [
        ("profiles", "profile"),
        ("research", "research"),
        ("plans", "plan"),
        ("orders", "order"),
        ("runs", "run"),
    ]:
        if model_name in payload:
            model = JsonStore.collections[collection].model_validate(payload[model_name])
            store.save(collection, model)
            saved.append(f"{model_name}: {model.id}")
    for event in payload.get("events", []):
        store.append_event(RunEvent.model_validate(event))
    console.print(Panel("\n".join(saved), title=f"Loaded fixture: {fixture}"))


if __name__ == "__main__":
    app()
