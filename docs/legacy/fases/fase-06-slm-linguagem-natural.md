# Fase 6 — SLM e linguagem natural

| Campo | Valor |
|-------|-------|
| **Objetivo** | Interpretar pedidos em português (ou inglês) e mapear para estruturas NGSI e intenções de agentes, usando SLM (microsoft/phi-2) com fallback heurístico. |
| **Duração estimada** | 3–4 semanas |
| **Status** | Planejada |
| **Dependências** | [Fase 3](fase-03-arquitetura-multiagentes.md), [Fase 5](fase-05-interface-cli.md) (comando `ask`) |

---

## 1. Contexto

Requisito **R3**: suporte a SLMs. O README cita **Transformers (Hugging Face)** e exemplo com `microsoft/phi-2` para converter linguagem natural em consulta NGSI.

## 2. Escopo

| Incluído | Excluído (v1) |
|----------|----------------|
| Serviço `SLMService.interpret_query()` | Fine-tuning completo do modelo |
| Mapeamento para `NgsiQueryParams` + `intent` | LLM cloud proprietário obrigatório |
| Modo heurístico sem GPU (`SLM_ENABLED=false`) | RAG dentro do modelo (usa Fase 8 separada) |
| Integração com `dkrt ask` | Multi-idioma avançado |

## 3. Fluxo

```mermaid
flowchart LR
    NL[Texto natural] --> SLM[SLMService]
    SLM -->|phi-2| JSON[Estrutura NGSI + intent]
    SLM -->|heurística| JSON
    JSON --> O[Orchestrator]
    O --> CB[Orion]
```

## 4. Saída esperada de `interpret_query`

```json
{
  "intent": "query",
  "ngsi_query": { "type": "Sensor", "limit": 20, "q": null },
  "raw_interpretation": "...",
  "source": "heuristic | phi-2"
}
```

## 5. Entregáveis

- [ ] `services/slm_service.py` com carregamento lazy do modelo.
- [ ] Variáveis `SLM_MODEL`, `SLM_ENABLED` no `.env.example`.
- [ ] Comando CLI `ask` exibindo interpretação antes da orquestração.
- [ ] Documentação de requisitos de hardware (RAM/GPU) no README.

## 6. Atividades

| # | Atividade |
|---|-----------|
| 6.1 | Implementar heurísticas PT (consultar, criar, inscrever) |
| 6.2 | Integrar pipeline Transformers para phi-2 |
| 6.3 | Prompt de geração JSON NGSI (few-shot opcional) |
| 6.4 | Tratar falha de parse → fallback heurístico |
| 6.5 | Testes unitários sem carregar modelo (mock) |
| 6.6 | Avaliar FiLiP (README §4.1) para NLP FIWARE — estudo comparativo |

## 7. Critérios de conclusão

- [ ] 10 frases de teste mapeadas corretamente para `intent`.
- [ ] Modo heurístico funciona sem torch instalado (CI).
- [ ] Modo phi-2 documentado para demonstração opcional na banca.

## 8. Exemplos de teste (aceite)

| Entrada | intent esperado |
|---------|-----------------|
| "listar sensores" | query |
| "criar dispositivo Device:99" | provision |
| "avisar quando temperatura subir" | subscribe |

## 9. Riscos

| Risco | Mitigação |
|-------|-----------|
| Modelo pesado na máquina do aluno | `SLM_ENABLED=false` por padrão |
| Alucinação de endpoints NGSI | Validar com Pydantic + docs RAG (Fase 8) |

## 10. Próxima fase

→ [Fase 8 — Inferência RAG](fase-08-inferencia-rag-tempo-real.md) (melhora precisão do contexto)

## 11. Referências

- README §6 (Ecossistema IA e SLM)
- `prompts/inference/query-rewriting.md`
