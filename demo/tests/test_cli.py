from typer.testing import CliRunner

from hyper_demo.cli import app


def test_cli_setup_check(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(app, ["setup-check"])
    assert result.exit_code == 0
    assert "Demo Setup" in result.output


def test_cli_analyze_creates_trade_idea(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "--asset", "BTC"])

    assert result.exit_code == 0
    assert "Trade Idea" in result.output


def test_cli_scan_creates_proactive_trade_idea(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    runner = CliRunner()
    result = runner.invoke(app, ["scan"])

    assert result.exit_code == 0
    assert "Proactive Trade Idea" in result.output


def test_cli_removed_legacy_commands(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DEMO_STATE_DIR", str(tmp_path))
    runner = CliRunner()

    for command in ["profile", "research", "propose", "skills", "debate", "replay"]:
        result = runner.invoke(app, [command])
        assert result.exit_code != 0
