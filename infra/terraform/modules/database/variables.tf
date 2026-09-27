variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "security_group_id" {
  type = string
}

variable "engine_version" {
  description = <<-DESC
    Versão do PostgreSQL. pgvector está disponível no RDS a partir do
    PostgreSQL 15.2 (não requer shared_preload_libraries — é habilitado via
    `CREATE EXTENSION IF NOT EXISTS vector`, já feito pela migration do
    Fase 6, migrations/, que usa vector(384) para os embeddings do
    catálogo semântico — 384 dimensões porque o modelo de embeddings usado
    é local/pequeno, não os 768 de um modelo maior; ver
    docs/plano_refatoracao_v3.md, que ainda cita VECTOR(768) como
    placeholder desatualizado da fase de planejamento).
  DESC
  type    = string
  default = "15.7"
}

variable "instance_class" {
  description = "Menor classe elegível ao free tier / mais barata para um protótipo (db.t3.micro ou db.t4g.micro)."
  type        = string
  default     = "db.t3.micro"
}

variable "allocated_storage_gb" {
  type    = number
  default = 20
}

variable "database_name" {
  type    = string
  default = "auditor"
}

variable "master_username" {
  type    = string
  default = "auditor"
}

variable "manage_master_user_password" {
  description = <<-DESC
    Quando true, o RDS gerencia a senha automaticamente via Secrets Manager
    (sem senha em texto plano no state ou nas variáveis). Recomendado; exige
    permissão secretsmanager:CreateSecret além de rds:* — na Academy, a
    LabRole normalmente já inclui isso, mas se `terraform apply` falhar por
    permissão aqui, ajuste para false e forneça `master_password` via
    variável sensível/tfvars fora do controle de versão.
  DESC
  type    = bool
  default = true
}

variable "master_password" {
  description = "Usado apenas se manage_master_user_password = false. Nunca comitar um valor real; passar via TF_VAR_ ou .tfvars fora do git."
  type        = string
  default     = null
  sensitive   = true
}

variable "backup_retention_days" {
  type    = number
  default = 1
}

variable "skip_final_snapshot" {
  description = "true na Academy (sessões são efêmeras, sem necessidade de snapshot final); false em produção."
  type        = bool
  default     = true
}

variable "multi_az" {
  type    = bool
  default = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
