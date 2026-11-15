# Backend S3 + DynamoDB (lock), criados pelo stack infra/terraform/bootstrap.
# bucket, key, region e dynamodb_table são passados via -backend-config (ver
# docs/devops/pipeline-e-ambientes.md); a key deste ambiente é
# dev/terraform.tfstate.
terraform {
  backend "s3" {
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
