"""SubscribeAgent — planejamento de subscrições NGSI-v2."""

from context_broker_agent.agents.base import BaseAgent
from context_broker_agent.models.messages import AgentMessage, AgentResponse


class SubscribeAgent(BaseAgent):
    name = "subscribe"

    async def process(self, message: AgentMessage) -> AgentResponse:
        entity_type = message.metadata.get("ngsi_query", {}).get("type", "Sensor")
        condition = message.metadata.get("condition", "temperature>25")

        plan = {
            "description": {
                "entities": [{"id": ".*", "type": entity_type}],
                "attrs": ["temperature"],
                "condition": {"attrs": condition},
            },
            "notification": {
                "http": {"url": "http://localhost:5050/notify"},
                "attrs": ["temperature"],
            },
        }

        return AgentResponse(
            agent_name=self.name,
            success=True,
            message="Plano de subscrição NGSI-v2 gerado (não enviado ao Orion)",
            data={"subscription_plan": plan},
        )
