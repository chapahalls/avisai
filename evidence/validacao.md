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
