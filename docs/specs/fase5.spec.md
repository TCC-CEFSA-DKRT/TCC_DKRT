# Specs — Fase 5: Fila e Worker

Introduz processamento assíncrono sem trocar o contrato da API (já preparado na Fase 4).
Ponto de partida importante: a Fase 3 já especificou `append_report` como idempotente por
`(run_id, entity_id)` — é essa idempotência, já garantida, que torna o reprocessamento de um
job seguro nesta fase, sem precisar de nenhum mecanismo novo de deduplicação.

---

## 1. Decisão de granularidade: um job por *run*, não por entidade

A fila carrega **um job por auditoria inteira** (`run_id`), não um job por entidade. O
worker, ao processar o job, executa a mesma lógica de `RunAuditUseCase` da Fase 4 (buscar
entidades, validar, persistir uma a uma). Motivo: reentrega de job em caso de falha (padrão
"at-least-once" de fila de mensagens, seja SQS ou a fila local) reprocessa o run inteiro —
como a validação estrutural é uma função pura (mesma entidade + mesmo schema sempre produz
o mesmo resultado) e `append_report` já é idempotente, reprocessar é **seguro e produz o
mesmo resultado final**, só com o custo de refazer trabalho já feito (não risco de dado
inconsistente).

```python
@dataclass(frozen=True)
class AuditJob:
    run_id: UUID
    tenant: Tenant
    entity_type: EntityType | None
    entity_id: str | None
    enqueued_at: datetime
```

---

## 2. `JobQueuePort`

```python
class JobHandle(Protocol):
    job: AuditJob
    async def ack(self) -> None: ...     # confirma processamento — remove da fila
    async def nack(self) -> None: ...    # falhou — disponível para reentrega

class JobQueuePort(Protocol):
    async def enqueue(self, job: AuditJob) -> None: ...
    def consume(self) -> AsyncIterator[JobHandle]: ...
```

Desenhado deliberadamente no nível de abstração do SQS (at-least-once, ack/nack explícito,
redelivery automática) — é a semântica mais restritiva das duas implementações; a fila local
de desenvolvimento simula o mesmo contrato, para que o comportamento não surpreenda na troca
dev→produção.

### 2.1 Casos de teste (contrato — rodam para as duas implementações)

- **Dado** um `AuditJob` enfileirado, **quando** `consume()` itera, **então** entrega um
  `JobHandle` com o mesmo job.
- **Dado** um `JobHandle` recebido e `ack()` chamado, **quando** se verifica a fila depois,
  **então** o job não é entregue de novo.
- **Dado** um `JobHandle` recebido e `nack()` chamado (ou nenhum `ack()`/`nack()` dentro do
  tempo de visibilidade), **quando** o tempo expira, **então** o mesmo job é entregue
  novamente a um consumidor.
- **Dado** um job que falhou (via `nack()`) um número de vezes acima do limite configurado
  (ex.: 3), **quando** a última falha ocorre, **então** o job vai para a fila de mensagens
  mortas (DLQ) em vez de ser reentregue outra vez — evita loop infinito de reprocessamento
  de um job permanentemente quebrado.

### 2.2 `LocalJobQueue` (dev, sem infraestrutura)

- **Dado** 500 jobs enfileirados rapidamente em sequência, **quando** consumidos, **então**
  todos os 500 são entregues, nenhum perdido — corresponde ao volume citado no critério de
  pronto desta fase (500 **entidades** dentro de **um** run/job, não 500 jobs — mas a fila
  em si precisa suportar volume sem gargalo).
- **Dado** o processo Python é reiniciado com jobs pendentes na fila local, **quando** o
  processo volta, **então** os jobs em memória são perdidos — **limitação documentada e
  aceita** para o ambiente de desenvolvimento (a fila local não precisa de durabilidade;
  produção usa SQS, que é durável).

### 2.3 `SqsJobQueue` (produção)

- Testado via mock/`moto` (biblioteca de simulação de serviços AWS) nesta fase — teste de
  integração contra SQS real fica reservado para a Fase 9 (deploy), não bloqueia esta fase.
- **Dado** o adaptador `SqsJobQueue`, **quando** `enqueue()` é chamado, **então** a
  mensagem enviada ao SQS contém o `run_id` serializado e nenhum dado sensível de tenant
  além do necessário para roteamento (não vaza segredo de conexão do broker do cliente na
  mensagem da fila).

---

## 3. `AuditWorker`

```python
class AuditWorker:
    def __init__(self, queue: JobQueuePort, run_audit: RunAuditUseCase): ...
    async def run_forever(self) -> None:
        """Loop principal: consome jobs, executa, ack/nack conforme resultado."""
```

### 3.1 Casos de teste

