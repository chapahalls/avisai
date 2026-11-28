# Validação ponta a ponta — 2026-11-27 23:47 (BRT)

Commit avaliado: `c9c040c` (o `sha` que `GET /health` expõe nesse momento). **Primeira validação
publicada direto contra o ambiente público da AWS** (`https://d3fy4m7zwukr3x.cloudfront.net`,
não `localhost`), já com `LIGAR_RECEBEDOR_NA_APROXIMACAO=true` aplicado em
[`infra/envs/dev/ecs.tf`](../infra/envs/dev/ecs.tf) e exposto em `GET /health` — risco do júri
de hoje (score.md 2026-11-27, H1) sobre esse fluxo estar desligado na demo pública sem avisar.
LLM e LiveKit são os de verdade da conta da Rumo, nenhuma chave de teste/mock.

Esta rodada também traz o conserto determinístico pedido para a etapa 3d (`fila`↔`atraso`):
`corrigir_tipo_por_estado()` em [`app/dominio/ocorrencias.py`](../backend/app/dominio/ocorrencias.py),
aplicado em `registrar_ocorrencia()` antes de persistir — se a rota está `em_transito`
(antes da geocerca de aproximação), uma ocorrência classificada como `fila` pelo LLM é
corrigida para `atraso`, porque não existe fila de caminhões num recebedor antes de chegar lá.
Testes unitários e um teste de integração reproduzindo a fala ambígua real estão em
`backend/tests/dominio/test_ocorrencias.py` e `backend/tests/api/test_lacunas_rastreabilidade.py`.

