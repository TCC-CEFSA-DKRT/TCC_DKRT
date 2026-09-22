output "orion_credentials_parameter_name" {
  value = aws_ssm_parameter.orion_credentials.name
}

output "orion_credentials_parameter_arn" {
  value = aws_ssm_parameter.orion_credentials.arn
}

output "jwt_signing_key_parameter_name" {
  value = aws_ssm_parameter.jwt_signing_key.name
}

output "jwt_signing_key_parameter_arn" {
  value = aws_ssm_parameter.jwt_signing_key.arn
}
