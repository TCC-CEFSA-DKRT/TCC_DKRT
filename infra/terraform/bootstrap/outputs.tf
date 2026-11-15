output "tf_state_bucket" {
  description = "Variável de repositório TF_STATE_BUCKET."
  value       = aws_s3_bucket.tfstate.id
}

output "tf_state_lock_table" {
  description = "Variável de repositório TF_STATE_LOCK_TABLE."
  value       = aws_dynamodb_table.tflock.name
}

output "artifacts_bucket" {
  description = "Variável de repositório ARTIFACTS_BUCKET."
  value       = aws_s3_bucket.artifacts.id
}

output "plan_role_arn" {
  description = "Variável de repositório AWS_PLAN_ROLE_ARN (plan em pull requests)."
  value       = aws_iam_role.plan.arn
}

output "deploy_role_arns" {
  description = "Variável AWS_DEPLOY_ROLE_ARN de cada GitHub Environment de deploy."
  value       = { for k, r in aws_iam_role.deploy : local.github_environments[k].deploy => r.arn }
}

output "terraform_role_arns" {
  description = "Variável AWS_TERRAFORM_ROLE_ARN de cada GitHub Environment de infraestrutura."
  value       = { for k, r in aws_iam_role.terraform : local.github_environments[k].infra => r.arn }
}
