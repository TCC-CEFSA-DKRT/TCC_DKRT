variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "auditor-prod"
}

variable "key_name" {
  type    = string
  default = null
}

variable "ollama_model" {
  type    = string
  default = "qwen2.5:3b-instruct"
}

variable "provision_ollama" {
  type    = bool
  default = true
}

variable "database_name" {
  description = "Repassado para modules/database E modules/lambda_compute (DB_NAME) -- fonte única, em vez de cada um usar o próprio default e arriscar divergir."
  type        = string
  default     = "auditor"
}

variable "fiware_broker_url" {
  description = "URL do Orion do cliente real -- sobrescrever via tfvars antes de um apply real (mesmo placeholder de modules/compute)."
  type        = string
  default     = "http://localhost:1026"
}

variable "lambda_image_tag" {
  description = "Tag da imagem publicada no ECR (modules/lambda_compute) -- ver Dockerfile na raiz do repo. O build/push da imagem é um passo de deploy manual, fora do terraform apply (mesmo espírito do fluxo de segredos)."
  type        = string
  default     = "latest"
}

variable "deployment_mode" {
  description = "ADR-0019: \"saas\" ou \"selfhosted\" -- repassado a modules/lambda_compute, que já valida o valor (sem validation aqui para não duplicar)."
  type        = string
  default     = "selfhosted"
}

# --- ADR-0017: domínio real, necessário para ACM/Route53 (modules/edge_alb,
# modules/frontend_delivery). Nenhum dos três tem default -- este projeto
# (AWS Academy Learner Lab) nunca registrou um domínio próprio; fornecer
# via tfvars/-var no dia em que houver um domínio real e um hosted zone já
# delegado a ele.

variable "api_domain_name" {
  description = "Domínio da API (ex.: \"api.auditor-tcc.exemplo.com\"), delegado a var.route53_zone_id."
  type        = string
}

variable "frontend_domain_name" {
  description = "Domínio do frontend (ex.: \"app.auditor-tcc.exemplo.com\"), delegado a var.route53_zone_id."
  type        = string
}

variable "route53_zone_id" {
  description = "Hosted zone (Route53) onde api_domain_name/frontend_domain_name estão delegados."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = { Project = "auditor-tcc", Environment = "production" }
}
