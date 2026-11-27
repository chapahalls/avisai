output "cluster_name" {
  value = aws_ecs_cluster.rumolog.name
}

output "ecr_repository_url" {
  value = aws_ecr_repository.rumolog_backend.repository_url
}

output "db_endpoint" {
  value = aws_db_instance.rumolog.address
}

output "db_identifier" {
  value = aws_db_instance.rumolog.id
}

output "service_discovery_namespace" {
  value = aws_service_discovery_private_dns_namespace.rumolog.name
}

output "api_internal_url" {
  value = "http://api.${var.service_discovery_namespace}:8000"
}

output "api_public_url" {
  description = "URL HTTPS pública da api (CloudFront na frente do ALB, sem domínio próprio)."
  value       = "https://${aws_cloudfront_distribution.api.domain_name}"
}

output "api_public_url_http_alb_direto" {
  description = "DNS name HTTP puro do ALB (debug/uso interno; não usar de página HTTPS por causa de mixed content)."
  value       = "http://${aws_lb.rumolog.dns_name}"
}

output "app_secret_arns" {
  value = { for k, s in aws_secretsmanager_secret.app : k => s.arn }
}
