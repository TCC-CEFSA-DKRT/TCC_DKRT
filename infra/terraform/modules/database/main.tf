# Fase 9 (.cursor/specs/fase9.spec.md, secao 2.2) — RDS PostgreSQL com
# pgvector, usado pelo catálogo semântico (Fase 6). Nenhuma redefinição de
# schema aqui: a migration Alembic existente (migrations/) já cria a
# extensão e as colunas vector(384); este módulo só provisiona a instância.

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db-subnets"
  subnet_ids = var.private_subnet_ids
  tags       = var.tags
}

resource "aws_db_instance" "this" {
  identifier     = "${var.name_prefix}-db"
  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage = var.allocated_storage_gb
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = var.database_name
  username = var.master_username

  manage_master_user_password = var.manage_master_user_password
  password                    = var.manage_master_user_password ? null : var.master_password

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.security_group_id]
  publicly_accessible    = false

  backup_retention_period = var.backup_retention_days
  multi_az                = var.multi_az
  skip_final_snapshot     = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.name_prefix}-db-final"

  # sslmode=require é reforçado do lado da aplicação (DATABASE_URL), não
  # pelo RDS em si -- o RDS aceita TLS por padrao mas nao recusa conexoes
  # em texto plano sozinho; ver output `database_url_template` abaixo.

  tags = var.tags
}
