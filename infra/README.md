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
  usado pelo voice-agent pra falar com a api), ALB público
  (`rumolog-dev-alb`, só HTTP/80 — ver HTTPS abaixo) expondo a api pra fora
  da VPC, CloudFront na frente do ALB (`cloudfront.tf`, HTTPS pra fora sem
  domínio próprio), RDS Postgres (`rumolog-dev-db`), ECR, Secrets Manager.

## Deploy em produção: URL pública e migração

A api está no ar em `https://<id>.cloudfront.net` (ver output
`api_public_url`).

**Migração: task separada, não o `CMD` da task da api.** `alembic upgrade
head` e `python -m app.seed` rodavam no `CMD` do container da api
(`backend/Dockerfile`), ou seja, em todo start/reinício de **todo** replica
do serviço — arriscado com `desired_count > 1` ou durante um deployment
(duas tasks disputando o mesmo `alembic upgrade head` ao mesmo tempo) e
redundante a cada substituição de task pelo ECS. Agora isso roda uma vez só,
numa task definition própria sem serviço (`aws_ecs_task_definition.migrate`
em `ecs.tf`), via `aws ecs run-task`:

```bash
cd infra/envs/dev
./migrar.sh   # usa os outputs cluster_name, migrate_task_definition_arn,
              # private_subnet_ids e ecs_tasks_security_group_id
```

**Ordem do deploy** (a task da api só roda `uvicorn`; não migra mais sozinha):

1. Build e push da imagem nova pro ECR (tag do commit).
2. `terraform.tfvars` com a tag nova em `api_image`/`voice_agent_image` (ou
   `tofu apply` já aplica o `command` novo da task da api, se for a primeira
   vez rodando esta mudança).
3. `./migrar.sh` — roda o alembic `upgrade head` e o seed **antes** de trocar
   a imagem em produção. Pular este passo com uma imagem que tenha uma
   migração pendente derruba a api (coluna/tabela que o código espera e o
   banco ainda não tem).
4. `aws ecs update-service --cluster rumolog-cluster-dev --service api
   --force-new-deployment` (e o mesmo pro `voice-agent`, se a imagem mudou).

O seed (`app/seed.py`) é idempotente e o `alembic upgrade head` não reaplica
migração já aplicada, então rodar `migrar.sh` de novo sem nada pendente não
tem efeito.

**HTTPS sem domínio próprio**: o ALB (`alb.tf`) só tem listener HTTP/80 —
sem domínio registrado pra esse app não tem como emitir um certificado ACM
nele. `rodar-web`/`rodar-mobile` são servidos via GitHub Pages (HTTPS), e
chamar um endpoint HTTP puro de uma página HTTPS é bloqueado pelo navegador
(mixed content). A solução (`cloudfront.tf`) é colocar uma distribuição
CloudFront na frente do ALB: ela já vem com certificado TLS válido no
domínio compartilhado `*.cloudfront.net`, emitido automaticamente pela AWS,
sem custo e sem precisar comprovar posse de domínio nenhum. O tráfego
CloudFront → ALB continua em HTTP (`origin_protocol_policy = "http-only"`),
mas isso é interno à rede da AWS, não exposto ao cliente final. Cache fica
desabilitado (`Managed-CachingDisabled` + `Managed-AllViewer`) porque é uma
api, não um site estático — toda request (headers, query string, cookies,
`Authorization`) passa direto pro ALB. `rodar-web`/`rodar-mobile` devem
apontar pra `api_public_url` (CloudFront), nunca pro DNS name do ALB
direto.

**Pegadinha de rede já resolvida**: as tasks ECS ficam nas subnets privadas,
e o tráfego pra `logs`/`ssmmessages`/`secretsmanager`(parcial)/`efs` passa
por um VPC Interface Endpoint compartilhado cujo security group
(`sg-002f850c754ce7e91`, na prática o SG de tasks do `sginfra-cluster-dev`)
só libera 443 pra uma allow-list explícita de SGs de outras apps. Sem uma
regra lá, o ECS mata a task com `ResourceInitializationError: ... cannot
find the Amazon CloudWatch log group ... connection issue` mesmo com
NAT/rotas/NACLs todas certas. A regra pro nosso SG já foi adicionada em
`security_groups.tf` (`aws_security_group_rule.shared_logs_endpoint_ingress_ecs_tasks`),
mas o SG de destino em si não é gerenciado por este state (é infra
compartilhada da VPC).

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

- **Secrets com placeholder**: `rumolog/dev/livekit`, `rumolog/dev/llm` e
  `rumolog/dev/auth` já foram preenchidos com os valores reais (vieram do
  `.env` local). `rumolog/dev/twilio` continua `CHANGE_ME` — não tem
  credencial Twilio disponível ainda; sem isso o app só loga
  `twilio_configurado: false` (não derruba a api). Pra preencher depois:
  `aws secretsmanager put-secret-value --secret-id <nome> --secret-string
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
- **Imagens**: já builda e publicada no ECR (`rumolog-backend`), tags `latest`
  e a SHA curta do commit. `terraform.tfvars` (local, gitignored) aponta
  `api_image`/`voice_agent_image` pra essa tag real e `desired_count = 1`
  nos dois serviços. Depois de um push novo da imagem com a mesma tag, só
  `aws ecs update-service --force-new-deployment` já pega a versão nova
  (sem precisar reaplicar o Tofu).

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