- **Dado** um job cujo processamento completa com sucesso (mesmo com entidades
  `NON_CONFORMANT`/`NO_MODEL_FOUND` entre os resultados), **quando** o worker termina de
  processar, **então** chama `ack()` — **um resultado de auditoria desfavorável não é uma
  falha de processamento**, é o resultado esperado do trabalho.
- **Dado** uma falha de infraestrutura durante o processamento (ex.: banco caiu no meio),
  **quando** o worker captura a exceção, **então** chama `nack()` — permitindo reentrega e
  nova tentativa.
- **Dado** um job reentregue após falha parcial (5 de 10 entidades já persistidas na
  tentativa anterior), **quando** o worker reprocessa o run inteiro do zero, **então** o
  resultado final tem exatamente 10 `EntityReport` (não 15, não duplicado) — comprova que a
  idempotência da Fase 3 realmente sustenta o reprocessamento seguro.
- **Dado** dois processos `AuditWorker` rodando simultaneamente consumindo da mesma fila,
  **quando** um job é publicado, **então** só um dos dois o processa (garantia da própria
  fila — teste de integração, não de lógica do worker em si).
- **Dado** um job que excede o limite de tentativas (seção 2.1) e vai para a DLQ, **quando**
  isso acontece, **então** o `AuditRun` correspondente é marcado `status=FAILED` com motivo
  `"max_retries_exceeded"` — o estado do run no banco nunca fica "pendente para sempre" sem
  explicação visível ao usuário.

---

## 4. Progresso — polling e streaming

### 4.1 `GET /audits/{run_id}/progress`

```json
{"status": "running", "processed": 120, "total": 500}
```

**Caso de borda importante:** o total de entidades só é conhecido depois que a consulta ao
Orion retorna — antes disso, não existe um número real para mostrar.

### 4.2 Casos de teste

- **Dado** um run que ainda está buscando entidades no Orion (antes de saber o total),
  **quando** `GET /audits/{run_id}/progress` é chamado, **então** retorna `{"status":
  "running", "processed": 0, "total": null}` — **nunca** um número inventado ou zero como
  se fosse "total conhecido igual a zero" (isso seria indistinguível de uma auditoria vazia
  de verdade).
- **Dado** um run processando, com 120 de 500 entidades já persistidas, **quando** chamado,
  **então** `processed=120` reflete uma contagem real (via `COUNT` no banco, não um valor
  em memória do worker — múltiplos consumidores da API precisam ver o mesmo progresso,
  então a fonte de verdade é o banco, não o processo do worker).
- **Dado** um run concluído, **quando** chamado, **então** `status` reflete o status final
  (`completed`/`failed`/`partial`) e `processed == total`.

### 4.3 `GET /audits/{run_id}/stream` (Server-Sent Events, opcional)

- **Dado** um cliente conectado ao stream durante o processamento, **quando** cada entidade
  é persistida, **então** um evento é emitido com o progresso atualizado — sem precisar de
  polling repetido. Escopo desta fase: implementação básica funcional; otimização de
  frequência de eventos fica para refinamento posterior, não bloqueia o critério de pronto.

---

## 5. Ajuste em `RunAuditUseCase` (Fase 4) necessário para esta fase

A Fase 4 especificou `execute()` criando o run e processando na mesma chamada. Para o
worker poder **retomar** um run já criado (reentrega de job), a interface precisa de duas
operações separadas:

```python
class RunAuditUseCase:
    async def start(self, tenant: Tenant, entity_type: EntityType | None,
                     entity_id: str | None) -> UUID:
        """Só cria o run (status=QUEUED) e publica o job. Não processa."""

    async def process(self, run_id: UUID) -> None:
        """Processa um run já criado — chamado pelo worker, idempotente
        quanto a reentrega (seção 3.1)."""
```

O endpoint `POST /audits` (Fase 4) passa a chamar `start()` (rápido, não bloqueia a
requisição HTTP) em vez de `execute()`. O `AuditWorker` chama `process()`.

**Caso de teste do ajuste:** dado `start()` chamado, quando a chamada retorna, então o
tempo de resposta não depende do número de entidades a processar (é `O(1)`, só cria o
registro do run e publica um job) — este é o teste que prova, na prática, que a API não
trava mais numa auditoria grande.

---

## 6. Definição de pronto da Fase 5

- Uma auditoria de 500 entidades (fixture sintética, não precisa ser Orion real nesta
  contagem) roda em background — `POST /audits` responde em milissegundos,
  independentemente do tamanho do lote.
- Reentrega de job simulada (matando o worker no meio do processamento) resulta no mesmo
  estado final correto, sem duplicação — teste automatizado, não só verificação manual.
- `GET /audits/{run_id}/progress` reflete progresso real, nunca inventa números para
  campos ainda desconhecidos.
- Dois workers rodando ao mesmo tempo não processam o mesmo job em duplicidade.