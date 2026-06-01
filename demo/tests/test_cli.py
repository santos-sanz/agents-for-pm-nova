from typer.testing import CliRunner

from hyper_demo.cli import app
from hyper_demo.config import Settings
from hyper_demo.models import TradePlan
from hyper_demo.storage import JsonStore


def test_cli_setup_check(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(app, ["setup-check"])
    assert result.exit_code == 0
    assert "Demo Setup" in result.output


def test_cli_profile_and_replay(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    runner = CliRunner()
    profile = runner.invoke(app, ["profile", "--asset", "BTC"])
    assert profile.exit_code == 0
    assert "Risk Profile" in profile.output

    replay = runner.invoke(app, ["replay", "--fixture", "fallback"])
    assert replay.exit_code == 0
    assert "Loaded fixture" in replay.output


def test_cli_skills_and_debate(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    runner = CliRunner()

    skills = runner.invoke(app, ["skills"])
    assert skills.exit_code == 0
    assert "Investor Agent Skills" in skills.output

    debate = runner.invoke(app, ["debate", "--asset", "BTC"])
    assert debate.exit_code == 0
    assert "Multi-Agent Decision" in debate.output


def test_cli_paper_executes_latest_plan(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    store = JsonStore(Settings(DEMO_STATE_DIR=tmp_path))
    plan = TradePlan(
        asset="BTC",
        side="long",
        size_usdc=100,
        entry_price=100,
        stop_loss=95,
        take_profit=110,
        max_loss_usdc=5,
        rationale="test",
        invalidation_criteria=[],
    )
    store.save("plans", plan)

    runner = CliRunner()
    result = runner.invoke(app, ["paper", "--plan", plan.id, "--confirm"])

    assert result.exit_code == 0
    assert "paper-coinbase" in result.output
