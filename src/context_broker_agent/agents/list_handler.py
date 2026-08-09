"""ListAgent — listagem de entidades por tipo NGSI-v2."""

from context_broker_multiagent.agents.base import BaseAgent
from context_broker_multiagent.models.messages import AgentMessage, AgentResponse
from context_broker_multiagent.models.ngsi import NgsiQueryParams
from context_broker_multiagent.services.fiware_client import FiwareClient


class ListAgent(BaseAgent):
    name = "list"

    def __init__(self, client: FiwareClient | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._client = client or FiwareClient()

    async def process(self, message: AgentMessage) -> AgentResponse:
        intent = message.metadata.get("chat_intent", {})
        params_data = message.metadata.get("ngsi_query", {})
        if params_data:
            params = NgsiQueryParams.model_validate(params_data)
        else:
            entity_type = intent.get("entity_type") or message.metadata.get("entity_type", "Sensor")
            limit = intent.get("limit", 50)
            params = NgsiQueryParams(type=entity_type, limit=limit)
        entity_type = params.type or "Sensor"
        try:
            entities = await self._client.query_entities(params)
            return AgentResponse(
                agent_name=self.name,
                success=True,
                message=f"Listadas {len(entities)} entidade(s) tipo {entity_type}",
                data={"entities": entities, "entity_type": entity_type},
            )
        except Exception as exc:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message=f"Falha ao listar: {exc}",
            )
