output "endpoint" {
  value = aws_db_instance.this.address
}

output "port" {
  value = aws_db_instance.this.port
}

output "db_instance_id" {
  value = aws_db_instance.this.id
}

output "master_user_secret_arn" {
  description = "ARN do segredo gerenciado pelo RDS com a senha do master user (só existe se manage_master_user_password=true)."
  # try() em vez de um ternário indexando [0] diretamente: quando
  # manage_master_user_password=false, master_user_secret é uma lista
  # computada vazia, e indexar [0] nesse branch é um erro conhecido do
  # Terraform mesmo dentro de um ternário (as duas alternativas de um
  # condicional não são garantidamente short-circuited para erros de
  # índice) -- try() evita isso de forma explícita.
  value = try(aws_db_instance.this.master_user_secret[0].secret_arn, null)
}

output "database_url_template" {
  description = <<-DESC
    Template do DATABASE_URL para a app (settings.py) -- a senha real deve
    ser resolvida a partir do Secrets Manager (master_user_secret_arn) em
    tempo de deploy (user_data / CI), nunca hardcoded aqui.
  DESC
  value       = "postgresql+asyncpg://${var.master_username}:<SENHA_DO_SECRETS_MANAGER>@${aws_db_instance.this.address}:${aws_db_instance.this.port}/${var.database_name}?ssl=require"
}
