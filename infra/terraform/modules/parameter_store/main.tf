# ADR-0017 -- Parameter Store (SSM, SecureString) para os segredos que o
# PROJETO cria (credenciais do Orion do cliente, chave de assinatura JWT,
# chaves Fernet de cifra do broker_api_key -- ADR-0019, mesmo padrao),
# no lugar do Secrets Manager comum (modules/secrets, usado por
# environments/academy) -- decisao explicita do diagrama
# (docs/design/implantacao-aws.html, card "Dados & Filas": "Parameter
# Store SecureString ... sem o custo de $0,40/segredo/mes").
#
# `key_id` deliberadamente OMITIDO em ambos os aws_ssm_parameter abaixo:
# sem ele, SecureString usa a chave gerenciada pela propria AWS
# (alias/aws/ssm), que nao tem custo de KMS proprio -- uma chave KMS
# gerenciada pelo cliente (como o modules/secrets faz, aws_kms_key.secrets)
# custaria ~US$1/mes so' pela chave, o que anularia parte da economia que
# motivou esta troca. A criptografia em repouso continua garantida (SSE via
# KMS), so' com a chave da AWS em vez de uma propria.
#
# Mesmo padrao de modules/secrets: nenhum valor REAL de segredo entra no
# Terraform ou no git. Diferenca em relacao a Secrets Manager: o recurso
# aws_ssm_parameter EXIGE um `value` na criacao (nao ha' equivalente a criar
# so' o "container" vazio, como aws_secretsmanager_secret sem
# aws_secretsmanager_secret_version) -- por isso var.orion_credentials_json/
# var.jwt_signing_key tem um placeholder default explicito, e
# `lifecycle.ignore_changes` garante que um valor real definido depois via
# `aws ssm put-parameter` (fora do terraform apply, mesmo espirito do
# comentario em modules/secrets/main.tf) nunca seja revertido pelo proximo
# `terraform apply`.

resource "aws_ssm_parameter" "orion_credentials" {
  name        = "/${var.name_prefix}/orion-credentials"
  description = "Credenciais de autenticacao do Orion do cliente (JSON) -- FIWARE_BROKER_URL em si nao e' segredo, ver modules/secrets."
  type        = "SecureString"
  value       = var.orion_credentials_json
  tags        = var.tags

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "jwt_signing_key" {
  name        = "/${var.name_prefix}/jwt-signing-key"
  description = "Chave de assinatura JWT da API (autenticacao, se/quando implementada)."
  type        = "SecureString"
  value       = var.jwt_signing_key
  tags        = var.tags

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "broker_api_key_encryption_keys" {
  name        = "/${var.name_prefix}/broker-api-key-encryption-keys"
  description = "Chaves Fernet (lista por virgula; a primeira cifra) de tenant_accounts.broker_api_key_encrypted -- ADR-0019."
  type        = "SecureString"
  value       = var.broker_api_key_encryption_keys
  tags        = var.tags

  lifecycle {
    ignore_changes = [value]
  }
}
