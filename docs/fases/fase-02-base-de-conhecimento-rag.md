# Fase 2 — Base de conhecimento (ingestão RAG)

| Campo | Valor |
|-------|-------|
| **Objetivo** | Preparar o “cérebro” da IA: documentação FIWARE e do projeto indexável com chunking híbrido, Small2Big e metadados. |
| **Duração estimada** | 2–3 semanas |
| **Status** | Em andamento |
| **Dependências** | [Fase 1](fase-01-fundamentos-e-ambiente.md) |

---

## 1. Contexto

Antes de gerar código ou responder com precisão, o assistente precisa de **contexto recuperável**. Esta fase não é o produto final do TCC, mas **habilita** qualidade na Fase 8 (inferência) e no desenvolvimento com Cursor.

## 2. Conceitos aplicados

| Técnica | Descrição |
|---------|-----------|
| **Chunking híbrido** | Dividir por cabeçalhos → parágrafos → tamanho (com overlap), sem cortar código NGSI. |
| **Small2Big** | Indexar frase curta (`small`); recuperar parágrafo/seção completa (`big`). |
| **Metadados** | `source_file`, `version`, `category` para filtrar busca. |

## 3. Escopo

### Incluído

- Pasta `knowledge/raw/` com documentação Markdown.
- Script `scripts/rag/chunk_hybrid.py` → `knowledge/chunks/chunks.jsonl`.
- Manifesto `knowledge/manifest.example.yaml`.
- Prompts em `prompts/ingestion/`.
- Skill Cursor `dkrt-knowledge-ingestion`.

### Excluído (esta fase)

- Banco vetorial em produção (Pinecone, etc.) — pode ser prototipado na Fase 8.
- Ingestão automática de PDF sem conversão prévia para MD.

## 4. Fontes de documentação recomendadas

| Fonte | category | Prioridade |
|-------|----------|------------|
| NGSI-v2 Orion (entidades, query, subscribe) | `fiware` | Alta |
| README e diagramas do TCC | `tcc` | Alta |
| Código `context_broker_multiagent` | `python` | Média |
| Notas de multiagentes / orquestração | `multiagent` | Média |

## 5. Entregáveis

| Entregável | Caminho |
|------------|---------|
| Guia de chunking | `prompts/ingestion/chunking.md` |
| Guia Small2Big | `prompts/ingestion/small2big.md` |
| Guia metadados | `prompts/ingestion/metadata.md` |
| Chunks JSONL | `knowledge/chunks/chunks.jsonl` |
| ≥ 3 documentos em `knowledge/raw/` | — |

## 6. Atividades

| # | Atividade | Status |
|---|-----------|--------|
| 2.1 | Estruturar `knowledge/` e manifesto | [x] |
| 2.2 | Implementar `chunk_hybrid.py` | [x] |
| 2.3 | Copiar trechos oficiais NGSI-v2 para `knowledge/raw/` | [ ] |
| 2.4 | Gerar primeiro `chunks.jsonl` | [ ] |
| 2.5 | Validar que blocos HTTP/JSON não foram partidos | [ ] |
| 2.6 | Documentar pipeline em `prompts/README.md` | [x] |

## 7. Comandos

```bash
python scripts/rag/chunk_hybrid.py knowledge/raw/ --out knowledge/chunks/ --category fiware
```

## 8. Critérios de conclusão

- [ ] Corpus mínimo indexado (≥ 50 chunks úteis).
- [ ] Cada chunk com `small`, `big` e `metadata` completos.
- [ ] Revisão manual de 10 chunks aleatórios sem corte inválido.
- [x] Skill e prompts de ingestão versionados.

## 9. Métricas (opcional para monografia)

- Tamanho médio de `big` (caracteres).
- Distribuição por `category`.
- Taxa de chunks com bloco de código intacto (auditoria manual).

## 10. Próxima fase

→ [Fase 8 — Inferência RAG](fase-08-inferencia-rag-tempo-real.md) (após Fase 3 e documentação estável)

## 11. Referências

- `prompts/ingestion/`
- `.cursor/skills/dkrt-knowledge-ingestion/`
