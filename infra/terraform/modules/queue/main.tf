# Fase 9 (.cursor/specs/fase9.spec.md, secao 2.3) — fila de jobs de auditoria
# + dead-letter queue (DLQ). Espelha o contrato de `JobQueuePort`
# (src/auditor/domain/ports/job_queue_port.py) já implementado localmente por
# `LocalJobQueue` e, para AWS, por `SqsJobQueue`
# (src/auditor/infrastructure/queue/sqs_job_queue.py).

resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name_prefix}-audit-jobs-dlq"
  message_retention_seconds = var.dlq_message_retention_seconds
  tags                      = var.tags
}

resource "aws_sqs_queue" "audit_jobs" {
  name                       = "${var.name_prefix}-audit-jobs"
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.message_retention_seconds

  # maxReceiveCount deve ficar sincronizado com LocalJobQueue.max_retries
  # (ver variables.tf, `max_receive_count`) — não há redefinição de schema
  # aqui, apenas o número de tentativas antes de mover para a DLQ.
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount = var.max_receive_count
  })

  tags = var.tags
}

# Permite que a fila principal envie para a DLQ (redrive) — requerido pelo
# SQS para a relação redrive_policy funcionar de fato.
resource "aws_sqs_queue_redrive_allow_policy" "dlq_allow" {
  queue_url = aws_sqs_queue.dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.audit_jobs.arn]
  })
}
