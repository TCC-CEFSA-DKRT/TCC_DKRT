# Bootstrap da conta AWS (ADR-0021). Roda UMA vez, por uma pessoa com
# credenciais administrativas na conta, antes de qualquer ambiente existir:
#
#   - bucket S3 + tabela DynamoDB para o state remoto dos três ambientes
#     (o backend não consegue criar a si mesmo);
#   - bucket de artefatos do pipeline (build do frontend, que é construído uma
#     vez na tag -rc e promovido sem recompilar);
#   - provedor OIDC do GitHub e os papéis IAM que o pipeline assume, sem chaves
#     de acesso guardadas no GitHub.
#
# O state deste stack é local (terraform.tfstate, ignorado pelo git). Ele
# raramente muda; se quiser, migre depois para o bucket criado aqui com
# `terraform init -migrate-state`.

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "auditor-tcc"
      Stack     = "bootstrap"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  repo       = var.github_repository

  state_bucket     = "${var.project}-tfstate-${local.account_id}"
  lock_table       = "${var.project}-tflock"
  artifacts_bucket = "${var.project}-artifacts-${local.account_id}"

  # Nome do GitHub Environment de cada ambiente (aprovações e variáveis ficam
  # lá). O de infraestrutura, "infra-<nome>", é separado: aplicar Terraform e
  # publicar uma versão têm aprovadores e permissões diferentes.
  github_environments = {
    for k, v in var.environments : k => {
      prefix  = v.name_prefix
      deploy  = v.github_environment
      infra   = "infra-${k}"
      is_prod = k == "production"
    }
  }
}

# ---------------------------------------------------------------------------
# State remoto
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "tfstate" {
  bucket = local.state_bucket
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "tflock" {
  name         = local.lock_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}

# ---------------------------------------------------------------------------
# Artefatos do pipeline
# ---------------------------------------------------------------------------
resource "aws_s3_bucket" "artifacts" {
  bucket = local.artifacts_bucket
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "expirar-versoes-antigas"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

# ---------------------------------------------------------------------------
# GitHub OIDC
# ---------------------------------------------------------------------------
resource "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 1 : 0

  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  # A AWS valida o certificado do GitHub pela própria cadeia de CAs e ignora
  # este valor, mas o argumento ainda é aceito/exigido por algumas versões.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1", "1c58a3a8518e8759bf075b76b750d4f2df264fcd"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_oidc_provider ? 0 : 1
  url   = "https://token.actions.githubusercontent.com"
}

locals {
  oidc_provider_arn = var.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
}

# Trust policy: só o repositório indicado e só o "subject" informado (um GitHub
# Environment, ou pull_request). Um workflow de outra branch/ambiente não
# consegue assumir o papel de produção.
data "aws_iam_policy_document" "trust" {
  for_each = merge(
    { "plan" = "repo:${local.repo}:pull_request" },
    { for k, v in local.github_environments : "deploy-${k}" => "repo:${local.repo}:environment:${v.deploy}" },
    { for k, v in local.github_environments : "terraform-${k}" => "repo:${local.repo}:environment:${v.infra}" },
  )

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [each.value]
    }
  }
}

# Acesso ao state e ao lock, comum aos papéis que rodam terraform.
data "aws_iam_policy_document" "state_access" {
  statement {
    sid       = "StateList"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.tfstate.arn]
  }

  statement {
    sid       = "StateObjects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.tfstate.arn}/*"]
  }

  statement {
    sid       = "StateLock"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem", "dynamodb:DescribeTable"]
    resources = [aws_dynamodb_table.tflock.arn]
  }
}

# ---------------------------------------------------------------------------
# Papel de plan (pull requests): somente leitura da conta + state/lock.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "plan" {
  name                 = "${var.project}-gh-plan"
  assume_role_policy   = data.aws_iam_policy_document.trust["plan"].json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_readonly" {
  role       = aws_iam_role.plan.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy" "plan_state" {
  name   = "state-access"
  role   = aws_iam_role.plan.id
  policy = data.aws_iam_policy_document.state_access.json
}

# ---------------------------------------------------------------------------
# Papéis de terraform apply (um por ambiente): PowerUser + IAM restrito ao
# prefixo do ambiente. O restante dos serviços não é limitado por prefixo, mas
# o ponto de maior risco (criar papéis/políticas arbitrários e escalar
# privilégio) fica contido.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "terraform" {
  for_each = local.github_environments

  name                 = "${var.project}-gh-terraform-${each.key}"
  assume_role_policy   = data.aws_iam_policy_document.trust["terraform-${each.key}"].json
  max_session_duration = 7200
}

