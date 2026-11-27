variable "aws_profile" {
  description = "Perfil AWS CLI (conta dev da Rumo)."
  type        = string
  default     = "cdk-manager-dev"
}

variable "region" {
  description = "Região AWS."
  type        = string
  default     = "us-east-1"
}

variable "env" {
  description = "Nome do ambiente (usado em tags e nomes de recursos)."
  type        = string
  default     = "dev"
}

variable "account_id" {
  description = "Account ID da conta AWS dev da Rumo."
  type        = string
  default     = "140147589257"
}

variable "vpc_id" {
  description = "VPC compartilhada já existente na conta dev (sginfra-adm-operacoes)."
  type        = string
  default     = "vpc-0f3ec8d0566651c6d"
}

variable "existing_ecs_app_security_group_id" {
  description = <<-EOT
    Security group das tasks ECS do sginfra-adm-operacoes (sg-002f850c754ce7e91).
    O dashboard antigo liberava leitura no Postgres pra esse SG (um serviço lia
    agregados do rumolog). Mantemos a regra pra não quebrar essa integração;
    o usuário/credencial de leitura em si precisa ser recriado à mão no banco novo.
  EOT
  type        = string
  default     = "sg-002f850c754ce7e91"
}

variable "cluster_name" {
  description = "Nome do cluster ECS dedicado ao rodar-backend."
  type        = string
  default     = "rumolog-cluster-dev"
}

variable "service_discovery_namespace" {
  description = "Namespace privado do Cloud Map usado pelos serviços do rodar-backend."
  type        = string
  default     = "rumolog.internal"
}

variable "db_instance_identifier" {
  description = "Identificador da instância RDS."
  type        = string
  default     = "rumolog-dev-db"
}

variable "db_instance_class" {
  description = "Classe da instância RDS."
  type        = string
  default     = "db.t4g.small"
}

variable "db_engine_version" {
  description = "Versão do PostgreSQL."
  type        = string
  default     = "16.4"
}

variable "db_name" {
  description = "Nome do banco de dados."
  type        = string
  default     = "rumolog"
}

variable "db_master_username" {
  description = "Usuário master do banco."
  type        = string
  default     = "rumolog_admin"
}

variable "db_allocated_storage_gib" {
  description = "Storage inicial (GiB)."
  type        = number
  default     = 20
}

variable "db_max_allocated_storage_gib" {
  description = "Storage máximo (GiB) pro autoscaling de storage."
  type        = number
  default     = 100
}

variable "api_image" {
  description = "Imagem do container da API (ECR URI:tag). Placeholder até o CI publicar a primeira imagem real."
  type        = string
  default     = "public.ecr.aws/docker/library/httpd:alpine"
}

variable "voice_agent_image" {
  description = "Imagem do container do voice-agent (ECR URI:tag). Placeholder até o CI publicar a primeira imagem real."
  type        = string
  default     = "public.ecr.aws/docker/library/httpd:alpine"
}

variable "api_desired_count" {
  description = "0 até o CI publicar a imagem de verdade no ECR (a placeholder não roda a app, só ficaria em crash loop)."
  type        = number
  default     = 0
}

variable "voice_agent_desired_count" {
  description = "0 até o CI publicar a imagem de verdade no ECR (a placeholder não roda a app, só ficaria em crash loop)."
  type        = number
  default     = 0
}

variable "api_cpu" {
  type    = number
  default = 512
}

variable "api_memory" {
  type    = number
  default = 1024
}

variable "voice_agent_cpu" {
  type    = number
  default = 512
}

variable "voice_agent_memory" {
  type    = number
  default = 1024
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "cors_origins" {
  description = <<-EOT
    Origens liberadas no CORS da api. O painel rodar-web (Henry) saiu do
    GitHub Pages (que parou de responder 404 nas publicações de 27/11) e
    ficou só na Vercel — ver commit 69cdfab do rodar-web.
  EOT
  type        = list(string)
  default = [
    "https://rodar-web-beta.vercel.app",
  ]
}
