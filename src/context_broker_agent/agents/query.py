"""QueryAgent — consultas NGSI-v2 via FiwareClient."""

from context_broker_multiagent.agents.base import BaseAgent
from context_broker_multiagent.models.messages import AgentMessage, AgentResponse
from context_broker_multiagent.models.ngsi import NgsiQueryParams
from context_broker_multiagent.services.fiware_client import FiwareClient


class QueryAgent(BaseAgent):
    name = "query"

    def __init__(self, client: FiwareClient | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._client = client or FiwareClient()

    async def process(self, message: AgentMessage) -> AgentResponse:
        params_data = message.metadata.get("ngsi_query", {})
        params = NgsiQueryParams.model_validate(params_data) if params_data else NgsiQueryParams(type="Sensor")

        try:
            entities = await self._client.query_entities(params)
            return AgentResponse(
                agent_name=self.name,
                success=True,
                message=f"{len(entities)} entidade(s) recuperada(s)",
                data={"entities": entities, "query": params.model_dump()},
            )
        except Exception as exc:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message=f"Falha na consulta NGSI: {exc}",
                data={"query": params.model_dump()},
            )
