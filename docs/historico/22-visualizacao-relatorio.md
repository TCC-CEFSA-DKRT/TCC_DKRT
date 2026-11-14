# 22 — Visualização do relatório por entidade

## 2026-11-14 — Ajustes da revisão dos PRs #62 e #63 (Tainara)

**Contexto:** revisão do Diego nos PRs da #22 e criação da política de "sem comentários no código" (`docs/historico/00-politica-sem-comentarios.md`).

**O que mudou:**
- Comentários e docstrings da #22 saíram do código e vieram para esta entrada.
- `@for` das entidades usa `report-view.mapper.ts::entityTrackKey` (tipo + id) como chave.
- A associação recomendação ↔ violação compara o `attribute_path` normalizado (`report-view.mapper.ts::normalizeAttributePath`: sem espaços nas pontas e sem diferença de maiúsculas).
- O antigo `<ng-template #recommendation let-rec>` virou o componente tipado `RecommendationCardComponent` (`recommendation-card/`), com `input.required<RecommendationView>()`.
- Tipos da tela em `report-detail.models.ts`, valores (rótulos, ordem, filtros) em `report-labels.ts` e funções de montagem da tela em `report-view.mapper.ts`. O componente ficou só com estado e eventos.
- Link do schema com `rel="noopener noreferrer"`.
- Testes novos: mensagem de `schema_unavailable`, "Origem do schema não registrada", dois achados no mesmo atributo, rótulos de todas as regras do Nível 1, entidades com o mesmo id e tipos diferentes, `rel` do link e o card de recomendação.

**Por quê / decisões:**
- Chave do `@for`: no NGSI-v2 a identidade de uma entidade é `id` + `type`. Com "Todos os tipos", dois tipos podem ter o mesmo `id`; com só o `id` como chave, o Angular avisa `NG0955` e pode reaproveitar o DOM errado ao filtrar.
- Normalização do `attribute_path`: o caminho da recomendação vem do SLM como texto livre (ver `src/auditor/infrastructure/llm/prompts/semantic_diagnosis.md`). Uma diferença só de maiúsculas ou espaço jogava a recomendação para "Outras recomendações", perdendo o contexto da violação. Não foi feita normalização mais agressiva (remover pontos, sinônimos) para não ligar uma recomendação ao atributo errado.
- `RecommendationCardComponent`: o `ng-template` com `let-rec` não tem tipo; um erro de digitação como `rec.confidencePrecent` compilava. O componente com input tipado faz o compilador pegar esse erro.

**Armadilhas e pontos de atenção:**
- `report-view.mapper.ts::toEntityReportView` — as recomendações são distribuídas na ordem de severidade (`SEVERITY_ORDER`). Se dois achados apontam o mesmo atributo, a recomendação fica no mais grave e o outro fica sem recomendação. Coberto por teste no mapper e no componente.
- `RecommendationCardComponent` — quando a recomendação está ligada a uma violação (`attachedToViolation`), o valor atual já aparece em "Encontrado" logo acima, então o card mostra só a correção proposta. Sem violação correspondente, o card compara o atributo com o `proposed_patch` (`DiffViewComponent`).
- `EntityReportView.validated` — o Nível 1 só roda quando existe schema. Para `no_model_found` e `schema_unavailable` não há validação, então a nota "só Nível 1" e o "Nenhuma violação encontrada." seriam enganosos e não aparecem.
- `report-labels.ts::RULE_LABELS` — as regras do Nível 1 vêm de `structural_validator.py` e `run_audit.py`. As do Nível 2 são texto livre do SLM: as conhecidas (ex.: `attribute_name_synonym`, frequente no `dataset/`) têm rótulo; as demais passam por `report-view.mapper.ts::ruleLabel`, que troca `_`/`-` por espaço, e o código original fica no `title` (tooltip).
- `STATUS_FILTER_LABELS` — "Sem modelo" corresponde a `no_model_found`. O filtro `schema_unavailable` só aparece quando existe alguma entidade com esse status.
- `audit.models.ts::EntityReportResponse` — `data_model` e `schema_origin` são opcionais para continuar aceitando respostas de um backend anterior à #22. `null` em `data_model` quando nenhum Smart Data Model corresponde ao tipo; `null` em `schema_origin` quando o schema não foi obtido (sem modelo, schema indisponível ou relatório antigo).
- `schemas.py::DataModelResponse` e `schemas.py::SchemaOriginResponse` — os dados já existiam no domínio (`EntityReport.data_model`, `SchemaOrigin`) e eram persistidos em `entity_reports`; só não eram expostos na API. Sem migration. A tela precisa da origem para que um resultado baseado em cache nunca fique indistinguível de um confirmado ao vivo.

**Pendências:**
- Paginação ou virtualização da lista de entidades: hoje a tela renderiza todas, e cada clique no filtro remonta o modelo de visão. Para os datasets atuais (dezenas de entidades) o desempenho é bom; vale rever se as auditorias passarem a ter centenas de entidades.

**Referências:** issue #22, PRs #62 (`main`) e #63 (`develop`), `docs/historico/00-politica-sem-comentarios.md`.
