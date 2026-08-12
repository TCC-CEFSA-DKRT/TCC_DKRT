"""RouteAgent — classifica intenção e papéis dos agentes."""

from context_broker_agent.agents.base import BaseAgent
from context_broker_agent.models.messages import AgentMessage, AgentResponse


class RouteAgent(BaseAgent):
    name = "route"

    async def process(self, message: AgentMessage) -> AgentResponse:
        text = message.content.lower()
        intent = message.metadata.get("intent", "query")

        if any(w in text for w in ("criar", "provision", "cadastrar", "inserir")):
            intent = "provision"
        elif any(w in text for w in ("inscrever", "subscribe", "avisar", "notificar")):
            intent = "subscribe"
        elif any(w in text for w in ("analisar", "resumir", "analyze")):
            intent = "analyze"

        roles = {
            "query": ["query", "analyze"],
            "provision": ["provision", "route"],
            "subscribe": ["subscribe", "route"],
            "analyze": ["analyze", "query"],
        }
        active = roles.get(intent, ["query", "route", "provision", "subscribe", "analyze"])

        return AgentResponse(
            agent_name=self.name,
            success=True,
            message=f"Intenção classificada: {intent}",
            data={"intent": intent, "active_agents": active},
        )
