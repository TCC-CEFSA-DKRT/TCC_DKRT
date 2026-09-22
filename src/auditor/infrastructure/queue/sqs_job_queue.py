"""SqsJobQueue — implementa JobQueuePort contra Amazon SQS. Ver
.cursor/specs/fase5.spec.md, secao 2.3.

boto3 e' sincrono — cada chamada roda em `asyncio.to_thread` para nao
bloquear o event loop. ack()/nack() usam o mecanismo nativo do SQS: ack()
apaga a mensagem (`delete_message`); nack() zera o visibility timeout
(`change_message_visibility(VisibilityTimeout=0)`), tornando-a visivel de
novo imediatamente para outro consumidor — o numero de tentativas e a
mudanca para a fila de mensagens mortas (DLQ) sao geridos pela propria
`RedrivePolicy` da fila SQS (configurada na infraestrutura, Fase 9), nao
por logica própria aqui.

Corpo da mensagem carrega so' o necessario para roteamento/processamento —
`run_id`, os dois campos do Tenant, `entity_type`/`entity_id` — nunca
segredo de conexao do broker do cliente (o dominio nem modela isso em
`Tenant` para comecar).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncIterator
from uuid import UUID

from auditor.domain.entities.audit_job import AuditJob
from auditor.domain.value_objects.entity_type import EntityType
from auditor.domain.value_objects.tenant import Tenant


def _job_to_message_body(job: AuditJob) -> str:
    return json.dumps(
        {
            "run_id": str(job.run_id),
            "fiware_service": job.tenant.fiware_service,
            "fiware_service_path": job.tenant.fiware_service_path,
            "entity_type": job.entity_type.value if job.entity_type else None,
            "entity_id": job.entity_id,
            "enqueued_at": job.enqueued_at.isoformat(),
        }
    )


def _message_body_to_job(body: str) -> AuditJob:
    return parse_audit_job(body)


def parse_audit_job(body: str) -> AuditJob:
    """Desserializa o corpo de uma mensagem SQS de volta para `AuditJob` —
    mesmo formato de `_job_to_message_body()` acima. Publica (sem
    underscore) porque a ADR-0017 introduz um segundo consumidor deste
    mesmo formato de mensagem: o handler Lambda do worker de producao
    (`interfaces/aws_lambda/worker_handler.py`), que recebe o batch de
    registros SQS diretamente do event source mapping em vez de chamar
    `SqsJobQueue.consume()` — não faz sentido instanciar um `SqsJobQueue`
    inteiro (com client/queue_url) só para reaproveitar este parsing."""
    data: dict[str, Any] = json.loads(body)
    return AuditJob(
        run_id=UUID(data["run_id"]),
        tenant=Tenant(
            fiware_service=data["fiware_service"],
            fiware_service_path=data["fiware_service_path"],
        ),
        entity_type=EntityType(data["entity_type"]) if data.get("entity_type") else None,
        entity_id=data.get("entity_id"),
        enqueued_at=datetime.fromisoformat(data["enqueued_at"]),
    )


class SqsJobQueue:
    def __init__(
        self,
        client: Any,
        queue_url: str,
        *,
        dead_letter_queue_url: str | None = None,
        wait_time_seconds: int = 5,
    ) -> None:
        self._client = client
        self._queue_url = queue_url
        self._dead_letter_queue_url = dead_letter_queue_url
        self._wait_time_seconds = wait_time_seconds

    async def enqueue(self, job: AuditJob) -> None:
        await asyncio.to_thread(
            self._client.send_message,
            QueueUrl=self._queue_url,
            MessageBody=_job_to_message_body(job),
        )

    async def consume(self) -> AsyncIterator["_SqsJobHandle"]:
        while True:
            response = await asyncio.to_thread(
                self._client.receive_message,
                QueueUrl=self._queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=self._wait_time_seconds,
            )
            for message in response.get("Messages", []):
                job = _message_body_to_job(message["Body"])
                yield _SqsJobHandle(job=job, queue=self, receipt_handle=message["ReceiptHandle"])

    async def consume_dead_letters(self) -> AsyncIterator[AuditJob]:
        if self._dead_letter_queue_url is None:
            return
        while True:
            response = await asyncio.to_thread(
                self._client.receive_message,
                QueueUrl=self._dead_letter_queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=self._wait_time_seconds,
            )
            for message in response.get("Messages", []):
                await asyncio.to_thread(
                    self._client.delete_message,
                    QueueUrl=self._dead_letter_queue_url,
                    ReceiptHandle=message["ReceiptHandle"],
                )
                yield _message_body_to_job(message["Body"])

    async def _delete(self, receipt_handle: str) -> None:
        await asyncio.to_thread(
            self._client.delete_message, QueueUrl=self._queue_url, ReceiptHandle=receipt_handle
        )

    async def _release(self, receipt_handle: str) -> None:
        await asyncio.to_thread(
            self._client.change_message_visibility,
            QueueUrl=self._queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=0,
        )


class _SqsJobHandle:
    def __init__(self, job: AuditJob, queue: SqsJobQueue, receipt_handle: str) -> None:
        self.job = job
        self._queue = queue
        self._receipt_handle = receipt_handle
        self._settled = False

    async def ack(self) -> None:
        if self._settled:
            return
        self._settled = True
        await self._queue._delete(self._receipt_handle)

    async def nack(self) -> None:
        if self._settled:
            return
        self._settled = True
        await self._queue._release(self._receipt_handle)
