# Bootstrap: bucket S3 para guardar o state do OpenTofu de `envs/dev` (e
# futuros envs). Segue a convenção de nome já usada nessa conta AWS:
# "tf-state-<projeto>-<account_id>".
#
# Lock é feito com o lockfile nativo do S3 (`use_lockfile` no backend "s3",
# suportado desde o OpenTofu 1.10), sem tabela DynamoDB — o usuário
# cdk-manager não tem permissão pra dynamodb:CreateTable nessa conta.
#
# Esse layer usa state local (de propósito: é o que cria o backend remoto que
# todos os outros usam). Roda uma vez só; depois disso é raro precisar tocar.

locals {
  state_bucket_name = "tf-state-${var.project}-${var.account_id}"
}

resource "aws_s3_bucket" "tf_state" {
  bucket = local.state_bucket_name

  tags = {
    Project            = var.project
    Environment        = "shared"
    ManagedBy          = "OpenTofu"
    Owner              = "infra-team"
    Repository         = "rodar-backend"
    "Centro-Custo"     = "1368FB"
    "Area-Solicitante" = "Diretoria expansao RMP"
  }
}

resource "aws_s3_bucket_versioning" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "tf_state" {
  bucket = aws_s3_bucket.tf_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
