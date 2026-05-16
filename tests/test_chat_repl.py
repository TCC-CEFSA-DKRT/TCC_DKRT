import pytest

from context_broker_multiagent.repl.chat import InteractiveChat


@pytest.mark.asyncio
async def test_slash_clear_and_history():
    chat = InteractiveChat()
    chat.engine.history.add("oi", "ola", None)
    assert len(chat.engine.history.list_turns()) == 1
    await chat._handle_slash("/clear")
    assert len(chat.engine.history.list_turns()) == 0


@pytest.mark.asyncio
async def test_slash_exit_returns_true():
    chat = InteractiveChat()
    should_exit = await chat._handle_slash("/exit")
    assert should_exit is True
