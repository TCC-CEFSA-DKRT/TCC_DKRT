"""Roteamento de ChatIntent para agentes especializados."""

from __future__ import annotations

import structlog

from context_broker_agent.agents.base import BaseAgent
from context_broker_agent.agents.create_handler import CreateHandler
from context_broker_agent.agents.delete_handler import DeleteHandler
from context_broker_agent.agents.list_handler import ListHandler
from context_broker_agent.agents.query import QueryAgent
from context_broker_agent.agents.update_handler import UpdateHandler
from context_broker_agent.models.intent import ChatIntent
from context_broker_agent.models.messages import AgentMessage, AgentResponse
from context_broker_agent.services.fiware_client import FiwareClient
from context_broker_agent.utils.ngsi_filters import normalize_entity_type, normalize_ngsi_q

logger = structlog.get_logger(__name__)


class IntentRouter:
    """Mapeia operation → agente e executa de forma assíncrona."""

    def __init__(self, client: FiwareClient | None = None) -> None:
        fw = client or FiwareClient()
        self._client = fw
        self._agents: dict[str, BaseAgent] = {
            "query": QueryAgent(client=fw),
            "list": ListHandler(client=fw),
            "create": CreateHandler(client=fw),
            "update": UpdateHandler(client=fw),
            "delete": DeleteHandler(client=fw),
        }

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

        return meta

    async def route(self, intent: ChatIntent, user_text: str) -> AgentResponse:
        """Executa o agente correspondente à operação."""
        agent = self._agents.get(intent.operation)
        if not agent:
            return AgentResponse(
                agent_name="router",
                success=False,
                message=f"Operação não suportada: {intent.operation}",
            )

        message = AgentMessage(content=user_text, metadata=self._build_metadata(intent, user_text))
        logger.debug("intent_route", operation=intent.operation, agent=agent.name)
        return await agent.execute_with_timeout(message)
