import pytest

from context_broker_multiagent.terminal.shell import DkrtTerminal


def test_parse_command():
    term = DkrtTerminal()
    name, args = term._parse_command("/query Sensor 10")
    assert name == "query"
    assert args == "Sensor 10"


def test_is_terminal_command():
    assert DkrtTerminal._is_terminal_command("/help")
    assert not DkrtTerminal._is_terminal_command("bom dia")


@pytest.mark.asyncio
async def test_dispatch_help_does_not_exit():
    term = DkrtTerminal()
    should_exit = await term._dispatch_command("/help")
    assert should_exit is False
