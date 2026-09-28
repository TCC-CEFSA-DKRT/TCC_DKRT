# Plano: distinguir "0 entidades encontradas" de "Concluído" (falso positivo)

## Problema real (confirmado no código)
`RunAuditUseCase.process_run()` e `RunAuditUseCase.process()` (`src/auditor/application/use_cases/run_audit.py`):
quando `fetch_entities()` devolve uma lista vazia (nenhuma entidade daquele tipo existe no
broker), o loop simplesmente não executa nenhuma iteração e o status final vira
`RunStatus.COMPLETED` — visualmente idêntico, na tela, a "auditei tudo e passou tudo". Não há
hoje nenhum jeito de diferenciar os dois casos só olhando o status do run.

## Design
Novo valor de status, sem migração de banco necessária: a coluna `audit_runs.status` já é
`sa.String()` (não é enum nativo do Postgres — confirmado em
`migrations/versions/2f62abb9e945_initial_schema.py`), e `mappers.py` faz `RunStatus(row["status"])`
genericamente. Um valor novo no enum Python não exige nenhuma migration.

## Arquivos e mudanças

### 1. `src/auditor/domain/entities/audit_run.py`
- `RunStatus`: adicionar `NO_ENTITIES_FOUND = "no_entities_found"`.
- `__post_init__`: hoje só exige `finished_at` não-nulo para `COMPLETED`. Estender pra também
  exigir para `NO_ENTITIES_FOUND` (mesmo raciocínio: ambos são status terminais de sucesso):
  ```python
  if self.status in (RunStatus.COMPLETED, RunStatus.NO_ENTITIES_FOUND) and self.finished_at is None:
      raise InvariantViolationError(
          "AuditRun.finished_at nao pode ser None quando status e COMPLETED ou NO_ENTITIES_FOUND."
      )
  ```
  (Ajustar a mensagem de erro é aceitável mesmo com "zero comentários novos" — é uma string de
  exceção, não um comentário.)

**Teste primeiro** (`tests/unit/domain/test_audit_run.py`, ao lado de `test_completed_run_requires_finished_at`):
```python
def test_no_entities_found_run_requires_finished_at(self):
    with pytest.raises(InvariantViolationError):
        AuditRun(
            id=uuid4(),
            tenant=_TENANT,
            entity_type=EntityType("Streetlight"),
            status=RunStatus.NO_ENTITIES_FOUND,
            reports=[],
            summary=RunSummary.empty(),
            started_at=datetime.now(timezone.utc),
            finished_at=None,
            broker_url="http://localhost:1026",
        )
```

### 2. `src/auditor/application/use_cases/run_audit.py`

**`process_run()`** — trocar o cálculo de `final_status` (hoje: `PARTIAL if partial else COMPLETED`) por:
```python
if partial:
    final_status = RunStatus.PARTIAL
elif not raw_entities:
    final_status = RunStatus.NO_ENTITIES_FOUND
else:
    final_status = RunStatus.COMPLETED
```

**`process()`** — trocar o `RunStatus.COMPLETED` fixo no `update_run_status` final por:
```python
final_status = RunStatus.NO_ENTITIES_FOUND if not raw_entities else RunStatus.COMPLETED
async with self._uow as uow:
    await uow.audits.update_run_status(
        run_id, tenant, final_status, finished_at=self._clock()
    )
```

**Teste primeiro** (`tests/unit/application/test_run_audit_use_case.py`, ao lado dos testes que já
exercitam `execute()`/`process()` com fakes de `ContextBrokerPort`/`UnitOfWork` — usar exatamente o
mesmo padrão de fakes/fixtures já usado nos testes vizinhos, não criar um novo):

- `test_execute_with_zero_entities_is_marked_no_entities_found`: fake context broker cujo
  `fetch_entities` devolve `[]` para o tenant/tipo do teste; chamar `use_case.execute(...)`;
  esperar `run.status == RunStatus.NO_ENTITIES_FOUND`, `run.summary.total_entities == 0`,
  `run.finished_at is not None`.
