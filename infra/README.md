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

## Deploy em produção: URL pública, migração e CI

A api está no ar em `https://<id>.cloudfront.net` (ver output
`api_public_url`).

**Migração: task separada, não o `CMD` da task da api.** `alembic upgrade
head` e `python -m app.seed` rodavam no `CMD` do container da api
(`backend/Dockerfile`), ou seja, em todo start/reinício de **todo** replica
do serviço — arriscado com `desired_count > 1` ou durante um deployment
(duas tasks disputando o mesmo `alembic upgrade head` ao mesmo tempo) e
redundante a cada substituição de task pelo ECS. Agora isso roda uma vez só,
numa task definition própria sem serviço (`aws_ecs_task_definition.migrate`
em `ecs.tf`), via `aws ecs run-task` (manualmente ou pela CI, ver abaixo).

### Deploy automático (CI)

A cada push em `main` que passa lint+testes, o job `deploy` do
[`../.github/workflows/ci.yml`](../.github/workflows/ci.yml):

1. Builda a imagem (`backend/Dockerfile`, com `--build-arg GIT_SHA=<sha
   curto>`) e publica no ECR com duas tags: `latest` (conveniência pra quem
   builda/roda na mão — ver "Deploy manual" abaixo) e o sha curto do commit,
   que é a que efetivamente vai pro ar no passo 3. O `GIT_SHA` vira uma
   variável de ambiente dentro do container e aparece em `GET /health`
   (campo `sha`) — é assim que o smoke do passo 4 confirma que a imagem
   deste deploy (e não uma anterior) está no ar.
2. Roda a task de migração (`aws ecs run-task` + `wait tasks-stopped`, mesma
   lógica do `migrar.sh`) e falha o job se o `exitCode` não for `0` — não
   segue pro próximo passo com uma migração quebrada.
3. Registra uma task definition nova pra `api` e pro `voice-agent`, a partir
   da que já está em uso (`describe-task-definition`), só troca o `image`
   do container pra `<repo>:<sha deste commit>` (`register-task-definition`)
   — e aponta o serviço pra essa revision (`update-service
   --task-definition`), não mais um `force-new-deployment` na mesma
   revision. Espera os dois ficarem estáveis (`wait services-stable`). Cada
   deploy fica uma revision imutável e auditável (`aws ecs
   describe-task-definition` mostra exatamente qual sha rodou quando), em
   vez de depender da tag `:latest`, que é mutável por desenho.
4. Confere `GET /health` na URL pública: falha o job se `sha` não for o
   commit deste deploy, e falha também se `ok` for falso — `/health` devolve
   **503** (não mais 200) nesse caso (`app/main.py`), então um `curl -fsS`
   simples já pega banco fora do ar. Em seguida faz login como a central
   seed (`POST /auth/sso`, sem senha) e um `GET /rotas/{id}/ocoren
   ?dry_run=true` autenticado — `dry_run` pede o arquivo sem consumir o
   número de sequência (`Empresa.ultima_sequencia_ocoren`, ver
   `app/servicos/edi._proxima_sequencia`), então o smoke confirma que a
   rota responde 200 (e que a migração
   `alembic/versions/20261127_sequencia_ocoren.py` rodou) sem gastar um
   número de sequência de produção a cada deploy só pra isso.

`api_image`/`voice_agent_image` (`terraform.tfvars`, local) só valem pro
primeiro `tofu apply` (bootstrap da task definition) e pro `migrate`, que
sempre roda imediatamente depois do push de `:latest` no passo 1 — a `api`
e o `voice-agent` passam a apontar pra revision que a CI registra no passo
3, não mais pra `aws_ecs_task_definition.*.arn` do Terraform. Por isso
`aws_ecs_service.api`/`voice_agent` (`ecs.tf`) tem
`lifecycle.ignore_changes = [task_definition]`: sem isso, o próximo
`tofu apply` veria a revision da CI como drift e devolveria o serviço pra
revision que o Terraform conhece (a do bootstrap).

### Credencial de deploy da CI e prazo de disponibilidade

