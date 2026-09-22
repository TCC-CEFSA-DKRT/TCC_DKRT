# Fase 10 — Testes, integração e deploy

| Campo | Valor |
|-------|-------|
| **Objetivo** | Validar o sistema de ponta a ponta, automatizar testes e preparar distribuição reproduzível (demo + instalação). |
| **Duração estimada** | 2–3 semanas |
| **Status** | Planejada |
| **Dependências** | Fases 4, 5, 6, 7, 9 |

---

## 1. Contexto

Requisitos **R5–R7**: latência aceitável, concorrência async, instalação simples. Esta fase consolida **qualidade de engenharia** antes da entrega acadêmica.

## 2. Pirâmide de testes

| Nível | Escopo | Ferramenta |
|-------|--------|------------|
| Unitário | Agentes, orquestrador, parsers SLM | pytest + pytest-asyncio |
| Integração | FiwareClient com Orion Docker | pytest (marker `integration`) |
| Smoke CLI | Comandos `dkrt` | CliRunner / subprocess |
| Guardrails | PII + schema | scripts em `scripts/rag/` |
| MCP | `/health`, `tools/list` | httpx / aiohttp client |

## 3. Cobertura mínima alvo

| Módulo | Meta indicativa |
|--------|-----------------|
| `orchestrator` | Cenários ok, partial, timeout |
| `agents/query` | Com mock FIWARE |
| `fiware_client` | Retry, validação id, mock HTTP |
| `slm_service` | Heurística sempre; phi-2 opcional |

## 4. Ambiente de integração

```yaml
# docker-compose.yml (a criar)
# - orion
# - mongo (dependência Orion)
# seed: entidades Sensor de exemplo
```

Documentar portas e tempo de warmup no README.

## 5. Entregáveis

- [ ] Suite `pytest` com ≥ 15 testes.
- [ ] `docker-compose.yml` para Orion de demonstração.
- [ ] Script `scripts/run_tests.sh` ou equivalente Windows.
- [ ] GitHub Actions (opcional): lint + pytest sem integração.
- [ ] Medição de latência documentada (tabela na monografia).

## 6. Atividades

| # | Atividade |
|---|-----------|
| 10.1 | Expandir `tests/` conforme módulos implementados |
| 10.2 | Marker `@pytest.mark.integration` para testes com Orion |
| 10.3 | Benchmark simples: N consultas async paralelas |
| 10.4 | Empacotamento `pip install -e .` e comando `dkrt` |
| 10.5 | Checklist de release para defesa (versão, tag, README) |
| 10.6 | Executar guardrails em CI |

## 7. Critérios de conclusão

- [ ] `pytest` verde no modo padrão (sem Orion).
- [ ] Demo gravada: CLI + Orion + um comando `ask`.
- [ ] README com seção “Testes e Orion local” completa.
- [ ] Requisito R6 demonstrado (ex.: 10 requisições paralelas sem deadlock).

## 8. Deploy / distribuição

| Canal | Descrição |
|-------|-----------|
| PyPI (opcional) | Não obrigatório para TCC |
| Repositório Git | Fonte principal |
| Release GitHub | Tag `v0.1.0` com artefatos de documentação |

## 9. Métricas sugeridas (monografia)

- Tempo médio de orquestração (5 agentes, mock).
- Tempo `query_entities` com Orion local (p50, p95).
- Taxa de falha com retry habilitado.

## 10. Próxima fase

→ [Fase 11 — Entrega TCC](fase-11-entrega-e-avaliacao-tcc.md)

## 11. Referências

- README §3.2 (benchmarks I/O)
- README §7 (concorrência multiagentes)
- `tests/test_orchestrator.py` (existente)
