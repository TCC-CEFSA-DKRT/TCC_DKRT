"""Roteamento de ChatIntent para agentes especializados."""

from __future__ import annotations

import structlog

from context_broker_agent.agents.base import BaseAgent
from context_broker_agent.agents.create_handler import CreateHandler
from context_broker_agent.agents.delete_handler import DeleteHandler
from context_broker_agent.agents.list_handler import ListHandler
from context_broker_agent.agents.query_handler import QueryHandler
from context_broker_agent.agents.registry import MUTATION_OPERATIONS
from context_broker_agent.agents.subscribe_handler import SubscribeHandler
from context_broker_agent.agents.iot_provision_handler import IoTProvisionHandler
from context_broker_agent.agents.update_handler import UpdateHandler
from context_broker_agent.core.action_executor import ActionExecutor
from context_broker_agent.models.intent import ChatIntent
from context_broker_agent.models.messages import AgentMessage, AgentResponse
from context_broker_agent.services.fiware_client import FiwareClient
from context_broker_agent.utils.ngsi_filters import normalize_entity_type, normalize_ngsi_q

logger = structlog.get_logger(__name__)


class IntentRouter:
    """Mapeia operation → agente e executa de forma assíncrona.

    Operações mutáveis (ADR-0002) passam pelo ActionExecutor, que roda o loop
    de verificação/correção após a execução. Operações somente-leitura
    (query, list) são executadas direto, sem verificação (não fazem sentido
    verificar uma leitura).
    """

    def __init__(self, client: FiwareClient | None = None) -> None:
        fw = client or FiwareClient()
        self._client = fw
        self._agents: dict[str, BaseAgent] = {
            "query": QueryHandler(client=fw),
            "list": ListHandler(client=fw),
            "create": CreateHandler(client=fw),
            "update": UpdateHandler(client=fw),
            "delete": DeleteHandler(client=fw),
            "subscribe": SubscribeHandler(client=fw),
            "iot_provision": IoTProvisionHandler(),
        }
        # registry de FÁBRICAS (não instâncias) para o ActionExecutor: ele cria
        # uma instância nova a cada chamada de execute(), reaproveitando o
        # mesmo FiwareClient (fw) para não perder cache/config.
        action_registry = {
            "create": lambda: CreateHandler(client=fw),
            "update": lambda: UpdateHandler(client=fw),
            "delete": lambda: DeleteHandler(client=fw),
            "subscribe": lambda: SubscribeHandler(client=fw),
            "iot_provision": lambda: IoTProvisionHandler(),
        }
        self._action_executor = ActionExecutor(
            registry=action_registry,
            query_handler=self._agents["query"],
            slm_service=None,
        )

    @property
    def agent_names(self) -> list[str]:
        return list(self._agents.keys())

    def agent_status(self) -> dict[str, str]:
        return {name: "ready" for name in self._agents}

    def _build_metadata(self, intent: ChatIntent, user_text: str) -> dict:
        entity_type = normalize_entity_type(intent.entity_type)
        ngsi_q = normalize_ngsi_q(intent.ngsi_q, user_text)
        ngsi_query: dict = {"limit": 20}
        if entity_type:
            ngsi_query["type"] = entity_type
        if intent.entity_id:
            ngsi_query["id"] = intent.entity_id
        if intent.attribute:
            ngsi_query["attrs"] = intent.attribute
        if ngsi_q:
            ngsi_query["q"] = ngsi_q

        meta: dict = {
            "chat_intent": intent.model_dump(),
            "intent": intent.operation,
            "entity_type": intent.entity_type,
            "entity_id": intent.entity_id,
            "ngsi_query": ngsi_query,
        }

        if intent.operation == "create" and intent.entity_type:
            eid = intent.entity_id or f"{intent.entity_type}:new"
            attrs: dict = {}
            if intent.attribute:
                attrs[intent.attribute] = {"type": "Float", "value": 0.0}
            else:
                attrs["status"] = {"type": "Text", "value": "active"}
            meta["entity"] = {"id": eid, "type": intent.entity_type, "attrs": attrs}

        if intent.operation == "iot_provision" and intent.entity_type:
            device_id = intent.entity_id or f"{intent.entity_type.lower()}-new"
            meta["device"] = {
                "device_id": device_id,
                "entity_name": f"{intent.entity_type}:{device_id}",
                "entity_type": intent.entity_type,
                "attributes": (
                    [{"object_id": "v", "name": intent.attribute, "type": "Number"}]
                    if intent.attribute
                    else []
                ),
            }

        return meta

    async def route(self, intent: ChatIntent, user_text: str) -> AgentResponse:
        """Executa o agente correspondente à operação.

        Mutações (create/update/delete/subscribe) passam pelo ActionExecutor
        (verificação pós-execução, ADR-0002). Leituras (query/list) executam
        direto via execute_with_timeout.
        """
        agent = self._agents.get(intent.operation)
        if not agent:
            return AgentResponse(
                agent_name="router",
                success=False,
                message=f"Operação não suportada: {intent.operation}",
            )

        message = AgentMessage(content=user_text, metadata=self._build_metadata(intent, user_text))
        logger.debug("intent_route", operation=intent.operation, agent=agent.name)

        if intent.operation in MUTATION_OPERATIONS:
            return await self._action_executor.execute(intent.operation, message)
        return await agent.execute_with_timeout(message)