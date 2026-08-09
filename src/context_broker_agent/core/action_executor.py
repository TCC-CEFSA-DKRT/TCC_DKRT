from context_broker_agent.models.messages import AgentMessage, AgentResponse
from context_broker_agent.agents.registry import MUTATION_OPERATIONS

class ActionExecutor:
    '''
    '''
    def __init__(self, registry, query_handler, slm_service, max-retries=2):
        self.registry = registry
        self.query_handler = query_handler
        self.slm_service = slm_service
        self.max_retries = max_retries

    async def  execute(self, operation: str, message: AgentMessage) -> AgentResponse:
        agent = self.registry[operation]()
        result = await agent.process(message)

        if operation not in MUTATION_OPERATIONS or not result.success:
            return result
        
        verified = await self.verify(operation, message, result)
        if verifield.ok:
            return result
        return await self.handler_error(operation, message, verified.diff)
