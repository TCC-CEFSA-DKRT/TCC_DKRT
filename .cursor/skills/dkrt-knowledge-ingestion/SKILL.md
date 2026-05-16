---
name: dkrt-knowledge-ingestion
description: >-
  Prepara a base de conhecimento DKRT com chunking híbrido, Small2Big e metadados
  antes de gerar código Python/FIWARE. Use ao indexar documentação, ingerir Markdown,
  criar chunks RAG, ou quando o usuário mencionar ingestão, embedding ou "cérebro" do projeto.
---

# DKRT — Fase de Ingestão

## Quando aplicar

Antes da IA gerar código para o TCC (FIWARE, multiagentes, CLI).

## Procedimento

1. Colocar docs em `knowledge/raw/` (Markdown).
2. Configurar `knowledge/manifest.yaml` a partir de `knowledge/manifest.example.yaml`.
3. Executar chunking híbrido:

```bash
python scripts/rag/chunk_hybrid.py knowledge/raw/ --out knowledge/chunks/
```

4. Garantir cada registro JSONL tenha:
   - `small` — frase curta para busca
   - `big` — contexto completo para o LLM
   - `metadata` — `source_file`, `version`, `category`, `section`

## Regras (não negociáveis)

- **Chunking híbrido**: cabeçalhos → parágrafos → tamanho (não só caracteres).
- **Small2Big**: nunca enviar só `small` ao modelo gerador.
- **Metadados**: sempre filtrar por `category` / `version` na busca.
- Não fragmentar blocos de código NGSI nem tabelas.

## Referências do projeto

- [prompts/ingestion/chunking.md](../../../prompts/ingestion/chunking.md)
- [prompts/ingestion/small2big.md](../../../prompts/ingestion/small2big.md)
- [prompts/ingestion/metadata.md](../../../prompts/ingestion/metadata.md)
