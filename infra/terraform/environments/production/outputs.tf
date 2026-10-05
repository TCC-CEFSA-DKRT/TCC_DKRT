# ADR-0017: api_public_ip (IP de uma instância EC2 da API) deixou de fazer
# sentido em produção -- a API roda como Lambda atrás do ALB
# (module.edge_alb). Trocado pela URL pública real da API/frontend.

output "api_url" {
  value = module.edge_alb.api_url
}

output "frontend_url" {
  value = module.frontend_delivery.frontend_url
}

output "database_endpoint" {
  value = module.database.endpoint
}

output "ollama_private_ip" {
  description = "IP privado da instância Ollama (EC2) -- alcançável pelo Lambda de dentro da VPC, nunca exposto publicamente."
  value       = module.compute.ollama_private_ip
}

output "ecr_repository_url" {
  description = "Repositório ECR onde a imagem de contêiner (Dockerfile na raiz do repo) deve ser publicada antes do primeiro apply real -- ver modules/lambda_compute."
  value       = module.lambda_compute.ecr_repository_url
}

output "admin_function_name" {
  value = module.lambda_compute.admin_function_name
}

output "admin_invoke_policy_arn" {
  value = module.lambda_compute.admin_invoke_policy_arn
}
