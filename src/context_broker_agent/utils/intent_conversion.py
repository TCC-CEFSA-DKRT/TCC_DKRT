"""Conversao SlmInterpretation -> ChatIntent (ADR-0001).

Usado por qualquer ponto de entrada que ainda interpreta via
SLMService.interpret_query() e precisa despachar pelo IntentRouter
(o unico despachante): cli.py (dkrt-tools ask/orchestrate), terminal/shell.py
(/orchestrate) e services/mcp_server.py (dkrt_orchestrate).
"""

from context_broker_agent.models.intent import ChatIntent
from context_broker_agent.models.ngsi import SlmInterpretation

# operacoes que existem em SlmInterpretation.intent mas nao sao operacoes
# roteaveis no IntentRouter: "analyze" e pos-processamento (ADR-0009), "route"
# nao e uma acao em si. Caem em "query" como padrao seguro.
_ROUTABLE_OPERATIONS = ("query", "create", "update", "list", "delete", "subscribe")
_NON_ROUTABLE_FALLBACK = "query"


def to_chat_intent(interpretation: SlmInterpretation, text: str) -> ChatIntent:
    """Converte a saida do SLMService.interpret_query() em ChatIntent, o
    formato que o IntentRouter entende."""
    operation = (
        interpretation.intent
        if interpretation.intent in _ROUTABLE_OPERATIONS
        else _NON_ROUTABLE_FALLBACK
    )

    entity_type = None
    entity_id = None
    ngsi_q = None
    if interpretation.ngsi_query:
        entity_type = interpretation.ngsi_query.type
        entity_id = interpretation.ngsi_query.id
        ngsi_q = interpretation.ngsi_query.q
    if interpretation.entity:
        entity_type = entity_type or interpretation.entity.type
        entity_id = entity_id or interpretation.entity.id

    source = interpretation.source if interpretation.source in ("ollama", "llama_cpp", "heuristic") else "heuristic"

    return ChatIntent(
        operation=operation,
        entity_type=entity_type or "Sensor",
        entity_id=entity_id,
        ngsi_q=ngsi_q,
        source=source,
        raw_text=text,
    )