# Fase 9 (.cursor/specs/fase9.spec.md, secao 2.4) — Secrets Manager + KMS.
# Só ARNs/placeholders aqui: nenhum valor real de segredo entra no
# Terraform ou no git. Os valores reais são preenchidos manualmente (ou por
# um passo separado, fora do `terraform apply`) após o `apply` inicial --
# por exemplo `aws secretsmanager put-secret-value`.

resource "aws_kms_key" "secrets" {
  description             = "Chave de criptografia para segredos do auditor (${var.name_prefix})"
  deletion_window_in_days = 7
  tags                    = var.tags
}

resource "aws_kms_alias" "secrets" {
  name          = "alias/${var.name_prefix}-secrets"
  target_key_id = aws_kms_key.secrets.key_id
}

# Credenciais do Orion (broker FIWARE do cliente) -- FIWARE_BROKER_URL não é
# segredo, mas eventuais tokens/credenciais de autenticação do broker (quando
# o Orion do cliente exigir) ficam aqui.
resource "aws_secretsmanager_secret" "orion_credentials" {
  name       = "${var.name_prefix}/orion-credentials"
  kms_key_id = aws_kms_key.secrets.arn
  tags       = var.tags
}

# Chave de assinatura JWT (autenticação da API, se/quando implementada).
resource "aws_secretsmanager_secret" "jwt_signing_key" {
  name       = "${var.name_prefix}/jwt-signing-key"
  kms_key_id = aws_kms_key.secrets.arn
  tags       = var.tags
}
