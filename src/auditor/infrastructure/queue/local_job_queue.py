"""LocalJobQueue — implementa JobQueuePort em memoria (asyncio), sem
infraestrutura externa. Ver .cursor/specs/fase5.spec.md, secao 2.2.

Simula deliberadamente a MESMA semantica restritiva do SQS (secao 2): cada
job entregue por `consume()` fica "invisivel" por `visibility_timeout`
segundos — se ninguem chamar `ack()`/`nack()` antes disso, e' tratado como
falha e reentregue (ou vai para DLQ, se ja' esgotou `max_retries`). Isso
evita que o comportamento surpreenda na troca dev -> producao (SqsJobQueue).

Limitacao documentada e aceita (secao 2.2, ultimo bullet): tudo isto vive em
memoria do processo Python. Se o processo reiniciar com jobs pendentes,
eles se perdem — a fila local nao precisa de durabilidade; producao usa SQS,
que e' durvel.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import AsyncIterator
from uuid import UUID

from auditor.domain.entities.audit_job import AuditJob
from auditor.domain.ports.job_queue_port import JobHandle


class LocalJobQueue:
    def __init__(self, *, visibility_timeout: float = 30.0, max_retries: int = 3) -> None:
        self._queue: asyncio.Queue[AuditJob] = asyncio.Queue()
        self._dead_letters: asyncio.Queue[AuditJob] = asyncio.Queue()
        self._attempts: dict[UUID, int] = {}
        self._visibility_timeout = visibility_timeout
        self._max_retries = max_retries

    async def enqueue(self, job: AuditJob) -> None:
        await self._queue.put(job)

    async def consume(self) -> AsyncIterator["_LocalJobHandle"]:
        while True:
            job = await self._queue.get()
            attempts = self._attempts.get(job.run_id, 0) + 1
            self._attempts[job.run_id] = attempts
            handle = _LocalJobHandle(job=job, queue=self, attempts=attempts)
            handle._start_visibility_timer(self._visibility_timeout)
            yield handle

    async def consume_dead_letters(self) -> AsyncIterator[AuditJob]:
        while True:
            yield await self._dead_letters.get()

    async def _ack(self, job: AuditJob) -> None:
        self._attempts.pop(job.run_id, None)

    async def _nack(self, job: AuditJob, attempts: int) -> None:
        if attempts >= self._max_retries:
            self._attempts.pop(job.run_id, None)
            await self._dead_letters.put(job)
        else:
            await self._queue.put(job)


@dataclass
class _LocalJobHandle:
    job: AuditJob
    queue: LocalJobQueue
    attempts: int
    _settled: bool = field(default=False, init=False)
    _timer: asyncio.Task | None = field(default=None, init=False)

    def _start_visibility_timer(self, timeout: float) -> None:
        self._timer = asyncio.create_task(self._expire_after(timeout))

    async def _expire_after(self, timeout: float) -> None:
        await asyncio.sleep(timeout)
        if not self._settled:
            # ninguem chamou ack()/nack() a tempo — mesma consequencia de um
            # nack() explicito: reentrega ou DLQ, conforme o numero de
            # tentativas ja' feitas.
            await self.nack()

    async def ack(self) -> None:
        if self._settled:
            return
        self._settled = True
        if self._timer is not None:
            self._timer.cancel()
        await self.queue._ack(self.job)

    async def nack(self) -> None:
        if self._settled:
            return
        self._settled = True
        if self._timer is not None:
            self._timer.cancel()
        await self.queue._nack(self.job, self.attempts)
