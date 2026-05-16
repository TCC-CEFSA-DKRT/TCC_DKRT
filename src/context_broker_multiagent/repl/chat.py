"""Compatibilidade: dkrt chat → terminal externo."""

import typer

from context_broker_multiagent.terminal.shell import run as run_terminal


def chat_command() -> None:
    """Abre o terminal DKRT (mesmo que executar `dkrt`)."""
    from context_broker_multiagent.core.chat_engine import configure_quiet_logging

    configure_quiet_logging()
    run_terminal()


def register_chat_command(app: typer.Typer) -> None:
    app.command("chat")(chat_command)
