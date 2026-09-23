# ADR-0017 -- VPC Interface Endpoints para SQS e Parameter Store (SSM),
# fielmente ao card "Rede & Seguranca" de docs/design/implantacao-aws.html:
# permite ao Lambda de producao (dentro da VPC, ver modules/network,
# enable_nat_gateway) chamar essas duas APIs da AWS SEM sair pelo NAT
# gateway -- mais barato (sem trafego pelo NAT) e mais rapido (latencia
# menor, trafego nunca sai da rede da AWS). O NAT gateway continua
# existindo para o que estes dois endpoints deliberadamente NAO cobrem: o
# Orion do cliente (endereco arbitrario na internet publica) e o Secrets
# Manager (usado so' pelo bootstrap da senha do RDS-managed secret,
# `secrets_bootstrap.py`) -- o diagrama so' lista SQS+Parameter Store como
# endpoints, entao nao adicionamos um terceiro so' por simetria.
#
# Interface endpoints (nao Gateway, que so' existe para S3/DynamoDB) --
# cada um cria um ENI com IP privado dentro das subnets informadas,
# resolvido automaticamente pelo DNS privado da VPC
# (private_dns_enabled=true) sem exigir nenhuma mudanca no codigo da
# aplicacao (boto3 continua chamando o endpoint publico do servico por
# nome; a resolucao e' que muda).

resource "aws_security_group" "endpoints" {
  name        = "${var.name_prefix}-vpce-sg"
  description = "HTTPS (443) dos VPC endpoints, apenas a partir do Lambda de producao"
  vpc_id      = var.vpc_id

  ingress {
    description     = "HTTPS a partir do Lambda (API/worker)"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [var.lambda_sg_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-vpce-sg" })
}

resource "aws_vpc_endpoint" "sqs" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.region}.sqs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-vpce-sqs" })
}

resource "aws_vpc_endpoint" "ssm" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.region}.ssm"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-vpce-ssm" })
}
