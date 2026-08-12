# Referência — Ingestão DKRT

## Categorias sugeridas

| category | Conteúdo |
|----------|----------|
| `fiware` | NGSI-v2, Orion, entidades, subscrições |
| `python` | Código do pacote `context_broker_agent` |
| `multiagent` | Orquestrador, agentes, mensagens |
| `tcc` | Documentação acadêmica, diagramas |

## Formato JSONL (exemplo)

```json
{
  "chunk_id": "uuid",
  "parent_id": "fiware_ngsi::Query entities",
  "small": "Listar entidades NGSI-v2 por tipo Sensor",
  "big": "GET /v2/entities?type=Sensor...",
  "metadata": {
    "source_file": "fiware_ngsi_v2.md",
    "version": "2.0",
    "category": "fiware",
    "section": "Query entities",
    "language": "pt-BR"
  }
}
```
