from unittest.mock import AsyncMock, patch

import pytest

from context_broker_multiagent.agents.base import BaseAgent
from context_broker_multiagent.core.intent_router import IntentRouter
from context_broker_multiagent.models.intent import ChatIntent
from context_broker_multiagent.models.messages import AgentMessage, AgentResponse


class StubAgent(BaseAgent):
    name = "stub"

    def __init__(self, response: AgentResponse, **kwargs):
        super().__init__(**kwargs)
        self._response = response

    async def process(self, message: AgentMessage) -> AgentResponse:
        return self._response


@pytest.mark.asyncio
async def test_route_query_operation():
    stub = StubAgent(
        AgentResponse(agent_name="query", success=True, message="ok", data={"entities": []}),
    )
    router = IntentRouter()
    router._agents["query"] = stub

    intent = ChatIntent(operation="query", entity_type="Sensor", confidence=0.9)
    resp = await router.route(intent, "listar sensores")
    assert resp.success is True


@pytest.mark.asyncio
async def test_route_unknown_operation():
    router = IntentRouter()
    intent = ChatIntent(operation="query", confidence=0.5)
    router._agents = {}
    resp = await router.route(intent, "teste")
    assert resp.success is False
