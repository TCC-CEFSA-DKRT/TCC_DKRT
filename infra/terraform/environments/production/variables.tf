variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "auditor-prod"
}

variable "api_domain_name" {
  description = "Domínio da API, delegado a var.route53_zone_id."
  type        = string
}

variable "frontend_domain_name" {
  description = "Domínio do frontend, delegado a var.route53_zone_id."
  type        = string
}

variable "route53_zone_id" {
  type = string
}

variable "deployment_mode" {
  description = "\"saas\" ou \"selfhosted\" (ADR-0019)."
  type        = string
  default     = "selfhosted"
}

variable "fiware_broker_url" {
  description = "URL do Orion auditado por este ambiente."
  type        = string
  default     = "http://localhost:1026"
}

variable "lambda_image_tag" {
  description = "Tag usada só na criação das funções; depois o pipeline de deploy troca a imagem."
  type        = string
  default     = "bootstrap"
}

variable "database_name" {
  type    = string
  default = "auditor"
}

variable "db_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "provision_ollama" {
  type    = bool
  default = true
}

variable "ollama_instance_type" {
  type    = string
  default = "g4dn.xlarge"
}

variable "ollama_model" {
  type    = string
  default = "qwen2.5:3b-instruct"
}

variable "key_name" {
  type    = string
  default = null
}

variable "tags" {
  type = map(string)
  default = {
    Project     = "auditor-tcc"
    Environment = "production"
    ManagedBy   = "terraform"
  }
}
