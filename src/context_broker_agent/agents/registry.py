
AGENT_REGISTRY: dict[str, type] = {
    "query": QueryHandler,
    "list": ListHandler,
    "create": CreateHandler,
    "update": UpdateHandler,
    "delete": DeleteHandler,
    "subscribe": SubscribeHandler
}

# operações que passam pelo loop de verificação/correção (ADR-0002)
MUTATION_OPERATIONS = {"create", "update", "delete", "subscribe"}