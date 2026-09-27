output "sqs_endpoint_id" {
  value = aws_vpc_endpoint.sqs.id
}

output "ssm_endpoint_id" {
  value = aws_vpc_endpoint.ssm.id
}

output "endpoints_sg_id" {
  value = aws_security_group.endpoints.id
}
