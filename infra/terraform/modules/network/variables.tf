variable "name_prefix" {
  type = string
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "azs" {
  description = "Availability zones a usar (2, para subnets públicas/privadas redundantes)."
  type        = list(string)
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.20.0.0/24", "10.20.1.0/24"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.20.10.0/24", "10.20.11.0/24"]
}

variable "enable_nat_gateway" {
  description = <<-DESC
    ADR-0017: cria um NAT gateway (+ EIP + rota da(s) subnet(s) privada(s)
    para ele) quando true. Default false preserva 100% do comportamento
    atual (Academy e o modulo em geral) -- nenhum recurso novo, nenhum
    custo novo, nenhuma mudanca de plano. So' producao liga isto
    (environments/production/main.tf), porque so' la' o Lambda de producao
    roda dentro da VPC e precisa de uma rota de saida para a internet
    (Orion do cliente + Secrets Manager -- ver comentario em main.tf,
    acima de aws_eip.nat).
  DESC
  type        = bool
  default     = false
}

variable "tags" {
  type    = map(string)
  default = {}
}
