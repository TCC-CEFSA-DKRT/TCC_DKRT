output "bucket_name" {
  value = aws_s3_bucket.site.id
}

output "website_url" {
  description = "URL do site (HTTP), usada no CORS da API do dev."
  value       = "http://${aws_s3_bucket_website_configuration.site.website_endpoint}"
}
