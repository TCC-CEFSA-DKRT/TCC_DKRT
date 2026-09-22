"""JobQueuePort — ver .cursor/specs/fase5.spec.md, secao 2.

Desenhado no nivel de abstracao do SQS (at-least-once, ack/nack explicito,
redelivery automatica por visibility timeout, DLQ apos N falhas) —
deliberadamente a semantica mais restritiva das duas implementacoes
(LocalJobQueue simula o mesmo contrato), para que o comportamento nao
surpreenda na troca dev -> producao.

`consume_dead_letters()` e' o canal separado por onde jobs que excederam o
limite de tentativas aparecem — e' o que permite ao AuditWorker marcar o
AuditRun correspondente como FAILED/max_retries_exceeded (secao 3.1, ultimo
bullet) em vez de o job simplesmente desaparecer sem explicacao visivel.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol

from auditor.domain.entities.audit_job import AuditJob


class JobHandle(Protocol):
    job: AuditJob

    async def ack(self) -> None:
        """Confirma processamento — remove da fila, nao e' reentregue."""
        ...

    async def nack(self) -> None:
        """Falhou — disponivel para reentrega (ou vai para DLQ, se excedeu
        o limite de tentativas configurado)."""
        ...


class JobQueuePort(Protocol):
    async def enqueue(self, job: AuditJob) -> None: ...

    def consume(self) -> AsyncIterator[JobHandle]: ...

    def consume_dead_letters(self) -> AsyncIterator[AuditJob]:
        """Jobs que excederam o limite de tentativas — nunca mais
        reentregues por `consume()`."""
        ...
