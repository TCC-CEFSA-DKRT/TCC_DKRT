"""ActionExecutor — loop de verificação/correção para operações mutáveis (ADR-0002)."""

from context_broker_agent.agents.registry import MUTATION_OPERATIONS
from context_broker_agent.models.messages import AgentMessage, AgentResponse


class ActionExecutor:
    """Executa um handler e, se a operação for mutável, verifica o resultado
    (re-consulta + comparação) antes de considerar concluído."""

    def __init__(self, registry, query_handler, slm_service, max_retries=2):
        self.registry = registry
        self.query_handler = query_handler
        self.slm_service = slm_service
        self.max_retries = max_retries

    async def execute(self, operation: str, message: AgentMessage) -> AgentResponse:
        agent = self.registry[operation]()
        result = await agent.execute_with_timeout(message)

        if operation not in MUTATION_OPERATIONS or not result.success:
            return result

        # agent (a instância já criada acima) é quem sabe verificar a SI MESMA —
        # por isso chamamos agent.verify(...), não self.verify(...) nem
        # ActionExecutor.verify(...): o método pertence ao handler, não ao executor.
        verified = await agent.verify(message, result)
        if verified.ok:
            return result
        return await agent.handle_error(message, verified.diff)