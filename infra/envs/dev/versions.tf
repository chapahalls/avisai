terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "s3" {
    bucket       = "tf-state-rodar-backend-140147589257"
    key          = "envs/dev/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true # lock nativo do S3 — sem DynamoDB (cdk-manager não tem permissão pra criar tabela)
    encrypt      = true
    profile      = "cdk-manager-dev"
  }
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project            = "rodar-backend"
      Environment        = var.env
      ManagedBy          = "OpenTofu"
      Owner              = "infra-team"
      Repository         = "rodar-backend"
      "Centro-Custo"     = "1368FB"
      "Area-Solicitante" = "Diretoria expansao RMP"
    }
  }
}
