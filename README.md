# AvisAI · backend

Copiloto de voz para transportadoras, focado no **caminhão parado**:
1. Na aproximação, o agente avisa o motorista e o CCO.
2. Na chegada, cria a Task do CCO e conta a estadia (Lei 11.442, franquia de 5 h, R$ 2,50 por t/h).
3. Insiste com o CCO e, sem resposta, **liga para o recebedor**.
4. Registra a resposta do recebedor como prova e a repassa por voz ao motorista.

Time Quarteto Chapahalls · hackathon UNMUTE by Agora · backend e infra: Lucas.

Toda a voz roda na **Agora Conversational AI**. O áudio vai do aparelho direto para a nuvem da Agora; este backend é o plano de controle: tokens, `/join`, `/leave`, `/speak` e `/call`, o LLM próprio com ferramentas e as regras de negócio.

---

## Rodar a partir de um clone limpo (só Docker)

Pré-requisitos: Docker com Compose v2. Nada roda direto na máquina.

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
  dominio/       regras puras: estadia, geocerca, escalonamento, prompts, payload da Agora, enums
  servicos/      casos de uso: sessoes, rotas, tasks, ligacoes, conversa, ferramentas
  portas.py      contratos (typing.Protocol): AgoraGateway, LLM, Relogio, Voz, Discador
  integracoes/   adaptadores reais: agora_rest, openai_llm, tokens, tunel
  api/           routers FastAPI + schemas Pydantic (contrato com o front)
  infra/         settings, db (Postgres/SQLModel), models, eventos (pub/sub), container
