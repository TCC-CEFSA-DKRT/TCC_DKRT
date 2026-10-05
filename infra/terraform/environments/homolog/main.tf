provider "aws" {
  region = var.region
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

# adr-0015: AMI dedicada para a instância Ollama (g4dn.xlarge). A AMI Ubuntu
# genérica acima (data.aws_ami.ubuntu) não traz driver NVIDIA/CUDA -- numa
# instância com GPU física presente, o Ollama simplesmente rodaria em CPU
# sem avisar. A "Deep Learning Base OSS Nvidia Driver GPU AMI" da própria
# AWS já vem com driver + CUDA instalados e é publicada/atualizada
# regularmente pela AWS para a família Ubuntu 22.04, com suporte
# confirmado a instâncias G4dn.
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

# Conta AWS real (não Academy -- ADR-0018): cria a própria IAM role/instance
# profile via create_role=true, sem depender de um instance profile
# pré-existente de laboratório (padrão create_role/existing_role_arn,
# fase9.spec.md secao 2.5, permanece genérico no módulo -- só o valor
# passado aqui muda).

module "network" {
  source      = "../../modules/network"
  name_prefix = var.name_prefix
  azs         = slice(data.aws_availability_zones.available.names, 0, 2)
  tags        = var.tags
}

module "queue" {
  source      = "../../modules/queue"
  name_prefix = var.name_prefix
  tags        = var.tags
  # max_receive_count usa o default do módulo (3), sincronizado manualmente
  # com LocalJobQueue.max_retries -- ver modules/queue/variables.tf.
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
  tags               = var.tags

  # Homologacao: sem necessidade de snapshot final nem multi-AZ (custo
  # desnecessario para um ambiente de staging de TCC, nao producao).
  skip_final_snapshot = true
  multi_az            = false
}

module "compute" {
  source = "../../modules/compute"

  name_prefix       = var.name_prefix
  vpc_id            = module.network.vpc_id
  public_subnet_id  = module.network.public_subnet_ids[0]
  api_sg_id         = module.network.api_sg_id
  worker_sg_id      = module.network.worker_sg_id
  ollama_sg_id      = module.network.ollama_sg_id
  ami_id            = data.aws_ami.ubuntu.id
  ollama_ami_id     = data.aws_ami.ollama_gpu.id
  key_name          = var.key_name
  provision_ollama  = var.provision_ollama
  ollama_model      = var.ollama_model

  # Padrão create_role/existing_role_arn: conta real cria a própria role.
  create_role = true

  queue_url                     = module.queue.queue_url
  queue_arn                     = module.queue.queue_arn
  database_url_template         = module.database.database_url_template
  orion_credentials_secret_arn  = module.secrets.orion_credentials_secret_arn
  jwt_signing_key_secret_arn    = module.secrets.jwt_signing_key_secret_arn

  tags = var.tags
}
