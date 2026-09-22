# Seção 8 (arquivada) — Implicações para o projeto TCC DKRT

> Esta seção foi extraída de `docs/base/fiware-e-orion-context-broker.md` (seção 8 original). Ela descreve as implicações da arquitetura multiagente descartada na reescrita registrada em `docs/plano_refatoracao_v3.md` — o restante daquele documento (seções 1-7 e 9-12) continua válido como referência genérica de FIWARE/NGSI-v2/Smart Data Models e **não foi alterado**. Preservada aqui por valor histórico; **não reflete o sistema atual**. Ver `.cursor/specs/` para o desenho vigente do projeto (índice completo em `docs/legacy/README.md`).

---

## 8. Implicações para o projeto TCC DKRT

O [pre-projeto](../entrega/pre_projeto_tcc.md) define orquestração multiagente sobre **Orion** via **NGSI-v2**. Consequências diretas:

| Decisão | Fundamentação |
|---------|---------------|
| Endpoints `/v2/entities`, `/v2/subscriptions` | API NGSI-v2 / Orion ([fase 4](../fases/fase-04-integracao-fiware-ngsi.md)) |
| Modelos `NgsiEntity` com `id`, `type`, attrs `{value,type}` | Modelo normativo NGSI-v2 §4 |
| Cabeçalhos `Fiware-Service` | Multi-tenancy Orion |
| NGSI-LD fora do escopo v1 | Spec e broker distintos; migração é projeto separado |

Erros comuns a evitar na implementação:

- Tratar `entity.type` como opcional em todas as operações (a unicidade é `id`+`type`).
- Enviar JSON NGSI-LD para Orion v2 sem adaptação.
- Assumir que o broker valida Smart Data Models automaticamente (harmonização é responsabilidade do integrador).
- Ignorar `406` por `Accept` incorreto.