**Resultado da etapa 3d contra o LLM de verdade em produção: 4 rodadas, 4 acertos** (abaixo,
tabela completa). Antes do conserto a etapa falhava em ~1 de cada 3 rodadas (ver "Registro
histórico"). A correção é por estado da rota, não por ajuste de prompt — por isso é
determinística e testável, e não depende de o LLM "acertar" a classificação.

Api `https://d3fy4m7zwukr3x.cloudfront.net` · LLM upstream: sim · recebedor: rtc · duração 101 s

**32/34 etapas OK** (rodada publicada — ver a tabela de 4 rodadas mais abaixo)

| Etapa | Resultado | Detalhe |
|---|---|---|
| 1. CCO publica a rota e atribui ao motorista | ✅ | rota 10, motorista 8 |
| 1b. Login do motorista traz a rota atribuída (SSO mock) | ✅ |  |
| 2. Agente LiveKit despachado para a sala do motorista | ✅ | dispatch AD_vCxMscu82kv3 |
| 3. Geocerca da origem dispara a pergunta da retirada | ✅ |  |
| 3b. Retirada confirmada por voz | ✅ | agente: A retirada da carga foi confirmada. Agora, preciso que você me diga: como está a carga coletada? |
| 3c. Relatório inicial completo por voz | ✅ | agente: O relatório inicial foi registrado com sucesso: o caminhão está em "tudo certo" e a carga coletada é de 20 paletes. Não há perguntas pendentes da central no momento. |
| 3d. Atraso na estrada: agente liga para o recebedor com o novo horário | ✅ | agente: Registrei a ocorrência de trânsito parado e a previsão de atraso de 40 minutos. Agora, preciso saber: quanto tempo de atraso, mais ou menos? |
| 4. Aproximação detectada (ETA ≤ 15 min) e CCO avisado | ✅ | ETA 14.9 min |
| 4b. Agente liga para o recebedor na aproximação (ReceiverNotified) | ✅ | ligação 14 via rtc |
| 4c. Resposta do recebedor registrada (doca e previsão) | ❌ | previsão 'em 40 minutos', agente: A resposta do recebedor foi registrada com sucesso. A doca 4 libera em 40 minutos devido a um atraso na descarga. |
| 4d. Motorista ouve a resposta do recebedor (/speak) | ✅ |  |
| 4e. Recebedor 'não recebe hoje' aplica a regra da transportadora | ✅ | evento nao_recebe_hoje |
| 5. Chegada (GPS + rastreador) cria Task e inicia a estadia | ✅ |  |
| 5b. Sem divergência de GPS quando celular e rastreador concordam | ✅ |  |
| 5x. Agente pede a confirmação da chegada (GPS detectou) | ✅ |  |
| 5y. Chegada confirmada por voz (prova GPS + rastreador + voz) | ✅ | agente: Chegada registrada com sucesso. O CCO foi avisado e a estadia está contando. |
| 5z. Estadia calculada sobre a capacidade do veículo (24 t, carga 20 t) | ✅ |  |
| 5c. Check-in parcial: agente pergunta só o que faltou | ✅ | agente: Ótimo! Agora, quanto tempo de viagem você fez até aqui e teve algum problema durante o trajeto? |
| 5d. Check-in completo | ✅ | agente: O check-in foi registrado com sucesso: a viagem durou 3 horas e não houve problemas. |
| 5e. Ocorrência por voz e o agente se aprofunda (pergunta de acompanhamento) | ✅ | agente: Registrei a ocorrência de fila de caminhões na portaria. Agora, quantos caminhões tem na sua frente? |
| 5e2. Respostas do aprofundamento viram ocorrência detalhada para o CCO | ❌ | agente: A ocorrência foi registrada com sucesso. Agora, preciso saber: a portaria deu alguma previsão? / A portaria informou que a doca 4 libera em 40 minutos. |
| 5f. Pergunta sobre a NF responde com o documento | ✅ | agente: Pela NF-e 000.600.111, o peso é 20.000 kg (20 toneladas). |
| 5g. Pergunta de tempo parado usa o estado real | ✅ | agente: Você está parado há 0 minutos. |
| 6. Pedido da central: pergunta ao motorista e resposta estruturada | ✅ | agente: O número do lacre foi enviado à central. |
| 7. CCO sem resposta: 3 tentativas (push → painel → ligação) | ✅ | 3 notificações |
| 7b. Após 3 tentativas o agente liga para o recebedor | ✅ |  |
| 7c. Resposta do recebedor vai para a Task | ✅ | A doca 2 libera às 15h. |
| 7d. CCO assume a Task e o motorista é avisado | ✅ |  |
| 8. Descarga por voz encerra a estadia e a Task | ✅ | agente: A descarga foi confirmada. A carga foi descarregada e você ficou parado por 1 minuto. |
| 9. /events traz os 14 tipos do contrato (docs/arquitetura-avisai.md §7) | ✅ | todos presentes |
| 9b. KPIs calculados (/api/metrics) | ✅ | entregas 7, estadia devida 0.0, % avisados 57.1 |
| 9c. Ranking de recebedores inclui o recebedor da viagem | ✅ |  |
| 10. Celular × rastreador divergentes: evento não validado e alerta ao CCO | ✅ |  |
| 11. OCOREN: GET /rotas/{id}/ocoren devolve o arquivo (registro 000 com CNPJ e sequência) | ✅ | rota 1, parceiro 'Intelipost (OCOREN 5.0 · padrão)', 756 bytes |

As falas de texto passam pelo gateway do LLM; a sala e o agente são LiveKit. Não substitui o
teste com pessoas falando (qualidade do ASR, latência, barge-in).

## 3d está determinístico agora; 4c e 5e2 são duas ambiguidades diferentes do LLM, ainda abertas

Rodei a validação 4 vezes contra a produção (CloudFront) na mesma sessão, sempre com o LLM de
verdade:

| Rodada | 3d (atraso×fila) | 4c (resposta doca/previsão) | 5e (nova ocorrência fila) | 5e2 (fila detalhada) | Total |
|---|---|---|---|---|---|
| 1 | ✅ | ❌ | ✅ | ❌ | 32/34 |
| 2 | ✅ | ❌ | ❌ | ❌ | 31/34 |
| 3 | ✅ | ✅ | ❌ | ❌ | 32/34 |
| 4 (publicada acima) | ✅ | ❌ | ✅ | ❌ | 32/34 |

**3d: 4 de 4.** A regra determinística resolveu exatamente o que foi pedido — não é mais uma
classificação livre do LLM, é uma correção pelo estado da rota (`em_transito` → nunca é `fila`).

**4c e 5e2 continuam falhando a maior parte das rodadas, mas por motivos diferentes do 3d e
entre si** (confirmado direto no banco de produção, não só pela resposta falada):

- **4c** — o problema é a extração dos campos da ferramenta `registrar_resposta_recebedor`, não
  a classificação da ocorrência. Na rodada 2, a ligação ficou com `doca=None, previsao=None` no
  banco, mesmo o agente dizendo em voz "a doca 4 liberará em 40 minutos". Na rodada 4 (acima), o
  modelo preencheu `doca="doca 4"` (com o prefixo) em vez de só `"4"` — o teste expõe esse
  detalhe específico, mas o campo em si foi capturado.
- **5e2** — é a fusão já registrada na rodada anterior (abaixo, "Registro histórico"), só que
  pelo lado contrário: às vezes o modelo não chama `detalhar_ocorrencia` logo depois das
  respostas "Uns cinco caminhões na frente" / "Disseram que em meia hora", e só chama a
  ferramenta bem mais tarde, ao responder uma pergunta sem relação ("O lacre é 4471"),
  preenchendo os campos com texto genérico (`"quantos": "não sei", "previsao": "não foi
  informada"`) em vez das respostas reais já dadas — confirmado no evento
  `ocorrencia_detalhada` da rodada 4, que carrega `transcricao: "O lacre é 4471"`.

Nenhuma das duas é a mesma ambiguidade da 3d (fila×atraso pelo estado da rota) — são sobre
*quando* e *com quais argumentos* o LLM chama a ferramenta, em dois fluxos diferentes
(resposta do recebedor; aprofundamento de ocorrência). Dar o mesmo tipo de conserto
determinístico a elas exigiria decidir, a partir de texto livre, se uma fala é nova informação
ou um dado faltante de uma ocorrência já aberta — isso é exatamente a ambiguidade de prompt que
a sessão anterior já tinha decidido não "corrigir" sem medir contra mais casos. Por isso não
mudei `detalhar_ocorrencia`/`registrar_resposta_recebedor` nesta rodada; ficam registradas como
risco conhecido, com a evidência de banco acima, para quem decidir atacá-las depois.

# Registro histórico

# Validação ponta a ponta — 2026-11-27 22:53 (BRT)

Commit avaliado: `bdc14e5` (o `sha` que `GET /health` expõe desde esse commit). Stack local
(`make up`) com credenciais reais de LiveKit Cloud (LiveKit Agents 1.9, Gemini Live pela
LiveKit Inference) e do LLM configurado em `LLM_API_KEY`/`LLM_BASE_URL` — nenhuma chave de
teste/mock. **Primeira validação ponta a ponta publicada do caminho de voz no LiveKit**
(a anterior, abaixo, era da era Agora, pré-migração).

Api `http://localhost:8000` · LLM upstream: sim · recebedor: rtc · duração 128 s

**32/34 etapas OK**

| Etapa | Resultado | Detalhe |
|---|---|---|
| 1. CCO publica a rota e atribui ao motorista | ✅ | rota 8, motorista 7 |
| 1b. Login do motorista traz a rota atribuída (SSO mock) | ✅ |  |
| 2. Agente LiveKit despachado para a sala do motorista | ✅ | dispatch AD_8u5HatgDgrSy |
| 3. Geocerca da origem dispara a pergunta da retirada | ✅ |  |
| 3b. Retirada confirmada por voz | ✅ | agente: A retirada da carga foi confirmada e o relatório inicial foi registrado. Agora, preciso que você me diga: como está a carga coletada? |
| 3c. Relatório inicial completo por voz | ✅ | agente: O relatório inicial foi registrado com sucesso: caminhão está tudo certo e a carga coletada é de 20 paletes. 

Não há perguntas pendentes da central no momento. Você está a 25.9 km do destino, com previsão de che |
| 3d. Atraso na estrada: agente liga para o recebedor com o novo horário | ❌ | agente: Registrei a ocorrência de trânsito parado, com previsão de atraso de 40 minutos. 

Agora, preciso saber: quantos caminhões tem na sua frente? |
| 4. Aproximação detectada (ETA ≤ 15 min) e CCO avisado | ✅ | ETA 14.9 min |
| 4b. Agente liga para o recebedor na aproximação (ReceiverNotified) | ✅ | ligação 6 via rtc |
| 4c. Resposta do recebedor registrada (doca e previsão) | ✅ | previsão 'em 40 minutos', agente: A resposta do recebedor foi registrada: a doca 4 libera em 40 minutos. Essa informação já foi repassada ao motorista e ao CCO. 

Se precisar de mais alguma coisa, é só avisar! |
| 4d. Motorista ouve a resposta do recebedor (/speak) | ✅ |  |
| 4e. Recebedor 'não recebe hoje' aplica a regra da transportadora | ✅ | evento nao_recebe_hoje |
| 5. Chegada (GPS + rastreador) cria Task e inicia a estadia | ✅ |  |
| 5b. Sem divergência de GPS quando celular e rastreador concordam | ✅ |  |
| 5x. Agente pede a confirmação da chegada (GPS detectou) | ✅ |  |
| 5y. Chegada confirmada por voz (prova GPS + rastreador + voz) | ✅ | agente: Chegada registrada com sucesso. O CCO foi avisado e a estadia está contando. 

Agora, como está a carga? Quanto tempo de viagem você teve? Teve algum problema durante o trajeto? |
| 5z. Estadia calculada sobre a capacidade do veículo (24 t, carga 20 t) | ✅ |  |
| 5c. Check-in parcial: agente pergunta só o que faltou | ✅ | agente: Ótimo! Agora, quanto tempo de viagem você fez e teve algum problema durante o trajeto? |
| 5d. Check-in completo | ✅ | agente: Check-in registrado com sucesso: a carga está inteira, a viagem durou 3 horas e não houve problemas. 

Agora, quantos caminhões tem na sua frente? |
| 5e. Ocorrência por voz e o agente se aprofunda (pergunta de acompanhamento) | ✅ | agente: Vamos entender melhor a situação da fila. Quantos caminhões tem na sua frente? |
| 5e2. Respostas do aprofundamento viram ocorrência detalhada para o CCO | ❌ | agente: A ocorrência foi registrada com sucesso. Agora, preciso saber: a portaria deu alguma previsão? / Certo. |
| 5f. Pergunta sobre a NF responde com o documento | ✅ | agente: Pela NF-e 000.600.111, o peso é 20.000 kg (20 toneladas). |
| 5g. Pergunta de tempo parado usa o estado real | ✅ | agente: Você está parado há 2 horas e 50 minutos. |
| 6. Pedido da central: pergunta ao motorista e resposta estruturada | ✅ | agente: O número do lacre foi enviado à central. Além disso, a portaria deu uma previsão de meia hora para atendimento. 

Se precisar de mais alguma coisa, é só avisar! |
| 7. CCO sem resposta: 3 tentativas (push → painel → ligação) | ✅ | 3 notificações |
| 7b. Após 3 tentativas o agente liga para o recebedor | ✅ |  |
| 7c. Resposta do recebedor vai para a Task | ✅ | A doca 2 libera às 15h |
| 7d. CCO assume a Task e o motorista é avisado | ✅ |  |
| 8. Descarga por voz encerra a estadia e a Task | ✅ | agente: A descarga foi confirmada com sucesso. O tempo parado foi de 11 horas e 19 minutos, totalizando uma estadia de R$ 420,00. Se precisar de mais alguma coisa, é só avisar! |
| 9. /events traz os 14 tipos do contrato (docs/arquitetura-avisai.md §7) | ✅ | todos presentes |
| 9b. KPIs calculados (/api/metrics) | ✅ | entregas 5, estadia devida 1260.0, % avisados 40.0 |
| 9c. Ranking de recebedores inclui o recebedor da viagem | ✅ |  |
| 10. Celular × rastreador divergentes: evento não validado e alerta ao CCO | ✅ |  |
| 11. OCOREN: GET /rotas/{id}/ocoren devolve o arquivo (registro 000 com CNPJ e sequência) | ✅ | rota 1, parceiro 'Intelipost (OCOREN 5.0 · padrão)', 756 bytes |

As falas de texto passam pelo gateway do LLM; a sala e o agente são LiveKit. Não substitui o teste com pessoas falando (qualidade do ASR, latência, barge-in).

## A falha: classificação de ocorrência pelo LLM de verdade (não um bug de código)

A etapa 3d falhou nesta execução porque o modelo classificou a fala "Vou atrasar uns 40
minutos, trânsito parado" como ocorrência `fila` (confirmado no log: `[ocorrencia] rota=N
Ocorrência (fila): Trânsito parado, previsão de atraso de 40 minutos.`) em vez de `atraso` —
por isso nenhum evento com `motivo: atraso` existe pra disparar a ligação ao recebedor que a
etapa espera. A etapa 5e2 (fila detalhada) tem o inverso: ao perguntar sobre a fila de
verdade mais adiante na conversa, o modelo às vezes funde a resposta com o acompanhamento do
atraso já aberto antes, e não persiste uma `ocorrencia_detalhada` separada.

Rodei a validação três vezes nesta sessão, sempre contra o LLM de verdade (sem contingência):

| Rodada | `LIGAR_RECEBEDOR_NA_APROXIMACAO` | Resultado | Etapas que falharam |
|---|---|---|---|
| 1 | `false` (padrão do `.env.example`) | 28/31 | 3d, 4b (bloco 4c-4e nem roda sem a ligação automática), 9 |
| 2 | `true` | 32/34 | 5e, 5e2 |
| 3 (publicada acima) | `true` | 32/34 | 3d, 5e2 |

Com a contingência (texto fixo, sem LLM real) essas etapas nunca falham, porque a resposta é
sempre a mesma string — é por isso que a evidência de 2026-11-22 (abaixo) deu 33/33. Com o
LLM de verdade, a fronteira entre `atraso` (trânsito, problema mecânico) e `fila`
(caminhões na porta do recebedor) depende de uma classificação livre do modelo, e as duas
falas de teste ("trânsito parado" e "fila de caminhões") são ambíguas o bastante pra cruzar
essa fronteira em cerca de 1 a cada 3 rodadas. O resto do fluxo (voz, LiveKit, estadia,
escalonamento, chamada ao recebedor, OCOREN) foi estável nas três rodadas. Não tentei
"corrigir" isso ajustando o prompt/ferramentas sem medir contra mais casos — seria trocar uma
ambiguidade conhecida por outra não testada.

# Registro histórico
