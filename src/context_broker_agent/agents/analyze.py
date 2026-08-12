"""AnalyzeAgent — resume dados retornados por outros agentes."""

from context_broker_agent.agents.base import BaseAgent
from context_broker_agent.models.messages import AgentMessage, AgentResponse


class AnalyzeAgent(BaseAgent):
    name = "analyze"

    async def process(self, message: AgentMessage) -> AgentResponse:
        entities = message.metadata.get("entities", [])
        count = len(entities) if isinstance(entities, list) else 0

        types: dict[str, int] = {}
        for ent in entities:
            if isinstance(ent, dict):
                t = ent.get("type", "Unknown")
                types[t] = types.get(t, 0) + 1

        summary = {
            "total_entities": count,
            "by_type": types,
            "sample_ids": [e.get("id") for e in entities[:5] if isinstance(e, dict)],
        }

        return AgentResponse(
            agent_name=self.name,
            success=True,
            message=f"Análise concluída: {count} entidade(s)",
            data={"summary": summary},
        )
