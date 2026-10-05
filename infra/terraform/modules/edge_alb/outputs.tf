output "alb_dns_name" {
  value = aws_lb.this.dns_name
}

output "alb_arn" {
  value = aws_lb.this.arn
}

output "api_url" {
  description = "URL publica da API (https://<domain_name>) -- consumida pelo frontend (modules/frontend_delivery) e/ou CORS_ALLOWED_ORIGINS."
  value       = "https://${var.domain_name}"
}
