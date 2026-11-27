# RDS novo, de verdade gerenciado pelo OpenTofu (o antigo, criado pela
# CloudFormation stack RumologPipelineDevStack, foi decomissionado: tirou
# snapshot final e apagou a instância antes desse apply — não tem import aqui).

resource "random_password" "db_master" {
  length  = 32
  special = false # evita caracteres que dão problema em connection string/URL
}

resource "aws_db_subnet_group" "rumolog" {
  name       = "rumolog-dev-db-subnet-group"
  subnet_ids = data.aws_subnets.private.ids

  tags = {
    Name = "rumolog-dev-db-subnet-group"
  }
}

resource "aws_db_instance" "rumolog" {
  identifier     = var.db_instance_identifier
  engine         = "postgres"
  engine_version = var.db_engine_version

  instance_class        = var.db_instance_class
  allocated_storage     = var.db_allocated_storage_gib
  max_allocated_storage = var.db_max_allocated_storage_gib
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_master_username
  password = random_password.db_master.result
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.rumolog.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false

  multi_az                  = false
  backup_retention_period   = 7
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.db_instance_identifier}-final"
  apply_immediately         = true

  tags = {
    Name = var.db_instance_identifier
  }
}

# Credenciais puras do master user — pro uso administrativo/rotação futura.
resource "aws_secretsmanager_secret" "db_master" {
  name                    = "rumolog/dev/rds_master"
  description             = "Master credentials da instância ${var.db_instance_identifier}."
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "db_master" {
  secret_id = aws_secretsmanager_secret.db_master.id
  secret_string = jsonencode({
    username = var.db_master_username
    password = random_password.db_master.result
  })
}

# DATABASE_URL pronta pra injetar direto na app (settings.database_url espera
# uma única string no formato postgresql+psycopg://...).
resource "aws_secretsmanager_secret" "app_database_url" {
  name                    = "rumolog/dev/database"
  description             = "DATABASE_URL completa do rodar-backend (api + voice-agent)."
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "app_database_url" {
  secret_id     = aws_secretsmanager_secret.app_database_url.id
  secret_string = "postgresql+psycopg://${var.db_master_username}:${random_password.db_master.result}@${aws_db_instance.rumolog.address}:${aws_db_instance.rumolog.port}/${var.db_name}"
}
