# Backend S3 + DynamoDB (lock) -- parcial: os valores reais de bucket/tabela
# não são fixados aqui (fornecidos via -backend-config para não acoplar este
# arquivo a uma conta específica). Passe-os via `terraform init -backend-config=...`
# ou um `backend.hcl` não versionado. `scripts/bootstrap_backend.sh` cria o
# bucket/tabela quando ainda não existem (o backend não pode se auto-provisionar).
terraform {
  backend "s3" {
    # bucket, key, region, dynamodb_table: fornecidos via -backend-config
    encrypt = true
  }

  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
