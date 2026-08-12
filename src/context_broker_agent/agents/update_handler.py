"""UpdateHandler — atualiza atributos de entidades NGSI-v2."""

from context_broker_agent.agents.base import BaseAgent
from context_broker_agent.models.messages import AgentMessage, AgentResponse
from context_broker_agent.services.fiware_client import FiwareClient


class UpdateHandler(BaseAgent):
    name = "update"

    def __init__(self, client: FiwareClient | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._client = client or FiwareClient()

    async def process(self, message: AgentMessage) -> AgentResponse:
        intent = message.metadata.get("chat_intent", {})
        entity_id = intent.get("entity_id") or message.metadata.get("entity_id")
        attr = intent.get("attribute") or "temperature"
        value = message.metadata.get("attr_value", 25.0)

        if not entity_id:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message="Informe entity_id (ex.: Sensor:001) para atualizar",
            )

        attrs = {attr: {"type": "Float", "value": value}}
        try:
            await self._client.update_attributes(entity_id, attrs)
            return AgentResponse(
                agent_name=self.name,
                success=True,
                message=f"Atributo {attr} atualizado em {entity_id}",
                data={"entity_id": entity_id, "attrs": attrs},
            )
        except Exception as exc:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message=f"Falha ao atualizar: {exc}",
            )
