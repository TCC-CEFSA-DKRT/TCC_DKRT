# Fase 9 (.cursor/specs/fase9.spec.md, secao 2.1) — rede: VPC com subnets
# públicas (API/worker, que precisam sair para a internet e, na Academy,
# ganhar IP público) e privadas (RDS), IGW, rotas e security groups.

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(var.tags, { Name = "${var.name_prefix}-vpc" })
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags   = merge(var.tags, { Name = "${var.name_prefix}-igw" })
}

resource "aws_subnet" "public" {
  count                   = length(var.public_subnet_cidrs)
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = merge(var.tags, { Name = "${var.name_prefix}-public-${count.index}" })
}

resource "aws_subnet" "private" {
  count             = length(var.private_subnet_cidrs)
  vpc_id            = aws_vpc.this.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.azs[count.index]
  tags              = merge(var.tags, { Name = "${var.name_prefix}-private-${count.index}" })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.this.id
  }
  tags = merge(var.tags, { Name = "${var.name_prefix}-public-rt" })
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Sem NAT gateway por padrao (var.enable_nat_gateway = false): seria custo
# always-on desnecessário para um protótipo de TCC com orçamento limitado
# (fase9.spec.md, secao 2 — "$100 de credito total, nada always-on por
# padrao"). A subnet privada (RDS) não precisa de saida para a internet;
# acesso de administracao ao RDS, quando necessario, passa pela instancia
# da API/worker na subnet publica. E' exatamente o comportamento da Academy
# e por isso o default fica false -- nenhum recurso novo e' criado la'.
#
# ADR-0017 (producao apenas): o Lambda de producao (modules/lambda_compute)
# precisa ficar DENTRO da VPC para alcancar o RDS e o Ollama (EC2) por IP
# privado -- mas isso tira dele o acesso a internet que uma funcao Lambda
# fora de VPC tem por padrao. VPC Interface Endpoints (modules/vpc_endpoints)
# cobrem SQS/Parameter Store sem custo de NAT, mas o Worker tambem precisa
# alcancar o Orion do CLIENTE (endereco arbitrario na internet publica,
# fora da AWS) e o bootstrap de segredos (`secrets_bootstrap.py`) precisa
# alcancar o Secrets Manager (RDS-managed secret) -- nenhum dos dois e' um
# endpoint de VPC provisionado aqui, propositalmente fiel ao diagrama
# (docs/design/implantacao-aws.html, card "Rede & Seguranca": "NAT
# reservado so' para Worker -> Orion externo"). Por isso o NAT gateway e'
# opcional (nao um redesenho do padrao "sem NAT" da Academy) e so' e' criado
# quando o ambiente chamador passa enable_nat_gateway=true
# (environments/production/main.tf).
resource "aws_eip" "nat" {
  count  = var.enable_nat_gateway ? 1 : 0
  domain = "vpc"
  tags   = merge(var.tags, { Name = "${var.name_prefix}-nat-eip" })
}

resource "aws_nat_gateway" "this" {
  count         = var.enable_nat_gateway ? 1 : 0
  allocation_id = aws_eip.nat[0].id
  # NAT gateway fica na subnet publica (precisa de rota direta para o IGW);
  # so' a subnet privada (onde o Lambda/RDS estao) roteia atraves dele.
  subnet_id = aws_subnet.public[0].id
  tags      = merge(var.tags, { Name = "${var.name_prefix}-nat" })

  depends_on = [aws_internet_gateway.this]
}

resource "aws_route_table" "private" {
  count  = var.enable_nat_gateway ? 1 : 0
  vpc_id = aws_vpc.this.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.this[0].id
  }
  tags = merge(var.tags, { Name = "${var.name_prefix}-private-rt" })
}

resource "aws_route_table_association" "private" {
  count          = var.enable_nat_gateway ? length(aws_subnet.private) : 0
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[0].id
}

resource "aws_security_group" "api" {
  name        = "${var.name_prefix}-api-sg"
  description = "API HTTP(S) + SSH de administracao"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "HTTP"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS (via ACM/listener, quando presente)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH administrativo"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-api-sg" })
}

resource "aws_security_group" "worker" {
  name        = "${var.name_prefix}-worker-sg"
  description = "Worker (consome SQS) + SSH de administracao"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "SSH administrativo"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-worker-sg" })
}

resource "aws_security_group" "ollama" {
  name        = "${var.name_prefix}-ollama-sg"
  description = "Ollama (porta 11434, só de dentro da VPC) + SSH de administracao"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "Ollama API, apenas de dentro da VPC (API/worker chamam por IP privado)"
    from_port   = 11434
    to_port     = 11434
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  ingress {
    description = "SSH administrativo"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-ollama-sg" })
}

resource "aws_security_group" "database" {
  name        = "${var.name_prefix}-db-sg"
  description = "PostgreSQL, apenas da API e do worker"
  vpc_id      = aws_vpc.this.id

  ingress {
    description     = "Postgres a partir da API"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id]
  }

  ingress {
    description     = "Postgres a partir do worker"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.worker.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-db-sg" })
}
