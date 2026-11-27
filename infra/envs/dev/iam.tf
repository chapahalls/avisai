data "aws_iam_policy_document" "ecs_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role — puxa a imagem do ECR, escreve logs, lê os secrets que vão
# virar env var no container.
resource "aws_iam_role" "ecs_execution" {
  name               = "${var.cluster_name}-task-execution-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "ecs_execution_secrets" {
  statement {
    actions = ["secretsmanager:GetSecretValue"]
    resources = concat(
      [
        aws_secretsmanager_secret.app_database_url.arn,
      ],
      [for s in aws_secretsmanager_secret.app : s.arn],
    )
  }
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name   = "read-app-secrets"
  role   = aws_iam_role.ecs_execution.id
  policy = data.aws_iam_policy_document.ecs_execution_secrets.json
}

# Task role — permissões que o código da aplicação usa em runtime. Vazia por
# enquanto (a app não chama nenhuma API AWS hoje); existe só pra não deixar o
# container sem task role nenhuma, caso precise mais pra frente (S3, SES etc).
resource "aws_iam_role" "ecs_task" {
  name               = "${var.cluster_name}-task-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}
