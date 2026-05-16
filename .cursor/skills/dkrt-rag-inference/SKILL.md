---
name: dkrt-rag-inference
description: >-
  Executa inferência RAG em tempo real para o DKRT: query rewriting, HyDE e reranking
  antes de gerar código FIWARE/Python. Use quando o usuário pedir implementação, explicação
  técnica, ou mencionar recuperação de contexto, busca semântica ou precisão de documentação.
---

# DKRT — Fase de Inferência

## Pipeline (ordem fixa)

1. **Query rewriting** — reescrever pedido para termos NGSI/Python/multiagent.
2. **Busca inicial** — top 20 chunks (vetorial + filtros de `metadata`).
3. **HyDE** (se pedido vago) — documento hipotético só para embedding; descartar na resposta.
4. **Reranking** — selecionar top 5 chunks `big` para o prompt.
5. Entregar contexto ao gerador.

## Query rewriting

Produzir JSON intermediário:

```json
{
  "original": "...",
  "rewritten_queries": ["...", "..."],
  "intent": "query"
}
```

Ver [prompts/inference/query-rewriting.md](../../../prompts/inference/query-rewriting.md).

## HyDE

Gerar parágrafo hipotético como se fosse doc oficial DKRT/FIWARE → embed → buscar chunks reais → usar só chunks reais no prompt.

Ver [prompts/inference/hyde.md](../../../prompts/inference/hyde.md).

## Reranking

- Entrada: 20 candidatos
- Saída: 5 chunks com `score` e `reason`
- Priorizar `trust_level: official` e exemplos HTTP/Python alinhados

Ver [prompts/inference/reranking.md](../../../prompts/inference/reranking.md).

## Checklist antes de codificar

- [ ] Intenção classificada
- [ ] Queries reescritas documentadas
- [ ] HyDE aplicado se necessário
- [ ] ≤ 5 chunks `big` no contexto