- `test_process_with_zero_entities_is_marked_no_entities_found`: mesmo cenário, mas pelo caminho
  do worker (`use_case.process(run.id, tenant, entity_type)`, run já criado via `create_run()`
  antes, como os testes vizinhos de `process()` já fazem); esperar `persisted.status ==
  RunStatus.NO_ENTITIES_FOUND`, `persisted.total_entities_discovered == 0`,
  `persisted.summary.total_entities == 0`.

Não é preciso teste novo pra confirmar que ≥1 entidade continua indo pra `COMPLETED` — os testes
existentes (`test_run_audit_use_case.py`, linhas ~311-398 e ~479-543) já cobrem isso e continuam
válidos sem alteração.

### 3. Frontend

`frontend/src/app/shared/models/audit.models.ts`, linha 20:
```ts
export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'partial' | 'no_entities_found';
```

`frontend/src/app/shared/components/status-badge/status-badge.component.ts`:
- `BadgeKind`: adicionar `'no_entities_found'` à união.
- `BADGE_STYLES`: adicionar `no_entities_found: { label: 'Nenhuma entidade encontrada', colorVar: '--color-warning' }`
  (usa o mesmo token `--color-warning` já existente em `frontend/src/styles.scss`, pra ficar
  visualmente diferente do verde de sucesso de `completed` sem ser vermelho de `failed`).

**Teste primeiro** (`frontend/src/app/shared/components/status-badge/status-badge.component.spec.ts`,
mesmo padrão do teste único que já existe ali):
```ts
it('renders a distinct label for a run with zero entities found', () => {
  TestBed.configureTestingModule({ imports: [StatusBadgeComponent] });
  const fixture = TestBed.createComponent(StatusBadgeComponent);
  fixture.componentRef.setInput('status', 'no_entities_found');
  fixture.detectChanges();

  expect((fixture.nativeElement as HTMLElement).textContent?.trim()).toBe('Nenhuma entidade encontrada');
});
```

### O que NÃO muda (confirmado, fora do escopo)
- `src/auditor/interfaces/rest/schemas.py`: `AuditRunResponse.status` já é `str` puro
  (`run.status.value`) — nenhuma mudança de schema/contrato necessária.
- `src/auditor/infrastructure/persistence/mappers.py`: `RunStatus(row["status"])` já é genérico —
  nenhuma mudança necessária.
- Nenhuma migration Alembic necessária (coluna é `sa.String()`, não enum nativo).
- `src/auditor/interfaces/cli/main.py`: já faz `typer.echo(f"status: {audit_run.status.value}")` —
  funciona automaticamente com o valor novo.
- Dashboard (`categoryAggregates`): agrega por `entity_type` somando campos de `RunSummary`, que
  já são todos zero num run vazio hoje — não depende do `status` do run, continua correto sem
  mudança.
- Não estamos tocando no gap de "qual broker cada run usou não aparece na tela" — é um gap
  separado (broker_url existe no domínio e na API mas nenhuma tela mostra), já registrado como
  pendente, fora do escopo desta rodada porque o usuário pediu especificamente "o falso positivo".

## Restrições padrão da sessão
1. TDD estrito: teste antes do código em cada passo.
2. Zero comentários novos em `.py`/`.ts` (a mensagem de exceção em `__post_init__` é string de
   erro, não comentário — pode mudar). Docstrings antigos ficam como estão.
3. Nenhum teste existente pode ser alterado nesta rodada (todos os testes citados acima são
   testes NOVOS; nenhum teste pré-existente precisa mudar).
4. `pytest` (backend) e `cd frontend && npx ng test --watch=false` (frontend) têm que passar no
   final, com os mesmos erros de infraestrutura ausente (Postgres/Orion/Ollama reais) de antes,
   nenhum novo.

## Checagem final
- `pytest` inteiro e `ng test` inteiro passando.
- `grep` no diff por comentários novos: zero, fora da string de mensagem de erro do invariante
  (que não é comentário).
- Confirmar manualmente (fora do sandbox, com Orion real): rodar uma auditoria contra um tipo
  que não existe no broker e ver o badge "Nenhuma entidade encontrada" em vez de "Concluído".
