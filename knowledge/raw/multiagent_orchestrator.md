# Orquestrador multiagentes DKRT

## Visão

O `MultiAgentOrchestrator` coordena agentes especializados em paralelo com `asyncio.gather`.

## Agentes

| Agente | Função |
|--------|--------|
| RouteDispatcher | Classifica intenção |
| QueryHandler | Consulta NGSI-v2 |
| SubscribeHandler | Planeja subscrições |
| AnalyzeHandler | Resume resultados |

## Contratos

- `AgentMessage`: content, metadata, correlation_id
- `AgentResponse`: agent_name, success, message, data, elapsed_ms
- `OrchestrationResult`: status ok | partial | error

## Timeout

Cada agente usa `execute_with_timeout()` com limite configurável via `AGENT_TIMEOUT_SECONDS`.
