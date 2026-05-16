# DKRT — Context Broker Multiagent

## Objetivo

Sistema multiagentes para operar o FIWARE Orion Context Broker via CLI, SLM e MCP, com base RAG e guardrails.

## Stack

- Python 3.11+
- Typer + Rich (CLI)
- aiohttp (FIWARE async)
- Pydantic v2 (modelos)
- pytest + pytest-asyncio

## Comandos principais

```bash
dkrt query --type Sensor
dkrt ask "listar sensores"
dkrt orchestrate "consultar temperatura"
dkrt serve --port 8000
```

## Segurança

Saídas de codegen passam por detecção PII e validação JSON Schema antes de aplicar arquivos no disco.