**Credencial:** um usuário IAM dedicado, `rumolog-dev-ci-deploy`
(`ci.tf`), sem OIDC (decisão do time: a troca por não usar federação de
curta duração é a política ser bem restrita) — só `ecr:*Push*` neste repo
ECR, `ecs:UpdateService`/`DescribeServices` nos dois serviços,
`ecs:RunTask`/`DescribeTasks` só no cluster `rumolog-cluster-dev`,
`ecs:DescribeTaskDefinition`/`RegisterTaskDefinition` (resource `"*"` —
essas duas ações não aceitam resource-level permission na AWS, não dá pra
restringir pela família da task) e `iam:PassRole` só nas duas roles que as
tasks já usam. A access key em si
**não é gerenciada pelo Terraform** (não grava segredo no state): foi criada
uma vez com `aws iam create-access-key` e vive só nos secrets do GitHub
Actions (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` do repositório — as
outras variáveis do job, como cluster/subnets/SG, são *variables* públicas
do repositório, não secrets, porque não são sensíveis).

**Compromisso de disponibilidade:** essa access key não expira por desenho
(uma credencial fixa que nunca gira é um risco permanente, não só enquanto
o Hack Brasil avalia), então o time se compromete por escrito a não
revogá-la e a manter o cluster `rumolog-cluster-dev` (ECS, RDS, CloudFront)
no ar, saudável e sem alteração deliberada até **15/12/2026** — cobre a
reavaliação de 12/12 do Hack Brasil e os dias de congelamento da `main`
(01/12 a 12/12, quando não há mais push para alterar a imagem no ar). Depois
de 15/12, o risco de uma access key que nunca expira deixa de valer a pena
sem o prazo que o justifica: revogar a access key
(`aws iam delete-access-key`) e apagar o usuário `rumolog-dev-ci-deploy`.

### Deploy manual (fallback)

Pra rodar fora da CI (debug, ou se a credencial da CI expirar/for revogada):

```bash
cd infra/envs/dev
./migrar.sh   # usa os outputs cluster_name, migrate_task_definition_arn,
              # private_subnet_ids e ecs_tasks_security_group_id
```

**Ordem do deploy manual** (a task da api só roda `uvicorn`; não migra mais
sozinha):

1. Build e push da imagem nova pro ECR (tag `latest`, ou outra — nesse caso
   ajuste `api_image`/`voice_agent_image` em `terraform.tfvars` e rode
   `tofu apply`; isso registra uma task definition revision nova pra
   família, mas **não** troca o serviço — `aws_ecs_service.*` ignora esse
   campo de propósito, ver "Deploy automático (CI)" acima).
2. `./migrar.sh` — roda o alembic `upgrade head` e o seed **antes** de trocar
   a imagem em produção. Pular este passo com uma imagem que tenha uma
   migração pendente derruba a api (coluna/tabela que o código espera e o
   banco ainda não tem).
3. Aponta o serviço pra revision que o `tofu apply` acabou de registrar
   (`force-new-deployment` sozinho **não** pega a imagem nova, porque o
   serviço ignora o campo `task_definition` do Terraform — precisa apontar
   pra revision explicitamente):
   ```bash
   NOVA_ARN="$(aws ecs describe-task-definition --task-definition rumolog-dev-api \
     --profile cdk-manager-dev --query 'taskDefinition.taskDefinitionArn' --output text)"
   aws ecs update-service --cluster rumolog-cluster-dev --service api \
     --task-definition "$NOVA_ARN" --profile cdk-manager-dev
   # mesma coisa pro voice-agent (família rumolog-dev-voice-agent), se a imagem mudou.
   ```

O seed (`app/seed.py`) é idempotente e o `alembic upgrade head` não reaplica
migração já aplicada, então rodar `migrar.sh` de novo sem nada pendente não
tem efeito.

### Rollback

A `api`/`voice-agent` rodam a partir de uma task definition revision travada
em `<repo>:<sha do commit>` que a CI registra a cada deploy (ver "Deploy
automático (CI)" acima) — não depende de nenhuma tag mutável. Voltar atrás
é registrar uma revision nova apontando pro sha "bom", já publicado no ECR
em todo deploy verde anterior (passo 1 da seção acima), e trocar o serviço
pra ela — sem reapontar tag nenhuma no ECR. O sha em uso hoje é o campo
`sha` de `GET /health`; os shas anteriores ficam no ECR (`aws ecr
list-images --repository-name rumolog-backend`) e no histórico de commits
da `main`.

```bash
# 1. Escolha o sha curto (7 chars) do commit "bom" pra voltar (ex.: HEAD~1 em produção).
SHA_BOM=xxxxxxx
CLUSTER=rumolog-cluster-dev

# 2. Pra cada serviço, lê a task definition em uso, troca só a imagem pro sha bom e registra
# uma revision nova (a migração NÃO roda sozinha aqui: se o sha bom precisa de uma migração
# anterior desfeita, rode isso manualmente antes — ./migrar.sh não reverte, só aplica o que falta).
for SERVICO in api voice-agent; do
  TD_ATUAL="$(aws ecs describe-services --cluster "$CLUSTER" --services "$SERVICO" \
    --profile cdk-manager-dev --query 'services[0].taskDefinition' --output text)"
  NOVA_ARN="$(aws ecs describe-task-definition --task-definition "$TD_ATUAL" \
    --profile cdk-manager-dev --query 'taskDefinition' \
    | jq --arg img "140147589257.dkr.ecr.us-east-1.amazonaws.com/rumolog-backend:$SHA_BOM" '
        .containerDefinitions[0].image = $img
        | {family, taskRoleArn, executionRoleArn, networkMode, containerDefinitions,
           volumes, placementConstraints, requiresCompatibilities, cpu, memory}
      ' \
    | aws ecs register-task-definition --profile cdk-manager-dev --cli-input-json file:///dev/stdin \
        --query 'taskDefinition.taskDefinitionArn' --output text)"
  aws ecs update-service --cluster "$CLUSTER" --service "$SERVICO" --task-definition "$NOVA_ARN" \
    --profile cdk-manager-dev > /dev/null
done
aws ecs wait services-stable --cluster "$CLUSTER" --services api voice-agent --profile cdk-manager-dev

# 3. Confirme que o sha certo está no ar.
curl -fsS "$(cd infra/envs/dev && tofu output -raw api_public_url)/health" | jq .sha
```

Sem domínio registrado pra esse app, `rollback.sh` próprio não existe ainda
— os passos acima são o comando a rodar hoje; promover isso a um script em
`infra/envs/dev/` é a próxima melhoria óbvia.

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
  `api_image`/`voice_agent_image` pra `:latest` e `desired_count = 1` nos
  dois serviços — isso agora é automático, ver "Deploy automático (CI)"
  acima.

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
