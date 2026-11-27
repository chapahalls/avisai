variable "aws_profile" {
  description = "Perfil AWS CLI usado para provisionar o bootstrap (conta dev da Rumo)."
  type        = string
  default     = "cdk-manager-dev"
}

variable "region" {
  description = "Região AWS."
  type        = string
  default     = "us-east-1"
}

variable "account_id" {
  description = "Account ID da conta AWS onde o bootstrap é criado."
  type        = string
  default     = "140147589257"
}

variable "project" {
  description = "Nome do projeto, usado para nomear o bucket de state e a tabela de lock."
  type        = string
  default     = "rodar-backend"
}
