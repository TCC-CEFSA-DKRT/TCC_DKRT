# Ambiente de produção: NÃO usado neste TCC (que roda inteiramente na AWS
# Academy Learner Lab). Mantido para mostrar que a mesma base de módulos
# suporta uma conta AWS real, sem as restrições da Academy. Nunca aplicado
# neste projeto: escrito e validado localmente (python-hcl2, já que o
# binário terraform não pôde ser baixado neste ambiente de execução --
# releases.hashicorp.com bloqueado pelo proxy de saída), não contra uma
# conta AWS de produção real, e nunca incluído no `terraform plan` do CI
# (.github/workflows/terraform-and-audit.yml só valida environments/academy).
#
# ADR-0017 (ver docs/adr/adr-0017.md): principal diferença em relação à
# Academy deixa de ser só create_role=true/multi_az=true/
# skip_final_snapshot=false -- agora também: API e worker rodam como
# Lambda (imagem de contêiner) atrás de um ALB com HTTPS/ACM, o frontend
# (Fase 8) é servido via CloudFront+S3, os segredos do próprio projeto
# (credenciais do Orion, chave JWT) ficam no Parameter Store em vez do
# Secrets Manager, e a VPC ganha um NAT gateway + VPC endpoints (SQS/SSM)
# para o Lambda alcançar o que precisa de dentro da VPC. Ollama continua em
# EC2 (modules/compute), inalterado -- decisão própria (ADR-0013), não uma
# limitação técnica do Lambda.
#
# Domínio real necessário: var.domain_name/var.route53_zone_id (sem
# default, ver modules/edge_alb e modules/frontend_delivery) -- este
# projeto nunca registrou um domínio próprio. Fornecer via tfvars/-var
# antes de um `terraform apply` real.

provider "aws" {
  region = var.region
}

# ADR-0017: certificados ACM usados por uma distribuição CloudFront têm que
# existir em us-east-1, independente da região do resto do stack (ver
# modules/frontend_delivery).
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
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

# Gap pre-existente encontrado ao implementar ADR-0017: este ambiente nunca
# resolvia uma AMI com driver NVIDIA/CUDA para o Ollama (ao contrário de
# environments/academy/main.tf, que já faz isso desde a adr-0015) -- o
# `module.compute` abaixo usaria data.aws_ami.ubuntu (genérica) mesmo com
# ollama_instance_type default = g4dn.xlarge, exatamente o cenário que
# adr-0015 avisa: GPU fisicamente presente, mas ociosa, Ollama rodando em
# CPU sem avisar. Corrigido aqui, mesmo filtro da Academy.
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
  source      = "../../modules/network"
  name_prefix = var.name_prefix
  azs         = slice(data.aws_availability_zones.available.names, 0, 2)
  tags        = var.tags

  # ADR-0017: o Lambda de produção fica dentro da VPC (RDS/Ollama por IP
  # privado) -- precisa de uma rota de saída para o Orion do cliente e o
  # Secrets Manager (RDS-managed secret). Ver modules/network/main.tf.
  enable_nat_gateway = true
}

module "queue" {
  source      = "../../modules/queue"
  name_prefix = var.name_prefix
  tags        = var.tags
}

# ADR-0017: os segredos do próprio projeto (credenciais do Orion, chave
# JWT) migram para Parameter Store em produção -- modules/secrets
# (Secrets Manager) não é mais instanciado aqui. O RDS continua usando o
# Secrets Manager também (manage_master_user_password=true, abaixo), mas
# isso é uma decisão da própria feature do RDS, independente desta.
module "parameter_store" {
  source      = "../../modules/parameter_store"
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
  tags               = var.tags

  skip_final_snapshot = false
  multi_az            = true
}

