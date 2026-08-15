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
        """Executa e verifica, tentando novamente até max_retries vezes se a
        verificação falhar (ADR-0002, passo 4 — 'corrigir automaticamente').

        Cada tentativa reexecuta a operação inteira (process + verify), não só
        a re-consulta: uma falha de verificação pode significar que a escrita
        original não colou (ex.: latência de propagação), então repetir a
        própria ação é a correção determinística mais simples e segura.
        Esgotadas as tentativas, cai em handle_error() (pausa e reporta).
        """
        agent = None
        result = None
        verified = None

        for attempt in range(1, self.max_retries + 1):
            agent = self.registry[operation]()
            result = await agent.execute_with_timeout(message)

            if operation not in MUTATION_OPERATIONS:
                return result

            if not result.success:
                if attempt < self.max_retries:
                    continue
                return result  # esgotou tentativas; falha é da própria execução, não de verificação

            verified = await agent.verify(message, result)
            if verified.ok:
                return result

            if attempt < self.max_retries:
                continue  # divergência: tenta de novo (correção automática)

        # esgotou max_retries com verificação sempre divergente -> pausa e reporta
        return await agent.handle_error(message, verified.diff)