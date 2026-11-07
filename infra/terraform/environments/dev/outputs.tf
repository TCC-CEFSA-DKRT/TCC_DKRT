output "api_url" {
  description = "URL da API do dev (IP fixo, porta 8000, HTTP)."
  value       = "http://${aws_eip.api.public_ip}:8000"
}

output "frontend_url" {
  value = module.frontend.website_url
}

output "frontend_bucket_name" {
  value = module.frontend.bucket_name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "api_instance_id" {
  value = module.compute.api_instance_id
}

output "ollama_instance_id" {
  value = module.compute.ollama_instance_id
}

output "database_endpoint" {
  value = module.database.endpoint
}

output "queue_url" {
  value = module.queue.queue_url
}

output "dlq_url" {
  value = module.queue.dlq_url
}
