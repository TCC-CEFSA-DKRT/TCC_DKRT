variable "name_prefix" {
  description = "Prefixo de nomes dos recursos (ex.: \"auditor-academy\")."
  type        = string
}

variable "visibility_timeout_seconds" {
  description = "Tempo (s) em que uma mensagem entregue fica invisível para outros consumidores."
  type        = number
  default     = 120
}

variable "message_retention_seconds" {
  description = "Retenção de mensagens na fila principal (s). Default AWS: 4 dias."
  type        = number
  default     = 345600
}

variable "dlq_message_retention_seconds" {
  description = "Retenção de mensagens na DLQ (s). Maior que a fila principal para dar tempo de investigar falhas."
  type        = number
  default     = 1209600 # 14 dias (máximo permitido pelo SQS)
}

variable "max_receive_count" {
  description = <<-DESC
    Número de tentativas de entrega antes de uma mensagem ir para a DLQ
    (RedrivePolicy.maxReceiveCount).

    FONTE ÚNICA DE VERDADE: este valor deve espelhar
    `LocalJobQueue.max_retries` (src/auditor/infrastructure/queue/local_job_queue.py,
    default=3), para que o comportamento de retry seja o mesmo rodando local
    (fila em memória) ou na AWS (SqsJobQueue). `SqsJobQueue`
    (src/auditor/infrastructure/queue/sqs_job_queue.py) não tem um campo
    `max_retries` próprio — ela delega toda a semântica de retry/DLQ à
    RedrivePolicy nativa do SQS, configurada aqui. Se `LocalJobQueue.max_retries`
    mudar, este default deve ser atualizado manualmente (não há como
    compartilhar a constante entre Python e Terraform).
  DESC
  type        = number
  default     = 3
}

variable "tags" {
  type    = map(string)
  default = {}
}
