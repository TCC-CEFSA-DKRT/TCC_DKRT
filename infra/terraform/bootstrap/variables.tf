variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  description = "Prefixo dos recursos compartilhados (buckets, tabela de lock, papéis)."
  type        = string
  default     = "auditor"
}

variable "github_repository" {
  description = "Repositório que pode assumir os papéis, no formato organização/nome."
  type        = string
  default     = "TCC-CEFSA-DKRT/TCC_DKRT"
}

variable "create_oidc_provider" {
  description = "false se a conta já tem o provedor OIDC do GitHub (só pode existir um por conta); ele é então só consultado."
  type        = bool
  default     = true
}

variable "environments" {
  description = "Ambientes da conta. name_prefix deve ser igual ao name_prefix do ambiente em infra/terraform/environments/<chave>; github_environment é o nome do GitHub Environment de deploy."
  type = map(object({
    name_prefix        = string
    github_environment = string
  }))
  default = {
    dev        = { name_prefix = "auditor-dev", github_environment = "dev" }
    homolog    = { name_prefix = "auditor-homolog", github_environment = "homologacao" }
    production = { name_prefix = "auditor-prod", github_environment = "producao" }
  }
}
