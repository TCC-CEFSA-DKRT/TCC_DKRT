output "api_url" {
  value = module.edge_alb.api_url
}

output "frontend_url" {
  value = module.frontend_delivery.frontend_url
}

output "frontend_bucket_name" {
  value = module.frontend_delivery.bucket_name
}

output "database_endpoint" {
  value = module.database.endpoint
}

output "ollama_instance_id" {
  value = module.compute.ollama_instance_id
}

output "ollama_private_ip" {
  description = "IP privado da instância Ollama, alcançável pelo Lambda de dentro da VPC."
  value       = module.compute.ollama_private_ip
}

output "ecr_repository_url" {
  value = module.lambda_compute.ecr_repository_url
}

output "api_function_name" {
  value = module.lambda_compute.api_function_name
}

output "worker_function_name" {
  value = module.lambda_compute.worker_function_name
}

output "worker_dlq_function_name" {
  value = module.lambda_compute.worker_dlq_function_name
}

output "admin_function_name" {
  value = module.lambda_compute.admin_function_name
}

output "admin_invoke_policy_arn" {
  value = module.lambda_compute.admin_invoke_policy_arn
}
