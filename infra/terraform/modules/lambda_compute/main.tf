# ADR-0017 -- API e worker de producao como Lambda (imagem de conteiner),
# atras do ALB (modules/edge_alb) e da fila SQS (modules/queue) — ver
# docs/design/implantacao-aws.html, card "Compute", e o Dockerfile na raiz
# do repo (uma unica imagem, tres comandos diferentes via
# image_config.command). Ollama continua em EC2 (modules/compute), fora
# deste modulo.

# --- ECR: repositorio unico para a imagem compartilhada pelos tres Lambdas
# (api/worker/worker_dlq). force_delete=true so' para nao deixar o
# `terraform destroy` de um prototipo de TCC bloqueado por imagens
# residuais -- nao seria a escolha certa numa conta de producao real de
# longa duracao.
resource "aws_ecr_repository" "this" {
  name                 = "${var.name_prefix}-auditor"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

# --- Security group do Lambda: sem ingress (ALB->Lambda e' uma chamada de
# API do plano de controle, nao uma conexao de rede dentro da VPC -- este
# SG so' rege o trafego de SAIDA do Lambda para dentro da VPC: RDS, Ollama
# EC2, VPC endpoints). Egress "all" mantem a mesma convencao das outras
# SGs do projeto (modules/network: api/worker/ollama/database todas usam
# egress -1/0.0.0.0/0 -- nenhuma faz egress restrito hoje).
resource "aws_security_group" "lambda" {
  name        = "${var.name_prefix}-lambda-sg"
  description = "Lambda de producao (API + worker) -- so' egress, ver comentario acima"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-lambda-sg" })
}

# --- IAM: execution role dos tres Lambdas. AWSLambdaVPCAccessExecutionRole
# (gerenciada pela AWS) sozinha ja' cobre logs:CreateLogGroup/
# CreateLogStream/PutLogEvents + ec2:CreateNetworkInterface/
# DescribeNetworkInterfaces/DeleteNetworkInterface (ENIs do Lambda dentro
# da VPC) -- nao e' preciso anexar AWSLambdaBasicExecutionRole em paralelo,
# a de VPC e' um superconjunto dela.
resource "aws_iam_role" "lambda_execution" {
  name = "${var.name_prefix}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "vpc_access" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy" "lambda_permissions" {
  name = "${var.name_prefix}-lambda-policy"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # SendMessage: API (RunAuditUseCase.start()) publicando o AuditJob.
        # ReceiveMessage/DeleteMessage/GetQueueAttributes/ChangeMessageVisibility:
        # exigidas pela propria integracao SQS->Lambda (event source
        # mapping) na role de execucao, mesmo o codigo do worker nunca as
        # chamando diretamente (worker_handler.py recebe o lote ja' via
        # event["Records"], nao via SqsJobQueue.consume()) -- sem elas o
        # event source mapping falha ao tentar ler/apagar mensagens em
        # nome do Lambda.
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:ChangeMessageVisibility",
        ]
        Resource = [var.queue_arn, var.dead_letter_queue_arn]
      },
      {
        Effect = "Allow"
        Action = ["ssm:GetParameter"]
        Resource = [
          var.orion_credentials_parameter_arn,
          var.jwt_signing_key_parameter_arn,
          var.broker_api_key_encryption_keys_parameter_arn,
        ]
      },
      {
        # So' o segredo gerenciado pelo RDS (senha do master user) --
        # nunca os segredos do modules/secrets (Secrets Manager comum),
        # que ADR-0017 substitui por Parameter Store para producao; ver
        # secrets_bootstrap.py.
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = [var.db_master_user_secret_arn]
      },
    ]
  })
}

