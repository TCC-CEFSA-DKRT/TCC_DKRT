# Compute EC2: API, worker e Ollama. Nos ambientes Lambda (homologação e
# produção, modules/stack_lambda) só o Ollama é provisionado aqui; no ambiente
# dev (EC2) a API roda como contêiner numa única instância (ADR-0021).
#
# create_role=true (padrão) cria a role/instance profile do ambiente.
# create_role=false permite informar um instance profile já existente em
# existing_instance_profile_name (referenciado por nome no aws_instance).

# --- IAM: só existe de fato quando create_role=true.

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
      var.database_secret_arn != null ? [
        {
          Effect   = "Allow"
          Action   = ["secretsmanager:GetSecretValue"]
          Resource = [var.database_secret_arn]
        },
      ] : [],
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

# Acesso por SSM Session Manager/Run Command (sem SSH) e leitura de imagens no
# ECR. O pipeline de deploy do dev usa SSM Run Command para trocar a imagem.
resource "aws_iam_role_policy_attachment" "ssm_core" {
  count      = var.create_role ? 1 : 0
  role       = aws_iam_role.instance_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "ecr_read" {
  count      = var.create_role ? 1 : 0
  role       = aws_iam_role.instance_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

locals {
  # Nome do instance profile efetivamente usado nas instâncias: o recém
  # criado ou o pré-existente informado.
  instance_profile_name = var.create_role ? aws_iam_instance_profile.instance_profile[0].name : var.existing_instance_profile_name

  common_env = {
    database_url         = var.database_url_template
    fiware_broker_url    = var.fiware_broker_url
    ollama_base_url      = var.provision_ollama ? "http://${aws_instance.ollama[0].private_ip}:11434" : "http://localhost:11434"
    ollama_model         = var.ollama_model
    queue_url            = var.queue_url
    cors_allowed_origins = var.cors_allowed_origins

    # Usados pelo user_data da API (contêiner, ADR-0021).
    aws_region          = var.aws_region
    deployment_mode     = var.deployment_mode
    database_host       = var.database_host
    database_port       = var.database_port
    database_name       = var.database_name
    database_secret_arn = var.database_secret_arn
  }
}

# ADR-0017: count em vez de recurso unico -- necessario para produção poder
# desativar a instancia EC2 (provision_api=false, ver variables.tf) quando
# a API passa a rodar como Lambda. O bloco `moved` abaixo evita que um
# ambiente que nao define provision_api (default true) sofra
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

  root_block_device {
    volume_size = var.api_root_volume_size
    # Sem repetir as tags aqui, o terraform apagaria as que o disco ja tem.
    tags = var.tags
  }

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
# start_ollama.sh/stop_ollama.sh (scripts/), fora do
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
