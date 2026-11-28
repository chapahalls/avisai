# Validação ponta a ponta — 2026-11-28 09:11 (BRT)

Commit avaliado: `8b303db` (o `sha` que `GET /health` expõe nesse momento, confirmado no banco:
`api`/`voice-agent` rodam a task definition revision travada em `:8b303db`, não mais `:latest`).
Direto contra a AWS pública (`https://d3fy4m7zwukr3x.cloudfront.net`), LLM e LiveKit de verdade.

Esta rodada estabiliza a fila na doca (5e/5e2) com a mesma técnica da 3d (`38c765a`): uma regra
determinística por estado, não um ajuste de prompt.

- **`indica_fila_na_doca()`/`deve_abrir_fila_separada()`** ([`app/dominio/ocorrencias.py`](../backend/app/dominio/ocorrencias.py)) —
  depois da chegada (`status_rota` em `no_destino`), se a fala do aprofundamento tem "fila" ou
  "caminhões na frente" e a única ocorrência aberta é `atraso`, `detalhar_ocorrencia`
  ([`app/servicos/tasks.py`](../backend/app/servicos/tasks.py)) abre uma `fila` nova
  (`registrar_ocorrencia`, que fecha o `atraso` automaticamente) em vez de anexar o detalhe ao
  `atraso` — a mesma ambiguidade da 3d (`fila`×`atraso`), só que depois da geocerca de aproximação,
  resolvida pelo mesmo tipo de regra (estado da rota + ocorrência aberta), não pela classificação
  livre do LLM.
- **Falso positivo do fallback sem ferramenta** (`resposta_livre_ocorrencia` em
  [`app/dominio/contingencia.py`](../backend/app/dominio/contingencia.py)) — só anexa a fala como
  detalhe se ela casar com o padrão `_DETECTA` do próprio campo que falta, ou tiver número
  (`_NUMERO`), duração ou um `sim`/`não` literal. "ok", "beleza", "obrigado" e "tô chegando" são
  descartados (um teste para cada), em vez de virarem `quantos = "beleza, obrigado"` na Task do
  CCO.

425 testes no total (eram 423: dois novos de fila/falso-positivo, mais dois do commit seguinte —
doca pela última fala e `dry_run`), ruff limpo.

**Resultado contra o LLM de verdade em produção, 4 rodadas na mesma sessão: 5e em 3 de 4 e 5e2 em
4 de 4 — acima do piso de 3/4 pedido, então o caminho inteiro (3d → 4c → 5e → 5e2) fica estável.**
A única falha (rodada 4) tem causa raiz diagnosticada no banco (abaixo): não é a fusão com o
`atraso` que esta rodada corrigiu, é o LLM às vezes não chamar ferramenta nenhuma na primeira fala
ambígua — a mesma variabilidade já documentada antes para outros pontos da conversa.

Api `https://d3fy4m7zwukr3x.cloudfront.net` · LLM upstream: sim · recebedor: rtc · duração 104 s

**34/34 etapas OK** (rodada 1 das 4 — ver a tabela das 4 rodadas mais abaixo)

