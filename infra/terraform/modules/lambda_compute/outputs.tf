output "lambda_sg_id" {
  value = aws_security_group.lambda.id
}

output "ecr_repository_url" {
  value = aws_ecr_repository.this.repository_url
}

output "api_function_name" {
  value = aws_lambda_function.api.function_name
}

output "worker_function_name" {
  value = aws_lambda_function.worker.function_name
}

output "worker_dlq_function_name" {
  value = aws_lambda_function.worker_dlq.function_name
}

output "api_target_group_arn" {
  value = aws_lb_target_group.api.arn
}
