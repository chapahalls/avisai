# Validação ponta a ponta — 2026-11-22 05:59 (BRT)

Api `http://localhost:8000` · LLM upstream: não (contingência) · recebedor: rtc · duração 82 s

**28/28 etapas OK**

| Etapa | Resultado | Detalhe |
|---|---|---|
| 1. CCO publica a rota e atribui ao motorista | ✅ | rota 10, motorista 8 |
| 1b. Login do motorista traz a rota atribuída (SSO mock) | ✅ |  |
| 2. Agente ConvoAI entra no canal do motorista (/join na Agora) | ✅ | agent_id A46AJ33KK24FL98KL34FR24WN46NK84R |
| 3. Geocerca da origem dispara a pergunta da retirada | ✅ |  |
| 3b. Retirada confirmada por voz | ✅ | agente: Retirada confirmada. Me conta: como tá o caminhão e qual a carga que você pegou? |
| 3c. Relatório inicial completo por voz | ✅ | agente: Relatório inicial completo. Boa viagem! |
| 4. Aproximação detectada (ETA ≤ 15 min) e CCO avisado | ✅ | ETA 14.9 min |
| 4b. Agente liga para o recebedor na aproximação (ReceiverNotified) | ✅ | ligação 10 via rtc |
| 4c. Resposta do recebedor registrada (doca e previsão) | ✅ | previsão 'em 40 minutos', agente: Anotado: doca 4, em 40 minutos. Vou passar pro motorista agora. Obrigada! |
| 4d. Motorista ouve a resposta do recebedor (/speak) | ✅ |  |
| 4e. Recebedor 'não recebe hoje' aplica a regra da transportadora | ✅ | evento nao_recebe_hoje |
| 5. Chegada (GPS + rastreador) cria Task e inicia a estadia | ✅ |  |
| 5b. Sem divergência de GPS quando celular e rastreador concordam | ✅ |  |
| 5c. Check-in parcial: agente pergunta só o que faltou | ✅ | agente: Anotado. E quanto tempo de viagem e se teve algum problema? |
| 5d. Check-in completo | ✅ | agente: Check-in completo, valeu! |
| 5e. Ocorrência por voz | ✅ | agente: Registrei a ocorrência de fila e o CCO já tá vendo. |
| 5f. Pergunta sobre a NF responde com o documento | ✅ | agente: Pela NF-e 000.600.111, o peso é 20.000 kg (20 toneladas). |
| 5g. Pergunta de tempo parado usa o estado real | ✅ | agente: Você tá parado há 0 minutos. Faltam 4 horas e 59 minutos de franquia e a estadia acumulada tá em R$ 0,00. |
| 6. Pedido da central: pergunta ao motorista e resposta estruturada | ✅ | agente: Fechado, passei pra central. |
| 7. CCO sem resposta: 3 tentativas (push → painel → ligação) | ✅ | 3 notificações |
| 7b. Após 3 tentativas o agente liga para o recebedor | ✅ |  |
| 7c. Resposta do recebedor vai para a Task | ✅ | A doca 2 libera às 15h |
| 7d. CCO assume a Task e o motorista é avisado | ✅ |  |
| 8. Descarga por voz encerra a estadia e a Task | ✅ | agente: Descarga registrada e estadia encerrada. Boa viagem, parceiro! |
| 9. /events traz os 14 tipos do contrato (docs/arquitetura-avisai.md §7) | ✅ | todos presentes |
| 9b. KPIs calculados (/api/metrics) | ✅ | entregas 7, estadia devida 0.0, % avisados 57.1 |
| 9c. Ranking de recebedores inclui o recebedor da viagem | ✅ |  |
| 10. Celular × rastreador divergentes: evento não validado e alerta ao CCO | ✅ |  |

Falas simuladas pelo mesmo endpoint que a Agora chama; /join, /speak e /leave reais na Agora. Não substitui o teste com pessoas falando (qualidade do ASR, latência, barge-in).