module "vpc_endpoints" {
  source              = "../../modules/vpc_endpoints"
  name_prefix         = var.name_prefix
  region              = var.region
  vpc_id              = module.network.vpc_id
  private_subnet_ids  = module.network.private_subnet_ids
  lambda_sg_id         = module.lambda_compute.lambda_sg_id
  tags                = var.tags
}

module "frontend_delivery" {
  source = "../../modules/frontend_delivery"

  providers = {
    aws.us_east_1 = aws.us_east_1
  }

  name_prefix     = var.name_prefix
  domain_name     = var.frontend_domain_name
  route53_zone_id = var.route53_zone_id
  tags            = var.tags
}

module "lambda_compute" {
  source = "../../modules/lambda_compute"

  name_prefix        = var.name_prefix
  vpc_id             = module.network.vpc_id
  private_subnet_ids = module.network.private_subnet_ids
  image_tag          = var.lambda_image_tag

  fiware_broker_url    = var.fiware_broker_url
  ollama_base_url      = "http://${module.compute.ollama_private_ip}:11434"
  ollama_model         = var.ollama_model
  cors_allowed_origins = module.frontend_delivery.frontend_url

  queue_url              = module.queue.queue_url
  queue_arn              = module.queue.queue_arn
  dead_letter_queue_url  = module.queue.dlq_url
  dead_letter_queue_arn  = module.queue.dlq_arn

  db_host                   = module.database.endpoint
  db_port                   = module.database.port
  db_name                   = var.database_name
  db_master_user_secret_arn = module.database.master_user_secret_arn

  orion_credentials_parameter_name = module.parameter_store.orion_credentials_parameter_name
  orion_credentials_parameter_arn  = module.parameter_store.orion_credentials_parameter_arn
  jwt_signing_key_parameter_name   = module.parameter_store.jwt_signing_key_parameter_name
  jwt_signing_key_parameter_arn    = module.parameter_store.jwt_signing_key_parameter_arn

  tags = var.tags
}

# Regra isolada em vez de editar modules/network/modules/database: o SG do
# RDS (aws_security_group.database, criado dentro de modules/network) só
# aceitava tráfego dos SGs de API/worker EC2 (Fase 9) -- precisa aceitar
# também do novo SG do Lambda. Uma aws_security_group_rule à parte, aqui no
# ambiente que efetivamente usa Lambda, evita qualquer risco de regressão
# na Academy (que nunca instancia modules/lambda_compute e continua com o
# SG do RDS exatamente como estava).
resource "aws_security_group_rule" "rds_from_lambda" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = module.network.database_sg_id
  source_security_group_id = module.lambda_compute.lambda_sg_id
  description              = "Postgres a partir do Lambda de producao (ADR-0017)"
}

module "edge_alb" {
  source = "../../modules/edge_alb"

  name_prefix           = var.name_prefix
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  domain_name           = var.api_domain_name
  route53_zone_id       = var.route53_zone_id
  api_target_group_arn  = module.lambda_compute.api_target_group_arn

  tags = var.tags
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
  provision_ollama = var.provision_ollama
  ollama_model     = var.ollama_model

  # ADR-0017: API e worker migram para Lambda (module.lambda_compute,
  # acima) -- este módulo, em produção, existe só para o Ollama.
  provision_api    = false
  provision_worker = false

  # Produção: conta real, sem restrição da Academy -- cria a própria role
  # com permissões mínimas em vez de reusar LabRole/LabInstanceProfile.
  create_role = true

  # queue_url/queue_arn/database_url_template/orion_credentials_secret_arn/
  # jwt_signing_key_secret_arn ficam nos defaults (não usados -- só a
  # instância Ollama é provisionada aqui; os dois primeiros são
  # necessários pelo módulo mesmo sem API/worker EC2, os dois últimos são
  # null por padrão desde ADR-0017, ver modules/compute/variables.tf).
  queue_url              = module.queue.queue_url
  queue_arn              = module.queue.queue_arn
  database_url_template  = module.database.database_url_template

  tags = var.tags
}