resource "aws_iam_role_policy_attachment" "terraform_poweruser" {
  for_each = local.github_environments

  role       = aws_iam_role.terraform[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

data "aws_iam_policy_document" "terraform_iam" {
  for_each = local.github_environments

  statement {
    sid     = "IamDoAmbiente"
    actions = ["iam:*"]
    resources = [
      "arn:aws:iam::${local.account_id}:role/${each.value.prefix}-*",
      "arn:aws:iam::${local.account_id}:policy/${each.value.prefix}-*",
      "arn:aws:iam::${local.account_id}:instance-profile/${each.value.prefix}-*",
    ]
  }

  # Papéis vinculados a serviços (ALB, RDS, Lambda em VPC...) são criados pela
  # AWS na primeira vez que o serviço é usado na conta.
  statement {
    sid       = "ServiceLinkedRoles"
    actions   = ["iam:CreateServiceLinkedRole"]
    resources = ["*"]
  }

  statement {
    sid       = "LeituraIam"
    actions   = ["iam:Get*", "iam:List*"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "terraform_iam" {
  for_each = local.github_environments

  name   = "iam-do-ambiente"
  role   = aws_iam_role.terraform[each.key].id
  policy = data.aws_iam_policy_document.terraform_iam[each.key].json
}

# ---------------------------------------------------------------------------
# Papéis de deploy (um por ambiente): publicar a versão, nada de infraestrutura.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "deploy" {
  for_each = local.github_environments

  name                 = "${var.project}-gh-deploy-${each.key}"
  assume_role_policy   = data.aws_iam_policy_document.trust["deploy-${each.key}"].json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "deploy" {
  for_each = local.github_environments

  statement {
    sid       = "EcrLogin"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrDoAmbiente"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:DescribeImages",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:ListImages",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = ["arn:aws:ecr:${var.region}:${local.account_id}:repository/${each.value.prefix}-auditor"]
  }

  # Produção promove a imagem já homologada: lê do repositório de homologação,
  # sem rebuild.
  dynamic "statement" {
    for_each = each.value.is_prod && contains(keys(local.github_environments), "homolog") ? [1] : []

    content {
      sid = "EcrOrigemDaPromocao"
      actions = [
        "ecr:BatchGetImage",
        "ecr:DescribeImages",
        "ecr:GetDownloadUrlForLayer",
        "ecr:ListImages",
      ]
      resources = ["arn:aws:ecr:${var.region}:${local.account_id}:repository/${local.github_environments["homolog"].prefix}-auditor"]
    }
  }

  statement {
    sid = "LambdaDoAmbiente"
    actions = [
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
      "lambda:InvokeFunction",
      "lambda:UpdateFunctionCode",
    ]
    resources = ["arn:aws:lambda:${var.region}:${local.account_id}:function:${each.value.prefix}-*"]
  }

  statement {
    sid       = "SsmRunCommandDocumento"
    actions   = ["ssm:SendCommand"]
    resources = ["arn:aws:ssm:${var.region}::document/AWS-RunShellScript"]
  }

  statement {
    sid       = "SsmRunCommandInstancias"
    actions   = ["ssm:SendCommand"]
    resources = ["arn:aws:ec2:${var.region}:${local.account_id}:instance/*"]

    condition {
      test     = "StringEquals"
      variable = "ssm:resourceTag/Environment"
      values   = [each.key]
    }
  }

  statement {
    sid       = "SsmAcompanharComando"
    actions   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations", "ec2:DescribeInstances"]
    resources = ["*"]
  }

  statement {
    sid       = "FrontendBucket"
    actions   = ["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${each.value.prefix}-frontend", "arn:aws:s3:::${each.value.prefix}-frontend/*"]
  }

  statement {
    sid       = "CloudFront"
    actions   = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation", "cloudfront:ListDistributions"]
    resources = ["*"]
  }

  statement {
    sid       = "ArtefatosDoFrontend"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.artifacts.arn}/frontend/*"]
  }

  statement {
    sid       = "ArtefatosLista"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.artifacts.arn]
  }
}

resource "aws_iam_role_policy" "deploy" {
  for_each = local.github_environments

  name   = "deploy-do-ambiente"
  role   = aws_iam_role.deploy[each.key].id
  policy = data.aws_iam_policy_document.deploy[each.key].json
}
