resource "aws_security_group" "ecs_tasks" {
  name        = "rumolog-dev-ecs-tasks-sg"
  description = "Tasks ECS do rodar-backend (api + voice-agent). Sem ALB, tudo interno a VPC."
  vpc_id      = var.vpc_id

  egress {
    description = "Saida livre (APIs externas: LiveKit, Twilio, LLM, Nominatim, ECR, Secrets Manager via NAT)."
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "rumolog-dev-ecs-tasks-sg"
  }
}

# voice-agent fala com a api pelo Cloud Map (api.rumolog.internal:8000) — libera
# tráfego entre as próprias tasks do cluster.
resource "aws_security_group_rule" "ecs_tasks_self_ingress" {
  type                     = "ingress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.ecs_tasks.id
  source_security_group_id = aws_security_group.ecs_tasks.id
  description              = "api e voice-agent conversando entre si via Cloud Map"
}

resource "aws_security_group" "db" {
  name        = "rumolog-dev-db-sg"
  description = "Instancia RDS rumolog-dev-db. So aceita 5432 das tasks ECS do rodar-backend."
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "rumolog-dev-db-sg"
  }
}

resource "aws_security_group_rule" "db_ingress_ecs_tasks" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.db.id
  source_security_group_id = aws_security_group.ecs_tasks.id
  description              = "Tasks ECS do rodar-backend (api, voice-agent)"
}

# Preserva a integração que já existia no banco antigo: o app do
# sginfra-adm-operacoes lê agregados do dashboard rumolog. A conectividade de
# rede é recriada aqui; o usuário/credencial de leitura em si precisa ser
# recriado à mão no banco novo (não existia dump/import desses dados).
resource "aws_security_group_rule" "db_ingress_sginfra_app" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.db.id
  source_security_group_id = var.existing_ecs_app_security_group_id
  description              = "Tasks ECS do sginfra-adm-operacoes lendo agregados do dashboard"
}
