# Fase 9 (.cursor/specs/fase9.spec.md, secao 2.5) -- compute EC2 para API,
# worker e Ollama, com padrão create_role/existing_role_arn para lidar com
# a restrição da AWS Academy Learner Lab (iam:CreateRole bloqueado).

# --- IAM: só existe de fato quando create_role=true (produção). Na Academy
# (create_role=false), usamos o instance profile "LabInstanceProfile" já
# existente na conta via data source no próprio ambiente chamador
# (environments/academy/main.tf) e passamos o NOME dele diretamente --
# instance profiles são referenciados por nome no aws_instance, não por ARN.

resource "aws_iam_role" "instance_role" {
  count = var.create_role ? 1 : 0
  name  = "${var.name_prefix}-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "instance_policy" {
  count = var.create_role ? 1 : 0
  name  = "${var.name_prefix}-ec2-policy"
  role  = aws_iam_role.instance_role[0].id

  # Permissões mínimas: SQS (consumir/publicar jobs) + leitura dos segredos
  # necessários para montar DATABASE_URL/credenciais do Orion. A statement
  # de secretsmanager só entra quando os dois ARNs são informados (ver
  # variables.tf) -- produção (ADR-0017) usa este módulo só para o Ollama,
  # que não lê nenhum dos dois segredos.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Effect = "Allow"
          Action = [
            "sqs:SendMessage",
            "sqs:ReceiveMessage",
            "sqs:DeleteMessage",
            "sqs:GetQueueAttributes",
            "sqs:ChangeMessageVisibility",
          ]
          Resource = [var.queue_arn]
        },
      ],
      var.orion_credentials_secret_arn != null && var.jwt_signing_key_secret_arn != null ? [
        {
          Effect = "Allow"
          Action = ["secretsmanager:GetSecretValue"]
          Resource = [
            var.orion_credentials_secret_arn,
            var.jwt_signing_key_secret_arn,
          ]
        },
      ] : []
    )
  })
}

resource "aws_iam_instance_profile" "instance_profile" {
  count = var.create_role ? 1 : 0
  name  = "${var.name_prefix}-ec2-profile"
  role  = aws_iam_role.instance_role[0].name
}

locals {
  # Nome do instance profile efetivamente usado nas instâncias: o recém
  # criado (produção) ou o pré-existente informado (Academy: LabInstanceProfile).
  instance_profile_name = var.create_role ? aws_iam_instance_profile.instance_profile[0].name : var.existing_instance_profile_name

  common_env = {
    database_url          = var.database_url_template
    fiware_broker_url     = "http://localhost:1026" # sobrescrito por variável de ambiente/tfvars do cliente real
    ollama_base_url       = var.provision_ollama ? "http://${aws_instance.ollama[0].private_ip}:11434" : "http://localhost:11434"
    ollama_model          = var.ollama_model
    queue_url             = var.queue_url
    cors_allowed_origins  = "http://localhost:4200"
  }
}

# ADR-0017: count em vez de recurso unico -- necessario para produção poder
# desativar a instancia EC2 (provision_api=false, ver variables.tf) quando
# a API passa a rodar como Lambda. O bloco `moved` abaixo evita que a
# Academy (que nao define provision_api, fica no default true) sofra
# destroy+recreate so' por causa da mudanca de endereco do recurso
# (aws_instance.api -> aws_instance.api[0]) -- o objeto real na AWS
# continua sendo o mesmo.
resource "aws_instance" "api" {
  count = var.provision_api ? 1 : 0

  ami                    = var.ami_id
  instance_type          = var.api_instance_type
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [var.api_sg_id]
  iam_instance_profile   = local.instance_profile_name
  key_name               = var.key_name

  user_data = templatefile("${path.module}/user_data/api.sh.tftpl", local.common_env)

  tags = merge(var.tags, { Name = "${var.name_prefix}-api" })
}

moved {
  from = aws_instance.api
  to   = aws_instance.api[0]
}

resource "aws_instance" "worker" {
  count = var.provision_worker ? 1 : 0

  ami                    = var.ami_id
  instance_type          = var.worker_instance_type
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [var.worker_sg_id]
  iam_instance_profile   = local.instance_profile_name
  key_name               = var.key_name

  user_data = templatefile("${path.module}/user_data/worker.sh.tftpl", local.common_env)

  tags = merge(var.tags, { Name = "${var.name_prefix}-worker" })
}

moved {
  from = aws_instance.worker
  to   = aws_instance.worker[0]
}

# Instância Ollama: NUNCA iniciada automaticamente em todo `apply` -- ela
# nasce ligada (para o `ollama pull` do user_data rodar uma vez), mas a
# partir daí seu estado ligado/desligado é gerenciado pelos scripts
# start_ollama.sh/stop_ollama.sh (environments/academy/scripts/), fora do
# Terraform, porque `aws_instance` não tem um argumento de "estado
# desejado" -- só existe/não existe. Ver docs/decisions/0001-ollama-ec2-vs-bedrock.md.
resource "aws_instance" "ollama" {
  count = var.provision_ollama ? 1 : 0

  # adr-0015: AMI própria (com driver NVIDIA/CUDA) quando ollama_ami_id é
  # informado -- necessário para instance types com GPU (g4dn.*). Cai de
  # volta para var.ami_id (Ubuntu genérico) só quando ollama_ami_id é null,
  # o que só é seguro junto com um ollama_instance_type sem GPU.
  ami                    = coalesce(var.ollama_ami_id, var.ami_id)
  instance_type          = var.ollama_instance_type
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [var.ollama_sg_id]
  iam_instance_profile   = local.instance_profile_name
  key_name               = var.key_name

  root_block_device {
    volume_size = 60 # pesos do modelo + imagem base do Ollama + driver/CUDA da Deep Learning AMI (adr-0015; era 40 antes da GPU)
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/user_data/ollama.sh.tftpl", {
    ollama_model = var.ollama_model
  })

  tags = merge(var.tags, { Name = "${var.name_prefix}-ollama" })
}
