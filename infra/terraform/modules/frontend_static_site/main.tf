# Frontend estático (Angular) do ambiente dev: bucket S3 com website hosting
# público, em HTTP. Sem CloudFront nem domínio, de propósito: o dev é uma stack
# enxuta (ADR-0021). Homologação e produção usam modules/frontend_delivery.

resource "aws_s3_bucket" "site" {
  bucket        = "${var.name_prefix}-frontend"
  force_destroy = true # ambiente de desenvolvimento, descartável

  tags = var.tags
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket = aws_s3_bucket.site.id

  block_public_acls       = true
  block_public_policy     = false
  ignore_public_acls      = true
  restrict_public_buckets = false
}

resource "aws_s3_bucket_website_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  index_document {
    suffix = "index.html"
  }

  # SPA: rota desconhecida cai no index.html (o Angular Router decide no cliente).
  error_document {
    key = "index.html"
  }
}

data "aws_iam_policy_document" "public_read" {
  statement {
    sid       = "PublicRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = data.aws_iam_policy_document.public_read.json

  depends_on = [aws_s3_bucket_public_access_block.site]
}
