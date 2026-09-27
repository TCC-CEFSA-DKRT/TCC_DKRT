#!/bin/bash
# Cria o bucket S3 + tabela DynamoDB de lock para o backend remoto do
# Terraform (backend.tf usa -backend-config, pois o backend não consegue se
# auto-provisionar: não dá pra guardar o state de "criar onde o state vai
# morar" no próprio state). Rodar uma vez por conta antes do primeiro
# `terraform init`.
set -euo pipefail

REGION="${1:-us-east-1}"
BUCKET="${2:?Uso: bootstrap_backend.sh <region> <bucket-name> <dynamodb-table-name>}"
TABLE="${3:?Uso: bootstrap_backend.sh <region> <bucket-name> <dynamodb-table-name>}"

aws s3api create-bucket \
  --bucket "$BUCKET" \
  --region "$REGION" \
  $( [ "$REGION" != "us-east-1" ] && echo "--create-bucket-configuration LocationConstraint=$REGION" )

aws s3api put-bucket-versioning \
  --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket "$BUCKET" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

aws dynamodb create-table \
  --table-name "$TABLE" \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$REGION"

echo "Backend pronto. Rode:"
echo "  terraform init -backend-config=\"bucket=$BUCKET\" -backend-config=\"key=homolog/terraform.tfstate\" -backend-config=\"region=$REGION\" -backend-config=\"dynamodb_table=$TABLE\""