backend/alembic/ migrações
backend/tests/   cenários dado/quando/então: dominio, servicos, integracoes, api
scripts/simular_rota.py   GPS simulado
```

- Os serviços recebem as portas pelo container (`infra/container.py`); os testes trocam por fakes.
- Ligação ao recebedor: `DiscadorRTC` (plano B) ou `DiscadorSIP` (plano A), escolhidos por config.
- Ferramentas do LLM: um registro `{nome: Ferramenta}` em `servicos/ferramentas.py`. Uma ferramenta nova é uma entrada nova.

---

## Integração com os fronts

| Quem | Usa SDK da Agora? | Como fala com o backend |
|---|---|---|
| App do motorista (React Native) | `react-native-agora` (só áudio) | REST + **WebSocket `/ws?rota_id=`** |
| Painel do CCO (Vite) | não (só para o "ouvir ao vivo", opcional) | REST + **SSE `/cco/stream`** |
| Recebedor, plano B | Web SDK (página `/recebedor` do backend) | `GET /ligacoes/atual/recebedor` |
| Recebedor, plano A | nenhum, é um telefone de verdade | — |

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

| Método | Caminho | Corpo | O que faz |
|---|---|---|---|
| GET | `/health` | — | estado da config e URL pública |
| GET | `/token?channel=&uid=` | — | `{app_id, channel, uid, token}` RTC+RTM (24 h) |
| POST | `/sessions` | `{rota_id}` | inicia o agente no canal do motorista e devolve `SessaoOut` com o token do motorista |
| GET | `/sessions` | — | últimas sessões |
| DELETE | `/sessions/{id}` | — | `/leave` do agente |
| POST | `/sessions/{id}/speak` | `{texto, prioridade?}` | fala manual (teste) |
| GET | `/rotas`, `/rotas/{id}` | — | rotas (com `trajeto`, canal e uids) |
| POST | `/rotas/{id}/posicao` | `{lat, lng, velocidade_kmh?, precisao_m?}` | GPS; devolve `{distancia_m, eta_min, status, disparos[]}` |
| POST | `/rotas/{id}/chegada` | — | chegada manual (idempotente) |
| POST | `/rotas/{id}/descarga` | `{por?}` | encerra estadia e Task |
| POST | `/rotas/{id}/ligar-recebedor` | `{motivo?}` | liga para o recebedor na hora |
| POST | `/rotas/{id}/reset` | — | reinicia a demo da rota |
| GET | `/tasks` | — | Tasks do CCO |
| POST | `/tasks/{id}/confirmar` | `{confirmado_por}` | CCO assume e o escalonamento para |
| GET | `/ligacoes`, `/ligacoes/{id}` | — | ligações (com token do recebedor) |
| GET | `/ligacoes/atual/recebedor` | — | ligação em andamento, ou `{ligacao: null}` |
| GET | `/cco/estado?rota_id=` | — | snapshot: rotas, tasks, estadias, ligações, ocorrências, eventos |
| GET | `/cco/stream?rota_id=` | — | **SSE** |
| WS | `/ws?rota_id=` | — | **WebSocket**: `{canal, dado}` com as mesmas mensagens do SSE |
| GET | `/eventos?rota_id=&limite=` | — | linha do tempo (`EventoStream`) |
| POST | `/v1/chat/completions` | OpenAI | **LLM próprio**, chamado pela Agora; não é para o front |
| GET | `/teste`, `/recebedor` | — | páginas de teste do motorista e do recebedor (plano B) |

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
| `LLM_MODE` | `custom` | `custom` = nosso LLM com ferramentas; `agora` = LLM gerenciado |
| `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` | `gpt-4o-mini` | upstream do nosso LLM; sem chave, usa a contingência por palavras-chave |
| `PUBLIC_URL` | descoberta automática | URL do túnel |
| `RECEBEDOR_MODO` | `rtc` | `rtc` (plano B) ou `sip` (plano A) |
| `AGORA_SIP_FROM_NUMBER`, `RECEBEDOR_TELEFONE_E164` | — | plano A |
| `ASR_LANGUAGE` | `pt-BR` | idioma do ASR |
| `TTS_VOICE_ID`, `TTS_VOICE_ID_RECEBEDOR` | vozes PT da MiniMax | vozes dos dois agentes |
| `AGORA_SAL` | `false` | Selective Attention Locking (Beta) no agente do motorista |
| `CCO_INTERVALO_S`, `CCO_MAX_TENTATIVAS` | `20`, `3` | ritmo do escalonamento (a regra da empresa no seed define 3) |
| `ESTADIA_ACELERACAO` | `1` | relógio da estadia; use `600` na demo |
| `LIGAR_RECEBEDOR_NA_APROXIMACAO` | `false` | liga também na aproximação |
| `LIGACAO_TIMEOUT_S` | `180` | sem resposta até aqui, a ligação é registrada como não atendida |

### Ativar a ligação telefônica real (plano A)
1. No console da Agora, importe um número (Import phone numbers) ou configure um SIP trunk.
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
- **GPS simulado:** `scripts/simular_rota.py` move o caminhão por um trajeto reto de Jundiaí a Campinas, chamando `POST /rotas/{id}/posicao`. Em produção, a posição viria do GPS do celular do motorista pelo mesmo endpoint.
- **Ligação ao recebedor (plano B):** na demo, o recebedor atende por uma página web (`/recebedor`) num canal Agora RTC, não por telefone. A ligação telefônica real (plano A, `POST /call`) está implementada e testada com mock, mas desligada: o time não tem número importado na Agora.
- **Seed fictício:** a transportadora, o motorista, a placa, a NF, o recebedor e os telefones são inventados (`backend/app/seed.py`).
- **Estadia acelerada:** com `ESTADIA_ACELERACAO=600`, 1 s real conta 10 min, para mostrar a franquia de 5 h e o valor em minutos de demo. Sem a variável, o relógio é real. Os intervalos com o CCO também são curtos (20 s).
- **CCO:** as "notificações" ao CCO (push, painel, ligação) são eventos no stream do painel. Não há envio real de push nem ligação para a central.
- **Pré-existente / terceiros:**
  - Agora Conversational AI, com os presets gerenciados Deepgram nova-3 (ASR) e MiniMax (TTS);
  - OpenAI (LLM);
  - SDK `agora-agents` (só os tokens);
  - Web SDK da Agora nas páginas de teste;
  - cloudflared (túnel).
  O formato do `/join` seguiu o quickstart oficial `agent-quickstart-python` e o OpenAPI da Agora.
- **Contingência:** sem `LLM_API_KEY`, ou com a OpenAI fora do ar, o nosso LLM responde por palavras-chave (cheguei, fila, descarreguei, doca...) para a demo não travar.
- **LGPD:** não guardamos áudio, só a transcrição. Não há gravação na nuvem nem dado de saúde.
