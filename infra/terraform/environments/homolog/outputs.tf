output "api_public_ip" {
  value = module.compute.api_public_ip
}

output "ollama_instance_id" {
  value = module.compute.ollama_instance_id
}

output "database_endpoint" {
  value = module.database.endpoint
}

output "database_url_template" {
  value = module.database.database_url_template
}

output "queue_url" {
  value = module.queue.queue_url
}

output "dlq_url" {
  value = module.queue.dlq_url
}
