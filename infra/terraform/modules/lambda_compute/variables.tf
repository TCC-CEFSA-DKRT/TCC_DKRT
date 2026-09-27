variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  description = "Subnets privadas onde os ENIs do Lambda sao criados -- mesmas subnets do RDS (modules/network); precisam de rota de saida (NAT, enable_nat_gateway=true) e dos VPC endpoints (modules/vpc_endpoints) para o Lambda funcionar."
  type        = list(string)
}

variable "image_tag" {
  description = "Tag da imagem no ECR (este modulo cria o repositorio, mas NAO builda/publica a imagem -- isso e' um passo de deploy separado, `docker build && docker push`, fora do terraform apply, mesmo espirito do fluxo de segredos de modules/secrets/modules/parameter_store)."
  type        = string
  default     = "latest"
}

variable "api_timeout_seconds" {
  type    = number
  default = 29 # limite do target type "lambda" de um ALB (30s) -- 29 deixa 1s de margem.
}

variable "api_memory_mb" {
  type    = number
  default = 512
}

variable "worker_timeout_seconds" {
  description = "Bem mais generoso que o da API -- process() percorre TODAS as entidades do run (Nivel 1 + Nivel 2/SLM por entidade, ADR-0014), sem limite de tempo do ALB para respeitar."
  type        = number
  default     = 300
}

variable "worker_memory_mb" {
  description = "Maior que a API: carrega sentence-transformers/torch em memoria (PgVectorRetriever/SentenceTransformersEmbedder) a cada cold start."
  type        = number
  default     = 1024
}

variable "worker_batch_size" {
  type    = number
  default = 1
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "fiware_broker_url" {
  description = "Sobrescrito por tfvars do cliente real -- mesmo placeholder de modules/compute (local.common_env.fiware_broker_url)."
  type        = string
  default     = "http://localhost:1026"
}

variable "ollama_base_url" {
  type = string
}

variable "ollama_model" {
  type = string
}

variable "cors_allowed_origins" {
  description = "Dominio do frontend (CloudFront, modules/frontend_delivery) -- ver environments/production/main.tf."
  type        = string
}

variable "queue_url" {
  type = string
}

variable "queue_arn" {
  type = string
}

variable "dead_letter_queue_url" {
  type = string
}

variable "dead_letter_queue_arn" {
  type = string
}

variable "db_host" {
  type = string
}

variable "db_port" {
  type = number
}

variable "db_name" {
  type = string
}

variable "db_master_user_secret_arn" {
  type = string
}

variable "orion_credentials_parameter_name" {
  type = string
}

variable "orion_credentials_parameter_arn" {
  type = string
}

variable "jwt_signing_key_parameter_name" {
  type = string
}

variable "jwt_signing_key_parameter_arn" {
  type = string
}

variable "broker_api_key_encryption_keys_parameter_name" {
  type = string
}

variable "broker_api_key_encryption_keys_parameter_arn" {
  type = string
}

variable "deployment_mode" {
  description = "ADR-0019: \"saas\" exige JWT_SIGNING_KEY/BROKER_API_KEY_ENCRYPTION_KEYS reais (Settings valida em runtime, ver secrets_bootstrap.py); \"selfhosted\" (default) e' o comportamento de hoje."
  type        = string
  default     = "selfhosted"

  validation {
    condition     = contains(["saas", "selfhosted"], var.deployment_mode)
    error_message = "deployment_mode deve ser \"saas\" ou \"selfhosted\"."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}
