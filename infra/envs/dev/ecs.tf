resource "aws_ecs_cluster" "rumolog" {
  name = var.cluster_name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

locals {
  # Env vars não sensíveis, iguais pros dois serviços (api e voice-agent) —
  # espelha o docker-compose.yml e o .env.example.
  common_environment = {
    AUTH_OBRIGATORIA               = "true"
    AUTH_TOKEN_VALIDADE_H          = "12"
    CORS_ORIGENS                   = jsonencode(var.cors_origins)
    PUBLIC_URL                     = "http://${aws_lb.rumolog.dns_name}"
    LIGACOES_MANUAIS_MAX           = "5"
    LIGACOES_MANUAIS_JANELA_S      = "600"
    RECEBEDOR_MODO                 = "rtc"
    RECEBEDOR_TELEFONE_E164        = "+5519900000002"
    CHAMADA_OPERADOR_TIMEOUT_S     = "30"
    CCO_INTERVALO_S                = "20"
    CCO_MAX_TENTATIVAS             = "3"
    ESTADIA_ACELERACAO             = "1"
    LIGAR_RECEBEDOR_NA_APROXIMACAO = "false"
    LIGACAO_TIMEOUT_S              = "180"
    GEOCODIFICACAO_PROVEDOR        = "nominatim"
    GEOCODIFICACAO_URL             = "https://nominatim.openstreetmap.org"
    LIVEKIT_TOKEN_VALIDADE_MIN     = "60"
  }

  common_secrets = [
    {
      name      = "DATABASE_URL"
      valueFrom = aws_secretsmanager_secret.app_database_url.arn
    },
    { name = "AUTH_SEGREDO", valueFrom = "${aws_secretsmanager_secret.app["auth"].arn}:AUTH_SEGREDO::" },
    { name = "LIVEKIT_URL", valueFrom = "${aws_secretsmanager_secret.app["livekit"].arn}:LIVEKIT_URL::" },
    { name = "LIVEKIT_API_KEY", valueFrom = "${aws_secretsmanager_secret.app["livekit"].arn}:LIVEKIT_API_KEY::" },
    { name = "LIVEKIT_API_SECRET", valueFrom = "${aws_secretsmanager_secret.app["livekit"].arn}:LIVEKIT_API_SECRET::" },
    { name = "LIVEKIT_AGENT_NAME", valueFrom = "${aws_secretsmanager_secret.app["livekit"].arn}:LIVEKIT_AGENT_NAME::" },
    { name = "LIVEKIT_SIP_TRUNK_ID", valueFrom = "${aws_secretsmanager_secret.app["livekit"].arn}:LIVEKIT_SIP_TRUNK_ID::" },
    { name = "LIVEKIT_SIP_FROM_NUMBER", valueFrom = "${aws_secretsmanager_secret.app["livekit"].arn}:LIVEKIT_SIP_FROM_NUMBER::" },
    { name = "LIVEKIT_MODEL", valueFrom = "${aws_secretsmanager_secret.app["livekit"].arn}:LIVEKIT_MODEL::" },
    { name = "LIVEKIT_VOICE", valueFrom = "${aws_secretsmanager_secret.app["livekit"].arn}:LIVEKIT_VOICE::" },
    { name = "LLM_API_KEY", valueFrom = "${aws_secretsmanager_secret.app["llm"].arn}:LLM_API_KEY::" },
    { name = "LLM_BASE_URL", valueFrom = "${aws_secretsmanager_secret.app["llm"].arn}:LLM_BASE_URL::" },
    { name = "LLM_MODEL", valueFrom = "${aws_secretsmanager_secret.app["llm"].arn}:LLM_MODEL::" },
    { name = "TWILIO_ACCOUNT_SID", valueFrom = "${aws_secretsmanager_secret.app["twilio"].arn}:TWILIO_ACCOUNT_SID::" },
    { name = "TWILIO_AUTH_TOKEN", valueFrom = "${aws_secretsmanager_secret.app["twilio"].arn}:TWILIO_AUTH_TOKEN::" },
    { name = "TWILIO_FROM_NUMBER", valueFrom = "${aws_secretsmanager_secret.app["twilio"].arn}:TWILIO_FROM_NUMBER::" },
    { name = "TWILIO_OPERATOR_PHONE_E164", valueFrom = "${aws_secretsmanager_secret.app["twilio"].arn}:TWILIO_OPERATOR_PHONE_E164::" },
    { name = "TWILIO_SUPERVISOR_PHONE_E164", valueFrom = "${aws_secretsmanager_secret.app["twilio"].arn}:TWILIO_SUPERVISOR_PHONE_E164::" },
  ]
}

resource "aws_ecs_task_definition" "api" {
  family                   = "rumolog-dev-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "api"
    image     = var.api_image
    essential = true
    command   = ["sh", "-c", "alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    environment = [for k, v in local.common_environment : { name = k, value = v }]
    secrets     = local.common_secrets

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "api"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "voice_agent" {
  family                   = "rumolog-dev-voice-agent"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.voice_agent_cpu
  memory                   = var.voice_agent_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name      = "voice-agent"
    image     = var.voice_agent_image
    essential = true
    command   = ["python", "-m", "app.voice_agent", "start"]

    environment = concat(
      [for k, v in local.common_environment : { name = k, value = v }],
      [{ name = "LIVEKIT_LLM_URL", value = "http://api.${var.service_discovery_namespace}:8000/v1" }],
    )
    secrets = local.common_secrets

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.voice_agent.name
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "voice-agent"
      }
    }
  }])
}

resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.rumolog.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.private.ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.api.arn
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.http]
}

resource "aws_ecs_service" "voice_agent" {
  name            = "voice-agent"
  cluster         = aws_ecs_cluster.rumolog.id
  task_definition = aws_ecs_task_definition.voice_agent.arn
  desired_count   = var.voice_agent_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.private.ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }

  depends_on = [aws_ecs_service.api]
}
