# Specs — Fase 3: Persistência

Mesmo formato das fases anteriores. Cobre a porta `AuditRepositoryPort`, o mapeamento
domínio ↔ ORM, o Unit of Work, as migrations e — o ponto mais crítico desta fase — o
isolamento por tenant garantido no repositório, não no controller.

---

## 1. Uma decisão de design que muda o contrato: escrita incremental, não um `save()` único

Antes de especificar a porta, um ajuste em relação ao que o plano geral sugeria
implicitamente: uma auditoria pode ter **milhares de entidades**, processadas por um worker
assíncrono (Fase 5) ao longo de minutos. Um único `save(run)` no fim, com o agregado
inteiro em memória, tem dois problemas — usa memória proporcional ao tamanho do run, e
perde todo o progresso se o worker cair no meio. A porta é desenhada para escrita
incremental desde o início:

```python
# domain/ports/audit_repository_port.py

class AuditRepositoryPort(Protocol):
    async def create_run(self, run: AuditRun) -> None:
        """Grava o run no estado inicial (QUEUED, sem relatórios ainda)."""

    async def append_report(self, run_id: UUID, tenant: Tenant,
                             report: EntityReport) -> None:
        """Adiciona um relatório de entidade a um run existente. Chamado uma vez
        por entidade processada, não no fim do run inteiro."""

    async def update_run_status(self, run_id: UUID, tenant: Tenant,
                                 status: RunStatus,
                                 finished_at: datetime | None = None) -> None: ...

    async def get_by_id(self, run_id: UUID, tenant: Tenant) -> AuditRun | None:
        """Reconstrói o agregado completo — usado para leitura (dashboard,
        detalhe do relatório), não durante o processamento."""

    async def list_runs(self, tenant: Tenant,
                         filters: RunFilters) -> Page[AuditRunSummaryView]: ...

    async def list_run_summaries_over_time(
        self, tenant: Tenant, entity_type: EntityType
    ) -> list[AuditRunSummaryView]:
        """Suporta o caso de uso de comparação/evolução (compare_audit_runs)."""
```

Consequência de performance a testar: os contadores agregados (`RunSummary`) são mantidos
por incremento atômico no banco a cada `append_report` (`UPDATE ... SET conformant_count =
conformant_count + 1`, dentro da mesma transação do insert do relatório) — não por
reconstrução do agregado inteiro em memória a cada chamada. Isso evita custo quadrático
numa auditoria grande.

---

## 2. Casos de teste — `create_run` e `append_report`

- **Dado** um `AuditRun` novo (`status=QUEUED`, sem relatórios), **quando**
  `create_run()` é chamado, **então** uma consulta subsequente por `get_by_id()` retorna o
  run com `reports=[]` e `summary` zerado.
- **Dado** um run já criado, **quando** `append_report()` é chamado 3 vezes com relatórios
  de status diferentes (1 `CONFORMANT`, 1 `PARTIAL`, 1 `NON_CONFORMANT`), **então**
  `get_by_id()` retorna um run com `summary.total_entities=3`,
  `summary.conformant_count=1`, `summary.partial_count=1`,
  `summary.non_conformant_count=1` — consistente com o invariante já validado no domínio
  (Fase 1, `RunSummary.__post_init__`).
- **Dado** `append_report()` chamado para um `run_id` que não existe, **quando** a chamada é
  feita, **então** levanta `RunNotFoundError` — nunca cria o relatório "solto", órfão de
  run.
- **Idempotência (requisito da Fase 5/3.6 — reprocessamento de job):** **dado** o mesmo
  `EntityReport` (mesmo `entity_id` dentro do mesmo `run_id`) enviado duas vezes via
  `append_report()` (simulando reentrega de mensagem da fila), **quando** a segunda chamada
  é processada, **então** o relatório não é duplicado — a segunda chamada substitui a
  primeira (mesmo resultado) ou é ignorada, e `summary` reflete a contagem correta uma única
  vez, não duas.

## 3. Casos de teste — `update_run_status`

