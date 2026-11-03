# Stack "Lambda": API + worker em AWS Lambda (imagem de contêiner) atrás de um
# ALB com HTTPS, frontend em CloudFront + S3, fila SQS, RDS PostgreSQL com
# pgvector e Ollama em EC2 (GPU). É a arquitetura da ADR-0017, compartilhada
# pelos ambientes de homologação e produção (ADR-0021): as duas pastas em
# environments/ só diferem nos valores que passam para este módulo (tamanho,
# alta disponibilidade, domínios). Assim, a homologação valida exatamente o
# desenho que vai ao ar, e não uma aproximação dele.
#
# O ambiente chamador precisa declarar o provider padrão e o alias
# aws.us_east_1 (certificados ACM do CloudFront só existem nessa região):
#
#   providers = {
#     aws           = aws
#     aws.us_east_1 = aws.us_east_1
#   }

terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      configuration_aliases = [aws.us_east_1]
    }
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

# ADR-0015: AMI com driver NVIDIA/CUDA para a instância Ollama (g4dn). Com a
# AMI Ubuntu genérica a GPU ficaria ociosa e o Ollama rodaria em CPU sem avisar.
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
  source      = "../network"
  name_prefix = var.name_prefix
  azs         = slice(data.aws_availability_zones.available.names, 0, 2)
  tags        = var.tags

  # O Lambda roda dentro da VPC (RDS e Ollama por IP privado) e precisa de
  # uma rota de saída para o Orion do cliente. Ver modules/network.
  enable_nat_gateway = var.enable_nat_gateway
}

module "queue" {
  source      = "../queue"
  name_prefix = var.name_prefix
  tags        = var.tags
}

# Segredos do projeto (credenciais do Orion, chave JWT, chaves Fernet) ficam no
# Parameter Store (ADR-0017). A senha do RDS fica no Secrets Manager, por
# decisão da própria feature manage_master_user_password do RDS.
module "parameter_store" {
  source      = "../parameter_store"
  name_prefix = var.name_prefix
  tags        = var.tags
}

module "database" {
  source             = "../database"
  name_prefix        = var.name_prefix
  vpc_id             = module.network.vpc_id
  private_subnet_ids = module.network.private_subnet_ids
  security_group_id  = module.network.database_sg_id
  database_name      = var.database_name
  instance_class     = var.db_instance_class
  tags               = var.tags

  backup_retention_days = var.db_backup_retention_days
  skip_final_snapshot   = var.db_skip_final_snapshot
  multi_az              = var.db_multi_az
}

module "vpc_endpoints" {
  source             = "../vpc_endpoints"
  name_prefix        = var.name_prefix
  region             = var.region
  vpc_id             = module.network.vpc_id
  private_subnet_ids = module.network.private_subnet_ids
  lambda_sg_id       = module.lambda_compute.lambda_sg_id
  tags               = var.tags
}

module "frontend_delivery" {
  source = "../frontend_delivery"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  name_prefix     = var.name_prefix
  domain_name     = var.frontend_domain_name
  route53_zone_id = var.route53_zone_id
  tags            = var.tags
}

module "lambda_compute" {
  source = "../lambda_compute"

  name_prefix        = var.name_prefix
  vpc_id             = module.network.vpc_id
  private_subnet_ids = module.network.private_subnet_ids
  image_tag          = var.lambda_image_tag
  log_retention_days = var.log_retention_days

  deployment_mode      = var.deployment_mode
  fiware_broker_url    = var.fiware_broker_url
  ollama_base_url      = "http://${module.compute.ollama_private_ip}:11434"
  ollama_model         = var.ollama_model
  cors_allowed_origins = module.frontend_delivery.frontend_url

  queue_url             = module.queue.queue_url
  queue_arn             = module.queue.queue_arn
  dead_letter_queue_url = module.queue.dlq_url
  dead_letter_queue_arn = module.queue.dlq_arn

  db_host                   = module.database.endpoint
  db_port                   = module.database.port
  db_name                   = var.database_name
  db_master_user_secret_arn = module.database.master_user_secret_arn

  orion_credentials_parameter_name              = module.parameter_store.orion_credentials_parameter_name
  orion_credentials_parameter_arn               = module.parameter_store.orion_credentials_parameter_arn
  jwt_signing_key_parameter_name                = module.parameter_store.jwt_signing_key_parameter_name
  jwt_signing_key_parameter_arn                 = module.parameter_store.jwt_signing_key_parameter_arn
  broker_api_key_encryption_keys_parameter_name = module.parameter_store.broker_api_key_encryption_keys_parameter_name
  broker_api_key_encryption_keys_parameter_arn  = module.parameter_store.broker_api_key_encryption_keys_parameter_arn

  tags = var.tags
}

# O SG do RDS (criado em modules/network) só aceita tráfego dos SGs das EC2.
# Uma regra isolada aqui libera o SG do Lambda sem alterar o módulo de rede,
# que o ambiente dev (EC2) também usa.
resource "aws_security_group_rule" "rds_from_lambda" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = module.network.database_sg_id
  source_security_group_id = module.lambda_compute.lambda_sg_id
  description              = "Postgres a partir do Lambda (ADR-0017)"
}

module "edge_alb" {
  source = "../edge_alb"

  name_prefix          = var.name_prefix
  vpc_id               = module.network.vpc_id
  public_subnet_ids    = module.network.public_subnet_ids
  domain_name          = var.api_domain_name
  route53_zone_id      = var.route53_zone_id
  api_target_group_arn = module.lambda_compute.api_target_group_arn

  tags = var.tags
}

# Neste stack o módulo compute existe só para o Ollama: API e worker são Lambda.
module "compute" {
  source = "../compute"

  name_prefix          = var.name_prefix
  vpc_id               = module.network.vpc_id
  public_subnet_id     = module.network.public_subnet_ids[0]
  api_sg_id            = module.network.api_sg_id
  worker_sg_id         = module.network.worker_sg_id
  ollama_sg_id         = module.network.ollama_sg_id
  ami_id               = data.aws_ami.ubuntu.id
  ollama_ami_id        = data.aws_ami.ollama_gpu.id
  ollama_instance_type = var.ollama_instance_type
  key_name             = var.key_name
  provision_ollama     = var.provision_ollama
  ollama_model         = var.ollama_model

  provision_api    = false
  provision_worker = false

  # Conta AWS real: cria a própria role.
  create_role = true

  # Exigidos pelo módulo mesmo sem API/worker; os segredos do Secrets Manager
  # ficam nulos porque o Ollama não os lê.
  queue_url             = module.queue.queue_url
  queue_arn             = module.queue.queue_arn
  database_url_template = module.database.database_url_template

  tags = var.tags
}
