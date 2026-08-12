---
name: dkrt-tcc-codegen
description: >-
  Orquestra o pipeline completo DKRT (ingestão RAG, inferência com rewrite/HyDE/rerank,
  guardrails PII+schema) para gerar código Python/FIWARE no TCC. Use ao implementar
  features no context_broker_agent, CLI, agentes ou integração Orion.
---

# DKRT — Geração de código (pipeline completo)

## Visão

```
Pedido → Inferência (rewrite, HyDE, rerank) → JSON codegen → Guardrails → Aplicar files[]
```

Documentação base deve ter passado pela **ingestão** (`dkrt-knowledge-ingestion`).

## Workflow

### 1. Recuperar contexto

Seguir skill **dkrt-rag-inference**:

- Reescrever query
- Buscar top 20 → rerank top 5 chunks `big`
- Citar em `references[]` no JSON final

### 2. Planejar

Preencher `plan[]` com passos verificáveis (ex.: "adicionar método em FiwareClient", "teste pytest").

### 3. Gerar JSON (não arquivos soltos)

```json
{
  "intent": "query",
  "plan": ["..."],
  "files": [{ "path": "src/...", "action": "update", "content": "..." }],
  "references": [{ "chunk_id": "...", "source_file": "..." }],
  "guardrails": { "pii_passed": false, "schema_passed": false }
}
```

### 4. Guardrails

Seguir skill **dkrt-code-guardrails** — scripts em `scripts/rag/`.

### 5. Aplicar

Somente após validação OK: escrever arquivos listados em `files`.

## Convenções de código

- Python 3.11+, type hints, docstrings Google
- Async para I/O (FIWARE)
- Pacote: `src/context_broker_agent/`

## Prompts globais

- [prompts/rules.md](../../../prompts/rules.md)
- [prompts/code_generation.md](../../../prompts/code_generation.md)
- [prompts/intro.md](../../../prompts/intro.md)

## Skills relacionadas

| Fase | Skill |
|------|-------|
| Ingestão | `dkrt-knowledge-ingestion` |
| Inferência | `dkrt-rag-inference` |
| Segurança | `dkrt-code-guardrails` |
