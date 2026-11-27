# Exposicao publica da api (so dela — voice-agent nao recebe HTTP, so fala
# pra fora via LiveKit/Twilio). O ALB em si so tem listener HTTP/80 (sem
# dominio/certificado ACM proprio pra esse app) — o HTTPS exposto pro
# cliente final vem do CloudFront na frente dele (ver cloudfront.tf e
# infra/README.md). Nao expor o DNS name do ALB direto pra paginas HTTPS
# (rodar-web/rodar-mobile): usar sempre o output `api_public_url`.

data "aws_subnets" "public" {
  filter {
    name   = "vpc-id"
    values = [var.vpc_id]
  }

  filter {
    name   = "tag:Name"
    values = ["adm-operacoes-subnet-public*"]
  }
}

resource "aws_security_group" "alb" {
  name        = "rumolog-dev-alb-sg"
  description = "ALB publico da api do rodar-backend."
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP publico"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "rumolog-dev-alb-sg"
  }
}

resource "aws_security_group_rule" "ecs_tasks_ingress_alb" {
  type                     = "ingress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.ecs_tasks.id
  source_security_group_id = aws_security_group.alb.id
  description              = "ALB publico chegando na api"
}

resource "aws_lb" "rumolog" {
  name               = "rumolog-dev-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.public.ids
}

resource "aws_lb_target_group" "api" {
  name        = "rumolog-dev-api-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
    timeout             = 5
    matcher             = "200"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.rumolog.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