# --- CloudWatch Logs: um log group por funcao, criado explicitamente (em
# vez de deixar o Lambda criar implicitamente no primeiro invoke) so' para
# poder fixar retention_in_days -- sem isso o log group implicito nunca
# expira, acumulando custo de armazenamento indefinidamente.
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${var.name_prefix}-api"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/aws/lambda/${var.name_prefix}-worker"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "worker_dlq" {
  name              = "/aws/lambda/${var.name_prefix}-worker-dlq"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

locals {
  # Variaveis de ambiente comuns aos tres Lambdas -- mesmo `.env` conceitual
  # que api.sh.tftpl/worker.sh.tftpl escrevem no EC2 (Fase 9), agora como
  # `environment` do aws_lambda_function. DATABASE_URL fica DE FORA de
  # proposito: e' `_bootstrap.bootstrap_settings_from_aws()` (chamado no
  # module-level de cada handler, antes de qualquer Settings()) que monta e
  # popula essa variavel em runtime a partir do RDS-managed secret -- uma
  # DATABASE_URL estatica aqui faria o bootstrap pular essa etapa
  # silenciosamente (guard `if "DATABASE_URL" in os.environ: return` em
  # secrets_bootstrap.py).
  common_env = {
    DEPLOYMENT_MODE                               = var.deployment_mode
    FIWARE_BROKER_URL                             = var.fiware_broker_url
    OLLAMA_BASE_URL                               = var.ollama_base_url
    OLLAMA_MODEL                                  = var.ollama_model
    CORS_ALLOWED_ORIGINS                          = var.cors_allowed_origins
    QUEUE_BACKEND                                 = "sqs"
    SQS_QUEUE_URL                                 = var.queue_url
    SQS_DEAD_LETTER_QUEUE_URL                     = var.dead_letter_queue_url
    DB_HOST                                       = var.db_host
    DB_PORT                                       = tostring(var.db_port)
    DB_NAME                                       = var.db_name
    DB_MASTER_USER_SECRET_ARN                     = var.db_master_user_secret_arn
    ORION_CREDENTIALS_PARAMETER_NAME              = var.orion_credentials_parameter_name
    JWT_SIGNING_KEY_PARAMETER_NAME                = var.jwt_signing_key_parameter_name
    BROKER_API_KEY_ENCRYPTION_KEYS_PARAMETER_NAME = var.broker_api_key_encryption_keys_parameter_name
  }

  image_uri = "${aws_ecr_repository.this.repository_url}:${var.image_tag}"
}

resource "aws_lambda_function" "api" {
  function_name = "${var.name_prefix}-api"
  role          = aws_iam_role.lambda_execution.arn
  package_type  = "Image"
  image_uri     = local.image_uri
  # Sem image_config.command -- usa o CMD default da imagem
  # (auditor.interfaces.aws_lambda.api_handler.handler, ver Dockerfile).

  timeout     = var.api_timeout_seconds
  memory_size = var.api_memory_mb

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = local.common_env
  }

  # O pipeline de deploy troca a imagem com update-function-code; sem isto um
  # terraform apply voltaria a função para var.image_tag (ADR-0021).
  lifecycle {
    ignore_changes = [image_uri]
  }

  depends_on = [aws_cloudwatch_log_group.api, aws_iam_role_policy_attachment.vpc_access]
  tags       = merge(var.tags, { Name = "${var.name_prefix}-api" })
}

resource "aws_lambda_function" "worker" {
  function_name = "${var.name_prefix}-worker"
  role          = aws_iam_role.lambda_execution.arn
  package_type  = "Image"
  image_uri     = local.image_uri

  image_config {
    command = ["auditor.interfaces.aws_lambda.worker_handler.handler"]
  }

  timeout     = var.worker_timeout_seconds
  memory_size = var.worker_memory_mb

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = local.common_env
  }

  # O pipeline de deploy troca a imagem com update-function-code; sem isto um
  # terraform apply voltaria a função para var.image_tag (ADR-0021).
  lifecycle {
    ignore_changes = [image_uri]
  }

  depends_on = [aws_cloudwatch_log_group.worker, aws_iam_role_policy_attachment.vpc_access]
  tags       = merge(var.tags, { Name = "${var.name_prefix}-worker" })
}

resource "aws_lambda_function" "worker_dlq" {
  function_name = "${var.name_prefix}-worker-dlq"
  role          = aws_iam_role.lambda_execution.arn
  package_type  = "Image"
  image_uri     = local.image_uri

  image_config {
    command = ["auditor.interfaces.aws_lambda.worker_dlq_handler.handler"]
  }

  timeout     = var.worker_timeout_seconds
  memory_size = var.worker_memory_mb

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = local.common_env
  }

  # O pipeline de deploy troca a imagem com update-function-code; sem isto um
  # terraform apply voltaria a função para var.image_tag (ADR-0021).
  lifecycle {
    ignore_changes = [image_uri]
  }

  depends_on = [aws_cloudwatch_log_group.worker_dlq, aws_iam_role_policy_attachment.vpc_access]
  tags       = merge(var.tags, { Name = "${var.name_prefix}-worker-dlq" })
}

