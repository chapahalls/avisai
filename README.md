# RODAR · backend

[![CI](https://github.com/rodarglobal/rodar-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/rodarglobal/rodar-backend/actions/workflows/ci.yml)
[![API](https://img.shields.io/badge/api-online%20(AWS%2C%20com%20banco)-2ea44f?logo=amazonaws)](https://d3fy4m7zwukr3x.cloudfront.net/docs)

API persistente no ar na **AWS** (ECS Fargate + RDS Postgres gerenciado), HTTPS sem domínio próprio via CloudFront: [d3fy4m7zwukr3x.cloudfront.net](https://d3fy4m7zwukr3x.cloudfront.net), com a documentação interativa (Swagger) em **[/docs](https://d3fy4m7zwukr3x.cloudfront.net/docs)**. `GET /health` confere o banco de verdade (`banco_ok: true`); [detalhe abaixo](#já-em-produção-aws-persistente-com-banco-e-https). CI no GitHub Actions (lint com ruff e testes com pytest) a cada push e pull request em `main`; passando, há também um deploy automático na **Vercel**, [rodar-backend-five.vercel.app](https://rodar-backend-five.vercel.app) — esse é **temporário, só para o Hack Brasil, e sem banco** (nenhum login funciona nele); leia [a ressalva](#já-em-produção-temporário-para-o-hack-brasil) antes de testar uma rota que toque o banco por ali.

Copiloto de voz do RODAR para transportadoras, focado no **caminhão parado**:
1. Na aproximação, o agente avisa o motorista e o CCO.
2. Na chegada, cria a Task do CCO e conta a estadia (Lei 11.442, franquia de 5 h, R$ 2,50 por t/h).
3. Insiste com o CCO e, sem resposta, **liga para o recebedor**.
4. Registra a resposta do recebedor como prova e a repassa por voz ao motorista.

Time RODAR (4 pessoas: Jeferson, Henry, Lucas e Eduardo) · backend e infra: Lucas.

> **Histórico:** o projeto começou como *AvisAI* no hackathon UNMUTE by Agora (21–22/11/2026) e continua como **RODAR** no Hack Brasil 2026, na trilha Logística & automação. Os repositórios foram criados em 22/11/2026 e todo o histórico de commits está neles; o AvisAI virou o nome do agente de voz do RODAR. **Nenhum código anterior a 04/11/2026 21h (abertura oficial do Hack Brasil) entrou neste repositório:** o primeiro commit é de 22/11/2026, depois da abertura. Os três primeiros commits têm o mesmo segundo (`02:42:12 -03:00`) porque o trabalho feito em 21–22/11 no UNMUTE by Agora foi organizado em commits e enviado de uma vez na criação deste repositório — não é histórico de um projeto anterior à regra.

Licença: [MIT](LICENSE). As tags `v1.0-entrega` a `v1.3-entrega` marcam as versões entregues no UNMUTE by Agora; a versão avaliada no Hack Brasil é o último commit de `main`.

**Repositórios do projeto** (todos públicos):
| Repo | O quê | Responsável |
|---|---|---|
| [rodarglobal/rodar-backend](https://github.com/rodarglobal/rodar-backend) | este backend: API, agente de voz LiveKit, regras, infra Docker | Lucas |
| [rodarglobal/rodar-mobile](https://github.com/rodarglobal/rodar-mobile) | app do motorista (React Native / Expo): voz LiveKit, mapa, sincronização com o backend | Jeferson |
| [rodarglobal/rodar-web](https://github.com/rodarglobal/rodar-web) | painel do CCO (React + Vite): frota, Tasks, ligações, indicadores, publicação de rotas | Henry |
| [rodarglobal/rodar-ideas](https://github.com/rodarglobal/rodar-ideas) | pesquisa do problema com fontes, decisões de produto (ADRs) e plano (não entra na submissão) | time |

O áudio WebRTC e o worker de voz rodam no **LiveKit**. Os clientes publicam áudio diretamente na sala; o worker usa Gemini Live pelo LiveKit Inference e encaminha ferramentas, transcrições e eventos ao gateway do backend. A telefonia opcional usa LiveKit SIP.

## Para o júri

| | |
|---|---|
| **Trilha** | Logística & automação |
| **Em uma frase** | Um agente de voz que avisa o recebedor antes da chegada, conta a estadia do caminhão parado (Lei 11.442) e só chama a central quando alguém precisa decidir. |
| **Demo no ar** | [painel do CCO, modo Demo](https://rodar-web-beta.vercel.app/login) (clique em **Entrar com SSO**) — **só na Vercel**: o `rodar-web` saiu do GitHub Pages em 27/11 (parou de responder 404 nas publicações daquele dia) e ficou só nesse host; não use links antigos em `rodarglobal.github.io/rodar-web`. O app do motorista é nativo (Expo/React Native): sem demo web própria, veja o [tour em vídeo](#ver-sem-instalar-nada) |
| **API em produção** | backend persistente na **AWS** (ECS Fargate + RDS Postgres gerenciado), HTTPS sem domínio próprio via CloudFront: [d3fy4m7zwukr3x.cloudfront.net/docs](https://d3fy4m7zwukr3x.cloudfront.net/docs) · também em deploy contínuo na **Vercel**: [rodar-backend-five.vercel.app/docs](https://rodar-backend-five.vercel.app/docs) — esse é **temporário, só para o Hack Brasil**, sem banco; leia [abaixo](#já-em-produção-temporário-para-o-hack-brasil) antes de usar |
| **Ver sem instalar nada** | [tour em vídeo de 1 min](https://github.com/rodarglobal/rodar-web/blob/main/docs/assets/readme/tour.mp4) do site e do painel · [tour do app do motorista (1 min)](https://github.com/rodarglobal/rodar-mobile/blob/main/docs/assets/readme/tour.mp4) · [validação ponta a ponta histórica, anterior à troca do provedor de voz](https://github.com/rodarglobal/rodar-backend/blob/main/evidence/validacao.md) (33/33, era Agora, LLM em contingência; **o caminho de voz atual, no LiveKit, ainda não tem uma validação ponta a ponta publicada**) · [telas do app](https://github.com/rodarglobal/rodar-mobile#telas-do-aplicativo) |
| **Repositórios** | [rodar-backend](https://github.com/rodarglobal/rodar-backend) (este) · [rodar-web](https://github.com/rodarglobal/rodar-web) · [rodar-mobile](https://github.com/rodarglobal/rodar-mobile) |
| **Qualidade** | CI em cada repositório com lint e testes (e typecheck nos fronts) · 625 testes automatizados: 389 no backend, 127 no web, 109 no mobile · neste repo, CI no GitHub Actions a cada push; passando, publica a imagem e atualiza `api`+`voice-agent` na AWS automaticamente (ver [infra/README.md](infra/README.md)), e a Vercel (sem banco) também recebe deploy automático |
| **Segurança** | JWT assinado no login e exigido em toda escrita (padrão), papel `cco` nas ações da central, motorista só na própria rota, CORS restrito e limite de ligações. O que falta para produção está [escrito aqui](#o-que-falta-para-produção) |
| **O que é simulado** | login sem senha, GPS da rota, documentos fiscais e o modo Demo do painel: [lista completa](#simulado--pré-existente-e5e8) |
| **Glossário** | **CCO**: a central de operações da transportadora · **recebedor**: quem descarrega (CD, atacado, loja) · **doca**: o portão de descarga · **estadia**: o valor que a lei manda pagar pelo caminhão parado além de 5 h (a **franquia**; Lei 11.442) · **geocerca**: o raio em volta do destino que marca a chegada · **Task**: o pedido que o CCO precisa responder |
<!-- Vídeo de 3 min do Hack Brasil: incluir a linha aqui antes de 30/11. -->

## Por que importa

- **11h40 parado num CD.** Na Grande SP, a descarga levou 5h09 em média em 2025, a maior em 10 anos, e 11h40 nos centros de distribuição ([IER 2025, IPTC/SETCESP](https://setcesp.org.br/noticias/a-demora-que-compromete-a-eficiencia-2/), 175 recebedores).
- **9 em cada 10 não recebem pela espera.** 91% dos caminhoneiros autônomos que esperam mais de 5 h não recebem a estadia, embora a lei a garanta ([CNTA 2025](https://mundologistica.com.br/noticias/caminhoneiros-autonomos-aceitam-frete-abaixo-do-piso-por-necessidade), 2.002 autônomos; amostra não probabilística).
- **Ninguém registra o tempo parado.** Sem hora de chegada provada, não há o que cobrar.

**Quanto vale, por entrega:** uma carreta de 30 t que espera 11h40 num CD tem 7 h além da franquia: 7 h × 30 t × R$ 2,50 ([valor da ANTT](https://mundologistica.com.br/noticias/antt-reajusta-estadia-tempo-adicional-carga-descarga)) = **R$ 525 de estadia**, calculada por este backend. Numa frota de 50 carretas com uma entrega assim por semana, são cerca de **R$ 113 mil por mês** de estadia devida que hoje não é cobrada por falta de prova (estimativa nossa, com as premissas acima).

## Propósito, fronteiras e estado atual

O backend coordena a operação que começa na viagem atribuída e termina na descarga: recebe posições, detecta aproximação/chegada, cria Tasks, calcula estadia, registra chamadas, persiste mensagens/chamados e entrega atualizações aos dois frontends. Ele é adequado para demonstrar esse fluxo com dados fictícios e contratos integráveis, mas não deve ser tratado como uma plataforma pronta para operação real.

| Área | Implementado no repositório | Limite atual |
|---|---|---|
| Operação | rotas, geocerca, Tasks, escalonamento, estadia, ocorrências, pedidos e timeline | seed, GPS e documentos de demonstração |
| Tempo real | SSE do CCO e WebSocket para rota/motorista | sem replay/cursor garantido; clientes precisam reconciliar por REST |
| Voz e chamadas | LiveKit RTC/Agents com Gemini Live, ferramentas auditadas no backend, cascata Twilio → LiveKit RTC/SIP | LiveKit Cloud/Inference, PSTN e RTC exigem credenciais e configuração de trunk |
| Arquivos | metadados no Postgres e binários em `ARQUIVOS_DIR`; só a central anexa, e só a central e o motorista da rota leem e baixam | sem versionamento de arquivos |
| Integração EDI (OCOREN) | motor de largura fixa único (`conectores/edi/motor.py`) lê os layouts OCOREN 5.0 e 3.1 como dado, com perfil por parceiro (`ParceiroEdi`, De-Para editável) (`docs/edi/ocoren-integracao.md`) | só download manual pelo CCO; sem SFTP/fila, CNPJ e NF-e fictícios na demo, De-Para sem homologação de parceiro real |
| Identidade e acesso | perfis persistidos; `/auth/sso` emite **JWT assinado** (HS256, papel e validade); com `AUTH_OBRIGATORIA=true` (padrão) toda escrita exige token, as ações da central exigem papel `cco` e o motorista só age na rota atribuída a ele; CORS só nas origens de `CORS_ORIGENS`; segredo do LLM comparado em tempo constante; limite de ligações manuais por rota | o login continua simulado (sem senha); as leituras (`GET`, SSE e WebSocket) seguem abertas |

Os frontends devem conservar essa distinção. Não use um campo ausente da API para gerar GPS, valor de estadia, documento, evento ou sucesso de telefonia no cliente.

---

## Dependências

- **Para rodar:** Docker com Compose v2. Nada roda direto na máquina; as imagens instalam o resto.
- **Backend e worker (Python 3.12):** FastAPI, Uvicorn, SQLModel, Alembic, psycopg, pydantic-settings e LiveKit API/Agents (1.8.8+ para Gemini Live 3.8). As dependências estão em `backend/requirements.txt`; as de desenvolvimento em `backend/requirements-dev.txt`.
- **Infra:** Postgres 16 e cloudflared (túnel público), ambos via `docker-compose.yml`.
- **Serviços externos:**
  - LiveKit Cloud (URL, API key e secret; Inference para Gemini Live);
  - LLM compatível com OpenAI (opcional para os endpoints de conversa e avaliação; a voz usa o modelo LiveKit configurado);
  - OpenAI Audio Transcriptions (reconhecimento de fala), só para transcrever falas offline gravadas sem sinal (`POST /rotas/{id}/falas-offline`); a conversa de voz em tempo real não passa por essa API, só pelo LiveKit Inference;
  - Nominatim (OpenStreetMap), para a busca de endereço no cadastro de rota (`GET /geocodificacao`); opcional, pode ser desligado (`GEOCODIFICACAO_PROVEDOR=`) ou trocado por instância própria;
  - Twilio, só para a ligação telefônica real, que é opcional.

## Como rodar

### Já em produção: AWS (persistente, com banco e HTTPS)

Além da Vercel (abaixo), o backend também está no ar numa infra persistente na conta AWS **dev** da Rumo (`140147589257`, `us-east-1`), criada com OpenTofu em [`infra/`](infra/):

- **URL pública (HTTPS):** [`https://d3fy4m7zwukr3x.cloudfront.net`](https://d3fy4m7zwukr3x.cloudfront.net) — doc interativa em [`/docs`](https://d3fy4m7zwukr3x.cloudfront.net/docs). `GET /health` confere o banco de verdade.
- **O que está no ar:** `api` e `voice-agent` como processos de longa duração no **ECS Fargate** (não serverless — resolve a limitação da Vercel abaixo), Postgres gerenciado no **RDS**, segredos no **Secrets Manager**, rede privada na VPC compartilhada da conta.
- **Deploy automático pela CI:** a cada push em `main` que passa lint+testes, o job `deploy` do [`ci.yml`](.github/workflows/ci.yml) builda a imagem, publica no ECR, roda a migração numa task separada e atualiza os dois serviços (`aws ecs update-service --force-new-deployment`) — detalhe em [`infra/README.md`](infra/README.md#deploy-automático-ci).
- **HTTPS sem domínio próprio:** o ALB interno só fala HTTP; a URL pública passa pelo **CloudFront** na frente dele, que já vem com certificado TLS válido no domínio compartilhado `*.cloudfront.net` — sem precisar registrar/validar um domínio. Detalhe técnico em [`infra/README.md`](infra/README.md) e [`infra/envs/dev/cloudfront.tf`](infra/envs/dev/cloudfront.tf).
- **Ainda não é o ambiente de produção definitivo:** é a conta AWS **dev** da Rumo, RDS sem Multi-AZ, sem domínio próprio (só o da CloudFront) e o segredo do Twilio ainda está como placeholder (`twilio_configurado: false` no `/health`) — nada disso derruba a api, só limita a ligação telefônica real.

### Já em produção (temporário, para o Hack Brasil)

A cada push em `main`, o CI do GitHub Actions (lint + testes) roda primeiro e, passando, a **Vercel** publica a API em [rodar-backend-five.vercel.app](https://rodar-backend-five.vercel.app) (doc interativa em [/docs](https://rodar-backend-five.vercel.app/docs)). Esse deploy existe **só para a submissão do Hack Brasil** e é **temporário por desenho**, não um ambiente de produção:

- **Falta o banco gerenciado.** O painel da Vercel não tem `DATABASE_URL` configurada, então a API cai no padrão do Docker Compose (`db:5432`, que não existe na Vercel). `/docs`, `/health` e `/livekit/config` respondem; qualquer rota que toque o banco — incluindo `/auth/sso`, ou seja, nenhum login funciona — responde 500. `GET /health` mostra `banco_ok` para isso ficar visível em vez de escondido.
- **Isso é intencional pelo custo, não só um esquecimento.** Hoje só a API HTTP está instanciada na Vercel (plano gratuito). Colocar todas as peças no ar ao mesmo tempo — um Postgres gerenciado, o worker de voz (`voice-agent`, processo à parte, sempre ligado) e um WebSocket/SSE persistente — exigiria outro(s) serviço(s) pagos ou com limites de uso só para a demo rodar fora do horário da avaliação; o time preferiu manter isso no Docker Compose local/túnel até decidir hospedar aquilo que não seja a demo em si.
- **Mesmo com o banco ligado, a Vercel é o host errado para este backend.** É serverless: as tarefas de fundo que o fluxo "só chama a central quando precisa" usa (`infra/container.py:37`, `Container.em_segundo_plano` → `asyncio.create_task`, usadas por escalonamento, estadia e ligações) morrem quando a resposta HTTP termina. O WebSocket não roda lá, e o SSE (`/cco/stream`) tem limite de duração da função. Não existe `vercel.json` no repositório — a configuração do projeto vive só no painel da Vercel, sem rastro no código versionado.
- **Caminho mais seguro para uma demo que depende desses fluxos:** uma VM ou um container de longa duração (Fly.io, Render ou Railway) com Postgres gerenciado, mantendo `voice-agent` como processo separado — o mesmo desenho do `docker-compose.yml`, só que hospedado.

Até isso mudar, rode localmente para ver o fluxo completo (inclusive voz e estadia) funcionando de ponta a ponta.

Para rodar localmente (clone limpo, só Docker):

```bash
git clone https://github.com/rodarglobal/rodar-backend.git && cd rodar-backend
```

```bash
cp .env.example .env   # preencha LIVEKIT_URL, LIVEKIT_API_KEY/SECRET, AUTH_SEGREDO e LLM_API_KEY
```

```bash
make up                # Postgres + api + worker de voz + túnel cloudflared
```

```bash
make test              # roda os testes no container (banco avisai_test)
```

```bash
docker compose run --rm test ruff check .   # lint (o mesmo do CI)
```

- A api fica em `http://localhost:8000`, com a doc interativa em `/docs`. `curl localhost:8000/health` mostra a URL pública do túnel (`public_url`).
- O worker usa a rede interna do Compose para chamar `/v1/voice/context`, `/v1/voice/turn` e `/v1/voice/tool` (contexto, transcrição e ferramentas da conversa Gemini Live); `/v1/chat/completions` é o mesmo gateway de texto, só que para os clientes HTTP (scripts de validação/avaliação e o diálogo simulado). O túnel serve aos clientes fora da rede. A URL do quick tunnel é descoberta sozinha, e pode ser fixada em `PUBLIC_URL`.
- **Se o túnel reiniciar, a URL muda.** Abra uma nova sessão depois disso.
- Para a demo, use `ESTADIA_ACELERACAO=600` (1 s real conta 10 min de estadia) e `CCO_INTERVALO_S=20`.

### Roteiro da demo
0. Com `AUTH_OBRIGATORIA=true` (o padrão), faça login como central antes de qualquer `curl` de escrita — sem isso, o passo 1 abaixo devolve 401:
   ```bash
   TOKEN=$(curl -s -X POST localhost:8000/auth/sso -H 'Content-Type: application/json' \
     -d '{"email":"cco@avisai.test"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
   ```
1. `curl -X POST localhost:8000/rotas/1/reset -H "Authorization: Bearer $TOKEN"`: deixa a rota pronta.
2. Abra `{PUBLIC_URL}/teste` (cliente mínimo do motorista) e clique em **Iniciar conversa**. O agente saúda em PT-BR, e dá para interrompê-lo falando por cima (barge-in).
3. `make sim ARGS="--desde 25"`: o caminhão anda.
   - Na aproximação (ETA ≤ 15 min), o agente avisa por voz.
   - Na chegada (≤ 300 m), surge a Task pendente e o contador de estadia começa a andar.
4. Ninguém confirma a Task. Saem 3 notificações ao CCO (push, painel, ligação), e o agente diz "Tô ligando pro recebimento".
5. Abra `{PUBLIC_URL}/recebedor`, clique em **Atender** e responda algo como "A doca 4 libera em 40 minutos". A resposta vai para a Task e o agente do motorista repassa por voz.
6. Diga ao agente "descarreguei": a estadia é encerrada com o valor final.

Para refazer: `POST /rotas/1/reset` com o mesmo header `Authorization: Bearer $TOKEN` do passo 0, ou o botão "Reset da demo" na `/teste` (que já usa o login feito pelo navegador).

---

## Segurança

| O quê | Como | Onde |
|---|---|---|
| Token de acesso | `POST /auth/sso` devolve um JWT HS256 com `sub`, `email`, `role`, `driverId`, `iat` e `exp` (`AUTH_TOKEN_VALIDADE_H`, padrão 12 h), assinado com `AUTH_SEGREDO` | `infra/auth.py` |
| Login obrigatório | `AUTH_OBRIGATORIA=true` é o padrão: toda escrita exige `Authorization: Bearer <token>` (401 sem token). A api não sobe se `AUTH_SEGREDO` tiver menos de 32 caracteres. `false` só em desenvolvimento local | `infra/settings.py`, `main.py` (`checar_segredo_auth`) |
| Papel da central | publicar e atribuir rota, cadastrar motorista, assumir Task, responder chamado, mandar mensagem ou pedido ao motorista, anexar arquivo, atender chamada e ligar pelo CCO exigem papel `cco` (403 com papel errado) | `api/deps.py` (`exigir_cco`) |
| Dono da rota | GPS, chegada, descarga, ligação ao recebedor, reset, arquivos, falas offline, sessão de voz, `/agent/*`, `/call/receiver`, outbox (`POST /events`) e token LiveKit: o motorista só age na rota atribuída a ele (claim `driverId`, 403 na rota de outro); a central age em qualquer rota | `api/deps.py` (`exigir_acesso_rota`, `exigir_acesso_sessao`) |
| CORS | só as origens de `CORS_ORIGENS` (painel local e a demo publicada) | `main.py` |
| Custo de telefonia | no máximo `LIGACOES_MANUAIS_MAX` ligações manuais por rota a cada `LIGACOES_MANUAIS_JANELA_S` (429 depois disso); as ligações automáticas do agente não entram no limite | `infra/auth.py`, `api/deps.py` |

Testes em `tests/api/test_auth.py`. `GET /health` mostra `auth_obrigatoria`. As páginas de teste em `static/` e os clientes de exemplo em `clients/` não mandam token: use-os com `AUTH_OBRIGATORIA=false`. `scripts/simular_rota.py` e `scripts/validar_fluxos.py` entram como central.

### O que falta para produção

O que está acima basta para a demo, não para operar com dados reais. Falta, em ordem de prioridade:

| O quê | Onde | Como | Por quê |
|---|---|---|---|
| Deploy persistente com banco gerenciado | ~~Vercel (serverless, sem `DATABASE_URL`)~~ **resolvido** via AWS (ECS Fargate + RDS) — [detalhe acima](#já-em-produção-aws-persistente-com-banco-e-https) | promover a mesma infra pra uma conta de produção definitiva da Rumo (hoje é a conta **dev**), com RDS Multi-AZ | a conta/infra atual já é persistente e tem banco de verdade, mas ainda não é o ambiente de produção final |
| Login de verdade | `api/compat.py` (`/auth/sso`) e telas de login do app e do painel | central com o SSO da empresa (OIDC) ou senha com hash Argon2; motorista com código por SMS | hoje não há senha: quem conhece um e-mail do seed entra com aquele papel |
| 2FA para a central | `infra/auth.py` e uma tabela de fatores; tela de código no painel | TOTP com app autenticador, obrigatório para o papel `cco`, com códigos de recuperação | a central publica rotas, dispara ligações pagas e vê dados de motoristas |
| Leituras protegidas | `GET /rotas`, `/cco/*`, `/eventos`, `/api/*`, SSE e WebSocket | mesmo token das escritas; o motorista vê só a própria rota | transcrições, GPS e telefones ainda podem ser lidos sem login |
| Sessão segura | `api/deps.py` (`?token=` no SSE e WebSocket) | token de 15 min com refresh rotativo e revogação; ticket de uso único no WebSocket; `expo-secure-store` no app e cookie HttpOnly no painel | token na URL vaza em logs; hoje ele vale 12 h e não dá para revogar |
| Domínio próprio e cofre de segredos completo | `infra/` (AWS): HTTPS já resolvido via CloudFront (`*.cloudfront.net`), segredos no Secrets Manager, mas o segredo do Twilio ainda é placeholder | domínio próprio emitindo certificado ACM, preencher o segredo do Twilio, CORS só para o domínio de produção final | HTTPS e cofre de segredos já existem; falta o domínio da empresa e fechar o último segredo pendente |
| Dados pessoais (LGPD) | transcrições, GPS e telefones no banco e em `ARQUIVOS_DIR` | aviso ao motorista, prazo de retenção, registro de quem acessou, backup cifrado | voz e localização de trabalhador são dados pessoais |
| Limites com várias instâncias | `infra/auth.py` (`LimiteChamadas`, em memória) | mover o limite de ligações para Redis | em memória, cada instância conta sozinha |
| Rotas de demonstração | `POST /rotas/{id}/reset` | remover em produção | apaga o histórico da viagem |
| Gateway do LLM sem segredo próprio | `api/llm.py` (`/v1/chat/completions`, `/v1/voice/*`) | exigir um segredo compartilhado de novo (ou mTLS) entre o worker LiveKit e a api, numa rede que hoje é só interna ao Compose | quem souber um `sessao_id`/`x-avisai-sessao` ativo chama essas rotas sem token; a proteção anterior (`LLM_SHARED_SECRET`) foi removida por ficar sempre vazia e nunca validar nada |

## Arquitetura

```
backend/app/
  dominio/       regras puras: estadia, geocerca, escalonamento, prompts, contingência, documentos e enums
  servicos/      casos de uso: sessões, rotas, Tasks, chamadas, alertas, mensagens, chamados, conversa, ferramentas e EDI
  conectores/edi/ motor de EDI de largura fixa + layouts OCOREN 5.0/3.1 como dado (sem adapter por versão)
  portas.py      contratos (typing.Protocol): LiveKitGateway, LLM, Relogio, Voz, Discador
  integracoes/   adaptadores reais: LiveKit, Twilio, OpenAI e túnel
  api/           routers FastAPI + schemas Pydantic; cada módulo agrupa uma superfície HTTP/WS
  infra/         settings, banco (Postgres/SQLModel), modelos, eventos (pub/sub), container e limite de upload
backend/alembic/ migrações
backend/tests/   cenários dado/quando/então: dominio, servicos, integracoes, api
backend/docs/    perfis de demonstração e contrato de arquivos
backend/static/  páginas mínimas de motorista e recebedor para testar LiveKit RTC
clients/         contratos TypeScript e clientes de referência React Native/web
scripts/simular_rota.py   GPS simulado
```

- Os serviços recebem as portas pelo container (`infra/container.py`); os testes trocam por fakes.
- Ligação ao recebedor: `DiscadorRTC` (plano B) ou `DiscadorSIP` (plano A), escolhidos por config.
- Ferramentas do LLM: um registro `{nome: Ferramenta}` em `servicos/ferramentas.py`. Uma ferramenta nova é uma entrada nova.

---

## Compatibilidade com `docs/arquitetura-avisai.md` (repo de ideias)
Os fronts podem seguir o contrato do doc sem mudança. A api também responde na **porta 8787**, e as rotas do `agent-server` existem aqui:

| Rota do doc | O que faz aqui |
|---|---|
| `POST /agent/start` `{tripId}` | inicia o agente e devolve `{sessionId, agentDispatchId, livekitURL, room, identity, token}` |
| `POST /agent/stop` `{sessionId \| agentId}` | encerra o agente na sala LiveKit |
| `GET /token?room&identity` | token LiveKit para uma identidade autorizada |
| `POST /call/receiver` `{tripId, reason}` | liga para o recebedor (plano B ou plano A) |
| `POST /events` | **outbox idempotente**: `DomainEvent` com `idempotencyKey` (200 na primeira vez, 409 se repetido). Aplica `ArrivalRegistered`, `PickupConfirmed`, `OccurrenceCreated`, `UnloadConfirmed` e `ReportSubmitted` |
| `POST /rotas/{id}/falas-offline` | **fala gravada sem sinal** (multipart: `audio` WAV/M4A, `idempotencyKey`, `faladoEm`, `duracaoMs`). 201 na primeira vez, 409 se repetida. Em segundo plano: transcreve (`STT_MODEL`, mesma chave do LLM), passa ao agente do motorista com o horário em que foi falada e manda a resposta como `aviso_motorista`. Uma fala por vez por rota, na ordem de chegada. O áudio é apagado do disco depois de transcrito com sucesso (só a transcrição fica registrada); se a transcrição falhar, o arquivo é mantido para diagnóstico. Evento `fala_offline` com `status` (`recebida`, `transcrita`, `processada`, `sem_transcricao`, `erro_transcricao`, `vazia`) |
| `GET /events?tripId&since` | linha do tempo no formato `DomainEvent {id, idempotencyKey, tripId, type, occurredAt, receivedAt, source, payload}`; serve para o polling de 2 s |
| `GET /api/route?tripId` | rota do dia: polyline, origem, destino, recebedor, placa e NF |
| `GET /api/receivers` | ranking de recebedores: espera média, ligações atendidas, estadia devida, avisados antes da chegada |
| `GET /api/metrics` | KPIs da seção 6.2: horas paradas, estadia devida, tempo até ação do CCO, tasks escaladas, % avisados, % atendidas, % reportes completos na 1ª, latência do LLM |
| `GET /api/documents` | NF-e e CT-e da rota; a consulta por voz também lista os nomes disponíveis |
| `GET /cco/chamados?abertos=true` | chamados do motorista aguardando resposta do CCO |
| `POST /cco/chamados/{id}/responder` | resposta do CCO; o agente fala a resposta ao motorista |
| `POST /auth/sso` | login simulado (sem senha) que devolve um JWT assinado com o papel (`cco` ou `driver`) |

Os `type` do contrato saem dos nossos eventos: `retirada`→`PickupConfirmed`, `relatorio`→`ReportSubmitted`, `campo_faltante`→`ReportFieldMissing`, `ocorrencia`→`OccurrenceCreated`, `aproximacao`→`ApproachDetected`, `aviso_recebedor`→`ReceiverNotified`, `resposta_recebedor`/`ligacao_nao_atendida`→`ReceiverCallResult` (`payload.answered`), `chegada`→`ArrivalRegistered`, `task_criada`→`TaskCreated`, `notificacao_cco`/`escalada_recebedor`→`TaskEscalated`, `task_confirmada`→`TaskAcknowledged`, `descarga`→`UnloadConfirmed`.

Extensões fora da lista do doc: `AgentSessionStarted`, `PickupGeofenceEntered`, `ReceiverCallStarted`, `ReceiverCallFailed`, `ReceiverCallFallback`, `ReceiverRefusedToday`, `CentralRequestSent`, `CentralRequestAnswered`, `GpsDivergence`, `VoiceTranscript`.

O contrato HTTP e os eventos de negócio foram mantidos; transporte e credenciais de voz agora usam LiveKit. Além do polling, há **SSE** (`/cco/stream`) e **WebSocket** (`/ws`), com entrega instantânea.

### Publicação de rota e vínculo com o motorista
1. **CCO publica a rota:** `POST /rotas` com `origem`, `destino`, `recebedor {empresa, nome, telefone_e164}`, `carga_t`, `capacidade_t` (capacidade total do veículo, que é a base da estadia pela Lei 11.442; vazio usa `carga_t`), `placa`, `nota_fiscal`, `janela_descarga` e, opcionalmente, `motorista_id`. O trajeto é simulado em linha reta, e a rota fica `publicada`.
2. **Atribui ao motorista:** `POST /rotas/{id}/atribuir {motorista_id}`. A rota passa a `planejada`, sai o evento `rota_atribuida` (**`RouteAssigned`** no `/events`, `source: cco`) e, se o motorista estiver com o agente aberto, ele ouve "Rota nova: …".
3. **App do motorista:**
   - `POST /auth/sso {email}` devolve `driverId` e o `tripId` da rota atual;
   - `GET /api/route?driverId=` (ou `GET /motoristas/{id}/rota-atual`) traz a rota;
   - o WebSocket `/ws?motorista_id=` recebe as atribuições novas na hora (no hook RN: `motoristaId` e `onRotaAtribuida`).
4. **Motoristas:** `GET /motoristas` e `POST /motoristas {nome, telefone_e164, email}`. No seed, o Carlos é `carlos@rotasul.test`.
5. **Endereço e coordenada:** cada ponto de `POST /rotas` exige `lat`/`lng` válidos e aceita `endereco` e `geo {fonte: geocodificacao|manual, provedor, id, endereco}`. O painel busca o endereço em `GET /geocodificacao`, o CCO escolhe o resultado e a rota guarda o vínculo em `origem_geo`/`destino_geo`. A porta `Geocodificador` (`app/portas.py`) usa o Nominatim (OpenStreetMap) por padrão: **o endereço digitado sai para esse serviço**, com limite de 1 req/s e cache de 24 h; para produção, aponte `GEOCODIFICACAO_URL` para instância própria ou desligue com `GEOCODIFICACAO_PROVEDOR=`. Os testes usam `FakeGeocodificador` com lugares fictícios.
6. **Cancelamento:** `POST /rotas/{id}/cancelar {motivo}` vale de `publicada` a `aproximando`. Depois disso a rota não volta como rota atual, chegada/descarga/atribuição respondem 409 e o GPS recebido é ignorado. Eventos, arquivos e histórico ficam.

### Fluxos de operação cobertos (doc, seções 5.5 e 6.3)
1. **Retirada na origem:** a geocerca da origem faz o agente perguntar "Confirma a retirada da carga?". A confirmação por voz (`confirmar_retirada`) valida a prova, e em seguida vem o **relatório inicial** (caminhão e carga).
1b. **Atraso na estrada:** uma ocorrência de `atraso` antes da chegada faz o agente ligar para o recebedor com o novo horário (`ReceiverNotified`, `motivo: atraso`).
2. **Aproximação:** o CCO é avisado e o agente **liga para o recebedor** (`ReceiverNotified`). Os desfechos:
   - confirma a doca: o motorista ouve;
   - **não recebe hoje**: aplica a regra da transportadora (`RegraEscalonamento.acao_nao_recebe`) e avisa o CCO e o motorista;
   - não atende: a tentativa fica como prova.
3. **Chegada:** o GPS detecta e o agente pergunta **"Confirma a chegada?"**. A prova (`EventoGeo`) só fica validada com GPS do celular + rastreador + voz. Abre a Task (`TaskCreated`) e a estadia, e o **check-in por voz** com campos obrigatórios (estado da carga, tempo de viagem, problemas). O agente pergunta **só o que faltou** (`ReportFieldMissing`).
4. **Chegada e chamado direto ao CCO:** além da Task operacional, a chegada abre um chamado persistido `chegada`. O painel lista o chamado e pode responder; o agente entrega a resposta ao motorista. Sem resposta, fala um lembrete a cada 30 s, até 5 tentativas, e então registra `timeout`.
5. **CCO:** a Task segue o escalonamento configurado; sem resposta, o agente liga para o recebedor.
6. **Pedido da central:** `POST /rotas/{id}/solicitacoes {pergunta}`. O agente pergunta ao motorista e a resposta volta estruturada (`GET /rotas/{id}/solicitacoes`).
7. **Ocorrência por voz:** ao ouvir um problema, o agente persiste a `Ocorrencia` e abre imediatamente um chamado `ocorrencia` ao CCO. Km e BR são opcionais: entram apenas quando o motorista os informar. O chamado fica no banco e no stream, com os mesmos lembretes de 30 s/5 tentativas.
8. **Ocorrência aprofundada:** depois do registro, o agente faz as perguntas do tipo, **uma por vez**. Em acidente: feridos, envolvimento do caminhão, se dá para seguir e local; em avaria: o que houve, se precisa de socorro e a carga; em fila: quantos caminhões e previsão. Acidente com ferido leva o agente a orientar ligar **192 (SAMU) ou 193 (Bombeiros)** e gera `ocorrencia_grave` (prioridade crítica) para o CCO. O quadro completo sai em `ocorrencia_detalhada` (`OccurrenceDetailed`). O gateway de texto também inclui uma contingência local para esse fluxo.
9. **Pergunta sobre a NF ou o CT-e por voz:** a ferramenta `consultar_documento` responde com o nome do documento e os campos disponíveis (número, peso, valor, destinatário, itens, frete, placa ou chave). Se o motorista pedir a lista, informa os títulos; sem campo, diz "não encontrei". A resposta sai só dos campos extraídos e nunca arredonda. O evento é `pergunta_documento`, que aparece como `DocumentQuestionAnswered` no `/events`. O gateway de texto também atende sem `LLM_API_KEY`. Anexos reais da rota ficam em `/rotas/{id}/arquivos`.
10. **Dupla prova de GPS:** `POST /rotas/{id}/posicao` com `fonte=rastreador` registra o GPS do caminhão. Na retirada e na chegada, se celular e rastreador estiverem a mais de 500 m, o evento fica `nao_validado` e sai `divergencia_gps` para o CCO. O simulador manda os dois GPS (`--divergir` força a divergência).

## Integração com os fronts

| Quem | Usa SDK LiveKit? | Como fala com o backend |
|---|---|---|
| App do motorista (React Native) | `@livekit/react-native` | token de sala via REST + **WebSocket `/ws?rota_id=`** |
| Painel do CCO (Vite) | LiveKit opcional para ouvir/falar | REST + **SSE `/cco/stream`** |
| Recebedor, modo RTC | Web SDK LiveKit (página `/recebedor`) | `GET /ligacoes/atual/recebedor` |
| Recebedor, modo SIP | telefone via LiveKit SIP | trunk de saída configurado no LiveKit |

**Clientes de referência** em `clients/`:
- `clients/tipos.ts`: o contrato em TypeScript (Sessao, TaskCCO, Estadia, Ligacao, EventoStream e as mensagens do stream).
- `clients/react-native/useAvisaiVoz.ts`: hook do motorista com `@livekit/react-native`. Expõe `iniciar()`, `encerrar()`, `alternarMudo()`, `enviarPosicao()` e o estado vivo (`status`, `estadia`, `task`, `ligacao`, `falas`, `eventos`). Cuida da sessão, áudio nativo e reconexão do `/ws`.
- `clients/web/avisaiStream.ts`: cliente SSE tipado, sem framework, com reconexão e as ações REST do CCO. `clients/web/useAvisaiCCO.ts` é um hook React por cima dele.

Os clientes recebem tokens LiveKit de curta duração gerados pelo backend. As chaves do servidor e do worker ficam somente no `.env`.

### App do motorista (React Native)
- Precisa de dev build ou `expo prebuild`, porque o SDK LiveKit usa módulos nativos e não roda no Expo Go. Registre `registerGlobals()` na inicialização do app, configure `AudioSession` e as permissões de microfone para iOS/Android.

```ts
import { Room, RoomEvent } from "livekit-client";

const s = await fetch(`${API}/sessions`, { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ rota_id: 1 }) }).then(r => r.json());
// s = { id, canal, identity, livekit_url, token, status }
const room = new Room();
await room.connect(s.livekit_url, s.token);
await room.localParticipant.setMicrophoneEnabled(true);
room.on(RoomEvent.ParticipantConnected, p => p.identity === `rodar-agente-${s.id}` && setPronto(true));
const ws = new WebSocket(`${API.replace("http", "ws")}/ws?rota_id=1`);
ws.onmessage = (m) => { const { canal, dado } = JSON.parse(m.data); /* snapshot | evento | task | fala | contador */ };
// encerrar: room.disconnect(); fetch(`${API}/sessions/${s.id}`, { method: "DELETE" })
```

O `POST /sessions` despacha o agente e devolve token para conectar à sala. Aguarde o participante `rodar-agente-{id}` para mostrar a conversa como pronta. Fala proativa e comandos do CCO chegam ao worker por mensagens LiveKit na sala.

### Painel do CCO (Vite)
```ts
const es = new EventSource(`${API}/cco/stream`);
es.addEventListener("snapshot", e => setEstado(JSON.parse(e.data)));
es.addEventListener("evento",   e => addEvento(JSON.parse(e.data)));      // EventoStream
es.addEventListener("task",     e => upsertTask(JSON.parse(e.data).task));
es.addEventListener("contador", e => setEstadias(JSON.parse(e.data).estadias));
// assumir: POST /tasks/{id}/confirmar {"confirmado_por": "Ana (CCO)"}
```
Tipos TypeScript: `npx openapi-typescript {API}/openapi.json -o src/api.ts`.

### Salas e identidades LiveKit
| Participante | Sala | Identidade |
|---|---|---|
| Motorista | `rodar-rota-{rota_id}` | `motorista-{rota_id}` |
| Agente do motorista | `rodar-rota-{rota_id}` | `rodar-agente-{sessao_id}` |
| CCO, monitor opcional | sala ativa da sessão | `cco-monitor-{sessao_id}` |
| Recebedor, página web | `rodar-recebedor-{ligacao_id}` | `recebedor-{ligacao_id}` |
| Recebedor, chamada telefônica | `rodar-recebedor-{ligacao_id}` | `sip-recebedor-{ligacao_id}` |

---

## Contrato de API

Base local: `http://localhost:8000`. O OpenAPI vivo está em `/docs` e `/openapi.json`. As tabelas abaixo resumem as rotas públicas; campos, códigos de erro e schemas devem ser conferidos no OpenAPI da instância em uso.

### Infraestrutura, identidade e voz

| Método | Caminho | Corpo | O que faz |
|---|---|---|---|
| GET | `/health` | — | `banco_ok` (conexão real com o Postgres), `sha` (commit publicado na imagem) e o estado da configuração LiveKit, túnel, Twilio e LLM; devolve **503** (não 200) quando `ok` é falso |
| GET | `/usuarios?role=driver\|cco`<br>`/api/users` | — | perfis persistidos de demonstração |
| POST | `/usuarios` | `{nome, email}` | cadastra um operador da central (perfil `cco`); 409 se o e-mail já existir |
| GET | `/livekit/config` | — | diz se o LiveKit está configurado e a `LIVEKIT_URL`; nunca expõe chave ou segredo |
| POST | `/livekit/token` | `{sala?}` | token de participante (60 min) assinado com `LIVEKIT_API_SECRET`; exige login quando a autenticação está ativa |
| POST | `/auth/sso` | `{email}` | login MOCK (sem senha); devolve perfil e JWT assinado, exigido nas escritas |
| GET | `/token?room=&identity=` | — | token LiveKit de curta duração para uma identidade ativa autorizada |
| POST | `/sessions` | `{rota_id}` | inicia o agente da viagem e devolve o token do motorista |
| GET / DELETE / POST | `/sessions`<br>`/sessions/{id}`<br>`/sessions/{id}/speak` | — / — / `{texto, prioridade?}` | lista, encerra ou pede uma fala manual para teste |
| POST | `/v1/chat/completions` | OpenAI compatível | gateway de texto do LLM usado pelo diálogo simulado (scripts de validação/avaliação) e pelos testes; não é o endpoint da conversa de voz nem de frontend |
| GET | `/v1/voice/context` | — | estado atual da operação (resumo da rota, Task, estadia); o worker LiveKit busca antes de iniciar a sessão com o Gemini Live |
| POST | `/v1/voice/turn` | `{role, text}` | persiste cada turno transcrito da conversa de voz e devolve o estado atualizado; chamado pelo worker a cada fala |
| POST | `/v1/voice/tool` | `{name, arguments, utterance}` | executa no backend a ferramenta chamada pelo modelo Gemini Live (mesma lógica de domínio do `/v1/chat/completions`) |

### Rotas, motoristas, arquivos e comunicação

| Método | Caminho | Corpo | O que faz |
|---|---|---|---|
| GET / POST | `/rotas` | — / `NovaRota` | lista ou publica rota; `motorista_id` é opcional por compatibilidade, embora o painel CCO exija um motorista cadastrado |
| GET | `/rotas/{id}` | — | detalhe, trajetória e posições |
| POST | `/rotas/{id}/atribuir` | `{motorista_id}` | atribui/reatribui e emite `rota_atribuida`; rota descarregada ou cancelada → 409 |
| POST | `/rotas/{id}/cancelar` | `{motivo, por?}` | encerra a viagem sem descarga (`cancelada`) e emite `rota_cancelada` (`TripCancelled`); só antes de `no_destino`, senão 409 |
| GET | `/geocodificacao?q=&limite=` | — | candidatos `{id, endereco, lat, lng, tipo}` para o endereço digitado (papel `cco`); 503 sem provedor, 502 quando o provedor falha |
| POST | `/rotas/{id}/posicao` | GPS do celular ou rastreador | atualiza posição, geocerca e status |
| POST | `/rotas/{id}/chegada`<br>`/descarga`<br>`/reset` | — / `{por?}` / — | registra chegada, encerra descarga ou reinicia a rota de demonstração |
| GET / POST | `/rotas/{id}/solicitacoes` | — / `{pergunta}` | pedidos do CCO e resposta capturada pelo agente |
| GET / POST | `/rotas/{id}/mensagens` | — / `{texto}` | thread CCO → motorista e tentativa de fala do agente |
| GET | `/rotas/{id}/chamados` | — | chamados de chegada/ocorrência ligados à rota |
| GET / POST | `/rotas/{id}/arquivos` | — / multipart `arquivo` | lista ou envia anexo real |
| GET | `/rotas/{id}/arquivos/{arquivo_id}/download` | — | baixa o conteúdo binário do anexo |
| GET / POST | `/motoristas` | — / cadastro de motorista | lista ou cadastra o vínculo operacional |
| GET | `/motoristas/{id}/rota-atual` | — | alternativa snake_case para a rota atual |

### EDI / OCOREN (papel `cco`)

Conector de largura fixa para o **OCOREN 5.0** (manual Intelipost, 250 colunas, padrão) e o **OCOREN 3.1**
(manual PROCEDA, 120 colunas, variante). Um motor só (`backend/app/conectores/edi/motor.py`) lê cada
registro como dado (`layouts/ocoren_50.py`, `layouts/ocoren_31.py`); o que muda por parceiro é o perfil
(`ParceiroEdi`: layout, De-Para, caixa remetente/destinatário), nunca o código. Detalhe completo, mapeamento
de campos e o que ainda falta (SFTP/fila, De-Para homologado) em [`docs/edi/ocoren-integracao.md`](docs/edi/ocoren-integracao.md).

| Método | Caminho | Corpo | O que faz |
|---|---|---|---|
| GET | `/rotas/{id}/ocoren?parceiro=` | — | gera e baixa o arquivo (`OCOREN_<cnpj>_<ddMMHHmm>.txt`, `cp1252`); 409 sem `nfe_chave`/CNPJ cadastrados na rota ou na empresa |
| GET / POST | `/edi/parceiros` | — / `ParceiroEdiIn` | lista ou cadastra um perfil de parceiro (layout, De-Para, campos extras) |
| PATCH | `/edi/parceiros/{id}` | `ParceiroEdiPatch` | atualiza o perfil (ex.: trocar o layout ou sobrepor o De-Para) |
| POST | `/edi/validar?layout=&codificacao=` | multipart `arquivo` | valida um arquivo OCOREN já recebido e devolve o erro por linha/campo; não grava nada |

### CCO, eventos e chamadas

| Método | Caminho | Corpo | O que faz |
|---|---|---|---|
| GET | `/cco/estado?rota_id=` | — | snapshot de rotas, Tasks, estadias, chamadas, ocorrências, chamados e eventos |
| GET / POST | `/cco/chamados`<br>`/cco/chamados/{id}/responder` | — / `{resposta, respondido_por?}` | lista e responde chamados persistidos; resposta é enviada ao agente |
| GET / POST | `/cco/chamadas-agente`<br>`/cco/rotas/{id}/ligar` | — / `{motivo?}` | acompanha ou inicia a cascata Twilio → LiveKit RTC para operador |
| GET | `/cco/stream?rota_id=` | — | SSE: `snapshot`, `evento`, `task`, `posicao`, `fala`, `contador`, `reset`, `chamado` e alertas |
| WS | `/ws?rota_id=` ou `?motorista_id=` | — | atualizações da rota e novas atribuições ao motorista |
| GET / POST | `/tasks`<br>`/tasks/{id}/confirmar` | — / `{confirmado_por}` | lista Tasks e registra que o CCO assumiu |
| GET | `/eventos?rota_id=&limite=` | — | timeline operacional recente |
| GET | `/ligacoes`, `/ligacoes/{id}`<br>`/ligacoes/atual/recebedor` | — | chamadas ao recebedor, transcrição e chamada atual |
| POST | `/rotas/{id}/ligar-recebedor` | `{motivo?}` | inicia ligação ao recebedor |
| GET / POST | `/operador/chamadas/atual`<br>`/operador/chamadas/{id}/atender` | — / — | a chamada RTC pendente para o operador e ação de atender |
| GET | `/teste`, `/recebedor` | — | páginas mínimas para testar motorista e recebedor no plano RTC |

### Compatibilidade para clientes existentes

| Método | Caminho | O que faz |
|---|---|---|
| POST | `/agent/start`, `/agent/stop` | aliases para iniciar/parar o agente |
| POST | `/call/receiver` | alias de ligação por `tripId` |
| GET / POST | `/events` | timeline normalizada e outbox idempotente `DomainEvent` |
| GET | `/api/route`, `/api/receivers`, `/api/metrics`, `/api/documents` | contratos camelCase consumidos pelos frontends |

### Mensagens do stream (SSE `event:` / WS `canal`)
| canal | dado |
|---|---|
| `snapshot` | o mesmo de `/cco/estado` |
| `evento` | `EventoStream {id, tipo, rota_id, timestamp, mensagem, dados}` |
| `task` | `{task: TaskCCO}` (status `pendente`, `confirmada`, `escalada_recebedor` ou `concluida`; `tentativas`; `canal_atual`; `prioridade`; `resposta_recebedor`) |
| `posicao` | `{rota_id, lat, lng, distancia_m, eta_min, status}` |
| `fala` | `{rota_id, papel, texto}`: o que o agente respondeu |
| `contador` | `{estadias: [{rota_id, tempo_parado, franquia_restante, valor_fmt, horas_paradas, ...}]}` a cada 1 s |
| `reset` | `{rota_id}` |
| `chamado` | `{chamado: ChamadoCCO}`; abertura, lembrete, resposta ou timeout |
| `acao_cliente` | `{rota_id, acao, tela?, documento?}`: comando do app do motorista pedido por voz (ver abaixo) |
| `aviso_motorista` | `{id, rota_id, texto, prioridade, pede_resposta}`: o agente quis falar com o motorista sem conversa aberta; o app fala em voz local e, se for pergunta, abre a conversa |

### Comandos do app por voz (`acao_cliente`)
O motorista pede ("abre o mapa", "mostra a nota fiscal", "volta", "tchau, AvisAI", "sair da conta") e o agente chama a ferramenta `comandar_app`. O backend publica só a intenção no `/ws`; o app nunca age a partir da transcrição. O gateway de texto também reconhece esses pedidos sem `LLM_API_KEY` (`dominio/comandos_app.py`).

| `acao` | Campos | O app faz |
|---|---|---|
| `open_screen` | `tela`: `inicio`, `mapa`, `documentos`, `mensagens` ou `fila` | abre a tela |
| `open_document` | `documento`: `NF-e`, `CT-e`, `MDF-e` ou o nome do anexo | abre o documento (ou a lista, se não achar) |
| `go_back` | — | volta uma tela |
| `end_voice` | — | espera o agente se despedir e encerra a conversa |
| `logout` | — | sai da conta; o agente só manda depois de o motorista confirmar |
| `open_navigation` | — | abre a rota até o destino no app de mapas |
| `start_gps` | — | liga o GPS do aparelho |

Documentos e mensagens pedem leitura: com a rota `em_transito` ou `aproximando`, o agente diz que abre quando o motorista parar, e o app espera.

Também na voz do motorista: `enviar_mensagem_cco` abre um chamado `mensagem` com o recado livre (problemas continuam como ocorrência), e "repete" / "o que eu perdi" repete os últimos avisos (`ÚLTIMOS AVISOS` no estado do LLM e na contingência).

Valores de `EventoStream.tipo` (enum `TipoEvento`):
- sessão: `sessao_iniciada`;
- trajeto e chegada: `aproximacao`, `chegada`, `chegada_confirmada_voz`;
- CCO: `notificacao_cco`, `escalada_recebedor`, `task_confirmada`;
- ligação: `ligacao_recebedor`, `ligacao_falhou`, `fallback_plano_b`, `ligacao_nao_atendida`, `resposta_recebedor`;
- registros: `ocorrencia`, `descarga`;
- falas: `fala_motorista`, `fala_recebedor`, `fala_agente`.

---

## Variáveis do `.env`

Obrigatórias para voz: `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`. O worker usa o modelo de fala em tempo real configurado em `LIVEKIT_MODEL` e a voz em `LIVEKIT_VOICE`; o áudio não passa pelo pipeline separado de STT/TTS. `LLM_API_KEY` é usado pelos endpoints de conversa e pelos scripts de avaliação, não pelo diálogo de voz LiveKit.

| Variável | Padrão | Para quê |
|---|---|---|
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | — | conexão com LiveKit Cloud ou servidor compatível |
| `LIVEKIT_AGENT_NAME` | `rodar-voice-agent` | nome usado no dispatch explícito do agente |
| `LIVEKIT_LLM_URL` | `http://api:8000/v1` no Compose | gateway interno do backend para estado, transcrições e chamadas de ferramentas |
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | `gpt-4o-mini` | upstream OpenAI compatível para `/v1/chat/completions` e avaliação de diálogos |
| `PUBLIC_URL` | descoberta automática | URL do túnel |
| `RECEBEDOR_MODO` | `rtc` | `rtc` (plano B) ou `sip` (plano A) |
| `GEOCODIFICACAO_PROVEDOR`, `GEOCODIFICACAO_URL` | `nominatim`, instância pública | busca de endereço do cadastro de rota; vazio desliga (503) |
| `LIVEKIT_SIP_TRUNK_ID`, `LIVEKIT_SIP_FROM_NUMBER`, `RECEBEDOR_TELEFONE_E164` | — | trunk e números do plano SIP |
| `LIVEKIT_MODEL` | `google/gemini-3.8-live` | modelo realtime speech-to-speech do LiveKit Inference |
| `LIVEKIT_VOICE` | `Charon` | voz nativa do Gemini Live |
| `CCO_INTERVALO_S`, `CCO_MAX_TENTATIVAS` | `20`, `3` | ritmo do escalonamento (a regra da empresa no seed define 3) |
| `ESTADIA_ACELERACAO` | `1` | relógio da estadia; use `600` na demo |
| `LIGAR_RECEBEDOR_NA_APROXIMACAO` | `true` | liga para o recebedor já na aproximação (fluxo do repo de ideias) |
| `LIGACAO_TIMEOUT_S` | `180` | sem resposta até aqui, a ligação é registrada como não atendida |

### Voz realtime
O padrão usa `google/gemini-3.8-live` com a voz `Charon`. O Gemini processa áudio e gera fala nativamente; o worker mantém os schemas de ferramentas do backend e registra transcrições e eventos no gateway RODAR. Altere `LIVEKIT_MODEL` ou `LIVEKIT_VOICE` conforme a disponibilidade da conta LiveKit Inference. Recrie `voice-agent` e inicie uma sessão nova após mudar esses valores. Como o modelo gera fala nativamente, ele pode parafrasear saudações e avisos proativos mesmo quando recebe instrução para repeti-los literalmente.

### Avaliar a conversa do agente
`make avaliar` roda conversas difíceis (início com respostas soltas, ruído e conversa ao lado, ocorrência com desvio, resposta curta à central, pedidos vagos) contra a API e o LLM, sem transporte de áudio, e mostra turno a turno o que o gateway respondeu e registrou (`scripts/avaliar_conversas.py`). Reinicia a rota usada (padrão: rota 1; `ARGS="--rota 2 --cenario ruido"`).

O gateway de texto e `make avaliar` usam a contingência local quando `LLM_API_KEY` está vazia ou o upstream falha. A conversa por voz usa Gemini Live no LiveKit Inference; ela não depende dessa chave.

Travas contra o LLM se perder (valem para qualquer modelo):
- relatório inicial e check-in só gravam campos que saíram das últimas falas do motorista (`dominio/fundamentacao.py`); o resto volta como pergunta;
- ocorrência chamada de `outro` é reclassificada pelas palavras ("furou o pneu" → avaria), e o que a descrição já respondeu não é perguntado de novo;
- detalhes que chegam depois de a ocorrência fechar vão para a mais recente, e campos que a fala respondeu e o LLM esqueceu são somados.

### LLM sem custo (opcional)
Qualquer API compatível com OpenAI e com suporte a ferramentas serve. Duas opções com plano gratuito:
- **Groq** (muito rápido, bom para voz): `LLM_BASE_URL=https://api.groq.com/openai/v1`, `LLM_MODEL=llama-3.3-70b-versatile`, `LLM_API_KEY=` gerada em console.groq.com.
- **Gemini**: `LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`, `LLM_MODEL=gemini-2.5-flash`, `LLM_API_KEY=` gerada no aistudio.google.com.

Depois de editar o `.env`, rode `docker compose up -d --force-recreate api`.

**Sem `LLM_API_KEY`, os endpoints de texto e a avaliação funcionam pela contingência** (`dominio/contingencia.py`), que entende:
- **motorista:** início da rota por voz ("quero iniciar a viagem"), chegada ("cheguei", "tô na portaria"), ocorrências (fila, doca ocupada, documento, avaria, recusa, atraso, acidente), descarga ("descarreguei") e perguntas sobre documentos, tempo parado, estadia, doca e CCO, respondidas com o estado real da rota;
- **recebedor:** extrai a doca e a previsão ("a doca 4 libera em 40 minutos", "às 15h", "só amanhã").

### Ativar ligação telefônica por LiveKit SIP
1. Configure um outbound SIP trunk no LiveKit com seu provedor (por exemplo, Twilio Elastic SIP Trunking) e associe o número de origem.
2. No `.env`, preencha `LIVEKIT_SIP_TRUNK_ID`, `LIVEKIT_SIP_FROM_NUMBER`, `RECEBEDOR_TELEFONE_E164` e defina `RECEBEDOR_MODO=sip`.
3. Confirme que o provedor aceita chamadas do serviço SIP LiveKit e que o país de destino está habilitado na conta.
4. Suba novamente `voice-agent` e `api`. O backend cria um participante SIP de saída para a sala do agente. Se a chamada SIP falhar na criação, registra `fallback_plano_b` e deixa o recebedor entrar por RTC no navegador.

Chamadas manuais para operador mantêm a cascata Twilio PSTN → sala LiveKit RTC. O fallback aguarda atendimento e escala ao supervisor quando o operador não entra.

---

## Simulado / pré-existente (E5/E8)
- **Rastreador do caminhão simulado:** o simulador manda um segundo GPS (`fonte=rastreador`) com ruído de cerca de 10 m, que serve de dupla prova. Integração real com Sascar, Omnilink etc. fica fora.
- **Documentos, SSO e métricas:** `/api/documents` devolve NF-e e CT-e fictícios; `/auth/sso` não pede senha (o token é real, o login é simulado); a latência em `/api/metrics` mede só o nosso LLM até o primeiro trecho (não inclui ASR, TTS e rede).
- **GPS simulado:** `scripts/simular_rota.py` move o caminhão por um trajeto reto de Jundiaí a Campinas, chamando `POST /rotas/{id}/posicao`. Em produção, a posição viria do GPS do celular do motorista pelo mesmo endpoint.
- **Ligação ao recebedor:** o padrão `RECEBEDOR_MODO=rtc` usa uma página web (`/recebedor`) ligada à sala LiveKit; `sip` usa o trunk de saída configurado no LiveKit.
- **Seed fictício:** a transportadora, o motorista, a placa, a NF, o recebedor e os telefones são inventados (`backend/app/seed.py`).
- **EDI OCOREN:** o backend **gera OCOREN 3.1 e 5.0** a partir dos layouts dos manuais PROCEDA 3.1 e Intelipost/OCOREN 5.0 — não está integrado ao TOTVS, à Intelipost nem a nenhum parceiro real. `hfoletto/edi-proceda` (MIT) foi usado só como referência de posição de campo ao transcrever o layout 3.1, não como dependência. Até 30/11 só existe **download manual** pelo CCO (`GET /rotas/{id}/ocoren`): sem SFTP nem fila/outbox. CNPJs e chaves de NF-e do seed são **fictícios** (dígito verificador válido, mas o número não existe). O De-Para evento→código é o padrão documentado pela Intelipost; não foi homologado com nenhum parceiro real. Detalhe em [`docs/edi/ocoren-integracao.md`](docs/edi/ocoren-integracao.md).
- **Estadia acelerada:** com `ESTADIA_ACELERACAO=600`, 1 s real conta 10 min, para mostrar a franquia de 5 h e o valor em minutos de demo. Sem a variável, o relógio é real. Os intervalos com o CCO também são curtos (20 s).
- **CCO:** chamados de chegada e ocorrência são persistidos no banco local, aparecem no painel e podem ser respondidos por botão. O canal de voz do agente entrega a resposta ao motorista. As três tentativas sobem de canal de verdade: 1ª dispara uma notificação do navegador no painel (`Notification`, exige aba aberta e permissão concedida), 2ª sobe a prioridade da Task e destaca o alerta no painel, 3ª liga mesmo para a central (`chamadas_agente.ligar`, cascata Twilio PSTN → sala LiveKit RTC — nunca WhatsApp nem supervisor). Não há serviço de push/SMS externo: a "notificação" do 1º passo é só a do navegador.
- **Serviços externos:** LiveKit Cloud (RTC, Agents, Inference e SIP conforme plano), endpoint de LLM compatível com OpenAI (chat e, só para falas offline, reconhecimento de fala via Audio Transcriptions), Nominatim/OpenStreetMap para a busca de endereço no cadastro de rota, Twilio opcional para a primeira tentativa de ligação ao operador e cloudflared para clientes remotos.
- **Modo demo do token:** `POST /livekit/token` abre uma sala LiveKit sem rota nem sessão no backend, só para o teste de voz ao vivo da demo do app (botão "Entrar com SSO" no painel/site). O worker detecta a ausência de sessão e troca para `voice_agent.demo_ao_vivo` (`dominio/prompts.demo_ao_vivo`): prompt fixo, sem ferramentas, sem acesso ao sistema e sem gravar nada no banco. Esse token não verifica dono de rota, então o backend rejeita (400) qualquer `sala` com os prefixos reservados às sessões reais (`rodar-rota-`, `rodar-recebedor-`, `rodar-operador-`); só `GET /token`, restrito ao dono da rota ou à central, abre essas salas (`app/servicos/livekit.py`, `app/servicos/sessoes.py`).
- **Contingência:** sem `LLM_API_KEY`, ou com a OpenAI fora do ar, o nosso LLM responde por palavras-chave (cheguei, fila, descarreguei, doca...) para a demo não travar.
- **LGPD:** não guardamos áudio além do necessário para transcrever. As falas offline (`backend/app/servicos/falas_offline.py`) ficam em disco só até a transcrição ter sucesso, quando são apagadas e só a transcrição permanece no evento; o arquivo só persiste se a transcrição falhar, para permitir diagnóstico. Não há gravação na nuvem nem dado de saúde.
