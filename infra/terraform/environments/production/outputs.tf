output "api_url" {
  value = module.stack.api_url
}

output "frontend_url" {
  value = module.stack.frontend_url
}

output "frontend_bucket_name" {
  value = module.stack.frontend_bucket_name
}

output "database_endpoint" {
  value = module.stack.database_endpoint
}

output "ollama_instance_id" {
  value = module.stack.ollama_instance_id
}

output "ollama_private_ip" {
  value = module.stack.ollama_private_ip
}

output "ecr_repository_url" {
  value = module.stack.ecr_repository_url
}

output "admin_function_name" {
  value = module.stack.admin_function_name
}

output "admin_invoke_policy_arn" {
  value = module.stack.admin_invoke_policy_arn
}
