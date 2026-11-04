# Ambiente de homologação (espelho da produção, menor e sem alta disponibilidade): stack Lambda (ADR-0017) compartilhada com os demais
# ambientes Lambda via modules/stack_lambda (ADR-0021). Este arquivo só
# escolhe os valores que diferenciam o ambiente.

provider "aws" {
  region = var.region

  default_tags {
    tags = var.tags
  }
}

# Certificados ACM usados por uma distribuição CloudFront têm que existir em
# us-east-1, qualquer que seja a região do restante do stack.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = var.tags
  }
}

module "stack" {
  source = "../../modules/stack_lambda"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  name_prefix = var.name_prefix
  region      = var.region
  tags        = var.tags

  api_domain_name      = var.api_domain_name
  frontend_domain_name = var.frontend_domain_name
  route53_zone_id      = var.route53_zone_id

  deployment_mode   = var.deployment_mode
  fiware_broker_url = var.fiware_broker_url
  lambda_image_tag  = var.lambda_image_tag
  database_name     = var.database_name

  log_retention_days = 14

  # Dados: homologação (espelho da produção, menor e sem alta disponibilidade).
  db_instance_class        = var.db_instance_class
  db_multi_az              = false
  db_skip_final_snapshot   = true
  db_backup_retention_days = 1

  provision_ollama     = var.provision_ollama
  ollama_instance_type = var.ollama_instance_type
  ollama_model         = var.ollama_model
  key_name             = var.key_name
}
