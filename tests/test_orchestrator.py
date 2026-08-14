import asyncio

import pytest

from context_broker_agent.agents.query import QueryHandler
from context_broker_agent.models.messages import OrchestrationStatus
from context_broker_agent.models.ngsi import NgsiQueryParams
from context_broker_agent.orchestrator import MultiAgentOrchestrator


class MockFiwareClient:
    async def query_entities(self, params: NgsiQueryParams):
        return [{"id": "Sensor:001", "type": params.type or "Sensor"}]

    async def create_entity(self, entity):
        return entity.model_dump()


@pytest.mark.asyncio
async def test_orchestration_ok():
    orch = MultiAgentOrchestrator(client=MockFiwareClient())
    result = await orch.orchestrate(
        "consultar sensores",
        metadata={"intent": "query", "ngsi_query": {"type": "Sensor", "limit": 5}},
    )
    assert result.status in (OrchestrationStatus.OK, OrchestrationStatus.PARTIAL)
    assert len(result.responses) >= 5
    names = {r.agent_name for r in result.responses}
    assert "route" in names
    assert "query" in names


@pytest.mark.asyncio
async def test_agent_timeout():
    class SlowAgent(QueryHandler):
        name = "slow"

        async def process(self, message):
            await asyncio.sleep(2)
            return await super().process(message)

    slow = SlowAgent(client=MockFiwareClient())
    slow.timeout_seconds = 0.01
    from context_broker_agent.models.messages import AgentMessage

    resp = await slow.execute_with_timeout(
        AgentMessage(content="x", metadata={"ngsi_query": {"type": "Sensor"}})
    )
    assert resp.success is False
    assert "Timeout" in resp.message


@pytest.mark.asyncio
async def test_route_intent_create():
    orch = MultiAgentOrchestrator(client=MockFiwareClient())
    result = await orch.orchestrate("criar dispositivo Device:99")
    route = next(r for r in result.responses if r.agent_name == "route")
    assert route.data.get("intent") == "create"
