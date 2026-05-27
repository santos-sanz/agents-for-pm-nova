from typer.testing import CliRunner

from hyper_demo.cli import app


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
