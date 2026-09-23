variable "name_prefix" {
  type = string
}

variable "orion_credentials_json" {
  description = <<-DESC
    Placeholder na criacao -- aws_ssm_parameter exige um `value` (diferente
    de aws_secretsmanager_secret, ver comentario em main.tf). O valor real
    e' definido manualmente apos o apply (`aws ssm put-parameter --name
    /<name_prefix>/orion-credentials --type SecureString --overwrite
    --value '...'`) e preservado entre applies por
    lifecycle.ignore_changes.
  DESC
  type      = string
  default   = "REPLACE_AFTER_APPLY"
  sensitive = true
}

variable "jwt_signing_key" {
  description = "Placeholder na criacao -- mesmo raciocinio de orion_credentials_json, acima."
  type        = string
  default     = "REPLACE_AFTER_APPLY"
  sensitive   = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