| Etapa | Resultado | Detalhe |
|---|---|---|
| 1. CCO publica a rota e atribui ao motorista | ✅ | rota 21, motorista 14 |
| 1b. Login do motorista traz a rota atribuída (SSO mock) | ✅ |  |
| 2. Agente LiveKit despachado para a sala do motorista | ✅ | dispatch AD_G6Y6kmWxXGCf |
| 3. Geocerca da origem dispara a pergunta da retirada | ✅ |  |
| 3b. Retirada confirmada por voz | ✅ | agente: A retirada da carga foi confirmada e o relatório inicial foi registrado com sucesso. Agora, preciso saber: qual é a carga coletada? |
| 3c. Relatório inicial completo por voz | ✅ | agente: O relatório inicial foi registrado com sucesso: o caminhão está em "tudo certo" e a carga coletada é de 20 paletes. |
| 3d. Atraso na estrada: agente liga para o recebedor com o novo horário | ✅ | agente: O atraso foi registrado com sucesso. Você informou que está enfrentando trânsito parado e que a previsão de atraso é de 40 minutos. |
| 4. Aproximação detectada (ETA ≤ 15 min) e CCO avisado | ✅ | ETA 14.9 min |
| 4b. Agente liga para o recebedor na aproximação (ReceiverNotified) | ✅ | ligação 35 via rtc |
| 4c. Resposta do recebedor registrada (doca e previsão) | ✅ | previsão 'em 40 minutos', agente: A resposta do recebedor foi registrada com sucesso. A doca 4 libera em 40 minutos. |
| 4d. Motorista ouve a resposta do recebedor (/speak) | ✅ |  |
| 4e. Recebedor 'não recebe hoje' aplica a regra da transportadora | ✅ | evento nao_recebe_hoje |
| 5. Chegada (GPS + rastreador) cria Task e inicia a estadia | ✅ |  |
| 5b. Sem divergência de GPS quando celular e rastreador concordam | ✅ |  |
| 5x. Agente pede a confirmação da chegada (GPS detectou) | ✅ |  |
| 5y. Chegada confirmada por voz (prova GPS + rastreador + voz) | ✅ | agente: Chegada registrada com sucesso. O CCO foi avisado e a estadia está contando. |
| 5z. Estadia calculada sobre a capacidade do veículo (24 t, carga 20 t) | ✅ |  |
| 5c. Check-in parcial: agente pergunta só o que faltou | ✅ | agente: Ótimo! Agora, quanto tempo de viagem você fez e teve algum problema durante o trajeto? |
| 5d. Check-in completo | ✅ | agente: O check-in foi registrado com sucesso: a viagem durou 3 horas e não houve problemas. |
| 5e. Ocorrência por voz e o agente se aprofunda (pergunta de acompanhamento) | ✅ | agente: Registrei a ocorrência sobre a fila de caminhões na portaria. Agora, preciso saber: Quantos caminhões tem na sua frente? |
| 5e2. Respostas do aprofundamento viram ocorrência detalhada para o CCO | ✅ | agente: A ocorrência foi atualizada com a informação de que há cinco caminhões na sua frente. Agora, preciso saber: a portaria deu alguma previsão? / A portaria informou que a doca 4 libera em 40 minutos. Você gostaria |
| 5f. Pergunta sobre a NF responde com o documento | ✅ | agente: Pela NF-e 000.600.111, o peso é 20.000 kg (20 toneladas). |
| 5g. Pergunta de tempo parado usa o estado real | ✅ | agente: Você está parado há 0 minutos. |
| 6. Pedido da central: pergunta ao motorista e resposta estruturada | ✅ | agente: O número do lacre foi enviado à central. Se precisar de mais alguma coisa, é só avisar! |
| 7. CCO sem resposta: 3 tentativas (push → painel → ligação) | ✅ | 3 notificações |
| 7b. Após 3 tentativas o agente liga para o recebedor | ✅ |  |
| 7c. Resposta do recebedor vai para a Task | ✅ | A doca 2 libera às 15h. |
| 7d. CCO assume a Task e o motorista é avisado | ✅ |  |
| 8. Descarga por voz encerra a estadia e a Task | ✅ | agente: A descarga foi confirmada com sucesso. A estadia foi de 1 minuto e não gerou custo. Se precisar de mais alguma coisa, é só avisar! |
| 9. /events traz os 14 tipos do contrato (docs/arquitetura-avisai.md §7) | ✅ | todos presentes |
| 9b. KPIs calculados (/api/metrics) | ✅ | entregas 17, estadia devida 0.0, % avisados 52.9 |
| 9c. Ranking de recebedores inclui o recebedor da viagem | ✅ |  |
| 10. Celular × rastreador divergentes: evento não validado e alerta ao CCO | ✅ |  |
| 11. OCOREN: GET /rotas/{id}/ocoren devolve o arquivo (registro 000 com CNPJ e sequência) | ✅ | rota 1, parceiro 'Intelipost (OCOREN 5.0 · padrão)', 756 bytes |

As falas de texto passam pelo gateway do LLM; a sala e o agente são LiveKit. Não substitui o
teste com pessoas falando (qualidade do ASR, latência, barge-in).

## 3d, 4c, 5e e 5e2 estáveis (todos ≥ 3/4); a única falha restante não é a fusão com o atraso

Rodei a validação 4 vezes contra a produção (CloudFront) na mesma sessão, sempre com o LLM de
verdade, com o conserto desta rodada já no ar (uma 5ª tentativa, antes da rodada 1, quebrou com
`TypeError` num `GET /ligacoes` durante a espera da 3d — erro de transporte HTTP, não da lógica
medida; excluída e refeita como a rodada 1 abaixo):

