variable "name_prefix" {
  description = "Prefixo de todos os recursos do ambiente (ex.: auditor-homolog, auditor-prod). Separa os ambientes dentro da mesma conta AWS."
  type        = string
}

variable "region" {
  description = "Região AWS do stack (a do provider padrão do ambiente chamador)."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

# --- Domínios (ACM + Route53) ---
variable "api_domain_name" {
  description = "Domínio da API (ex.: api.homolog.exemplo.com), delegado a var.route53_zone_id."
  type        = string
}

variable "frontend_domain_name" {
  description = "Domínio do frontend (ex.: app.homolog.exemplo.com), delegado a var.route53_zone_id."
  type        = string
}

variable "route53_zone_id" {
  description = "Hosted zone (Route53) onde os dois domínios estão delegados."
  type        = string
}

# --- Aplicação ---
variable "deployment_mode" {
  description = "ADR-0019: \"saas\" ou \"selfhosted\" (validado em modules/lambda_compute)."
  type        = string
  default     = "selfhosted"
}

variable "fiware_broker_url" {
  description = "URL do Orion que o ambiente audita."
  type        = string
  default     = "http://localhost:1026"
}

variable "lambda_image_tag" {
  description = "Tag da imagem no ECR usada na CRIAÇÃO das funções. Depois disso o pipeline de deploy troca a imagem (update-function-code) e o Terraform ignora a mudança (lifecycle.ignore_changes em modules/lambda_compute)."
  type        = string
  default     = "bootstrap"
}

variable "log_retention_days" {
  type    = number
  default = 14
}

# --- Dados e rede (a única diferença estrutural entre homologação e produção) ---
variable "database_name" {
  description = "Repassado ao RDS e ao Lambda (DB_NAME), para não haver duas fontes."
  type        = string
  default     = "auditor"
}

variable "db_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "db_skip_final_snapshot" {
  type    = bool
  default = true
}

variable "db_backup_retention_days" {
  type    = number
  default = 1
}

variable "enable_nat_gateway" {
  description = "Rota de saída do Lambda (dentro da VPC) para o Orion do cliente e o Secrets Manager. Custo fixo mensal; só desligue se o Orion for alcançável por endpoint privado."
  type        = bool
  default     = true
}

# --- Ollama (SLM) ---
variable "provision_ollama" {
  type    = bool
  default = true
}

variable "ollama_instance_type" {
  description = "g4dn.xlarge (GPU) por padrão, ver ADR-0015. Em homologação pode-se usar família sem GPU se ollama_ami_id não for necessário; ligar/desligar com scripts/start_ollama.sh e stop_ollama.sh."
  type        = string
  default     = "g4dn.xlarge"
}

variable "ollama_model" {
  type    = string
  default = "qwen2.5:3b-instruct"
}

variable "key_name" {
  description = "Key pair EC2 existente (opcional). O acesso padrão deve ser por SSM, sem SSH."
  type        = string
  default     = null
}
