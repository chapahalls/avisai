# Reaproveita a VPC compartilhada da conta dev (sginfra-adm-operacoes) — nunca
# criamos uma VPC nova aqui, só lemos a existente via data source.

data "aws_vpc" "shared" {
  id = var.vpc_id
}

# Subnets privadas (já têm rota 0.0.0.0/0 via NAT Gateway) — é onde ficam as
# tasks Fargate e a instância RDS. Sem ALB/subnet pública envolvida.
data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [var.vpc_id]
  }

  filter {
    name   = "tag:Name"
    values = ["adm-operacoes-subnet-private*"]
  }
}