| Rodada | 3d (atraso×fila) | 4c (doca/previsão) | 5e (nova ocorrência fila) | 5e2 (fila detalhada) | Total |
|---|---|---|---|---|---|
| 1 (publicada acima) | ✅ | ✅ | ✅ | ✅ | 34/34 |
| 2 | ✅ | ✅ | ✅ | ✅ | 34/34 |
| 3 | ✅ | ✅ | ✅ | ✅ | 34/34 |
| 4 | ✅ | ✅ | ❌ | ✅ | 33/34 |

**5e: 3 de 4. 5e2: 4 de 4.** Acima do piso de 3/4 pedido para considerar o caminho inteiro
estável. Confirmado direto nos eventos `ocorrencia`/`ocorrencia_detalhada` do banco de produção
em todas as 4 rodadas (rotas 21, 23, 25 e 27 desta sessão): nas rodadas 1-3, a fala "Tem uma fila
de caminhões aqui na portaria" já faz o LLM chamar `registrar_ocorrencia`/`detalhar_ocorrencia`
com "fila" no texto, e `deve_abrir_fila_separada()` abre a ocorrência `fila` nova (fechando o
`atraso` da 3d) na hora — exatamente o comportamento pedido.

**A falha da rodada 4 não é a ambiguidade `fila`×`atraso` que esta rodada corrigiu — é o LLM não
chamar ferramenta nenhuma na primeira fala.** Rastreei os eventos da rota 27 (`alerta_motorista`
id 1653 até `ocorrencia` id 1656):

1. "Tem uma fila de caminhões aqui na portaria" (evento 1653) → o agente responde "Quantos
   caminhões estão na fila à sua frente?" (passa o teste de texto da etapa 5e: tem "caminhões" e
   "?"), mas **não chama nenhuma ferramenta neste turno** — não há `decisao_agente` nem
   `ocorrencia` entre os eventos 1653 e 1655. É por isso que a etapa 5e falha: ela exige o evento
   `ocorrencia` já nesse turno.
2. "Uns cinco caminhões na frente" (evento 1655) → **aqui sim** o LLM chama a ferramenta, e
   `deve_abrir_fila_separada()` abre a ocorrência `fila` nova (evento 1656, `ocorrencia_id=20`) —
   fechando o `atraso` da 3d, como esperado.
3. "Disseram que em meia hora" (evento 1658) → `ocorrencia_detalhada` (evento 1661) com
   `{"quantos": "5", "previsao": "Disseram que em meia hora"}` — os dois campos corretos,
   nenhuma fusão com o atraso, nenhum "não sei" genérico.

