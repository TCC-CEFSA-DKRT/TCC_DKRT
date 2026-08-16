from context_broker_agent.agents.query_handler import QueryHandler
from context_broker_agent.agents.list_handler import ListHandler
from context_broker_agent.agents.create_handler import CreateHandler
from context_broker_agent.agents.update_handler import UpdateHandler
from context_broker_agent.agents.delete_handler import DeleteHandler
from context_broker_agent.agents.subscribe_handler import SubscribeHandler
from context_broker_agent.agents.iot_provision_handler import IoTProvisionHandler

AGENT_REGISTRY: dict[str, type] = {
    "query": QueryHandler,
    "list": ListHandler,
    "create": CreateHandler,
    "update": UpdateHandler,
    "delete": DeleteHandler,
    "subscribe": SubscribeHandler,
    "iot_provision": IoTProvisionHandler,
}

# operações que passam pelo loop de verificação/correção (ADR-0002)
MUTATION_OPERATIONS = {"create", "update", "delete", "subscribe", "iot_provision"}