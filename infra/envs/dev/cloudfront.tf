# HTTPS pra api sem precisar de domínio/DNS proprio: o ALB (alb.tf) so tem
# listener HTTP/80 (sem dominio pra emitir certificado ACM nele). O
# CloudFront resolve isso ficando na frente do ALB e expondo a api em
# `https://<id>.cloudfront.net` com certificado TLS gerenciado pela própria
# AWS no domínio compartilhado *.cloudfront.net — sem custo e sem precisar
# comprovar posse de domínio nenhum. rodar-web/rodar-mobile (GitHub Pages,
# HTTPS) passam a chamar essa URL em vez do DNS name puro do ALB, resolvendo
# o bloqueio de mixed content do navegador (ver infra/README.md).
#
# CloudFront -> ALB continua em HTTP (origin_protocol_policy = "http-only"):
# esse trecho é tráfego dentro da rede da AWS, não exposto ao cliente final.

data "aws_cloudfront_cache_policy" "caching_disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer" {
  name = "Managed-AllViewer"
}

resource "aws_cloudfront_distribution" "api" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "rodar-backend api (HTTPS na frente do ALB, sem dominio proprio)"

  origin {
    domain_name = aws_lb.rumolog.dns_name
    origin_id   = "rumolog-dev-alb"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "http-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id = "rumolog-dev-alb"
    allowed_methods  = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods   = ["GET", "HEAD"]

    # Api sem cache: cada request deve chegar na api de verdade. Origin
    # request policy "AllViewer" repassa todos os headers/query
    # strings/cookies (inclusive Authorization) pro ALB.
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id

    viewer_protocol_policy = "redirect-to-https"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name = "rumolog-dev-api-cdn"
  }
}
