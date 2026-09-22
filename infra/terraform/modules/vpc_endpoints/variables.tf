variable "name_prefix" {
  type = string
}

variable "region" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  description = "Subnets onde os ENIs dos endpoints (e o Lambda, ver modules/lambda_compute) sao criados -- mesmas subnets privadas do RDS (modules/network); nenhuma subnet nova e' provisionada so' para isto."
  type        = list(string)
}

variable "lambda_sg_id" {
  description = "Security group do Lambda de producao (modules/lambda_compute) -- unica origem permitida a falar HTTPS com os endpoints."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
