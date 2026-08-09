"""CreateAgent — cria entidades no FIWARE Orion."""

from context_broker_multiagent.agents.base import BaseAgent
from context_broker_multiagent.models.messages import AgentMessage, AgentResponse
from context_broker_multiagent.models.ngsi import NgsiEntity
from context_broker_multiagent.services.fiware_client import FiwareClient


class CreateAgent(BaseAgent):
    name = "create"

    def __init__(self, client: FiwareClient | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._client = client or FiwareClient()

    async def process(self, message: AgentMessage) -> AgentResponse:
        intent = message.metadata.get("chat_intent", {})
        entity_data = message.metadata.get("entity")

        if entity_data:
            entity = NgsiEntity.model_validate(entity_data)
        else:
            entity_type = intent.get("entity_type") or "Sensor"
            entity_id = intent.get("entity_id") or f"{entity_type}:new"
            attrs: dict = {}
            attr_name = intent.get("attribute")
            if attr_name:
                attrs[attr_name] = {"type": "Float", "value": 0.0}
            else:
                attrs["status"] = {"type": "Text", "value": "active"}
            entity = NgsiEntity(id=entity_id, type=entity_type, attrs=attrs)

        try:
            result = await self._client.create_entity(entity)
            return AgentResponse(
                agent_name=self.name,
                success=True,
                message=f"Entidade {entity.id} criada",
                data={"entity": result},
            )
        except Exception as exc:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message=f"Falha ao criar: {exc}",
            )
