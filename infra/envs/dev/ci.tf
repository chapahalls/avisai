# Usuário de serviço pra CI (GitHub Actions) publicar imagem nova e atualizar os
# serviços ECS a cada push na main — ver "Deploy automático (CI)" no infra/README.md.
#
# Sem OIDC por decisão do time: a troca é a credencial ser uma access key fixa (não
# expira/gira sozinha) em vez de federação por token de curta duração. O que compensa
# isso é a política abaixo: só este repo ECR, só o cluster rumolog-dev, só RunTask na
# task de migração e só PassRole nas 2 roles que as tasks já usam — nada de IAM, rede,
# RDS ou outro `tofu apply` (a chave não consegue mudar a própria política).
resource "aws_iam_user" "ci_deploy" {
  name = "rumolog-dev-ci-deploy"
}

data "aws_iam_policy_document" "ci_deploy" {
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"] # a AWS exige recurso "*" nessa ação específica; não dá acesso a outro repo
  }

  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:PutImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
    ]
    resources = [aws_ecr_repository.rumolog_backend.arn]
  }

  statement {
    sid       = "EcsForceNewDeployment"
    actions   = ["ecs:UpdateService", "ecs:DescribeServices"]
    resources = [aws_ecs_service.api.id, aws_ecs_service.voice_agent.id]
  }

  statement {
    sid       = "EcsRunTaskDeMigracao"
    actions   = ["ecs:RunTask"]
    resources = ["arn:aws:ecs:${var.region}:${var.account_id}:task-definition/${aws_ecs_task_definition.migrate.family}:*"]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.rumolog.arn]
    }
  }

  statement {
    sid       = "EcsDescreverTasksDoCluster"
    actions   = ["ecs:DescribeTasks"]
    resources = ["*"] # task ARN não existe antes do RunTask; restrito pelo cluster abaixo
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.rumolog.arn]
    }
  }

  statement {
    sid       = "PassRoleParaAsTasksDaApi"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.ecs_execution.arn, aws_iam_role.ecs_task.arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_user_policy" "ci_deploy" {
  name   = "deploy-rumolog-dev"
  user   = aws_iam_user.ci_deploy.name
  policy = data.aws_iam_policy_document.ci_deploy.json
}

# A access key em si NÃO é criada aqui (aws_iam_access_key gravaria o secret em
# texto no state do Terraform). Foi criada uma vez na mão (`aws iam create-access-key
# --user-name rumolog-dev-ci-deploy`) e guardada só nos secrets do GitHub Actions
# (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY do repositório), nunca neste código.
