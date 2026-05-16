from typer.testing import CliRunner

from context_broker_multiagent.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "query" in result.stdout


def test_cli_agents():
    result = runner.invoke(app, ["agents"])
    assert result.exit_code == 0
    assert "route" in result.stdout
