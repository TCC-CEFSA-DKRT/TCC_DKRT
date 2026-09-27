# Fase 0 — Planejamento e escopo

| Campo | Valor |
|-------|-------|
| **Objetivo** | Definir o problema, requisitos, restrições e justificativa técnica do TCC DKRT. |
| **Duração estimada** | 2–4 semanas (atividade de acompanhamento) |
| **Status** | Concluída |
| **Dependências** | Nenhuma |

---

## 1. Contexto

O **FIWARE Orion Context Broker** é o núcleo de muitas soluções IoT/smart cities. A API **NGSI-v2** é poderosa, porém verbosa. O TCC propõe um **sistema multiagentes** em Python que:

- Orquestra tarefas especializadas (consulta, subscrição, provisionamento, análise).
- Oferece **CLI** para usuários técnicos.
- Usa **SLM** para linguagem natural.
- Expõe capacidades via **MCP** para ferramentas de IA.

A escolha de **Python** está documentada no README (ecossistema FIWARE, IA, asyncio, Typer).

## 2. Escopo

### Dentro do escopo

- Multiagentes com orquestrador central.
- Integração NGSI-v2 com Orion.
- CLI local (Typer + Rich).
- SLM para interpretação de pedidos (ex.: microsoft/phi-2).
- Servidor MCP com ferramentas do domínio.
- Pipeline RAG (ingestão + inferência + guardrails) para apoiar desenvolvimento assistido por IA.
- Documentação acadêmica e diagramas de arquitetura.

### Fora do escopo (v1)

- Interface web completa para usuário final.
- Substituição do Orion por outro broker.
- Fine-tuning pesado de LLM em produção.
- Alta disponibilidade em cluster Kubernetes (pode ser trabalho futuro).

## 3. Requisitos (extraídos do README)

| ID | Requisito |
|----|-----------|
| R1 | Arquitetura multiagentes para consulta e manipulação no Context Broker |
| R2 | CLI para instalação local (e evolução online) |
| R3 | SLM para processamento de linguagem natural |
| R4 | Protocolos NGSI-v2 e MCP |
| R5 | Baixa latência em consultas I/O-bound |
| R6 | Múltiplas requisições simultâneas (async) |
| R7 | Facilidade de instalação e distribuição |
| R8 | Manutenibilidade do código multiagente |

## 4. Restrições

- Predominância de operações **I/O-bound** (rede com Orion).
- Uso de Python 3.11+ e práticas async onde aplicável.
- Conformidade com documentação oficial NGSI-v2.

## 5. Entregáveis

| Entregável | Local |
|------------|-------|
| Pré-projeto / proposta | `docs/entrega/pre_projeto_tcc.md` (.pdf) |
| Análise comparativa de linguagens | `README.md` §3 |
| Diagramas (orquestrador, sequência, fluxo) | `docs/*.png`, `docs/*.svg` |
| Matriz de decisão Python | `README.md` §9 |

## 6. Atividades realizadas

- [x] Definição do título e objetivos do TCC.
- [x] Levantamento de bibliotecas (filip, Typer, Transformers).
- [x] Diagramas de arquitetura e sequência.
- [x] Documentação da justificativa Python vs Node.js vs Go.

## 7. Critérios de conclusão

- [x] Pré-projeto aprovado na orientação.
- [x] Requisitos R1–R8 documentados.
- [x] Diagramas versionados no repositório.

## 8. Próxima fase

→ [Fase 1 — Fundamentos e ambiente](fase-01-fundamentos-e-ambiente.md)

## 9. Referências

- [README do projeto](../../README.md)
- [FIWARE Orion](https://fiware-orion.readthedocs.io/)
