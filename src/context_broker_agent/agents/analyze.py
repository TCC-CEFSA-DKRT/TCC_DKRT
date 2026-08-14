"""AnalyzeHandler — pós-processamento de apresentação (ADR-0009).

Nunca executa ação nem verifica resultado — só recebe um AgentResponse já
pronto (de query/list, ou já verificado pelo ActionExecutor no caso de
create/update/delete) e o traduz para uma mensagem legível ao usuário.
"""

from context_broker_agent.agents.base import BaseAgent
from context_broker_agent.models.messages import AgentMessage, AgentResponse


class AnalyzeHandler(BaseAgent):
    name = "analyze"

    async def process(self, message: AgentMessage) -> AgentResponse:
        operation = message.metadata.get("operation", "query")
        source: AgentResponse | None = message.metadata.get("agent_response")

        if source is None:
            return AgentResponse(
                agent_name=self.name,
                success=False,
                message="Nada para analisar (nenhum resultado recebido).",
            )

        # erro não é "reformatado" — passa direto, preservando a mensagem original
        # (ex.: chat_engine detecta "Cannot connect" para dar uma dica ao usuário)
        if not source.success:
            return source

        if operation in ("query", "list"):
            return self._summarize_query(source)

        return self._summarize_mutation(source)

    @staticmethod
    def _summarize_query(source: AgentResponse) -> AgentResponse:
        entities = source.data.get("entities", [])
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
            agent_name="analyze",
            success=True,
            message=f"{count} entidade(s) encontrada(s)" if count else "Nenhuma entidade encontrada",
            data={**source.data, "summary": summary},
        )

    @staticmethod
    def _summarize_mutation(source: AgentResponse) -> AgentResponse:
        """create/update/delete: source já foi verificado pelo ActionExecutor
        (ADR-0002) — aqui só formatamos a confirmação, não re-verificamos nada."""
        return AgentResponse(
            agent_name="analyze",
            success=True,
            message=f"✓ {source.message}",
            data=source.data,
        )