# ADR-0017: aws_instance.api/aws_instance.worker passaram a usar `count`
# (provision_api/provision_worker, ver variables.tf/main.tf) -- os outputs
# abaixo, que antes indexavam o recurso direto (aws_instance.api.id), agora
# precisam de try(...[0]..., null): a lista fica vazia quando
# provision_api/provision_worker=false (produção, API/worker como Lambda) e
# indexar [0] direto nesse caso é erro do Terraform. Mesmo padrão já usado
# em ollama_instance_id/ollama_private_ip abaixo (var.provision_ollama) e em
# modules/database/outputs.tf (master_user_secret_arn).

output "api_instance_id" {
  value = try(aws_instance.api[0].id, null)
}

output "api_public_ip" {
  description = "null quando provision_api=false (produção, ADR-0017: API roda como Lambda atrás do ALB)."
  value       = try(aws_instance.api[0].public_ip, null)
}

output "worker_instance_id" {
  value = try(aws_instance.worker[0].id, null)
}

output "ollama_instance_id" {
  description = "null quando provision_ollama=false."
  value       = var.provision_ollama ? aws_instance.ollama[0].id : null
}

output "ollama_private_ip" {
  value = var.provision_ollama ? aws_instance.ollama[0].private_ip : null
}
