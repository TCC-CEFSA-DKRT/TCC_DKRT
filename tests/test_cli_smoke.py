from typer.testing import CliRunner

from context_broker_agent.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "query" in result.stdout


def test_cli_agents():
    result = runner.invoke(app, ["agents"])
    assert result.exit_code == 0
    # "route" não aparece mais: é fallback determinístico (ADR-0007), não uma
    # operação roteável do AGENT_REGISTRY (ADR-0001).
    assert "create" in result.stdout
    assert "subscribe" in result.stdout