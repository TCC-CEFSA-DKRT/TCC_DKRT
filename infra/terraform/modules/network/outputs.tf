output "vpc_id" {
  value = aws_vpc.this.id
}

output "public_subnet_ids" {
  value = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "api_sg_id" {
  value = aws_security_group.api.id
}

output "worker_sg_id" {
  value = aws_security_group.worker.id
}

output "ollama_sg_id" {
  value = aws_security_group.ollama.id
}

output "database_sg_id" {
  value = aws_security_group.database.id
}
