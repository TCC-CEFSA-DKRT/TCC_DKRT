# Fase 5 — Interface CLI (Typer + Rich)

| Campo | Valor |
|-------|-------|
| **Objetivo** | Expor o sistema via linha de comando profissional: consultas diretas, linguagem natural e orquestração multiagente. |
| **Duração estimada** | 2–3 semanas |
| **Status** | Planejada |
| **Dependências** | [Fase 4](fase-04-integracao-fiware-ngsi.md) (parcial: pode mockar FIWARE) |

---

## 1. Contexto

O README justifica **Typer** (type hints, Rich, async). O requisito **R2** exige CLI para usuários finais com instalação simples (`pip install -e .`).

## 2. Comandos planejados

| Comando | Função |
|---------|--------|
| `dkrt query` | Consulta NGSI direta (`--type`, `--id`, `--limit`) |
| `dkrt ask` | Linguagem natural + SLM + orquestração |
| `dkrt orchestrate` | Orquestrador explícito |
| `dkrt agents` | Lista agentes registrados |
| `dkrt serve` | Servidor MCP (Fase 7) |

## 3. UX (Rich)

- Tabelas de respostas por agente.
- JSON formatado para entidades NGSI.
- Mensagens de erro coloridas (`typer.secho` / Rich).
- Help automático a partir de docstrings.

## 4. Estado atual

| Item | Situação |
|------|----------|
| CLI com `argparse` e JSON | `src/.../cli.py` — evoluir para Typer |
| Entry point `context-broker-agent` | `pyproject.toml` |
| Comando `dkrt` unificado | Planejado |

## 5. Entregáveis

- [ ] `cli.py` com Typer + suporte async (`asyncio.run`).
- [ ] Comandos documentados no README.
- [ ] Exemplos de uso na defesa do TCC.
- [ ] Tempo de startup aceitável (ver README §3.2 Typer ~22 ms overhead).

## 6. Atividades

| # | Atividade |
|---|-----------|
| 5.1 | Migrar parser para Typer |
| 5.2 | Implementar `query` com `FiwareClient` |
| 5.3 | Implementar `ask` integrando SLM (Fase 6) |
| 5.4 | Implementar `agents` e `orchestrate` |
| 5.5 | Carregar `.env` com `python-dotenv` |
| 5.6 | Testes de smoke da CLI (opcional: Typer CliRunner) |

## 7. Critérios de conclusão

- [ ] `dkrt --help` lista todos os comandos.
- [ ] Fluxo demo: `dkrt ask "consultar sensores"` sem crash.
- [ ] Saída legível em terminal Windows e Linux.

## 8. Exemplo alvo (README §5.2)

```python
@app.command()
def query(
    entity_type: str = typer.Option("Sensor", "--type", "-t"),
    limit: int = typer.Option(20, "--limit", "-l"),
):
    """Consulta entidades no Context Broker."""
```

## 9. Próxima fase

→ [Fase 6 — SLM](fase-06-slm-linguagem-natural.md) (integração com `ask`)

## 10. Referências

- README §5 (Ecossistema CLI)
- `docs/fases/fase-04-integracao-fiware-ngsi.md`
