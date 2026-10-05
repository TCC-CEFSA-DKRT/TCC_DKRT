# ADR-0017 -- ALB com listener HTTPS (ACM) na frente do Lambda da API
# (target_type=lambda, criado em modules/lambda_compute) -- fecha o gap
# real encontrado ao auditar a Fase 9 original: o security group da API
# (modules/network, aws_security_group.api) ja' abria a porta 443 desde a
# Fase 9, mas nenhum listener HTTPS/certificado ACM jamais existiu (a API
# EC2 so' respondia HTTP na porta 8000). Ver
# docs/design/implantacao-aws.html, card "Compute".
#
# Certificado ACM com validacao DNS via Route53 -- exige um dominio de
# verdade DELEGADO a um Route53 hosted zone (var.route53_zone_id) e
# var.domain_name apontando para ele. Este projeto (AWS Academy Learner
# Lab) nunca teve um dominio proprio registrado -- por isso var.domain_name/
# var.route53_zone_id NAO tem default (see variables.tf): quem for aplicar
# environments/production de verdade precisa fornecer os dois via tfvars,
# depois de registrar/delegar um dominio. Gap real, disclosed ao inves de
# fabricado -- mesmo espirito do restante do modulo `production`, que ja'
# documenta no topo de main.tf que nunca foi de fato aplicado.

resource "aws_security_group" "alb" {
  name        = "${var.name_prefix}-alb-sg"
  description = "ALB publico -- HTTP(80, redireciona) e HTTPS(443) da internet"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP (redireciona para HTTPS)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb-sg" })
}

resource "aws_lb" "this" {
  name               = "${var.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.public_subnet_ids

  tags = merge(var.tags, { Name = "${var.name_prefix}-alb" })
}

resource "aws_acm_certificate" "api" {
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-api-cert" })
}

resource "aws_route53_record" "api_cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.api.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  zone_id = var.route53_zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.record]
}

resource "aws_acm_certificate_validation" "api" {
  certificate_arn         = aws_acm_certificate.api.arn
  validation_record_fqdns = [for record in aws_route53_record.api_cert_validation : record.fqdn]
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.api.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = var.api_target_group_arn
  }
}

resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_route53_record" "api" {
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = true
  }
}
