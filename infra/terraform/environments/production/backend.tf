terraform {
  backend "s3" {
    # bucket, key, region, dynamodb_table: fornecidos via -backend-config,
    # igual ao ambiente academy (ver environments/academy/backend.tf) --
    # tipicamente um bucket/tabela SEPARADOS dos da academy, para não
    # misturar state de ambientes.
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
