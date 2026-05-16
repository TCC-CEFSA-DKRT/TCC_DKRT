# Fase 11 — Entrega e avaliação do TCC

| Campo | Valor |
|-------|-------|
| **Objetivo** | Consolidar documentação acadêmica, demonstração funcional, métricas e defesa alinhadas aos objetivos do DKRT. |
| **Duração estimada** | 3–4 semanas |
| **Status** | Planejada |
| **Dependências** | [Fase 10](fase-10-testes-integracao-deploy.md) |

---

## 1. Contexto

Esta fase fecha o ciclo iniciado na [Fase 0](fase-00-planejamento-e-escopo.md): transformar o repositório técnico em **produto acadêmico** avaliável pela banca.

## 2. Produtos de entrega

| Produto | Descrição |
|---------|-----------|
| **Monografia / artigo** | Problema, fundamentação Python, arquitetura, RAG, resultados |
| **Repositório** | Código, testes, docs, diagramas versionados |
| **Apresentação** | Slides com fluxo multiagente + demo CLI |
| **Vídeo demo (opcional)** | 5–10 min: Orion + `dkrt ask` + MCP |

## 3. Estrutura sugerida da monografia

1. Introdução e problema (Context Broker + barreira de uso).
2. Fundamentação teórica (IoT, FIWARE, multiagentes, SLM, MCP, RAG).
3. Metodologia (fases 0–11 deste documento).
4. Arquitetura e implementação (diagramas do `docs/`).
5. Avaliação experimental (latência, precisão RAG, casos de uso).
6. Considerações finais e trabalhos futuros.

## 4. Roteiro de demonstração (banca)

| Min | Atividade |
|-----|-----------|
| 0–2 | Contexto: Orion + NGSI-v2 |
| 2–5 | Arquitetura multiagente (diagrama orquestrador) |
| 5–8 | `dkrt query --type Sensor` com Orion rodando |
| 8–12 | `dkrt ask "consultar sensores..."` (SLM + orquestração) |
| 12–15 | MCP: `tools/list` / chamada de ferramenta |
| 15–18 | Guardrails + pipeline RAG (slides, não obrigatório live) |
| 18–20 | Perguntas |

## 5. Checklist de entrega

### Documentação

- [ ] README atualizado com todas as fases concluídas marcadas.
- [ ] `docs/fases/` com status final de cada fase.
- [ ] `docs/entrega/` com versão final do texto (pdf).
- [ ] Diagramas exportados em alta resolução.

### Software

- [ ] Tag de versão no Git (`v0.1.0` ou superior).
- [ ] Testes automatizados documentados.
- [ ] `.env.example` sem segredos.

### Avaliação

- [ ] Tabela de requisitos R1–R8 × implementado (sim/parcial/não).
- [ ] Discussão limitações (GIL, latência vs Node — README §3).
- [ ] Trabalhos futuros: UI web, NGSI-LD, fine-tuning SLM.

## 6. Critérios de sucesso acadêmico

| Critério | Evidência |
|----------|-----------|
| Objetivo multiagente atingido | Demo orquestração + diagramas |
| Integração FIWARE | Consulta real ao Orion |
| IA / NL | Comando `ask` funcional |
| MCP | Servidor respondendo ferramentas |
| Rigour técnico | Testes + guardrails documentados |

## 7. Cronograma reverso (exemplo)

| Marco | Data (ajustar) |
|-------|----------------|
| Feature freeze | T-4 semanas |
| Texto completo | T-2 semanas |
| Ensaio defesa | T-1 semana |
| Entrega oficial | T |

## 8. Artefatos do repositório para citar na bibliografia

- README principal (análise Python).
- `docs/entrega/pre_projeto_tcc.md`.
- Código: `src/context_broker_multiagent/`.
- Pipeline IA: `prompts/`, `.cursor/skills/`.

## 9. Trabalhos futuros (seção padrão)

- Interface web para operadores IoT.
- Indexação vetorial em produção com reranker dedicado.
- Suporte NGSI-LD e broker Scorpio.
- Agentes adicionais (governança, QoS, histórico QuantumLeap).

## 10. Referências cruzadas

- [Índice de fases](README.md)
- [README do projeto](../../README.md)
- [Pré-projeto](../entrega/pre_projeto_tcc.md)
