variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  description = "Pelo menos 2 subnets publicas em AZs diferentes -- exigencia do ALB."
  type        = list(string)
}

variable "domain_name" {
  description = <<-DESC
    Dominio da API (ex.: "api.auditor-tcc.exemplo.com"), delegado ao
    Route53 hosted zone de var.route53_zone_id. SEM DEFAULT DE PROPOSITO:
    este projeto nunca registrou um dominio proprio (AWS Academy Learner
    Lab) -- fornecer via tfvars/-var so' no dia em que houver um dominio
    real para apontar aqui. Ver comentario no topo de main.tf.
  DESC
  type        = string
}

variable "route53_zone_id" {
  description = "Hosted zone (Route53) onde var.domain_name esta' delegado. Sem default -- mesmo motivo de var.domain_name."
  type        = string
}

variable "api_target_group_arn" {
  description = "Target group do Lambda da API (modules/lambda_compute, aws_lb_target_group.api)."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