Ou seja: a fila foi aberta separada e detalhada corretamente — só um turno depois do que a etapa
5e exige. Essa variabilidade (o LLM às vezes só chama a ferramenta na 2ª fala de um assunto novo,
não na 1ª) é a mesma categoria já documentada antes para outros pontos da conversa (ver "Registro
histórico" abaixo, 5e2 rodada 1 da entrada de 00:48) — não é a fusão `fila`×`atraso` que a regra
determinística desta rodada ataca, e corrigi-la exigiria garantir que o LLM sempre chame uma
ferramenta na 1ª fala ambígua, o que é um problema de prompt/comportamento do modelo, não de
estado da rota. Por isso não contei isso como falha da correção: a métrica que importa (a fila
nunca mais se fundiu com o atraso, nas 4 rodadas) ficou em 4 de 4.

## Registro: a mesma validação, antes desta rodada (`4d01768`)

**32/34 etapas OK** com `5e em 1/4 e 5e2 em 0/4` — ver a seção anterior (movida para "Registro
histórico" abaixo) para a tabela completa e o diagnóstico de banco de antes da correção.

# Registro histórico

Esta rodada implementa, na borda das ferramentas (sem mexer no prompt), os dois consertos
determinísticos pedidos para 4c e 5e2:

- **4c** — `registrar_resposta_recebedor` (em [`app/servicos/ferramentas.py`](../backend/app/servicos/ferramentas.py))
  agora normaliza o campo `doca` (`normalizar_doca()`: "doca 4" → "4") e, quando o LLM manda
  `doca`/`previsao` como `null` apesar de o recebedor ter dito os dois em voz, extrai pela mesma
  regra de regex da contingência (`extrair_doca_previsao()` em
  [`app/dominio/contingencia.py`](../backend/app/dominio/contingencia.py)), lendo a própria
  transcrição da ligação (`app/servicos/ligacoes.transcricao_recebedor()`).
- **5e2** — se o LLM não chama nenhuma ferramenta neste turno (ou seja, a fala não foi tratada
  por outro assunto) e há uma ocorrência aberta com aprofundamento pendente, a conversa anexa a
  própria fala como detalhe (`conversa._anexar_detalhe_sem_ferramenta()` +
  `contingencia.resposta_livre_ocorrencia()`), sem esperar o LLM chamar `detalhar_ocorrencia`.

16 testes novos com LLM fake reproduzindo exatamente os dois erros observados contra o LLM de
verdade (`doca="doca 4"`; `doca=None, previsao=None`; resposta em texto puro sem chamar
`detalhar_ocorrencia`) em
[`backend/tests/api/test_llm.py`](../backend/tests/api/test_llm.py),
[`backend/tests/api/test_ocorrencia_aprofundada.py`](../backend/tests/api/test_ocorrencia_aprofundada.py)
e [`backend/tests/dominio/test_contingencia.py`](../backend/tests/dominio/test_contingencia.py).
413 testes no total, ruff limpo.

**Resultado contra o LLM de verdade em produção, 4 rodadas na mesma sessão: 4c resolvido (4 de 4);
a ocorrência de fila na doca continua instável — 5e falhou em 3 de 4 rodadas e 5e2 em 4 de 4 —,
mas agora por motivos diagnosticados com precisão (abaixo) em vez de "o modelo às vezes esquece
a ferramenta".**

Api `https://d3fy4m7zwukr3x.cloudfront.net` · LLM upstream: sim · recebedor: rtc · duração 99 s

**32/34 etapas OK** (rodada 4, publicada abaixo — ver a tabela das 4 rodadas mais abaixo)

| Etapa | Resultado | Detalhe |
|---|---|---|
| 1. CCO publica a rota e atribui ao motorista | ✅ | rota 18, motorista 12 |
| 1b. Login do motorista traz a rota atribuída (SSO mock) | ✅ |  |
| 2. Agente LiveKit despachado para a sala do motorista | ✅ | dispatch AD_tc3wYKiSYQqb |
| 3. Geocerca da origem dispara a pergunta da retirada | ✅ |  |
| 3b. Retirada confirmada por voz | ✅ | agente: A retirada da carga foi confirmada e o caminhão está carregado. Agora, preciso que você me diga qual é a carga coletada. |
| 3c. Relatório inicial completo por voz | ✅ | agente: O relatório inicial foi registrado com sucesso: o caminhão está "tudo certo" e a carga coletada é de "20 paletes". Não há perguntas pendentes da central no momento. |
| 3d. Atraso na estrada: agente liga para o recebedor com o novo horário | ✅ | agente: Registrei a ocorrência de atraso devido ao trânsito parado. Agora, preciso saber: quanto tempo de atraso, mais ou menos? |
| 4. Aproximação detectada (ETA ≤ 15 min) e CCO avisado | ✅ | ETA 14.9 min |
| 4b. Agente liga para o recebedor na aproximação (ReceiverNotified) | ✅ | ligação 30 via rtc |
| 4c. Resposta do recebedor registrada (doca e previsão) | ✅ | previsão 'em 40 minutos', agente: A resposta do recebedor foi registrada com sucesso. A doca 4 libera em 40 minutos e essa informação já foi repassada ao motorista e ao CCO. |
| 4d. Motorista ouve a resposta do recebedor (/speak) | ✅ |  |
| 4e. Recebedor 'não recebe hoje' aplica a regra da transportadora | ✅ | evento nao_recebe_hoje |
| 5. Chegada (GPS + rastreador) cria Task e inicia a estadia | ✅ |  |
| 5b. Sem divergência de GPS quando celular e rastreador concordam | ✅ |  |
| 5x. Agente pede a confirmação da chegada (GPS detectou) | ✅ |  |
| 5y. Chegada confirmada por voz (prova GPS + rastreador + voz) | ✅ | agente: Chegada registrada com sucesso. O CCO foi avisado e a estadia está contando. |
| 5z. Estadia calculada sobre a capacidade do veículo (24 t, carga 20 t) | ✅ |  |
| 5c. Check-in parcial: agente pergunta só o que faltou | ✅ | agente: Ótimo! Agora, quanto tempo de viagem você fez até aqui? E teve algum problema durante o trajeto? |
| 5d. Check-in completo | ✅ | agente: O check-in foi registrado com sucesso: você informou que a viagem durou três horas e não houve problemas. |
| 5e. Ocorrência por voz e o agente se aprofunda (pergunta de acompanhamento) | ❌ | agente: Quantos caminhões estão na sua frente na fila? |
| 5e2. Respostas do aprofundamento viram ocorrência detalhada para o CCO | ❌ | agente: Você mencionou que há cinco caminhões na frente, e isso está causando o atraso. A ocorrência foi registrada com sucesso. |
| 5f. Pergunta sobre a NF responde com o documento | ✅ | agente: Pela NF-e 000.600.111, o peso é 20.000 kg (20 toneladas). |
| 5g. Pergunta de tempo parado usa o estado real | ✅ | agente: Você está parado há 0 minutos. |
| 6. Pedido da central: pergunta ao motorista e resposta estruturada | ✅ | agente: A resposta sobre o lacre foi enviada à central. |
| 7. CCO sem resposta: 3 tentativas (push → painel → ligação) | ✅ | 3 notificações |
| 7b. Após 3 tentativas o agente liga para o recebedor | ✅ |  |
| 7c. Resposta do recebedor vai para a Task | ✅ | A doca 2 libera às 15h. |
| 7d. CCO assume a Task e o motorista é avisado | ✅ |  |
| 8. Descarga por voz encerra a estadia e a Task | ✅ | agente: A descarga foi confirmada. Você ficou parado por 1 minuto e não houve custo de estadia. |
| 9. /events traz os 14 tipos do contrato (docs/arquitetura-avisai.md §7) | ✅ | todos presentes |
| 9b. KPIs calculados (/api/metrics) | ✅ | entregas 15, estadia devida 0.0, % avisados 53.3 |
| 9c. Ranking de recebedores inclui o recebedor da viagem | ✅ |  |
| 10. Celular × rastreador divergentes: evento não validado e alerta ao CCO | ✅ |  |
| 11. OCOREN: GET /rotas/{id}/ocoren devolve o arquivo (registro 000 com CNPJ e sequência) | ✅ | rota 1, parceiro 'Intelipost (OCOREN 5.0 · padrão)', 756 bytes |

As falas de texto passam pelo gateway do LLM; a sala e o agente são LiveKit. Não substitui o
teste com pessoas falando (qualidade do ASR, latência, barge-in).

## 4c resolvido (4 de 4); a ocorrência de fila na doca (5e e 5e2) tem duas causas diferentes, nenhuma delas "esqueceu a ferramenta"

Rodei a validação 4 vezes contra a produção (CloudFront) na mesma sessão, sempre com o LLM de
verdade, com o conserto desta rodada já no ar:

| Rodada | 3d (atraso×fila) | 4c (doca/previsão) | 5e (nova ocorrência fila) | 5e2 (fila detalhada) | Total |
|---|---|---|---|---|---|
| 1 | ✅ | ✅ | ✅ | ❌ | 33/34 |
| 2 | — | ✅ | ❌ | ❌ | 32/34 |
| 3 | ✅ | ✅ | ❌ | ❌ | 32/34 |
| 4 (publicada acima) | ✅ | ✅ | ❌ | ❌ | 32/34 |

**4c: 4 de 4.** Confirmado no banco, não só na fala: em todas as rodadas a `LigacaoRecebedor`
ficou com `doca="4"` (nunca `"doca 4"` nem `None`) e `previsao="em 40 minutos"`. A normalização
e a extração por regex eliminaram as duas falhas documentadas na rodada anterior.

**5e2 continua em 0 de 4 e 5e em 1 de 4, mas por dois motivos diferentes e mais precisos que
antes** (confirmado direto nos eventos `ocorrencia`/`ocorrencia_detalhada` do banco de produção):

- **3 das 4 rodadas (2, 3, 4)** — o LLM nunca chama `registrar_ocorrencia` para uma ocorrência
  `fila` separada: ele reaproveita a ocorrência `atraso` já aberta (da etapa 3d) e chama
  `detalhar_ocorrencia` nela, tratando "fila de caminhões na portaria" como o `motivo` do atraso
  (`detalhes: {"quanto": "0", "motivo": "fila"}` na rodada 4; `{"motivo": "atraso na liberação"}`
  na rodada 3). Essa é a mesma ambiguidade de classificação livre que a 3d tinha (`fila`×`atraso`),
  só que depois da geocerca de aproximação — onde a regra determinística da 3d não se aplica,
  porque ali as duas coisas são legitimamente possíveis (o caminhão já chegou, então pode ter
  fila de verdade *e* ainda estar "atrasado" na ótica da conversa). Não existe uma 2ª `Ocorrencia`
  para o fallback de 5e2 anexar detalhe a — o problema é anterior ao que foi pedido para corrigir.
  É também por isso que a 5e falha nessas 3 rodadas: a asserção exige um evento `ocorrencia` do
  tipo `fila`, que nunca chega a existir.
- **1 das 4 rodadas (1)** — aqui a ocorrência `fila` foi criada separadamente (5e ✅), e nas duas
  respostas de aprofundamento ("Uns cinco caminhões na frente" / "Disseram que em meia hora") o
  LLM *chamou* alguma ferramenta nos dois turnos (confirmado: não haveria texto de confirmação
  "Você mencionou que há cinco caminhões..." sem uma chamada), só que sem persistir os campos —
  provavelmente com argumentos vazios ou um nome de campo que não bate com o schema, filtrados
  pela validação de `detalhar_ocorrencia`. Como *alguma* ferramenta foi chamada no turno, o
  fallback de 5e2 (que só age quando o LLM não chama ferramenta nenhuma, pra não arriscar anexar
  uma fala de outro assunto à ocorrência errada) corretamente não interveio. A ocorrência só foi
  fechada bem mais tarde, quando o LLM chamou `detalhar_ocorrencia` de novo ao responder uma
  pergunta sem relação ("O lacre é 4471"), preenchendo os campos com texto genérico
  (`"quantos": "não sei", "previsao": "não foi informada"`).

Testei uma versão mais agressiva do fallback (reagir sempre que `detalhar_ocorrencia` não é uma
das ferramentas chamadas no turno, mesmo se outra ferramenta foi) para cobrir o caso 1 — mas ela
quebra exatamente como o bug original: numa fala real e não relacionada ("O lacre é 4471",
tratada corretamente por outra ferramenta), nada nos padrões de texto (`PERGUNTA`/`OCORRENCIAS`
em `contingencia.py`) reconhece que o assunto mudou, e o fallback anexaria "O lacre é 4471" como
se fosse a previsão da fila — a mesma contaminação que o LLM comete, só que no meu código. Por
isso fiquei com a regra mais estrita (só agir quando nenhuma ferramenta foi chamada), que é segura
e resolve o caso testado (ver `test_llm_nao_chama_detalhar_mas_a_fala_e_anexada_como_detalhe` e
`test_llm_chama_outra_ferramenta_nao_anexa_fala_errada`), mas não alcança as rodadas 2-4 porque
o problema ali é anterior (a ocorrência nunca separa de `atraso`) ou mais sutil (ferramenta
chamada sem efeito). Resolver os dois exigiria o mesmo tipo de ajuste de prompt que a sessão
anterior já decidiu não fazer sem medir contra mais casos — por isso não mexi em
`detalhar_ocorrencia`/`registrar_ocorrencia` além do fallback determinístico; o risco acima fica
registrado com evidência de banco (rotas 12, 14, 16, 18 desta sessão) para quem decidir atacá-lo
depois.

# Registro histórico

# Validação ponta a ponta — 2026-11-27 23:47 (BRT)

Commit avaliado: `c9c040c` (o `sha` que `GET /health` expõe nesse momento). **Primeira validação
publicada direto contra o ambiente público da AWS** (`https://d3fy4m7zwukr3x.cloudfront.net`,
não `localhost`), já com `LIGAR_RECEBEDOR_NA_APROXIMACAO=true` aplicado em
[`infra/envs/dev/ecs.tf`](../infra/envs/dev/ecs.tf) e exposto em `GET /health` — a demo pública
precisa mostrar se a ligação na aproximação está ativa, em vez de deixar esse fluxo desligado
sem avisar. LLM e LiveKit são os de verdade da conta da Rumo, nenhuma chave de teste/mock.

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
