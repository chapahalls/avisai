# AvisAI · backend

Copiloto de voz para transportadoras, focado no **caminhão parado**:
1. Na aproximação, o agente avisa o motorista e o CCO.
2. Na chegada, cria a Task do CCO e conta a estadia (Lei 11.442, franquia de 5 h, R$ 2,50 por t/h).
3. Insiste com o CCO e, sem resposta, **liga para o recebedor**.
4. Registra a resposta do recebedor como prova e a repassa por voz ao motorista.

Time Chapahalls (3 pessoas: Jeferson, Henry e Lucas) · hackathon UNMUTE by Agora · backend e infra: Lucas.

**Versão entregue: tag [`v1.3-entrega`](https://github.com/chapahalls/avisai/releases/tag/v1.3-entrega)** (substitui as anteriores). Se houver nova correção, ela sai numa tag nova, e a tag `v*-entrega` mais recente é a versão entregue. Licença: [MIT](LICENSE).

**Repositórios do projeto** (todos públicos):
| Repo | O quê | Responsável |
|---|---|---|
| [chapahalls/avisai](https://github.com/chapahalls/avisai) | este backend: API, agente de voz (Agora ConvoAI), regras, infra Docker | Lucas |
| [chapahalls/avisai-mobile](https://github.com/chapahalls/avisai-mobile) | app do motorista (React Native / Expo): voz pela Agora, mapa, sincronização com o backend | Jeferson |
| [chapahalls/avisai-web](https://github.com/chapahalls/avisai-web) | painel do CCO (React + Vite): frota, Tasks, ligações, indicadores, publicação de rotas | Henry |
| [chapahalls/chapahalls-ideas](https://github.com/chapahalls/chapahalls-ideas) | pesquisa, decisões de produto e plano de arquitetura | time |

Toda a voz roda na **Agora Conversational AI**. O áudio vai do aparelho direto para a nuvem da Agora; este backend é o plano de controle: tokens, `/join`, `/leave`, `/speak` e `/call`, o LLM próprio com ferramentas e as regras de negócio.

## Propósito, fronteiras e estado atual

O backend coordena a operação que começa na viagem atribuída e termina na descarga: recebe posições, detecta aproximação/chegada, cria Tasks, calcula estadia, registra chamadas, persiste mensagens/chamados e entrega atualizações aos dois frontends. Ele é adequado para demonstrar esse fluxo com dados fictícios e contratos integráveis, mas não deve ser tratado como uma plataforma pronta para operação real.

| Área | Implementado no repositório | Limite atual |
|---|---|---|
| Operação | rotas, geocerca, Tasks, escalonamento, estadia, ocorrências, pedidos e timeline | seed, GPS e documentos de demonstração |
| Tempo real | SSE do CCO e WebSocket para rota/motorista | sem replay/cursor garantido; clientes precisam reconciliar por REST |
| Voz e chamadas | controle de sessão Agora, LLM com ferramentas, contingência local, cascata Twilio → Agora RTC | PSTN/RTC reais exigem credenciais, URL pública e permissões externas |
| Arquivos | metadados no Postgres e binários em `ARQUIVOS_DIR` | não há autenticação/autorização ou versionamento de arquivos |
| Identidade | perfis persistidos e token SSO MOCK | token não protege endpoints; CORS está amplo para a demonstração |

Os frontends devem conservar essa distinção. Não use um campo ausente da API para gerar GPS, valor de estadia, documento, evento ou sucesso de telefonia no cliente.

---

## Dependências

- **Para rodar:** Docker com Compose v2. Nada roda direto na máquina; as imagens instalam o resto.
- **Backend (Python 3.12):** FastAPI, Uvicorn, SQLModel, Alembic, psycopg, pydantic-settings, httpx e `agora-agents` (só o gerador de tokens). As versões fixadas estão em `backend/requirements.txt`; as de teste (pytest, pytest-asyncio, respx), em `backend/requirements-dev.txt`.
- **Infra:** Postgres 16 e cloudflared (túnel público), ambos via `docker-compose.yml`.
- **Serviços externos:**
  - Agora Conversational AI (App ID e App Certificate; Customer ID e Secret opcionais);
  - LLM compatível com OpenAI (opcional; sem ele, vale a contingência);
  - Twilio, só para a ligação telefônica real, que é opcional.

## Como rodar (clone limpo, só Docker)

```bash
git clone https://github.com/chapahalls/avisai.git && cd avisai
```

```bash
cp .env.example .env   # preencha AGORA_APP_ID, AGORA_APP_CERTIFICATE e LLM_API_KEY
```

```bash
make up                # Postgres + api (migra e roda o seed) + túnel cloudflared
```

```bash
make test              # roda os testes no container (banco avisai_test)
```

- A api fica em `http://localhost:8000`, com a doc interativa em `/docs`. `curl localhost:8000/health` mostra a URL pública do túnel (`public_url`).
- O túnel é obrigatório: a nuvem da Agora precisa chamar o nosso `/v1/chat/completions`. A URL do quick tunnel é descoberta sozinha, e você pode fixá-la em `PUBLIC_URL` se preferir.
- **Se o túnel reiniciar, a URL muda.** Abra uma nova sessão depois disso.
- Para a demo, use `ESTADIA_ACELERACAO=600` (1 s real conta 10 min de estadia) e `CCO_INTERVALO_S=20`.

### Roteiro da demo
1. `curl -X POST localhost:8000/rotas/1/reset`: deixa a rota pronta.
2. Abra `{PUBLIC_URL}/teste` (cliente mínimo do motorista) e clique em **Iniciar conversa**. O agente saúda em PT-BR, e dá para interrompê-lo falando por cima (barge-in).
3. `make sim ARGS="--desde 25"`: o caminhão anda.
   - Na aproximação (ETA ≤ 15 min), o agente avisa por voz.
   - Na chegada (≤ 300 m), surge a Task pendente e o contador de estadia começa a andar.
4. Ninguém confirma a Task. Saem 3 notificações ao CCO (push, painel, ligação), e o agente diz "Tô ligando pro recebimento".
5. Abra `{PUBLIC_URL}/recebedor`, clique em **Atender** e responda algo como "A doca 4 libera em 40 minutos". A resposta vai para a Task e o agente do motorista repassa por voz.
6. Diga ao agente "descarreguei": a estadia é encerrada com o valor final.

Para refazer: `POST /rotas/1/reset`, ou o botão "Reset da demo" na `/teste`.

---

## Arquitetura

```
backend/app/
  dominio/       regras puras: estadia, geocerca, escalonamento, prompts, contingência, documentos e enums
  servicos/      casos de uso: sessões, rotas, Tasks, chamadas, alertas, mensagens, chamados, conversa e ferramentas
  portas.py      contratos (typing.Protocol): AgoraGateway, LLM, Relogio, Voz, Discador
  integracoes/   adaptadores reais: Agora REST, Twilio, OpenAI, tokens e túnel
  api/           routers FastAPI + schemas Pydantic; cada módulo agrupa uma superfície HTTP/WS
  infra/         settings, banco (Postgres/SQLModel), modelos, eventos (pub/sub), container e limite de upload
backend/alembic/ migrações
backend/tests/   cenários dado/quando/então: dominio, servicos, integracoes, api
backend/docs/    perfis de demonstração e contrato de arquivos
backend/static/  páginas mínimas de motorista e recebedor para testar RTC
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
| `POST /agent/start` `{tripId}` | inicia o agente e devolve `{sessionId, agentId, agentUid, appId, channel, uid, token}` |
| `POST /agent/stop` `{sessionId \| agentId}` | `/leave` do agente |
| `GET /token?channel&uid` | token RTC+RTM |
| `POST /call/receiver` `{tripId, reason}` | liga para o recebedor (plano B ou plano A) |
| `POST /events` | **outbox idempotente**: `DomainEvent` com `idempotencyKey` (200 na primeira vez, 409 se repetido). Aplica `ArrivalRegistered`, `PickupConfirmed`, `OccurrenceCreated`, `UnloadConfirmed` e `ReportSubmitted` |
| `GET /events?tripId&since` | linha do tempo no formato `DomainEvent {id, idempotencyKey, tripId, type, occurredAt, receivedAt, source, payload}`; serve para o polling de 2 s |
| `GET /api/route?tripId` | rota do dia: polyline, origem, destino, recebedor, placa, NF, canal e uids |
| `GET /api/receivers` | ranking de recebedores: espera média, ligações atendidas, estadia devida, avisados antes da chegada |
| `GET /api/metrics` | KPIs da seção 6.2: horas paradas, estadia devida, tempo até ação do CCO, tasks escaladas, % avisados, % atendidas, % reportes completos na 1ª, latência do LLM |
| `GET /api/documents` | NF-e e CT-e da rota; a consulta por voz também lista os nomes disponíveis |
| `GET /cco/chamados?abertos=true` | chamados do motorista aguardando resposta do CCO |
| `POST /cco/chamados/{id}/responder` | resposta do CCO; o agente fala a resposta ao motorista |
| `POST /auth/sso` | SSO mock (token fake; papel `cco` se o e-mail tiver "cco") |

Os `type` do contrato saem dos nossos eventos: `retirada`→`PickupConfirmed`, `relatorio`→`ReportSubmitted`, `campo_faltante`→`ReportFieldMissing`, `ocorrencia`→`OccurrenceCreated`, `aproximacao`→`ApproachDetected`, `aviso_recebedor`→`ReceiverNotified`, `resposta_recebedor`/`ligacao_nao_atendida`→`ReceiverCallResult` (`payload.answered`), `chegada`→`ArrivalRegistered`, `task_criada`→`TaskCreated`, `notificacao_cco`/`escalada_recebedor`→`TaskEscalated`, `task_confirmada`→`TaskAcknowledged`, `descarga`→`UnloadConfirmed`.

Extensões fora da lista do doc: `AgentSessionStarted`, `PickupGeofenceEntered`, `ReceiverCallStarted`, `ReceiverCallFailed`, `ReceiverCallFallback`, `ReceiverRefusedToday`, `CentralRequestSent`, `CentralRequestAnswered`, `GpsDivergence`, `VoiceTranscript`.

As variáveis do doc também valem: `AGORA_REST_KEY` e `AGORA_REST_SECRET` (equivalem a `AGORA_CUSTOMER_*`) e `SIP_FROM_NUMBER`. Além do polling, há **SSE** (`/cco/stream`) e **WebSocket** (`/ws`), com entrega instantânea.

### Publicação de rota e vínculo com o motorista
1. **CCO publica a rota:** `POST /rotas` com `origem`, `destino`, `recebedor {empresa, nome, telefone_e164}`, `carga_t`, `capacidade_t` (capacidade total do veículo, que é a base da estadia pela Lei 11.442; vazio usa `carga_t`), `placa`, `nota_fiscal`, `janela_descarga` e, opcionalmente, `motorista_id`. O trajeto é simulado em linha reta, e a rota fica `publicada`.
2. **Atribui ao motorista:** `POST /rotas/{id}/atribuir {motorista_id}`. A rota passa a `planejada`, sai o evento `rota_atribuida` (**`RouteAssigned`** no `/events`, `source: cco`) e, se o motorista estiver com o agente aberto, ele ouve "Rota nova: …".
3. **App do motorista:**
   - `POST /auth/sso {email}` devolve `driverId` e o `tripId` da rota atual;
   - `GET /api/route?driverId=` (ou `GET /motoristas/{id}/rota-atual`) traz a rota;
   - o WebSocket `/ws?motorista_id=` recebe as atribuições novas na hora (no hook RN: `motoristaId` e `onRotaAtribuida`).
4. **Motoristas:** `GET /motoristas` e `POST /motoristas {nome, telefone_e164, email}`. No seed, o Carlos é `carlos@rotasul.test`.

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
8. **Ocorrência aprofundada:** depois do registro, o agente faz as perguntas do tipo, **uma por vez**. Em acidente: feridos, envolvimento do caminhão, se dá para seguir e local; em avaria: o que houve, se precisa de socorro e a carga; em fila: quantos caminhões e previsão. Acidente com ferido leva o agente a orientar ligar **192 (SAMU) ou 193 (Bombeiros)** e gera `ocorrencia_grave` (prioridade crítica) para o CCO. O quadro completo sai em `ocorrencia_detalhada` (`OccurrenceDetailed`). Funciona com o LLM (ferramenta `detalhar_ocorrencia`) e na contingência.
9. **Pergunta sobre a NF ou o CT-e por voz:** a ferramenta `consultar_documento` responde com o nome do documento e os campos disponíveis (número, peso, valor, destinatário, itens, frete, placa ou chave). Se o motorista pedir a lista, informa os títulos; sem campo, diz "não encontrei". A resposta sai só dos campos extraídos e nunca arredonda. O evento é `pergunta_documento`, que aparece como `DocumentQuestionAnswered` no `/events`. Funciona também sem LLM. Anexos reais da rota ficam em `/rotas/{id}/arquivos`.
10. **Dupla prova de GPS:** `POST /rotas/{id}/posicao` com `fonte=rastreador` registra o GPS do caminhão. Na retirada e na chegada, se celular e rastreador estiverem a mais de 500 m, o evento fica `nao_validado` e sai `divergencia_gps` para o CCO. O simulador manda os dois GPS (`--divergir` força a divergência).

## Integração com os fronts

| Quem | Usa SDK da Agora? | Como fala com o backend |
|---|---|---|
| App do motorista (React Native) | `react-native-agora` (só áudio) | REST + **WebSocket `/ws?rota_id=`** |
| Painel do CCO (Vite) | não (só para o "ouvir ao vivo", opcional) | REST + **SSE `/cco/stream`** |
| Recebedor, plano B | Web SDK (página `/recebedor` do backend) | `GET /ligacoes/atual/recebedor` |
| Recebedor, plano A | nenhum, é um telefone de verdade | — |

**Clientes prontos para copiar** (em `clients/`, com tipos checados por `tsc --strict` contra `react-native-agora` 4.6.4):
- `clients/tipos.ts`: o contrato em TypeScript (Sessao, TaskCCO, Estadia, Ligacao, EventoStream e as mensagens do stream).
- `clients/react-native/useAvisaiVoz.ts`: hook do app do motorista. Expõe `iniciar()`, `encerrar()`, `alternarMudo()`, `enviarPosicao()` e o estado vivo (`status`, `estadia`, `task`, `ligacao`, `falas`, `eventos`). Dentro dele já estão o `POST /sessions`, o join com `AUDIO_SCENARIO_AI_CLIENT`, os parâmetros de áudio da Agora (reaplicados quando o áudio troca de saída), o viva-voz, a renovação do token, o `DELETE` e o `/ws` com reconexão.
- `clients/web/avisaiStream.ts`: cliente SSE tipado, sem framework, com reconexão e as ações REST do CCO. `clients/web/useAvisaiCCO.ts` é um hook React por cima dele.

O front **nunca** chama a REST da Agora: App Certificate e Customer Secret ficam só aqui. O front recebe tokens de 24 h e renova por `GET /token`.

### App do motorista (React Native)
- Precisa de dev build ou `expo prebuild`, porque `react-native-agora` tem módulo nativo e não roda no Expo Go.
- Boas práticas da Agora para agentes de voz (`/en/ai/best-practices/audio-setup`):
  - SDK ≥ 4.5.1 com `AUDIO_SCENARIO_AI_CLIENT` na inicialização;
  - os `setParameters` de áudio da página audio-setup antes do join e a cada `onAudioRouteChanged` (Bluetooth ↔ viva-voz);
  - as extensões de IA de supressão de ruído e de cancelamento de eco;
  - viva-voz ligado, sem vídeo.

```ts
const s = await fetch(`${API}/sessions`, { method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ rota_id: 1 }) }).then(r => r.json());
// s = { id, canal, user_uid, agent_uid, agent_id, app_id, token, status }
const engine = createAgoraRtcEngine();
engine.initialize({ appId: s.app_id /* + audioScenario: AI client, ver doc */ });
engine.registerEventHandler({
  onUserJoined: (_c, uid) => uid === s.agent_uid && setPronto(true),       // agente entrou
  onTokenPrivilegeWillExpire: async () => engine.renewToken(
    (await fetch(`${API}/token?channel=${s.canal}&uid=${s.user_uid}`).then(r => r.json())).token),
});
engine.setEnableSpeakerphone(true);
engine.joinChannel(s.token, s.canal, s.user_uid, {
  clientRoleType: ClientRoleType.ClientRoleBroadcaster,
  publishMicrophoneTrack: true, autoSubscribeAudio: true, publishCameraTrack: false,
});
const ws = new WebSocket(`${API.replace("http", "ws")}/ws?rota_id=1`);
ws.onmessage = (m) => { const { canal, dado } = JSON.parse(m.data); /* snapshot | evento | task | fala | contador */ };
// encerrar: engine.leaveChannel(); fetch(`${API}/sessions/${s.id}`, { method: "DELETE" })
```

O `POST /sessions` voltar 200 não quer dizer que o agente já está no canal. Espere `onUserJoined` do uid 9001. A fala proativa ("o recebimento disse doca 4") chega sozinha: o backend chama o `/speak` da Agora.

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

### Canais e UIDs (fixos)
| | canal | uid |
|---|---|---|
| Motorista | `avisai-rota-{rota_id}` | 1001 |
| Agente do motorista | `avisai-rota-{rota_id}` | 9001 |
| CCO, ouvindo (opcional) | o canal que for ouvir | 2001 |
| Recebedor (página ou gateway SIP) | `avisai-recebedor-{ligacao_id}` | 3001 |
| Agente que liga ao recebedor | `avisai-recebedor-{ligacao_id}` | 9002 |

---

## Contrato de API

Base local: `http://localhost:8000`. O OpenAPI vivo está em `/docs` e `/openapi.json`. As tabelas abaixo resumem as rotas públicas; campos, códigos de erro e schemas devem ser conferidos no OpenAPI da instância em uso.

### Infraestrutura, identidade e voz

| Método | Caminho | Corpo | O que faz |
|---|---|---|---|
| GET | `/health` | — | estado da configuração, túnel, Agora, Twilio e LLM |
| GET | `/usuarios?role=driver\|cco`<br>`/api/users` | — | perfis persistidos de demonstração |
| POST | `/auth/sso` | `{email}` | login MOCK; devolve perfil e token não autorizador |
| GET | `/token?channel=&uid=` | — | token RTC+RTM de 24 h |
| POST | `/sessions` | `{rota_id}` | inicia o agente da viagem e devolve o token do motorista |
| GET / DELETE / POST | `/sessions`<br>`/sessions/{id}`<br>`/sessions/{id}/speak` | — / — / `{texto, prioridade?}` | lista, encerra ou pede uma fala manual para teste |
| POST | `/v1/chat/completions` | OpenAI compatível | gateway interno do LLM chamado pela Agora; não é endpoint de frontend |

### Rotas, motoristas, arquivos e comunicação

| Método | Caminho | Corpo | O que faz |
|---|---|---|---|
| GET / POST | `/rotas` | — / `NovaRota` | lista ou publica rota; `motorista_id` é opcional por compatibilidade, embora o painel CCO exija um motorista cadastrado |
| GET | `/rotas/{id}` | — | detalhe, trajetória, posições, canal e UIDs |
| POST | `/rotas/{id}/atribuir` | `{motorista_id}` | atribui/reatribui e emite `rota_atribuida` |
| POST | `/rotas/{id}/posicao` | GPS do celular ou rastreador | atualiza posição, geocerca e status |
| POST | `/rotas/{id}/chegada`<br>`/descarga`<br>`/reset` | — / `{por?}` / — | registra chegada, encerra descarga ou reinicia a rota de demonstração |
| GET / POST | `/rotas/{id}/solicitacoes` | — / `{pergunta}` | pedidos do CCO e resposta capturada pelo agente |
| GET / POST | `/rotas/{id}/mensagens` | — / `{texto}` | thread CCO → motorista e tentativa de fala do agente |
| GET | `/rotas/{id}/chamados` | — | chamados de chegada/ocorrência ligados à rota |
| GET / POST | `/rotas/{id}/arquivos` | — / multipart `arquivo` | lista ou envia anexo real |
| GET | `/rotas/{id}/arquivos/{arquivo_id}/download` | — | baixa o conteúdo binário do anexo |
| GET / POST | `/motoristas` | — / cadastro de motorista | lista ou cadastra o vínculo operacional |
| GET | `/motoristas/{id}/rota-atual` | — | alternativa snake_case para a rota atual |

### CCO, eventos e chamadas

| Método | Caminho | Corpo | O que faz |
|---|---|---|---|
| GET | `/cco/estado?rota_id=` | — | snapshot de rotas, Tasks, estadias, chamadas, ocorrências, chamados e eventos |
| GET / POST | `/cco/chamados`<br>`/cco/chamados/{id}/responder` | — / `{resposta, respondido_por?}` | lista e responde chamados persistidos; resposta é enviada ao agente |
| GET / POST | `/cco/chamadas-agente`<br>`/cco/rotas/{id}/ligar` | — / `{motivo?}` | acompanha ou inicia a cascata Twilio → Agora para operador |
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

Valores de `EventoStream.tipo` (enum `TipoEvento`):
- sessão: `sessao_iniciada`;
- trajeto e chegada: `aproximacao`, `chegada`, `chegada_confirmada_voz`;
- CCO: `notificacao_cco`, `escalada_recebedor`, `task_confirmada`;
- ligação: `ligacao_recebedor`, `ligacao_falhou`, `fallback_plano_b`, `ligacao_nao_atendida`, `resposta_recebedor`;
- registros: `ocorrencia`, `descarga`;
- falas: `fala_motorista`, `fala_recebedor`, `fala_agente`.

---

## Variáveis do `.env`

Obrigatórias: `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE`. Recomendadas: `LLM_API_KEY` (OpenAI) e `LLM_SHARED_SECRET`.

| Variável | Padrão | Para quê |
|---|---|---|
| `AGORA_CUSTOMER_ID` / `AGORA_CUSTOMER_SECRET` | vazio | Basic auth na REST; vazio usa auth por token |
| `LLM_MODE` | `custom` | Define sessões não auditáveis. As sessões de **motorista** e **operador** sempre usam o gateway `custom`, pois alertas, decisões e tool calls precisam chegar ao backend/SSE da CCO. |
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | `gpt-4o-mini` | upstream do nosso LLM (qualquer API compatível com OpenAI); sem chave, usa a contingência |
| `PUBLIC_URL` | descoberta automática | URL do túnel |
| `RECEBEDOR_MODO` | `rtc` | `rtc` (plano B) ou `sip` (plano A) |
| `AGORA_SIP_FROM_NUMBER`, `RECEBEDOR_TELEFONE_E164` | — | plano A |
| `ASR_LANGUAGE` | `pt-BR` | idioma do ASR |
| `ASR_VENDOR` | `ares` | `ares` (ASR da Agora, gerenciado, com palavras-chave; padrão), `deepgram` (gerenciado) ou `openai` (chave própria) |
| `ASR_MODEL` | vazio | Deepgram: `nova-2` ou `nova-3`; OpenAI: `gpt-4o-mini-transcribe` ou `gpt-4o-transcribe` |
| `ASR_API_KEY` | vazio | só para `openai`; vazio usa `LLM_API_KEY` se o LLM for a OpenAI |
| `TTS_VOICE_ID`, `TTS_VOICE_ID_RECEBEDOR` | vozes PT da MiniMax | vozes dos dois agentes |
| `TTS_SAMPLE_RATE`, `TTS_LANGUAGE_BOOST`, `TTS_SPEED` | `24000`, `Portuguese`, `1.0` | MiniMax `speech-2.8-turbo`: a taxa de amostragem é obrigatória na doc da Agora; `language_boost` fixa o português |
| `AGORA_SAL` | `false` | Selective Attention Locking (Beta) no agente do motorista |
| `CCO_INTERVALO_S`, `CCO_MAX_TENTATIVAS` | `20`, `3` | ritmo do escalonamento (a regra da empresa no seed define 3) |
| `ESTADIA_ACELERACAO` | `1` | relógio da estadia; use `600` na demo |
| `LIGAR_RECEBEDOR_NA_APROXIMACAO` | `true` | liga para o recebedor já na aproximação (fluxo do repo de ideias) |
| `LIGACAO_TIMEOUT_S` | `180` | sem resposta até aqui, a ligação é registrada como não atendida |

### Melhorar o reconhecimento de fala (ASR)
Se a transcrição vier ruim, troque só o ASR no `.env`. Ferramentas e fala proativa continuam iguais.
1. **`ASR_VENDOR=ares`** (padrão, grátis, ASR da Agora): suporta pt-BR e recebe **palavras-chave** do domínio (doca, portaria, CT-e, palete, estadia…) mais o destino, o recebedor e a placa da rota. É a melhor opção grátis para os termos da operação.
2. **`ASR_VENDOR=deepgram`** (grátis, gerenciado): `ASR_MODEL=nova-3` ou `nova-2`, sem palavras-chave.
3. **`ASR_VENDOR=openai`** (pago): `gpt-4o-mini-transcribe` com um prompt de contexto em PT-BR e os mesmos termos. É a melhor qualidade.

Depois de editar o `.env`, rode `docker compose up -d --force-recreate api` e abra uma sessão nova. O ARES e o Deepgram nova-2 foram aceitos pela Agora (`/join` 200); a qualidade se compara falando, de preferência com fone de ouvido.

### LLM sem custo (opcional)
Qualquer API compatível com OpenAI e com suporte a ferramentas serve. Duas opções com plano gratuito:
- **Groq** (muito rápido, bom para voz): `LLM_BASE_URL=https://api.groq.com/openai/v1`, `LLM_MODEL=llama-3.3-70b-versatile`, `LLM_API_KEY=` gerada em console.groq.com.
- **Gemini**: `LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai`, `LLM_MODEL=gemini-2.5-flash`, `LLM_API_KEY=` gerada no aistudio.google.com.

Depois de editar o `.env`, rode `docker compose up -d --force-recreate api`.

**Sem chave nenhuma, a demo funciona pela contingência** (`dominio/contingencia.py`), que entende:
- **motorista:** início da rota por voz ("quero iniciar a viagem"), chegada ("cheguei", "tô na portaria"), ocorrências (fila, doca ocupada, documento, avaria, recusa, atraso, acidente), descarga ("descarreguei") e perguntas sobre documentos, tempo parado, estadia, doca e CCO, respondidas com o estado real da rota;
- **recebedor:** extrai a doca e a previsão ("a doca 4 libera em 40 minutos", "às 15h", "só amanhã").

### Ativar a ligação telefônica real (plano A)
**Twilio (Elastic SIP Trunk), automatizado:**
1. Compre um número na Twilio. Um número dos EUA (+1) sai na hora; um brasileiro exige cadastro regulatório.
2. No `.env`, coloque `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_NUMERO=+1…` e `TWILIO_TRUNK_DOMINIO=avisai-<time>`. O backend não usa essas credenciais; só o script de setup.
3. Rode `make twilio`. O script cria o trunk com a Termination URI `<dominio>.pstn.twilio.com`, cria a IP ACL com os IPs SIP de saída da Agora (+1 e +55), vincula a ACL ao trunk, associa o número e imprime o que cadastrar na Agora.
4. Na Twilio, habilite o Brasil nas permissões geográficas de voz (Geo Permissions). Conta trial só liga para números verificados.

**Agora:**
1. No console da Agora, em *Phone Numbers → Add Phone Number*, cadastre o número com vendor *SIP Trunk*, o endereço e o protocolo que o script imprimiu.
2. No `.env`: `RECEBEDOR_MODO=sip`, `AGORA_SIP_FROM_NUMBER=+55…` e `RECEBEDOR_TELEFONE_E164=+55…` (o telefone de quem atende).
3. `make up` de novo. O agente passa a ligar com `POST /call` e acompanha o estado por `GET /calls/{id}`.

Se o `/call` falhar, a ligação **cai sozinha no plano B** e o evento `fallback_plano_b` fica registrado.

---

## Boas práticas da Agora aplicadas
Fonte: docs da Agora, via o MCP `mcp.agora.io` e o OpenAPI v2.
- Áudio do servidor nos padrões da Agora (sem overrides de VAD); interrupção (barge-in) explícita.
- Latência:
  - `gpt-4o-mini` com `max_tokens` 150;
  - streaming real dos chunks da OpenAI até a Agora;
  - **filler words** ("Peraí, deixa eu registrar") quando a resposta passa de 1,5 s, cobrindo as ferramentas.
- Nome de agente único por sessão (evita 409); `leave` explícito, porque o limite é de 20 agentes simultâneos por App ID; `idle_timeout` como rede de segurança.
- `/speak` com `INTERRUPT` só para o que muda a ação do motorista (a resposta do recebedor); o resto vai em `APPEND`.
- Fora do escopo: a Platform API (Preview, só EUA). A telefonia (`/call`) está em Beta.
- **SDK Python:** o `agora-agents` 2.15 força `turn_detection.language` e `asr.language` como `en-US`, e não aceita `pt-BR`. Por isso o `/join` vai por REST direto (payload do OpenAPI) com `pt-BR`. Do SDK, usamos só o gerador oficial de AccessToken2 (o pacote `agora-token` é só npm).

---

## Simulado / pré-existente (E5/E8)
- **Rastreador do caminhão simulado:** o simulador manda um segundo GPS (`fonte=rastreador`) com ruído de cerca de 10 m, que serve de dupla prova. Integração real com Sascar, Omnilink etc. fica fora.
- **Documentos, SSO e métricas:** `/api/documents` devolve NF-e e CT-e fictícios; `/auth/sso` devolve token fake; a latência em `/api/metrics` mede só o nosso LLM até o primeiro trecho (não inclui ASR, TTS e rede).
- **GPS simulado:** `scripts/simular_rota.py` move o caminhão por um trajeto reto de Jundiaí a Campinas, chamando `POST /rotas/{id}/posicao`. Em produção, a posição viria do GPS do celular do motorista pelo mesmo endpoint.
- **Ligação ao recebedor (plano B):** na demo, o recebedor atende por uma página web (`/recebedor`) num canal Agora RTC, não por telefone. A ligação telefônica real (plano A, `POST /call`) está implementada e testada com mock, mas desligada: o time não tem número importado na Agora.
- **Seed fictício:** a transportadora, o motorista, a placa, a NF, o recebedor e os telefones são inventados (`backend/app/seed.py`).
- **Estadia acelerada:** com `ESTADIA_ACELERACAO=600`, 1 s real conta 10 min, para mostrar a franquia de 5 h e o valor em minutos de demo. Sem a variável, o relógio é real. Os intervalos com o CCO também são curtos (20 s).
- **CCO:** chamados de chegada e ocorrência são persistidos no banco local, aparecem no painel e podem ser respondidos por botão. O canal de voz do agente entrega a resposta ao motorista; push/telefonia reais para a central continuam fora do escopo.
- **Pré-existente / terceiros:**
  - Agora Conversational AI, com o ASR da Agora (ARES, com palavras-chave; Deepgram nova-3 como alternativa) e preset gerenciado MiniMax (TTS);
  - OpenAI (LLM);
  - SDK `agora-agents` (só os tokens);
  - Web SDK da Agora nas páginas de teste;
  - cloudflared (túnel).
  O formato do `/join` seguiu o quickstart oficial `agent-quickstart-python` e o OpenAPI da Agora.
- **Contingência:** sem `LLM_API_KEY`, ou com a OpenAI fora do ar, o nosso LLM responde por palavras-chave (cheguei, fila, descarreguei, doca...) para a demo não travar.
- **LGPD:** não guardamos áudio, só a transcrição. Não há gravação na nuvem nem dado de saúde.