- **Dado** um run em `RUNNING`, **quando** `update_run_status(status=COMPLETED,
  finished_at=<agora>)` é chamado, **então** `get_by_id()` reflete o novo status e
  `finished_at` preenchido — consistente com o invariante da Fase 1 ("todo run concluído
  tem timestamp de fim").
- **Dado** uma tentativa de `update_run_status(status=COMPLETED, finished_at=None)`,
  **quando** chamado, **então** levanta erro de violação de invariante — o repositório não
  permite persistir um estado que o domínio já proíbe de existir.

## 4. Casos de teste — isolamento por tenant (o mais importante desta fase)

- **Dado** dois tenants, A e B, cada um com um run de auditoria salvo, **quando**
  `get_by_id(run_id_de_A, tenant=B)` é chamado, **então** retorna `None` — **mesmo o
  `run_id` sendo válido e existente**, o run de A nunca é visível para B.
- **Dado** os mesmos dois tenants, **quando** `list_runs(tenant=B, filters=sem_filtro)` é
  chamado, **então** a lista retornada não contém nenhum run de A, independentemente de
  quantos existam.
- **Teste de regressão obrigatório, escrito uma vez e mantido para sempre:** todo método de
  leitura da porta `AuditRepositoryPort` recebe `tenant` como parâmetro **obrigatório** (não
  opcional, não com valor padrão) — um teste de assinatura (via `inspect.signature`, rodando
  no CI) falha automaticamente se algum método novo for adicionado à porta sem esse
  parâmetro. Isso torna o requisito de segurança da seção 5 do plano geral ("impossível
  esquecer num endpoint novo") verificável por máquina, não só por revisão de código.

## 5. Casos de teste — filtros e paginação (`list_runs`)

```python
@dataclass(frozen=True)
class RunFilters:
    entity_type: EntityType | None = None
    status: RunStatus | None = None
    started_after: datetime | None = None
    started_before: datetime | None = None
    page: int = 1
    page_size: int = 20
```

- **Dado** um tenant com 25 runs salvos, **quando** `list_runs(filters=RunFilters(page=1,
  page_size=20))` é chamado, **então** retorna 20 itens e `Page.has_next=True`.
- **Dado** o mesmo tenant, **quando** `list_runs(filters=RunFilters(status=FAILED))` é
  chamado, **então** só os runs com esse status aparecem.
- **Dado** múltiplos runs com `started_at` diferentes, **quando** `list_runs()` é chamado
  sem filtro de ordenação explícito, **então** o resultado vem ordenado por `started_at`
  decrescente (mais recente primeiro — consistente com o índice já definido no plano geral,
  `audit_runs(tenant_id, started_at DESC)`).

## 6. Casos de teste — `list_run_summaries_over_time`

- **Dado** 5 runs do mesmo `entity_type` para um tenant, executados em datas diferentes,
  **quando** `list_run_summaries_over_time()` é chamado, **então** retorna os 5 resumos
  ordenados cronologicamente — é o dado bruto que a tela de "evolução de conformidade no
  tempo" (frontend, Fase 8) consome diretamente, sem processamento adicional.

## 7. Unit of Work

```python
class UnitOfWork(Protocol):
    async def __aenter__(self) -> "UnitOfWork": ...
    async def __aexit__(self, *exc) -> None: ...  # commit se sem exceção, rollback se houver
    audits: AuditRepositoryPort
```

**Casos de teste:**
- **Dado** um bloco `async with uow:` que chama `append_report()` e depois levanta uma
  exceção proposital antes de terminar, **quando** o bloco termina, **então** nada foi
  persistido (rollback completo) — nunca um relatório parcialmente salvo.
- **Dado** o mesmo bloco sem exceção, **quando** termina, **então** os dados estão
  persistidos e visíveis por uma nova consulta fora daquele `uow`.

## 8. Mapeamento domínio ↔ ORM

Teste de contrato fundamental do padrão Repository, roda para toda entidade do domínio:

- **Dado** um `AuditRun` de domínio construído em memória com relatórios, violações e
  recomendações, **quando** persistido via `create_run`+`append_report` e recarregado via
  `get_by_id`, **então** o objeto reconstruído é **igual** ao original em todos os campos
  (round-trip completo) — inclusive tipos que exigem atenção na conversão: `StrEnum` ↔
  coluna de texto, `UUID` ↔ coluna nativa, `dict` (`proposed_patch`) ↔ coluna `JSONB`,
  `datetime` com timezone preservado.

## 9. Migrations (Alembic)

- **Dado** um banco Postgres vazio, **quando** todas as migrations são aplicadas
  (`alembic upgrade head`), **então** todas as tabelas da seção 3.7 do plano geral existem
  com os tipos e constraints corretos (incluindo `schema_cache` da Fase 2).
- **Dado** o banco com todas as migrations aplicadas, **quando** a migration mais recente é
  revertida (`alembic downgrade -1`), **então** reverte sem erro — toda migration nova
  precisa de um `downgrade()` funcional, testado, não só o `upgrade()`.
- **Dado** duas migrations aplicadas em sequência, **quando** aplicadas numa ordem diferente
  (simulando conflito de merge de branches), **então** o Alembic detecta e recusa — não
  aplica silenciosamente numa ordem incorreta.

---

## 10. Definição de pronto da Fase 3

- Todos os casos de teste acima implementados com **testcontainers** (Postgres real, não
  SQLite nem mocks — o comportamento de constraint, upsert e transação precisa ser validado
  contra o banco de produção real).
- Teste de assinatura da seção 4 rodando no CI, falhando a build se qualquer método de
  leitura for adicionado à porta sem `tenant` obrigatório.
- Migrations aplicam e revertem sem erro num banco limpo.
- Nenhum teste desta fase depende de `SchemaCatalogPort` ou `SemanticAnalyzerPort` — a
  persistência é testável isoladamente das Fases 2 e 7.