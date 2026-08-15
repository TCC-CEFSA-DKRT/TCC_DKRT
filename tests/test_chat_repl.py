"""Testes do terminal interativo (DkrtTerminal, terminal/shell.py + commands.py).

Reescrito porque a classe antiga (InteractiveChat, repl/chat.py) foi
substituida pelo terminal atual antes desta refatoracao (repl/chat.py hoje e
so um atalho de compatibilidade que chama terminal.shell.run()).
"""

import os

import pytest

os.environ.setdefault("SLM_ENABLED", "false")

from context_broker_agent.terminal.shell import DkrtTerminal


@pytest.mark.asyncio
async def test_slash_clear_and_history():
    terminal = DkrtTerminal()
    terminal.engine.history.add("oi", "ola", None)
    assert len(terminal.engine.history.list_turns()) == 1

    should_exit = await terminal._dispatch_command("/clear")

    assert should_exit is False
    assert len(terminal.engine.history.list_turns()) == 0


@pytest.mark.asyncio
async def test_slash_exit_returns_true():
    terminal = DkrtTerminal()

    should_exit = await terminal._dispatch_command("/exit")

    assert should_exit is True


@pytest.mark.asyncio
async def test_unknown_command_does_not_exit():
    terminal = DkrtTerminal()

    should_exit = await terminal._dispatch_command("/naoexiste")

    assert should_exit is False


@pytest.mark.asyncio
async def test_command_aliases_resolve_to_canonical():
    """/q e /quit sao aliases de /exit (build_command_map, terminal/commands.py)."""
    terminal = DkrtTerminal()

    assert await terminal._dispatch_command("/q") is True
    assert await terminal._dispatch_command("/quit") is True