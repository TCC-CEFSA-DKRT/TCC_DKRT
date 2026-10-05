output "kms_key_arn" {
  value = aws_kms_key.secrets.arn
}

output "orion_credentials_secret_arn" {
  value = aws_secretsmanager_secret.orion_credentials.arn
}

output "jwt_signing_key_secret_arn" {
  value = aws_secretsmanager_secret.jwt_signing_key.arn
}
