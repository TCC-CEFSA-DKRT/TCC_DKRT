"""AuditWorker — consome AuditJob da fila e processa via RunAuditUseCase.
Ver .cursor/specs/fase5.spec.md, secao 3.

`run_forever()` dispara dois loops concorrentes:

1. `_consume_jobs()`: consome `JobHandle` de `queue.consume()`, chama
   `use_case.process(...)`. `ack()` em caso de sucesso — mesmo com
   resultado de auditoria desfavoravel entre os EntityReport
   (NON_CONFORMANT/NO_MODEL_FOUND etc.): isso e' o resultado ESPERADO do
   trabalho, nao uma falha de processamento (secao 3.1, primeiro caso de
   teste). `nack()` em qualquer excecao — deixa a propria fila decidir
   reentrega ou DLQ, o worker nao sabe nem precisa saber quantas tentativas
   ja' houve.
2. `_consume_dead_letters()`: consome `AuditJob` de
   `queue.consume_dead_letters()` (jobs que ja' excederam o limite de
   tentativas configurado na fila) e chama `use_case.mark_failed(...,
   reason="max_retries_exceeded")` — e' o que garante que o AuditRun nunca
   fica "pendente para sempre" sem explicacao visivel ao usuario (secao
   3.1, ultimo caso de teste).
"""

from __future__ import annotations

import asyncio
import logging

from auditor.application.use_cases.run_audit import RunAuditUseCase
from auditor.domain.ports.job_queue_port import JobHandle, JobQueuePort

logger = logging.getLogger(__name__)

MAX_RETRIES_EXCEEDED_REASON = "max_retries_exceeded"


class AuditWorker:
    def __init__(self, queue: JobQueuePort, run_audit: RunAuditUseCase) -> None:
        self._queue = queue
        self._run_audit = run_audit

    async def run_forever(self) -> None:
        await asyncio.gather(self._consume_jobs(), self._consume_dead_letters())

    async def _consume_jobs(self) -> None:
        async for handle in self._queue.consume():
            await self._process_one(handle)

    async def _process_one(self, handle: JobHandle) -> None:
        job = handle.job
        try:
            await self._run_audit.process(job.run_id, job.tenant, job.entity_type, job.entity_id)
        except Exception:
            logger.exception(
                "Falha ao processar AuditJob run_id=%s — nack, aguardando reentrega/DLQ.",
                job.run_id,
            )
            await handle.nack()
        else:
            await handle.ack()

    async def _consume_dead_letters(self) -> None:
        async for job in self._queue.consume_dead_letters():
            try:
                await self._run_audit.mark_failed(
                    job.run_id, job.tenant, reason=MAX_RETRIES_EXCEEDED_REASON
                )
            except Exception:
                logger.exception(
                    "Falha ao marcar AuditRun run_id=%s como FAILED apos DLQ.", job.run_id
                )
