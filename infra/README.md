# Infra do rodar-backend (AWS, OpenTofu)

Infra do rodar-backend/RumoLog na conta AWS dev da Rumo (`140147589257`,
`us-east-1`, perfil `cdk-manager-dev`). Usa OpenTofu, não CDK — essa app não
faz parte do `sginfra-adm-operacoes`, só reaproveita a VPC compartilhada dessa
conta.

## Estrutura

- `bootstrap/` — cria o bucket S3 (`tf-state-rodar-backend-140147589257`) que
  guarda o state remoto. Lock é o lockfile nativo do backend `s3`
  (`use_lockfile = true`, sem tabela DynamoDB — o usuário `cdk-manager` não
  tem permissão `dynamodb:CreateTable` nessa conta). Roda uma vez só, com
  state local. Depois disso quase nunca precisa tocar.
- `envs/dev/` — a infra de verdade: VPC (reaproveitada via data source, nunca
  criada aqui), ECS Fargate (cluster dedicado `rumolog-cluster-dev`, sem
  compartilhar com o `sginfra-cluster-dev`), Cloud Map (`rumolog.internal`,
  sem ALB — tudo interno), RDS Postgres (`rumolog-dev-db`), ECR, Secrets
  Manager.

## O que existia antes e foi decomissionado

O banco original (`rumologpipelinedevstack-dashboarddatabasef93c7646-...`)
era gerenciado por uma stack CloudFormation solta (`RumologPipelineDevStack`,
definida em `contigency_analisys_backend/infra`). Ele foi renomeado/redimensionado
na mão (virou `rumolog-dev-db`, `db.t4g.small`), o que quebrou o rastreamento
do CloudFormation. Em vez de tentar reconciliar isso, decidimos:

1. Tirar um snapshot manual final (`rumolog-dev-db-final-decommission-<data>`).
2. Apagar a stack CloudFormation (soltando os recursos que ela ainda
   rastreava) e a instância RDS órfã.
3. Criar uma instância RDS **nova**, gerenciada 100% pelo OpenTofu, sem
   import — é o `aws_db_instance.rumolog` em `envs/dev/database.tf`.

O snapshot final fica guardado na conta (manual, sem retenção automática) —
é a única cópia dos dados antigos. Se precisar recuperar algo de lá, é restore
manual do snapshot pra uma instância separada.

## Pendências pós-apply (não dá pra automatizar sem valores reais)

- **Secrets com placeholder** (`rumolog/dev/livekit`, `rumolog/dev/llm`,
  `rumolog/dev/auth`, `rumolog/dev/twilio`): preencha os valores de verdade
  com `aws secretsmanager put-secret-value --secret-id <nome> --secret-string
  '<json>' --profile cdk-manager-dev`. O OpenTofu tem `ignore_changes` no
  conteúdo desses secrets, então não vai reverter o que você colocar lá.
- **Integração de leitura do sginfra-adm-operacoes**: o banco antigo liberava
  leitura (porta 5432) pro security group das tasks do sginfra
  (`sg-002f850c754ce7e91`) — tinha um usuário Postgres read-only
  (`rumolog/dev/temp-user-dev/postgres-readonly`) que lia agregados do
  dashboard. A regra de rede foi recriada aqui
  (`aws_security_group_rule.db_ingress_sginfra_app`), mas o usuário read-only
  em si **não existe no banco novo** — precisa recriar na mão (`CREATE USER
  ... GRANT ...`) e atualizar a connection string que o app do sginfra usa.
- **Imagens placeholder**: `api_image`/`voice_agent_image` apontam pra uma
  imagem pública qualquer até o CI publicar a imagem real no ECR
  (`rumolog-backend`). Depois que o pipeline publicar, atualize
  `terraform.tfvars` com a tag real e reaplique (ou troque via `aws ecs
  update-service --force-new-deployment` depois de dar push com a mesma tag).

## Como aplicar

```bash
cd infra/bootstrap
tofu init
tofu apply   # cria o bucket de state + tabela de lock (só na primeira vez)

cd ../envs/dev
tofu init
tofu plan
tofu apply
```