# --- Event source mappings: substituem o polling de
# AuditWorker._consume_jobs()/_consume_dead_letters() (Fase 5, EC2) --
# ver worker_handler.py/worker_dlq_handler.py.
resource "aws_lambda_event_source_mapping" "worker" {
  event_source_arn = var.queue_arn
  function_name    = aws_lambda_function.worker.arn
  batch_size       = var.worker_batch_size

  # Obrigatorio para o retorno {"batchItemFailures": [...]} do
  # worker_handler.py ter efeito -- sem isto, QUALQUER retorno nao-vazio do
  # handler faz a AWS reentregar o LOTE INTEIRO (mesmo as mensagens que
  # processaram com sucesso), nao so' as listadas em batchItemFailures.
  function_response_types = ["ReportBatchItemFailures"]
}

resource "aws_lambda_event_source_mapping" "worker_dlq" {
  event_source_arn = var.dead_letter_queue_arn
  function_name    = aws_lambda_function.worker_dlq.arn
  batch_size       = var.worker_batch_size

  function_response_types = ["ReportBatchItemFailures"]
}

resource "aws_cloudwatch_log_group" "admin" {
  name              = "/aws/lambda/${var.name_prefix}-admin"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

# A3: comandos administrativos (audit tenant register/rotate-keys, migrations)
# contra o RDS privado. Sem aws_lambda_permission, function URL, event source
# mapping ou target group: só um principal IAM com lambda:InvokeFunction
# nesta ARN (aws_iam_policy.admin_invoke) consegue invocar.
resource "aws_lambda_function" "admin" {
  function_name = "${var.name_prefix}-admin"
  role          = aws_iam_role.lambda_execution.arn
  package_type  = "Image"
  image_uri     = local.image_uri

  image_config {
    command = ["auditor.interfaces.aws_lambda.admin_handler.handler"]
  }

  timeout     = 900 # máximo do Lambda; invocação manual e rara, sem ALB para respeitar
  memory_size = var.worker_memory_mb

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id] # já liberado no RDS por rds_from_lambda
  }

  environment {
    variables = local.common_env
  }

  # O pipeline de deploy troca a imagem com update-function-code; sem isto um
  # terraform apply voltaria a função para var.image_tag (ADR-0021).
  lifecycle {
    ignore_changes = [image_uri]
  }

  depends_on = [aws_cloudwatch_log_group.admin, aws_iam_role_policy_attachment.vpc_access]
  tags       = merge(var.tags, { Name = "${var.name_prefix}-admin" })
}

resource "aws_iam_policy" "admin_invoke" {
  name        = "${var.name_prefix}-admin-invoke"
  description = "Permite invocar SOMENTE o Lambda administrativo (A3). Anexar ao usuário/grupo do operador."
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = aws_lambda_function.admin.arn
    }]
  })
  tags = var.tags
}

# --- Target group do ALB (target_type=lambda -- sem port/protocol/vpc_id,
# a integracao e' via API do Lambda, nao TCP) + permissao explicita para o
# ALB invocar a funcao. Ver modules/edge_alb para o listener HTTPS que
# encaminha para este target group.
resource "aws_lb_target_group" "api" {
  name        = "${var.name_prefix}-api-tg"
  target_type = "lambda"

  tags = var.tags
}

resource "aws_lambda_permission" "alb_invoke_api" {
  statement_id  = "AllowALBInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "elasticloadbalancing.amazonaws.com"
  source_arn    = aws_lb_target_group.api.arn
}

resource "aws_lb_target_group_attachment" "api" {
  target_group_arn = aws_lb_target_group.api.arn
  target_id        = aws_lambda_function.api.arn

  depends_on = [aws_lambda_permission.alb_invoke_api]
}
