#!/usr/bin/env bash
# Roda a migração (alembic upgrade head + seed) uma vez, fora do CMD da task da api
# (ver aws_ecs_task_definition.migrate em ecs.tf e "Deploy em produção" no infra/README.md).
# Rode depois de publicar uma imagem nova no ECR e antes (ou depois) de
# `aws ecs update-service --force-new-deployment` nos dois sentidos é seguro: o seed é
# idempotente (app/seed.py) e o alembic upgrade head não reaplica migração já aplicada.
set -euo pipefail
cd "$(dirname "$0")"

PROFILE="${AWS_PROFILE:-cdk-manager-dev}"  # default = var.aws_profile em variables.tf
REGION="${AWS_REGION:-us-east-1}"          # default = var.region em variables.tf
CLUSTER="$(tofu output -raw cluster_name)"
TASK_DEF="$(tofu output -raw migrate_task_definition_arn)"
SUBNETS="$(tofu output -json private_subnet_ids | tr -d '[]\n "' )"
SG="$(tofu output -raw ecs_tasks_security_group_id)"

echo "cluster=$CLUSTER task_def=$TASK_DEF subnets=$SUBNETS sg=$SG"

TASK_ARN="$(aws ecs run-task \
  --profile "$PROFILE" --region "$REGION" \
  --cluster "$CLUSTER" \
  --task-definition "$TASK_DEF" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=DISABLED}" \
  --query 'tasks[0].taskArn' --output text)"

echo "task=$TASK_ARN — acompanhe em /ecs/rumolog-dev/api (prefixo migrate) no CloudWatch"
aws ecs wait tasks-stopped --profile "$PROFILE" --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK_ARN"

EXIT_CODE="$(aws ecs describe-tasks --profile "$PROFILE" --region "$REGION" --cluster "$CLUSTER" --tasks "$TASK_ARN" \
  --query 'tasks[0].containers[0].exitCode' --output text)"
echo "exitCode=$EXIT_CODE"
[ "$EXIT_CODE" = "0" ]
