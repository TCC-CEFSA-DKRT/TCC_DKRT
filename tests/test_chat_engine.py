from unittest.mock import AsyncMock, MagicMock

import pytest

from context_broker_agent.core.chat_engine import ChatEngine
from context_broker_agent.models.intent import ChatIntent, ChatTurnAnalysis
from context_broker_agent.models.messages import AgentResponse
from context_broker_agent.utils.history_manager import HistoryManager


@pytest.mark.asyncio
async def test_greeting_does_not_call_router():
    slm = MagicMock()
    slm.analyze_chat_turn = AsyncMock(
        return_value=ChatTurnAnalysis(
            response_type="conversation",
            assistant_message="Bom dia! Como posso ajudar?",
            confidence=0.9,
            source="heuristic",
        ),
    )
    router = MagicMock()
    router.route = AsyncMock()

    engine = ChatEngine(slm=slm, router=router, history=HistoryManager(), console=MagicMock())
    result = await engine.process_user_input("Bom dia")

    router.route.assert_not_called()
    assert "Bom dia" in result.summary
    assert result.analysis.response_type == "conversation"


@pytest.mark.asyncio
async def test_fiware_request_calls_router():
    slm = MagicMock()
    slm.analyze_chat_turn = AsyncMock(
        return_value=ChatTurnAnalysis(
            response_type="fiware",
            assistant_message="Buscando sensores.",
            operation="list",
            entity_type="Sensor",
            confidence=0.9,
            source="heuristic",
        ),
    )
    router = MagicMock()
    router.route = AsyncMock(
        return_value=AgentResponse(
            agent_name="list",
            success=True,
            message="2 entidades",
            data={"entities": [{"id": "Sensor:001", "type": "Sensor"}]},
        ),
    )

    engine = ChatEngine(slm=slm, router=router, history=HistoryManager(), console=MagicMock())
    await engine.process_user_input("listar sensores do lab 64")

    router.route.assert_called_once()
    call_intent: ChatIntent = router.route.call_args[0][0]
    assert call_intent.operation == "list"


@pytest.mark.asyncio
async def test_clarify_does_not_call_router():
    slm = MagicMock()
    slm.analyze_chat_turn = AsyncMock(
        return_value=ChatTurnAnalysis(
            response_type="clarify",
            assistant_message="Qual o ID da entidade?",
            operation="update",
            missing_fields=["entity_id"],
            source="heuristic",
        ),
    )
    router = MagicMock()
    router.route = AsyncMock()

    engine = ChatEngine(slm=slm, router=router, history=HistoryManager(), console=MagicMock())
    await engine.process_user_input("atualizar sensor")

    router.route.assert_not_called()
    assert engine.history.get_pending() is not None


def test_heuristic_greeting():
    from context_broker_agent.services.slm_service import SLMService

    analysis = SLMService()._analyze_chat_heuristic("Ola", None, None)
    assert analysis.response_type == "conversation"
    assert analysis.assistant_message
