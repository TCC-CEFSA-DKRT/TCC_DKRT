variable "region" {
  type    = string
  default = "us-east-1"
}

variable "name_prefix" {
  type    = string
  default = "auditor-dev"
}

variable "database_name" {
  type    = string
  default = "auditor"
}

variable "db_instance_class" {
  type    = string
  default = "db.t3.micro"
}

variable "api_instance_type" {
  description = "Host Docker da API (e do Orion de teste). A imagem carrega sentence-transformers/torch; t3.medium (4 GB) dá folga para API + Orion + Mongo."
  type        = string
  default     = "t3.medium"
}

variable "ollama_instance_type" {
  description = "Instância do Ollama. Em dev pode ser uma família sem GPU (ex.: t3.xlarge) para reduzir custo; nesse caso o Nível 2 roda em CPU e mais devagar."
  type        = string
  default     = "g4dn.xlarge"
}

variable "provision_ollama" {
  type    = bool
  default = true
}

variable "ollama_model" {
  type    = string
  default = "qwen2.5:3b-instruct"
}

variable "fiware_broker_url" {
  description = "URL do Orion auditado pelo dev."
  type        = string
  default     = "http://localhost:1026"
}

variable "deployment_mode" {
  description = "\"selfhosted\" (padrão) ou \"saas\" (ADR-0019)."
  type        = string
  default     = "selfhosted"
}

variable "key_name" {
  type    = string
  default = null
}

variable "ssh_cidr_blocks" {
  description = "CIDRs com SSH liberado. Vazio = sem SSH (acesso por SSM Session Manager)."
  type        = list(string)
  default     = []
}

variable "tags" {
  type = map(string)
  default = {
    Project     = "auditor-tcc"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}
