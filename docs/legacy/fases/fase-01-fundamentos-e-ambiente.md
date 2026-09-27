# Fase 1 — Fundamentos e ambiente

| Campo | Valor |
|-------|-------|
| **Objetivo** | Estabelecer repositório, ambiente Python, estrutura de pacotes e primeira execução demonstrável. |
| **Duração estimada** | 1–2 semanas |
| **Status** | Em andamento |
| **Dependências** | [Fase 0](fase-00-planejamento-e-escopo.md) |

---

## 1. Contexto

Antes de FIWARE, SLM ou MCP, o projeto precisa de um **esqueleto executável**: pacote instalável, testes mínimos e convenções de código alinhadas ao README (type hints, async para I/O futuro).

## 2. Escopo técnico

- Python **3.11+** com `pyproject.toml`.
- Pacote `context_broker_agent` em `src/`.
- Entry point CLI inicial.
- `pytest` configurado.
- `.gitignore`, estrutura `docs/`, `tests/`.

## 3. Estrutura alvo do repositório

```
agent_multi_IA_context_broker/
├── src/context_broker_agent/
├── tests/
├── docs/
├── prompts/
├── .cursor/skills/
├── knowledge/
├── schemas/
├── scripts/rag/
└── pyproject.toml
```

## 4. Entregáveis

| Entregável | Critério de aceite |
|------------|-------------------|
| Pacote instalável | `pip install -e .` sem erro |
| CLI mínima | `python -m context_broker_agent.cli` executa |
| Teste unitário | `pytest` com ≥ 1 teste do orquestrador |
| Documentação de execução | README com comando de exemplo |

## 5. Atividades

| # | Atividade | Responsável |
|---|-----------|-------------|
| 1.1 | Criar `pyproject.toml` e metadados do projeto | Dev |
| 1.2 | Implementar orquestrador e agentes iniciais | Dev |
| 1.3 | CLI argparse/Typer básica | Dev |
| 1.4 | Configurar `pytest` e `pythonpath` | Dev |
| 1.5 | Documentar setup no README | Dev |

## 6. Estado atual no repositório

- [x] `src/context_broker_agent/` com `agents.py`, `cli.py`
- [x] `tests/test_orchestrator.py`
- [x] `pyproject.toml` com script `context-broker-agent`
- [ ] Padronizar layout completo (models/, services/, utils/) — evolução nas fases 3–5
- [ ] `requirements.txt` ou extras opcionais documentados

## 7. Ambiente de desenvolvimento

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest tests/ -v
python -m context_broker_agent.cli "consultar sensores no Context Broker"
```

## 8. Critérios de conclusão

- [x] Repositório Git com histórico coerente.
- [x] Primeira demonstração multiagente (orquestrador + 2 agentes).
- [ ] Checklist de dependências de produção (aiohttp, pydantic, etc.) na Fase 4+.
- [ ] CI local ou GitHub Actions (opcional, recomendado na Fase 10).

## 9. Riscos

| Risco | Mitigação |
|-------|-----------|
| Versão Python inconsistente na equipe | Fixar `>=3.11` no `pyproject.toml` |
| Caminhos de import quebrados | Usar layout `src/` e `pip install -e .` |

## 10. Próxima fase

→ Paralelizar [Fase 2 — Base de conhecimento](fase-02-base-de-conhecimento-rag.md) e [Fase 3 — Multiagentes](fase-03-arquitetura-multiagentes.md)
