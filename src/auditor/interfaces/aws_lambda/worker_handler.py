"""Handler Lambda do Worker — ADR-0017. Substitui o `AuditWorker`
(`interfaces/worker/audit_worker.py`) do EC2 (Fase 9): em vez de um loop
`consume()` fazendo long-polling na fila SQS (`_consume_jobs()`), esta
funcao e' invocada pelo proprio event source mapping SQS->Lambda
(`modules/lambda_compute`) com um lote (`event["Records"]`) de mensagens ja'
recebidas — o "polling" passa a ser responsabilidade do proprio servico
Lambda, nao de um processo sempre ativo.

Falha parcial de lote: em vez de `handle.ack()`/`handle.nack()` por
mensagem (que so' fazem sentido com uma _SqsJobHandle viva, que este
handler nunca cria — nao ha' `consume()` aqui, so' `event["Records"]` que a
propria integracao SQS->Lambda ja' removeu da fila principal ao entregar o
lote), usa-se o mecanismo nativo do Lambda para batch parcial:
`batchItemFailures` no retorno, listando so' os `messageId` que falharam —
o proprio event source mapping torna so' essas mensagens visiveis de novo
(reentrega) e conta a tentativa para efeito da `RedrivePolicy`/DLQ da fila
(mesmo contrato de reentrega/DLQ da Fase 5, so' que o "consumidor" e' uma
invocacao em vez de um loop de polling — ver
`docs/design/implantacao-aws.html`, card "Dados & Filas"). As mensagens
SEM falha nem aparecem em `batchItemFailures`: sao consideradas
processadas e o proprio Lambda as remove da fila.

Requer `functionResponseTypes = ["ReportBatchItemFailures"]` no
`aws_lambda_event_source_mapping` (Terraform, `modules/lambda_compute`) —
sem isso a AWS trata QUALQUER retorno nao-vazio como falha do lote inteiro
(comportamento antigo, todas as mensagens do lote reentregues, mesmo as que
processaram com sucesso)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from auditor.interfaces.aws_lambda._bootstrap import bootstrap_settings_from_aws

bootstrap_settings_from_aws()

from auditor.infrastructure.config.container import get_run_audit_use_case  # noqa: E402
from auditor.infrastructure.queue.sqs_job_queue import parse_audit_job  # noqa: E402

logger = logging.getLogger(__name__)


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    return asyncio.run(_handle_async(event))


async def _handle_async(event: dict[str, Any]) -> dict[str, Any]:
    use_case = get_run_audit_use_case()
    batch_item_failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        job = parse_audit_job(record["body"])
        try:
            await use_case.process(job.run_id, job.tenant, job.entity_type, job.entity_id)
        except Exception:
            logger.exception(
                "Falha ao processar AuditJob run_id=%s (messageId=%s) — reportando "
                "batchItemFailure, aguardando reentrega/DLQ pela propria fila SQS.",
                job.run_id,
                record.get("messageId"),
            )
            batch_item_failures.append({"itemIdentifier": record["messageId"]})

    return {"batchItemFailures": batch_item_failures}
