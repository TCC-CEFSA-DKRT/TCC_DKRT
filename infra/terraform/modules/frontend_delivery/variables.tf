variable "name_prefix" {
  type = string
}

variable "domain_name" {
  description = "Dominio do frontend (ex.: \"app.auditor-tcc.exemplo.com\"). Sem default -- mesmo motivo de modules/edge_alb.domain_name: nenhum dominio real foi registrado neste projeto (AWS Academy Learner Lab)."
  type        = string
}

variable "route53_zone_id" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
