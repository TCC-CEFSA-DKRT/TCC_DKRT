# Ambiente dev (EC2), ADR-0021. Stack enxuta onde o Dev publica a branch de
# trabalho para o primeiro ciclo de testes do Q.A: uma instância EC2 roda a API
# (e o worker, no mesmo processo) como contêiner, o frontend fica num bucket S3
# com website hosting, e o Ollama roda numa instância própria. RDS e SQS são
# reais, como nos demais ambientes.

provider "aws" {
  region = var.region

  default_tags {
    tags = var.tags
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ADR-0015: AMI com driver NVIDIA/CUDA para o Ollama em instância g4dn.
data "aws_ami" "ollama_gpu" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

module "network" {
  source          = "../../modules/network"
  name_prefix     = var.name_prefix
  azs             = slice(data.aws_availability_zones.available.names, 0, 2)
  ssh_cidr_blocks = var.ssh_cidr_blocks
  tags            = var.tags
}

module "queue" {
  source      = "../../modules/queue"
  name_prefix = var.name_prefix
  tags        = var.tags
}

module "secrets" {
  source      = "../../modules/secrets"
  name_prefix = var.name_prefix
  tags        = var.tags
}

module "database" {
  source             = "../../modules/database"
  name_prefix        = var.name_prefix
  vpc_id             = module.network.vpc_id
  private_subnet_ids = module.network.private_subnet_ids
  security_group_id  = module.network.database_sg_id
  database_name      = var.database_name
  instance_class     = var.db_instance_class
  tags               = var.tags

  # Dev é descartável: sem snapshot final nem alta disponibilidade.
  skip_final_snapshot = true
  multi_az            = false
}

# Repositório da imagem da API (selfhosted/Dockerfile). Mesmo padrão de nome do
# ECR do stack Lambda (<prefixo>-auditor), para o pipeline tratar os ambientes
# do mesmo jeito.
resource "aws_ecr_repository" "app" {
  name                 = "${var.name_prefix}-auditor"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # dev descartável

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Mantém só as 20 imagens mais recentes (dev publica a cada deploy)"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 20
      }
      action = { type = "expire" }
    }]
  })
}

module "frontend" {
  source      = "../../modules/frontend_static_site"
  name_prefix = var.name_prefix
  tags        = var.tags
}

module "compute" {
  source = "../../modules/compute"

  name_prefix      = var.name_prefix
  vpc_id           = module.network.vpc_id
  public_subnet_id = module.network.public_subnet_ids[0]
  api_sg_id        = module.network.api_sg_id
  worker_sg_id     = module.network.worker_sg_id
  ollama_sg_id     = module.network.ollama_sg_id
  ami_id           = data.aws_ami.ubuntu.id
  ollama_ami_id    = data.aws_ami.ollama_gpu.id
  key_name         = var.key_name

  api_instance_type    = var.api_instance_type
  ollama_instance_type = var.ollama_instance_type
  provision_ollama     = var.provision_ollama
  ollama_model         = var.ollama_model

  # A API e o worker rodam no mesmo contêiner (a imagem sobe os dois), então
  # não há instância de worker separada.
  provision_api    = true
  provision_worker = false

  create_role = true

  queue_url                    = module.queue.queue_url
  queue_arn                    = module.queue.queue_arn
  database_url_template        = module.database.database_url_template
  orion_credentials_secret_arn = module.secrets.orion_credentials_secret_arn
  jwt_signing_key_secret_arn   = module.secrets.jwt_signing_key_secret_arn

  aws_region           = var.region
  fiware_broker_url    = var.fiware_broker_url
  cors_allowed_origins = module.frontend.website_url
  deployment_mode      = var.deployment_mode
  database_host        = module.database.endpoint
  database_port        = module.database.port
  database_name        = var.database_name
  database_secret_arn  = module.database.master_user_secret_arn

  tags = var.tags
}

# IP fixo para a API: sem ele o endereço muda a cada stop/start da instância e
# o frontend (que aponta para a URL da API) quebraria.
resource "aws_eip" "api" {
  instance = module.compute.api_instance_id
  domain   = "vpc"

  tags = merge(var.tags, { Name = "${var.name_prefix}-api" })
}
