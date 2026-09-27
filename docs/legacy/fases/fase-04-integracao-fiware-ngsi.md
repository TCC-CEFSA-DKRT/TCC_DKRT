# Fase 4 — Integração FIWARE (NGSI-v2)

| Campo | Valor |
|-------|-------|
| **Objetivo** | Conectar o sistema ao Orion Context Broker com cliente assíncrono, operações CRUD NGSI-v2 e modelos validados. |
| **Duração estimada** | 3–4 semanas |
| **Status** | Planejada |
| **Dependências** | [Fase 3](fase-03-arquitetura-multiagentes.md) |

---

## 1. Contexto

O README destaca o ecossistema Python para FIWARE (**filip**, clientes NGSI, Pydantic). Esta fase materializa o requisito **R4 (NGSI-v2)** e habilita QueryAgent e ProvisionAgent com dados reais.

## 2. Escopo NGSI-v2 (v1 do TCC)

| Operação | Endpoint | Agente principal |
|----------|----------|------------------|
| Listar/consultar entidades | `GET /v2/entities` | QueryAgent |
| Obter entidade | `GET /v2/entities/{entityId}` | QueryAgent |
| Criar entidade | `POST /v2/entities` | ProvisionAgent |
| Atualizar atributos | `PATCH /v2/entities/{id}/attrs` | ProvisionAgent |
| Subscrição (planejamento) | `POST /v2/subscriptions` | SubscribeAgent |

## 3. Componentes a implementar

| Componente | Descrição |
|------------|-----------|
| `FiwareClient` | aiohttp, timeout, retry, cache TTL |
| `models/ngsi.py` | `NgsiEntity`, `NgsiQueryParams`, atributos |
| Variáveis de ambiente | `FIWARE_BROKER_URL`, `FIWARE_API_KEY` |
| Integração filip (opcional) | Avaliar vs cliente próprio leve |

## 4. Ambiente Orion local

```bash
# Exemplo: stack FIWARE Lab / Docker Compose oficial
# URL padrão: http://localhost:1026
```

Documentar no README o `docker-compose` usado na defesa do TCC.

## 5. Entregáveis

| Entregável | Critério |
|------------|----------|
| Cliente assíncrono | 4 métodos principais testados com mock |
| Teste de integração (opcional) | Query real com Orion em CI/local |
| Agentes usando cliente | Query + Provision sem duplicar HTTP |
| `.env.example` | URLs e chaves documentadas |

## 6. Atividades

| # | Atividade |
|---|-----------|
| 4.1 | Implementar `FiwareClient` com retry exponencial |
| 4.2 | Validadores de `entity_id` (formato `Tipo:id`) |
| 4.3 | Conectar QueryAgent e ProvisionAgent |
| 4.4 | Subir Orion e popular entidades `Sensor` de teste |
| 4.5 | Medir latência de consulta (requisito R5) |
| 4.6 | Documentar cabeçalhos Fiware-Service |

## 7. Critérios de conclusão

- [ ] Consulta `type=Sensor` retorna JSON válido do Orion.
- [ ] Criação de entidade de teste idempotente ou com cleanup.
- [ ] Erros HTTP mapeados para mensagens claras na CLI.
- [ ] Nenhum segredo versionado no Git.

## 8. Métricas para monografia

| Métrica | Alvo indicativo |
|---------|-----------------|
| Latência média `query_entities` | Documentar vs README §3.2 (I/O-bound) |
| Taxa de sucesso após retry | ≥ 95% em rede estável |

## 9. Riscos

| Risco | Mitigação |
|-------|-----------|
| Orion indisponível na demo | Docker + script de seed |
| Versão NGSI diferente | Fixar NGSI-v2 na documentação |

## 10. Próxima fase

→ [Fase 5 — CLI](fase-05-interface-cli.md)

## 11. Referências

- README §4 (Ecossistema FIWARE)
- [Orion NGSI-v2 API](https://fiware-orion.readthedocs.io/en/master/)
