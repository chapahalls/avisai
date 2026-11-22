# Matriz de rastreabilidade: ideias × backend AvisAI

- **Gerado em:** 2026-11-22 05:47 (America/Sao_Paulo)
- **Commit verificado:** `ccb36e7 docs: LICENSE MIT, versão entregue e seções Dependências/Como rodar no README` (tag `v1.0-entrega`)
- **Fontes dos requisitos** (repo de ideias, `origin/main`): `ideas/parceiro-de-estrada/contexto-produto.md`, `ideas/parceiro-de-estrada/ajustes-pos-mentoria.md`, `docs/arquitetura-avisai.md`.
- **Método:** cada item foi conferido no código (`backend/app`, `scripts/`, `clients/`) e no teste que o exercita (`backend/tests`). O README não foi tomado como prova. A suíte foi rodada neste commit: `docker compose run --rm test pytest -q` deu **150 passed**.
- **Escopo:** só o backend. Telas, mapas, outbox SQLite do celular, i18n e design system estão marcados como 🖥️.

## Resumo

| Status | Significado | Linhas |
|---|---|---|
| ✅ | implementado e coberto por teste | 136 |
| 🟡 | implementado, sem teste que confira o comportamento | 13 |
| ⚠️ | parcial (falta parte do que o documento pede) | 20 |
| ⏸️ | fora por decisão do time | 18 |
| 🖥️ | front, fora do backend | 10 |
| ❌ | faltando | 2 |
| **Total** | | **199** |

A contagem é feita por linha. Alguns requisitos aparecem em mais de um documento e, por isso, em mais de uma tabela. Itens que não são software (preço, ROI, modelo de negócio, entrevistas, slides) ficaram fora da matriz.

---

## 1. `contexto-produto.md`

### §1 Atores e §2 Integração com o painel da central

| # | Requisito (resumo + seção de origem) | Status | Onde (arquivo:função ou rota) | Teste (arquivo::teste) | Observação |
|---|---|---|---|---|---|
| CP-1 | Agente de voz no meio: pergunta, valida, registra, escala e responde (§1) | ✅ | `servicos/conversa.py:responder` + `servicos/ferramentas.py:REGISTRO` | `tests/api/test_llm.py::test_estado_vivo_vai_para_o_llm_sem_campos_da_agora` | Expõe 9 ferramentas (8 para o motorista, 1 para o recebedor). O estado vivo da rota vai como mensagem de sistema. |
| CP-2.1 | Empresa cadastra a rota: origem, destino e trajeto (§2.1) | ✅ | `POST /rotas` → `servicos/publicacao.py:publicar` | `tests/api/test_publicacao_rota.py::test_cco_publica_rota_sem_motorista` | O trajeto é sempre gerado em linha reta (`seed.trajeto`), sem trajeto informado. `aproximacao_min` e os raios não entram no `POST`. |
| CP-2.2 | Motorista responsável pela rota (§2.2) | ✅ | `POST /rotas/{id}/atribuir` → `publicacao.atribuir`; `POST /motoristas` | `tests/api/test_publicacao_rota.py::test_atribuir_motorista_gera_route_assigned` | Gera `RouteAssigned`. |
| CP-2.3 | Break points opcionais na rota (§2.3) | ⏸️ | — (não há modelo `BreakPoint`) | — | Fazem parte dos reportes periódicos, que ficaram fora por decisão (segurança com o caminhão andando). |
| CP-2.4 | Intervalos de atualização a cada X tempo (§2.4) | ⏸️ | — | — | Reporte periódico fora por decisão. |
| CP-2.5 | Campos obrigatórios por reporte, configuráveis no painel (§2.5) | ⚠️ | `servicos/reportes.py:CAMPOS` (dict fixo) | `tests/api/test_fluxos_viagem.py::test_checkin_incompleto_pede_so_o_que_faltou` | Os campos estão fixos no código (inicial: `estado_caminhao`, `carga`; check-in: `status_carga`, `tempo_viagem`, `problemas`). Não existe `RegraReporte` nem rota para configurar. |
| CP-2.6 | Documentos da entrega: NF, CT-e, MDF-e, ordem de coleta (§2.6) | ⏸️ | `dominio/documentos.py:da_rota`; `GET /api/documents` | `tests/dominio/test_documentos.py::test_documentos_da_rota_tem_nfe_e_cte` | Por decisão, o upload real de documentos fica fora. O mock gera NF-e e CT-e a partir da rota, sem MDF-e nem ordem de coleta. |

### §3.1 Início da viagem e §3.1.1 Dupla prova por GPS

| # | Requisito (resumo + seção de origem) | Status | Onde (arquivo:função ou rota) | Teste (arquivo::teste) | Observação |
|---|---|---|---|---|---|
| CP-3.1a | App recebe a rota da central (§3.1) | ✅ | `publicacao.atribuir` + `_avisar_motorista`; `WS /ws?motorista_id=`; `GET /api/route?driverId=` | `tests/api/test_publicacao_rota.py::test_ws_do_motorista_recebe_a_atribuicao`, `::test_motorista_com_agente_aberto_ouve_a_rota_nova` | Com o agente aberto, o motorista ouve a rota nova por voz. |
| CP-3.1b | Relatório inicial por voz: caminhão, carga, posição, destino (§3.1) | ✅ | `ferramentas._relatorio_inicial` → `reportes.registrar(tipo="inicial")`, aberto por `tasks.confirmar_retirada` | `tests/api/test_fluxos_viagem.py::test_relatorio_inicial_por_voz`; `tests/dominio/test_contingencia.py::test_relatorio_inicial_extrai_campos` | Pela voz entram só `estado_caminhao` e `carga`. Posição e destino vêm do sistema (GPS e rota). |
| CP-3.1.1a | Monitora o GPS do celular e o do caminhão (§3.1.1) | ✅ | `POST /rotas/{id}/posicao` (`fonte=celular\|rastreador`) → `servicos/rotas.py:registrar_posicao` | `tests/api/test_central_metricas_gps.py::test_gps_e_rastreador_juntos_validam_a_chegada`, `::test_so_rastreador_nao_dispara_geocerca` | Os dois GPS são simulados (`scripts/simular_rota.py`). |
| CP-3.1.1b | Geocerca da origem → "Confirma a retirada?" → `RETIRADA` (§3.1.1) | ✅ | `rotas.on_origem`; `tasks.confirmar_retirada`; ferramenta `confirmar_retirada` | `tests/api/test_fluxos_viagem.py::test_na_origem_agente_pergunta_se_confirma_a_retirada`, `::test_motorista_confirma_retirada_por_voz`, `::test_retirada_dispara_uma_vez` | A retirada só fica `validado` depois da voz. |
| CP-3.1.1c | Geocerca do destino → "Confirma a chegada?" → `CHEGADA` inicia a estadia (§3.1.1) | ⚠️ | `rotas.registrar_posicao` → `tasks.on_chegada(origem="gps")` | `tests/api/test_geocercas.py::test_chegada_cria_task_pendente_e_inicia_estadia`; `tests/api/test_llm.py::test_cheguei_na_portaria_vira_chegada_validada` | Na geocerca, o agente **não pergunta** se confirma a chegada: já diz "Chegada registrada" e abre Task e estadia. Com o rastreador perto, o `EventoGeo CHEGADA` fica `validado` **sem voz**; a confirmação por voz só entra se o motorista disser "cheguei". |
| CP-3.1.1d | Cada evento guarda posição do celular e do caminhão, horário e confirmação por voz (§3.1.1) | ✅ | `infra/models.py:EventoGeo`; `rotas.prova` | `tests/api/test_fluxos_viagem.py::test_motorista_confirma_retirada_por_voz`; `tests/api/test_central_metricas_gps.py::test_gps_e_rastreador_juntos_validam_a_chegada` | Guarda só a transcrição, sem áudio (decisão de LGPD). O horário do rastreador não vai para o `EventoGeo`: fica em `Rota.rastreador_em`, que é sobrescrito a cada posição. |
| CP-3.1.1e | Divergência entre os GPS → `nao_validado` + alerta ao CCO (§3.1.1) | ✅ | `rotas.prova` + evento `divergencia_gps` (limite `DIVERGENCIA_GPS_MAX_M=500`) | `tests/api/test_central_metricas_gps.py::test_rastreador_longe_marca_nao_validado_e_alerta_cco` | |
| CP-3.1.1f | Um GPS sem sinal → `nao_validado` + alerta ao CCO (§3.1.1) | ⚠️ | `rotas.prova` (sem rastreador devolve `nao_validado`) | — | Sem rastreador, o evento fica `nao_validado`, mas **não sai alerta** (`divergentes` só recebe casos com distância medida). Depois, a voz valida a chegada mesmo sem rastreador. Não há rastreador "velho" (timeout). |

### §3.2 a §3.4: reportes, acionamento pelo motorista e pedido da central

| # | Requisito (resumo + seção de origem) | Status | Onde (arquivo:função ou rota) | Teste (arquivo::teste) | Observação |
|---|---|---|---|---|---|
| CP-3.2a | Reporte a cada X tempo ou ao atingir um break point (§3.2) | ⏸️ | — | — | Fora por decisão (caminhão andando, ponto em aberto da mentoria). |
| CP-3.2b | Validação de completude: o agente pergunta só o que faltou (§3.2) | ✅ | `reportes.registrar` (devolve `faltando` e `pergunte_so_isto`); `conversa.pendencias` | `tests/api/test_fluxos_viagem.py::test_checkin_incompleto_pede_so_o_que_faltou`; `tests/dominio/test_contingencia.py::test_checkin_parcial_pergunta_so_o_que_falta` | Vale para o relatório inicial e o check-in (não há reporte periódico). |
| CP-3.3a | Acionamento por wake word (§3.3) | 🖥️ | — | — | Fica no app. No backend, a sessão ConvoAI escuta direto. |
| CP-3.3b | Motorista passa informação a qualquer momento (§3.3) | ✅ | `conversa.responder` (evento `fala_motorista`) | `tests/api/test_llm.py::test_fala_registrada_como_transcricao` | |
| CP-3.3c | Motorista pede informação: rota, prazo, contato da central (§3.3) | ⚠️ | `prompts._carga` + `prompts.estado_atual` | `tests/api/test_sessoes.py::test_prompt_do_motorista_em_ptbr_com_dados_da_carga`; `tests/dominio/test_contingencia.py::test_pergunta_sobre_cco` | Rota, janela de descarga, recebedor e estado estão no prompt. **Contato da central:** não há telefone do CCO nem no modelo nem no prompt. |
| CP-3.3d | Registrar ocorrência: acidente, avaria, atraso, bloqueio, fiscalização (§3.3) | ✅ | ferramenta `registrar_ocorrencia` → `tasks.registrar_ocorrencia` | `tests/api/test_llm.py::test_fila_vira_ocorrencia`; `tests/dominio/test_contingencia.py::test_ocorrencias` | O enum não tem `bloqueio` nem `fiscalizacao` (esses casos caem em `outro`). |
| CP-3.3e | Solicitar documentos: a IA lê e responde (§3.3) | ✅ | ferramenta `consultar_documento` → `dominio/documentos.py:consultar` | `tests/api/test_llm.py::test_pergunta_sobre_a_nf_usa_ferramenta_e_registra_evento`, `::test_sem_llm_a_contingencia_responde_a_nf` | Responde sobre NF-e e CT-e mock, por campo. Documento real fica fora (⏸️). |
| CP-3.4 | Central pede uma informação → agente pergunta → resposta volta estruturada (§3.4) | ✅ | `POST/GET /rotas/{id}/solicitacoes` → `servicos/central.py:perguntar/responder`; ferramenta `responder_central` | `tests/api/test_central_metricas_gps.py::test_central_pergunta_agente_repassa_e_resposta_volta_estruturada`, `::test_pergunta_pendente_vai_no_estado_do_llm` | "Estruturada" aqui quer dizer pergunta, resposta, status e horário. A resposta em si é texto livre. |

### §3.5 Aviso de chegada e escalonamento e §3.5.1 Ligação ao recebedor

| # | Requisito (resumo + seção de origem) | Status | Onde (arquivo:função ou rota) | Teste (arquivo::teste) | Observação |
|---|---|---|---|---|---|
| CP-3.5a | Na aproximação (GPS + rota), avisa a central (§3.5) | ✅ | `dominio/geocerca.py:avaliar` (ETA) → `rotas.on_aproximacao` (evento `aproximacao`) | `tests/api/test_geocercas.py::test_aproximacao_dispara_uma_vez_e_avisa_motorista`; `tests/dominio/test_geocerca_escalonamento.py::test_eta_dentro_da_janela_de_aproximacao` | |
| CP-3.5b | Na aproximação, liga para o recebedor (placa, NF, horário previsto) pela Agora (§3.5) | ✅ | `ligacoes.ligar(motivo="aproximacao")`; `prompts.recebedor` | `tests/api/test_fluxos_viagem.py::test_aproximacao_liga_para_o_recebedor_por_padrao`; `tests/servicos/test_recebedor.py::test_plano_b_agente_entra_no_canal_do_recebedor` | Ligado por padrão (`LIGAR_RECEBEDOR_NA_APROXIMACAO=true`). O horário previsto sai como "em cerca de N minutos". Na demo, a ligação vai pelo plano B (RTC). |
| CP-3.5c | Recebedor confirma doca e horário → registra e avisa o motorista (§3.5) | ✅ | `ligacoes.registrar_resposta` + `_frase_motorista` (`/speak` INTERRUPT) | `tests/servicos/test_recebedor.py::test_resposta_do_recebedor_vai_para_task_e_motorista`; `tests/api/test_llm.py::test_recebedor_responde_doca_e_motorista_ouve` | |
| CP-3.5d | Não recebe hoje → aplica a regra da transportadora e avisa CCO e motorista (§3.5) | ✅ | `registrar_resposta(recebe_hoje=False)` + `regra_nao_recebe` (`RegraEscalonamento.acao_nao_recebe`) | `tests/api/test_fluxos_viagem.py::test_recebedor_nao_recebe_hoje_aplica_regra_e_avisa` | |
| CP-3.5e | Não atende → registra a tentativa como prova (§3.5) | ✅ | `ligacoes._vigiar` → `nao_atendida` + evento | `tests/servicos/test_recebedor.py::test_sem_resposta_ate_o_timeout_vira_nao_atendida_e_prova`, `::test_plano_a_desligou_sem_resposta_vira_nao_atendida` | No plano B, "não atendeu" quer dizer 180 s (`LIGACAO_TIMEOUT_S`) sem a ferramenta de resposta ser chamada. |
| CP-3.5f | Escalonamento troca de canal a cada tentativa: push → painel → ligação para a central (§3.5) | ⚠️ | `tasks.loop_escalonamento` + `dominio/escalonamento.py:nivel` | `tests/servicos/test_escalonamento.py::test_sem_resposta_do_cco_tres_tentativas_e_liga_para_recebedor`; `tests/dominio/test_geocerca_escalonamento.py::test_canal_e_prioridade_sobem_a_cada_tentativa` | Canal e prioridade sobem, mas são só **rótulos** no evento `notificacao_cco`. Não há push real nem ligação para a central (o README declara). |
| CP-3.5g | Depois de 3 tentativas sem resposta, liga para o recebedor (§3.5) | ✅ | `loop_escalonamento` → `ligacoes.ligar(motivo="cco_sem_resposta")` | `tests/servicos/test_escalonamento.py::test_sem_resposta_do_cco_tres_tentativas_e_liga_para_recebedor` | |
| CP-3.5h | A chegada cria uma Task no CCO: "carga chegou" (§3.5) | ✅ | `tasks.on_chegada` (idempotente) | `tests/api/test_geocercas.py::test_chegada_cria_task_pendente_e_inicia_estadia`, `::test_chegada_repetida_nao_duplica_task` | |
| CP-3.5i | Re-notifica a cada X com tempo parado, franquia e estadia, e a prioridade sobe (§3.5) | ✅ | `loop_escalonamento` (payload `estadia` em cada tentativa) | `tests/servicos/test_escalonamento.py::test_sem_resposta_do_cco_tres_tentativas_e_liga_para_recebedor` | |
| CP-3.5j | Tentativas, intervalo e canais seguem a `RegraEscalonamento` (§3.5) | ⚠️ | `tasks._regra` | `tests/servicos/test_escalonamento.py::test_regra_da_empresa_define_numero_de_tentativas` | `max_tentativas` e `niveis` vêm da regra. **`intervalo_s` e `acao_final` são ignorados**: o intervalo vem do `CCO_INTERVALO_S` global e a ação final é sempre ligar. Não há rota para editar a regra. |
| CP-3.5k | O CCO responde e assume a Task (§3.5) | ✅ | `POST /tasks/{id}/confirmar` → `tasks.confirmar` | `tests/api/test_cco.py::test_confirmar_task`; `tests/servicos/test_escalonamento.py::test_cco_confirma_e_loop_para_sem_ligacao` | |
| CP-3.5l | Motorista (voz) ou CCO confirma a descarga → Task concluída e estadia encerrada (§3.5) | ✅ | ferramenta `confirmar_descarga`; `POST /rotas/{id}/descarga` → `tasks.confirmar_descarga` | `tests/api/test_llm.py::test_descarreguei_encerra_estadia_e_task`; `tests/api/test_central_metricas_gps.py::test_metricas_do_dashboard` | |
| CP-3.5.1a | Avisa CCO e motorista: "ligando para o recebimento" (§3.5.1) | ✅ | `loop_escalonamento` (evento `escalada_recebedor` + `falar_motorista`) | `tests/servicos/test_escalonamento.py::test_sem_resposta_do_cco_tres_tentativas_e_liga_para_recebedor` | |
| CP-3.5.1b | Ligação de saída por SIP para o responsável cadastrado (código) (§3.5.1) | ✅ | `ligacoes.DiscadorSIP` → `agora_payload.montar_call` → `AgoraRest.call` / `call_status` / `hangup` | `tests/servicos/test_recebedor.py::test_plano_a_liga_por_sip_para_o_numero_do_recebedor`, `::test_plano_a_falhando_cai_no_plano_b`; `tests/integracoes/test_agora_rest.py::test_speak_leave_call_hangup_nas_rotas_documentadas` | Testado contra uma Agora falsa. Se o SIP falhar, cai sozinho no plano B. |
| CP-3.5.1c | Ligação telefônica real na demo (§3.5.1) | ⏸️ | `RECEBEDOR_MODO=rtc` (padrão); `scripts/twilio_trunk.py` | — | Fora por decisão: não há número pago. A demo usa o plano B, com o recebedor numa página do navegador (`/recebedor`). |
| CP-3.5.1d | Apresenta-se como assistente virtual e informa placa, carga, NF, horário e tempo parado (§3.5.1) | ✅ | `prompts.recebedor` (abertura) | `tests/servicos/test_recebedor.py::test_plano_b_agente_entra_no_canal_do_recebedor` | O teste confere "assistente virtual", placa e NF. Carga e tempo parado não são conferidos. A abertura diz "há X tempo", não o horário da chegada. |
| CP-3.5.1e | Registra a resposta: previsão, doca, motivo, pedido de documento (§3.5.1) | ✅ | ferramenta `registrar_resposta_recebedor` | `tests/servicos/test_recebedor.py::test_resposta_do_recebedor_vai_para_task_e_motorista` | Pedido de documento entra no campo `motivo`, sem campo próprio. |
| CP-3.5.1f | Repassa ao CCO (Task, transcrição) e ao motorista por voz (§3.5.1) | ✅ | `registrar_resposta` (`TaskCCO.resposta_recebedor`, `LigacaoRecebedor.transcricao`, `/speak` INTERRUPT) | `tests/api/test_llm.py::test_recebedor_responde_doca_e_motorista_ouve` | |
| CP-3.5.1g | Recebedor não atende → registra a tentativa e avisa CCO e motorista (§3.5.1) | ✅ | `ligacoes._vigiar` | `tests/servicos/test_recebedor.py::test_sem_resposta_ate_o_timeout_vira_nao_atendida_e_prova` | A tentativa fica em `LigacaoRecebedor` (com `task_id`), não num campo da Task. |
| CP-3.5.1h | A estadia continua até a descarga (§3.5.1) | ✅ | `Estadia.fim` só é preenchido em `confirmar_descarga` | `tests/dominio/test_estadia.py::test_estadia_encerrada_congela`; `tests/api/test_cco.py::test_stream_manda_snapshot_evento_e_contador` | |

### §3.6 Check-in

| # | Requisito (resumo + seção de origem) | Status | Onde (arquivo:função ou rota) | Teste (arquivo::teste) | Observação |
|---|---|---|---|---|---|
| CP-3.6a | Check-in por voz: estado final da carga, tempo de viagem, problemas (§3.6) | ✅ | `reportes.CAMPOS["checkin"]`, aberto em `tasks.on_chegada`; ferramenta `registrar_checkin` | `tests/api/test_fluxos_viagem.py::test_checkin_completo_gera_relatorio`; `tests/dominio/test_contingencia.py::test_chegada_ja_pede_o_checkin` | |
| CP-3.6b | A central recebe a confirmação de chegada (§3.6) | ✅ | eventos `chegada`, `task_criada` e `relatorio` em `GET /events` e `/cco/stream` | `tests/api/test_compat.py::test_get_events_no_formato_domain_event` | |

### §4 Modelo de dados

| # | Requisito (resumo + seção de origem) | Status | Onde (arquivo:função ou rota) | Teste (arquivo::teste) | Observação |
|---|---|---|---|---|---|
| CP-4.1 | `Empresa` (§4) | ✅ | `infra/models.py:Empresa` | `tests/servicos/test_seed.py::test_seed_cria_dados_da_demo` | |
| CP-4.2 | `Motorista` (§4) | ✅ | `models.Motorista` | `tests/api/test_publicacao_rota.py::test_lista_de_motoristas` | |
| CP-4.3 | `Rota` com `responsavel_recebimento {nome, telefone_e164}` (§4) | ✅ | `models.Rota` (`recebedor_nome`, `recebedor_telefone_e164`) | `tests/api/test_publicacao_rota.py::test_telefone_do_recebedor_precisa_ser_e164` | Valida E.164. |
| CP-4.4 | `BreakPoint` (§4) | ⏸️ | — | — | Faz parte dos reportes periódicos (fora). |
| CP-4.5 | `RegraReporte {intervalo, campos_obrigatorios[]}` (§4) | ⚠️ | — (só `reportes.CAMPOS`) | — | Não há tabela. Os campos estão fixos no código; o intervalo está fora por decisão. |
| CP-4.6 | `Reporte {timestamp, localizacao, campos, transcricao, completo}` (§4) | ⚠️ | `models.Reporte` | `tests/api/test_fluxos_viagem.py::test_checkin_completo_gera_relatorio` | **Falta `localizacao`.** Os outros campos existem, mais `perguntas_complemento`. |
| CP-4.7 | `Ocorrencia {tipo, descricao, localizacao, timestamp}` (§4) | ✅ | `models.Ocorrencia` | `tests/api/test_llm.py::test_fila_vira_ocorrencia` | |
| CP-4.8 | `Documento {rota_id, tipo, arquivo}` (§4) | ⏸️ | — (mock em `documentos.da_rota`, `fileUri: None`) | — | Documento real fora por decisão. |
| CP-4.9 | `SolicitacaoCentral {pergunta, resposta, status}` (§4) | ✅ | `models.SolicitacaoCentral` | `tests/api/test_central_metricas_gps.py::test_central_pergunta_agente_repassa_e_resposta_volta_estruturada` | |
| CP-4.10 | `RegraEscalonamento {niveis[], tempo_por_nivel, acao_final}` (§4) | ⚠️ | `models.RegraEscalonamento` | `tests/servicos/test_escalonamento.py::test_regra_da_empresa_define_numero_de_tentativas` | `intervalo_s` e `acao_final` existem na tabela, mas o código não os lê (ver CP-3.5j). |
| CP-4.11 | `TaskCCO` (status, prioridade, tentativas 0..3, canal_atual, confirmado_em/por) (§4) | ✅ | `models.TaskCCO` | `tests/servicos/test_escalonamento.py::test_cco_confirma_e_loop_para_sem_ligacao` | Tem o status extra `concluida` e o campo `resposta_recebedor`. |
| CP-4.12 | `LigacaoRecebedor` (atendida, resposta, transcrição, enviada ao CCO e ao motorista) (§4) | ✅ | `models.LigacaoRecebedor` | `tests/servicos/test_recebedor.py::test_resposta_do_recebedor_vai_para_task_e_motorista` | Sem `audio_url`, por decisão. |
| CP-4.13 | `EventoGeo` (RETIRADA, CHEGADA, DESCARGA; dois GPS; voz; status) (§4) | ✅ | `models.EventoGeo` | `tests/api/test_central_metricas_gps.py::test_rastreador_longe_marca_nao_validado_e_alerta_cco` | Tem também `APROXIMACAO`. Falta `gps_caminhao.ts`. |
| CP-4.14 | `Estadia {inicio, fim, franquia_h, capacidade_t, valor_t_h, horas_excedentes, valor_acumulado}` (§4) | ✅ | `models.Estadia` + `dominio/estadia.py:calcular` | `tests/dominio/test_estadia.py::test_sete_horas_parado_cobra_duas_horas_excedentes` | Horas excedentes e valor são calculados, não gravados. `capacidade_t` recebe o peso da carga (ver CP-6.5). |

### §5 Escopo do MVP

| # | Requisito (resumo + seção de origem) | Status | Onde (arquivo:função ou rota) | Teste (arquivo::teste) | Observação |
|---|---|---|---|---|---|
| CP-5.1 | 1 rota + regras cadastradas (seed ou mock) (§5) | ✅ | `app/seed.py:seed` | `tests/servicos/test_seed.py::test_seed_cria_dados_da_demo`, `::test_seed_idempotente` | |
| CP-5.2 | Relatório inicial + 1 ciclo de reporte com validação de campos faltantes (§5) | ✅ | ver CP-3.1b e CP-3.2b | ver CP-3.1b e CP-3.2b | O "ciclo" é o check-in. |
| CP-5.3 | Ocorrência por voz (§5) | ✅ | ver CP-3.3d | ver CP-3.3d | |
| CP-5.4 | Pedido da central → pergunta ao motorista (§5) | ✅ | ver CP-3.4 | ver CP-3.4 | |
| CP-5.5 | Aviso de aproximação ao CCO e ao recebedor + chegada com escalonamento (§5) | ✅ | ver CP-3.5a a CP-3.5i | ver CP-3.5a a CP-3.5i | |
| CP-5.6 | GPS simulado que percorre a rota (§5) | 🟡 | `scripts/simular_rota.py` | — | O endpoint que o script chama tem teste; o script não. |
| CP-5.7 | CCO sem resposta em 3 tentativas → liga para o recebedor e repassa ao CCO e ao motorista (§5) | ✅ | ver CP-3.5g e CP-3.5.1 | ver CP-3.5g e CP-3.5.1 | |
| CP-5.8 | Check-in de chegada (§5) | ✅ | ver CP-3.6a | ver CP-3.6a | |
| CP-5.9 | Fora: offline, mesh, LoRa (§5) | ⏸️ | — | — | |
| CP-5.10 | Fora: rádio PX (§5) | ⏸️ | — | — | |
| CP-5.11 | Fora: integração real com ERP ou TMS (§5) | ⏸️ | — | — | |
| CP-5.12 | Fora: rastreador real, simulado na demo (§5) | ⏸️ | `fonte=rastreador` em `/rotas/{id}/posicao` | ver CP-3.1.1a | O stream simulado funciona e tem teste. |

### §6 Decisões tomadas

| # | Requisito (resumo + seção de origem) | Status | Onde (arquivo:função ou rota) | Teste (arquivo::teste) | Observação |
|---|---|---|---|---|---|
| CP-6.1 | Escalonamento como regra configurável no painel, por transportadora (§6) | ⚠️ | `models.RegraEscalonamento`; `tasks._regra` | `tests/servicos/test_escalonamento.py::test_regra_da_empresa_define_numero_de_tentativas` | Mesma lacuna de CP-3.5j. Não há endpoint e só 2 dos 4 campos são lidos. |
| CP-6.2 | Na chegada, cria a Task "carga chegou" e notifica a cada X com o tempo parado (§6) | ✅ | `tasks.on_chegada` + `loop_escalonamento` | ver CP-3.5h e CP-3.5i | |
| CP-6.3 | O contador da estadia começa na chegada registrada por GPS e check-in (§6) | ✅ | `tasks.on_chegada` (`Estadia.inicio` = primeira chegada, por GPS, voz ou app) | `tests/api/test_geocercas.py::test_chegada_cria_task_pendente_e_inicia_estadia` | |
| CP-6.4 | Franquia de 5 h, mostra a franquia restante e depois a estadia acumulada (§6) | ✅ | `dominio/estadia.py:calcular`; contador SSE a cada 1 s (`api/cco.py:_contador`) | `tests/dominio/test_estadia.py::test_quatro_horas_parado_ainda_na_franquia`; `tests/api/test_cco.py::test_stream_manda_snapshot_evento_e_contador` | |
| CP-6.5 | Valor por t/h calculado sobre a **capacidade total do veículo** (§6) | ⚠️ | `tasks.on_chegada`: `Estadia(capacidade_t=r.carga_t)` | `tests/dominio/test_estadia.py::test_sete_horas_parado_cobra_duas_horas_excedentes` | A fórmula está certa, mas usa o **peso da carga** (`carga_t`), não a capacidade do veículo. A `Rota` não tem campo de capacidade. |
| CP-6.6 | Valor da ANTT configurável, nunca fixo no código (§6) | 🟡 | `infra/settings.py:estadia_valor_t_h` (env `ESTADIA_VALOR_T_H`, padrão 2,50) | — | Configurável por variável de ambiente. Nenhum teste troca o valor; todos usam o padrão. |
| CP-6.7 | Registro com horário (GPS + voz) como prova da estadia (§6) | ✅ | `models.Evento` (`timestamp` = `receivedAt`), `EventoGeo` | `tests/api/test_compat.py::test_get_events_no_formato_domain_event` | |
| CP-6.8 | Prova de retirada e chegada: GPS do celular + GPS do caminhão + voz no mesmo `EventoGeo` (§6) | ⚠️ | `EventoGeo` + `rotas.prova` + `tasks.on_chegada(origem="voz")` | `tests/api/test_llm.py::test_cheguei_na_portaria_vira_chegada_validada` | Na retirada, os três estão juntos. Na chegada, o evento é validado sem a voz (mesma lacuna de CP-3.1.1c). |
| CP-6.9 | CCO sem resposta em 3 tentativas: avisa, liga pelo SIP, repassa, e a ligação fica na Task como prova (§6) | ✅ | ver CP-3.5.1a a CP-3.5.1g | ver CP-3.5.1 | Em modo SIP, a ligação real está ⏸️ (CP-3.5.1c). |
| CP-6.10 | Documentos interpretados pela IA de voz ("qual o peso da NF?", "número do CT-e?") (§6) | ✅ | `documentos.consultar` | `tests/dominio/test_documentos.py::test_consulta_responde_com_campo_e_cita_documento`, `::test_cte_explicito_nao_cai_na_nfe` | Só com os documentos mock. |
| CP-6.11 | Atualização periódica obrigatória (§6) | ⏸️ | — | — | Ponto em aberto; a demo mostra só o caminhão parado. |

### §7 Riscos que continuam

| # | Requisito (resumo + seção de origem) | Status | Onde (arquivo:função ou rota) | Teste (arquivo::teste) | Observação |
|---|---|---|---|---|---|
| CP-7.1 | Documentos: responder só com campos extraídos, citar o documento e dizer "não encontrei" (§7) | ✅ | `documentos.consultar`; descrição da ferramenta e prompt | `tests/dominio/test_documentos.py::test_pergunta_sem_campo_diz_nao_encontrei` | Com LLM, a garantia depende de o modelo repetir o que a ferramenta devolveu. |
| CP-7.2 | Adiar a atualização por 2 min ("me pergunta em 2 min") (§7) | ⏸️ | — | — | Vai junto com o reporte periódico (fora). |
| CP-7.3 | Re-notificar trocando de canal: push → painel → ligação ou WhatsApp ao supervisor (§7) | ⚠️ | `loop_escalonamento` | ver CP-3.5f | Mesma lacuna de CP-3.5f: o canal é só um rótulo. |
| CP-7.4 | Notificar na aproximação e criar a Task na chegada (§7) | ✅ | `rotas.on_aproximacao`; `tasks.on_chegada` | `tests/api/test_geocercas.py::test_aproximacao_dispara_uma_vez_e_avisa_motorista` | |
| CP-7.5 | Motorista no loop: avisar quando a Task for confirmada (§7) | ✅ | `tasks.confirmar` → `falar_motorista` | `tests/servicos/test_escalonamento.py::test_cco_confirma_e_loop_para_sem_ligacao` | |
| CP-7.6 | Sem SIP trunk, simular com um 2º cliente Agora RTC e declarar no README (§7) | ✅ | `ligacoes.DiscadorRTC`; `static/recebedor.html`; `GET /ligacoes/atual/recebedor` | `tests/servicos/test_recebedor.py::test_plano_b_agente_entra_no_canal_do_recebedor`; `tests/api/test_ligacoes.py::test_dada_ligacao_em_andamento_entao_pagina_recebe_token` | Declarado no README, na seção "Simulado / pré-existente". |
| CP-7.7 | Na ligação a terceiro: identificar-se como assistente virtual, não prometer nada pelo CCO, usar o número do cadastro (§7) | ⚠️ | `prompts.recebedor`; `ligacoes.ligar` (`numero = r.recebedor_telefone_e164`) | `tests/servicos/test_recebedor.py::test_plano_b_agente_entra_no_canal_do_recebedor`, `::test_plano_a_liga_por_sip_para_o_numero_do_recebedor` | Identificação e número do cadastro estão OK. O prompt **não proíbe** prometer em nome do CCO (só "não ameace com cobrança" e "não invente"). |
| CP-7.8 | Áudio: guardar só a transcrição (§7) | ✅ | `models` sem colunas de áudio | `tests/api/test_llm.py::test_lgpd_sem_audio_nem_saude` | |
| CP-7.9 | Conectividade: fila e reenvio dos reportes (§7) | ✅ | `POST /events` idempotente (409 na chave repetida) | `tests/api/test_compat.py::test_post_events_e_idempotente` | A parte do servidor está feita. O outbox é do app (🖥️). Ver AR-7.15. |
| CP-7.10 | Wake word em cabine barulhenta e botão físico como alternativa (§7) | 🖥️ | — | — | |
| CP-7.11 | Completude: critério por campo, para não aceitar resposta vaga (§7) | ⚠️ | `reportes.registrar` (aceita qualquer texto não vazio) | `tests/dominio/test_contingencia.py::test_checkin_parcial_pergunta_so_o_que_falta` | Não há critério por campo no servidor: quem julga é o LLM. Só a contingência tem regex por campo. |
| CP-7.12 | Início da estadia pela geocerca do destino + check-in (§7) | ✅ | `tasks.on_chegada` | `tests/api/test_geocercas.py::test_chegada_cria_task_pendente_e_inicia_estadia` | |
| CP-7.13 | Fim da estadia: evento claro de descarga (voz ou CCO) (§7) | ✅ | `tasks.confirmar_descarga` (`UnloadConfirmed`) | `tests/api/test_llm.py::test_descarreguei_encerra_estadia_e_task` | |
| CP-7.14 | Prova independente do destinatário: QR, assinatura, canhoto (§7) | ⏸️ | — | — | Descartada (decisão 11). No lugar, vale a resposta do recebedor na ligação (AJ-5). |
| CP-7.15 | GPS falsificável: detectar mock location (`isMock`) (§7) | 🖥️ | — | — | Fica no app. `/rotas/{id}/posicao` não tem campo `is_mock`; a prova forte é o rastreador (CP-3.1.1e). |
| CP-7.16 | Localização em segundo plano (foreground service) (§7) | 🖥️ | — | — | |
| CP-7.17 | Simular o rastreador com um 2º stream de GPS (§7) | ✅ | `fonte=rastreador`; `scripts/simular_rota.py` (`--divergir`) | `tests/api/test_central_metricas_gps.py::test_gps_e_rastreador_juntos_validam_a_chegada` | |
| CP-7.18 | `franquia_h` configurável, porque contratos variam (§7) | 🟡 | `settings.estadia_franquia_h` → `Estadia.franquia_h` | — | Configurável só globalmente, por variável de ambiente (não por contrato nem por rota). Nenhum teste troca a franquia. |

---

## 2. `ajustes-pos-mentoria.md`

| # | Requisito (resumo + seção de origem) | Status | Onde (arquivo:função ou rota) | Teste (arquivo::teste) | Observação |
|---|---|---|---|---|---|
| AJ-1a | Na estrada com atraso: avisar o CCO e o recebedor do novo horário previsto (§1) | ❌ | — | — | A ocorrência `atraso` só gera um evento. Nada recalcula o horário previsto contra a janela de descarga nem liga para o recebedor antes da aproximação. |
| AJ-1b | Na aproximação: avisar o recebedor e confirmar doca e horário (§1) | ✅ | ver CP-3.5b e CP-3.5c | ver CP-3.5b e CP-3.5c | |
| AJ-1c | Na chegada: Task + contador de estadia + escalonamento se o CCO não responder (§1) | ✅ | ver CP-3.5h a CP-3.5i | ver CP-3.5h a CP-3.5i | |
| AJ-1d | Parado: ligar para o recebedor depois de 3 tentativas sem resposta (§1) | ✅ | ver CP-3.5g | ver CP-3.5g | |
| AJ-1e | Na descarga: encerrar o contador, por voz ou pelo CCO (§1) | ✅ | ver CP-3.5l | ver CP-3.5l | |
| AJ-1f | Add-ons: ocorrências, documentos e pedido da central (§1) | ✅ | ver CP-3.3d, CP-3.3e e CP-3.4 | ver CP-3.3d, CP-3.3e e CP-3.4 | |
| AJ-2 | Aviso prévio ao recebedor **na aproximação**, por ligação de voz pela Agora (conta para o C2) (§2, §8) | ✅ | `settings.ligar_recebedor_na_aproximacao=True`; evento `aviso_recebedor` (`ReceiverNotified`) | `tests/api/test_fluxos_viagem.py::test_aproximacao_liga_para_o_recebedor_por_padrao` | É uma ligação ConvoAI (não mensagem). Na demo, vai pelo canal RTC. |
| AJ-3 | Áudio: só transcrição (opção recomendada) (§3) | ✅ | `models` sem `audio_url` | `tests/api/test_llm.py::test_lgpd_sem_audio_nem_saude` | |
| AJ-4 | Reporte periódico com o caminhão andando (§4) | ⏸️ | — | — | Em aberto; a demo mostra só o caminhão parado. |
| AJ-4.1 | Campo de saúde do motorista removido do reporte e do modelo (§4.1) | ✅ | `models` sem `saude`; `prompts.motorista` ("Não pergunte sobre a saúde") | `tests/api/test_llm.py::test_lgpd_sem_audio_nem_saude` | |
| AJ-5 | Resposta do recebedor na ligação registrada na Task, com horário, como prova do outro lado (§5) | ✅ | `TaskCCO.resposta_recebedor`; `LigacaoRecebedor.transcricao` e `encerrada_em` | `tests/servicos/test_recebedor.py::test_resposta_do_recebedor_vai_para_task_e_motorista` | No aviso da aproximação ainda não há Task (`task_id` nulo), então a prova fica só em `LigacaoRecebedor`. |
| AJ-6a | Nome do produto: AvisAI (§6) | 🟡 | `main.py` (título da API), `prompts.motorista` ("Aqui é o AvisAI") | — | |
| AJ-6b | Estadia de R$ 2,50 por t/h (ANTT, abr/2026) (§6) | ✅ | `settings.estadia_valor_t_h = 2.50` | `tests/dominio/test_estadia.py::test_sete_horas_parado_cobra_duas_horas_excedentes` | |
| AJ-7 | Se o recebedor tiver agendamento de doca, usar esse sistema (§7) | ⏸️ | — | — | É uma resposta para a banca, como a integração com o TMS. Não estava planejada para o MVP. |
| AJ-8a | Voz no centro: o agente negocia com o recebedor ("outra doca, horário mais cedo?") (§8) | 🟡 | `prompts.recebedor` ("Negocie com educação...") | — | Está só no prompt; nenhum teste confere. |
| AJ-8b | Registro como dado para renegociar com o embarcador (horas paradas por cliente) (§8) | ✅ | `servicos/metricas.py:ranking_recebedores`; `GET /api/receivers` | `tests/api/test_central_metricas_gps.py::test_ranking_de_recebedores` | Agrupa por recebedor; não existe a entidade "embarcador". |
| AJ-8c | Testar o SIP de saída e, se falhar, usar o plano B declarado (§8) | ✅ | `ligacoes.ligar` (fallback automático, evento `fallback_plano_b`) | `tests/servicos/test_recebedor.py::test_plano_a_falhando_cai_no_plano_b`, `::test_plano_a_sem_numero_configurado_cai_no_plano_b` | |
| AJ-9.1 | Dia 1 com o GPS do celular (simulado e declarado); rastreador e TMS no setup (§9.1) | ✅ | `POST /rotas/{id}/posicao` (`fonte=celular`); README "Simulado" | `tests/api/test_geocercas.py::test_posicao_longe_fica_em_transito_sem_disparos` | |

---

## 3. `docs/arquitetura-avisai.md`

### §0 Regras, §2 Repositório, §3 e §4 (design e i18n)

| # | Requisito (resumo + seção de origem) | Status | Onde (arquivo:função ou rota) | Teste (arquivo::teste) | Observação |
|---|---|---|---|---|---|
| AR-0.1 | Tudo mock, menos a voz pela Agora ConvoAI, que é real (E2) (§0) | ✅ | `integracoes/agora_rest.py:AgoraRest` (REST v2 `/join`, `/leave`, `/speak`) | `tests/integracoes/test_agora_rest.py::test_join_usa_basic_auth_quando_tem_customer_id` | Os testes usam uma Agora falsa. A chamada real não tem teste automatizado. |
| AR-0.2 | Chaves fora do app e do git; o app nunca chama a REST da Agora (E7) (§0) | ✅ | Tokens gerados no servidor (`integracoes/tokens.py`); `.env` fora do git (`git ls-files` só tem `.env.example`) | `tests/api/test_tokens.py::test_sem_credenciais_entao_500_com_mensagem` | |
| AR-0.3 | Mocks declarados no README (E8) (§0, §11) | 🟡 | README, seção "Simulado / pré-existente (E5/E8)" | — | Declara GPS, rastreador, plano B, estadia acelerada, CCO sem push real e contingência. |
| AR-0.4 | Servidor P0: `/agent/start`, `/agent/stop`, token RTC, eventos (§0) | ✅ | ver AR-8.x | ver AR-8.x | |
| AR-0.5 | Servidor P1: ligação ao recebedor por SIP ou plano B (§0) | ✅ | ver CP-3.5.1b e CP-7.6 | ver CP-3.5.1b e CP-7.6 | |
| AR-0.6 | P2: PDF + busca vetorial local (§0, §5.3) | ⏸️ | — | — | Fora por decisão: só a NF-e e o CT-e mock com perguntas por campo. |
| AR-2.1 | `agent-server` em Node (Express ou Hono) num monorepo pnpm (§2) | ✅ | `backend/app` (FastAPI, Python) + `api/compat.py` | `tests/api/test_compat.py` (8 testes) | Desvio de stack: é Python, não Node. O contrato HTTP do documento foi mantido pela camada `compat`. |
| AR-2.2 | `packages/contracts`: tipos TS dos eventos e entidades (§2, §7) | ⚠️ | `clients/tipos.ts` | — | Os tipos não incluem `DomainEvent` nem `EventType` do §7. `TipoEvento` está desatualizado (faltam `pergunta_documento` e `sessao_encerrada`). |
| AR-3 | Design system, tokens Tailwind, estados visuais da voz (§3) | 🖥️ | — | — | |
| AR-4.1 | i18n pt-BR e en nos apps (§4) | 🖥️ | — | — | |
| AR-4.2 | Texto falado vem do prompt (idioma do LLM e do TTS), não do i18n (§4) | ✅ | `dominio/prompts.py` (pt-BR); `agora_payload.montar_asr` (`pt-BR`); TTS minimax com voz em português | `tests/api/test_sessoes.py::test_dada_rota_quando_cria_sessao_entao_join_com_llm_proprio_e_ptbr` | |

### §5 Mobile: o que é de backend

| # | Requisito (resumo + seção de origem) | Status | Onde (arquivo:função ou rota) | Teste (arquivo::teste) | Observação |
|---|---|---|---|---|---|
| AR-5.1 | Dev build com módulos nativos (§5.1) | 🖥️ | — | — | |
| AR-5.2a | `auth`: SSO mock com provedor e usuário no servidor (§5.2) | ✅ | `POST /auth/sso` | `tests/api/test_compat.py::test_api_route_receivers_documents_sso`; `tests/api/test_publicacao_rota.py::test_sso_e_api_route_trazem_a_rota_do_motorista` | Autenticação real fora por decisão (SSO mock). |
| AR-5.2b | `route`: rota e recebedores em JSON, com polilinha (§5.2) | ✅ | `GET /api/route` | `tests/api/test_compat.py::test_api_route_receivers_documents_sso` | O mapa é do app. |
| AR-5.2c | `location`: simulador que percorre a polilinha; geocercas de origem e destino e aproximação (§5.2) | ✅ | `scripts/simular_rota.py` + `rotas.registrar_posicao` | `tests/api/test_geocercas.py` (6 testes) | As geocercas ficam no servidor, não no celular como diz o documento. Funciona igual e fica centralizado. |
| AR-5.2d | `voice`: sessão Agora real com transcrição (§5.2) | ✅ | `sessoes.iniciar_motorista`; `POST /sessions`, `/agent/start`; evento `fala` no stream | `tests/api/test_sessoes.py` (11 testes) | O cliente RN fica em `clients/react-native/useAvisaiVoz.ts` (front). |
| AR-5.2e | `report`: campos obrigatórios; o agente pergunta só o que faltou (§5.2) | ✅ | ver CP-3.2b | ver CP-3.2b | |
| AR-5.2f | `arrival`: check-in, contador e aviso "o recebedor confirmou doca 4 às 15h" (§5.2) | ✅ | ver CP-3.6a, CP-6.4 e CP-3.5c | ver CP-3.6a, CP-6.4 e CP-3.5c | |
| AR-5.2g | `documents`: leitura de PDF e pergunta por voz (§5.2) | ⏸️ | — | — | Fica só a pergunta por voz sobre o mock (CP-3.3e). |
| AR-5.2h | `outbox` e SQLite local (§5.2, §5.3) | 🖥️ | — | — | |
| AR-5.4a | O servidor ignora `idempotency_key` repetida (200 ou 409) (§5.4) | ✅ | `api/compat.py:post_event` (`Evento.idempotency_key` UNIQUE) | `tests/api/test_compat.py::test_post_events_e_idempotente` | |
| AR-5.4b | Rede fraca, prioridade de eventos críticos, voz sem rede vira texto (§5.4) | 🖥️ | — | — | |
| AR-5.5a | Fluxo do app: SSO mock → rota do dia (mapa, paradas, documentos) (§5.5 A–D) | ✅ | `/auth/sso`, `/api/route`, `/api/documents` | `tests/api/test_compat.py::test_api_route_receivers_documents_sso` | |
| AR-5.5b | Iniciar viagem → geocerca da origem → "Confirma a retirada?" → relatório inicial (§5.5 E–H) | ✅ | ver CP-3.1.1b e CP-3.1b | ver CP-3.1.1b e CP-3.1b | |
| AR-5.5c | Aproximação → servidor avisa o CCO e liga para o recebedor → 3 desfechos (§5.5 J–O) | ✅ | ver CP-3.5a a CP-3.5e | ver CP-3.5a a CP-3.5e | O aviso ao motorista é só de ida (`/speak`). |
| AR-5.5d | Geocerca do destino → check-in por voz → campos completos? (§5.5 P–S) | ✅ | ver CP-3.6a e CP-3.2b | ver CP-3.6a e CP-3.2b | |
| AR-5.5e | Task + contador → 3 tentativas → CCO assume ou agente liga de novo e repassa (§5.5 T–W) | ✅ | ver CP-3.5g a CP-3.5k | ver CP-3.5g a CP-3.5k | |
| AR-5.5f | Descarga por voz → estadia encerrada → CCO (§5.5 X–Y) | ✅ | ver CP-3.5l | ver CP-3.5l | |
| AR-5.5g | A qualquer momento: ocorrência ou pergunta sobre a NF por voz (§5.5 Z) | ✅ | ver CP-3.3d e CP-3.3e | ver CP-3.3d e CP-3.3e | |

### §6 CCO web: o que vem do backend

| # | Requisito (resumo + seção de origem) | Status | Onde (arquivo:função ou rota) | Teste (arquivo::teste) | Observação |
|---|---|---|---|---|---|
| AR-6.1a | `tasks`: fila por prioridade, tentativas 1/3 a 3/3, botão "assumir" (§6.1) | ✅ | `GET /tasks`; `POST /tasks/{id}/confirmar`; evento `task` no SSE | `tests/api/test_cco.py::test_confirmar_task`, `::test_estado_do_cco` | |
| AR-6.1b | `fleet`: posições dos caminhões (§6.1) | ✅ | evento `posicao` no SSE e WS; `GET /rotas` (`ultima_lat`/`ultima_lng`) | `tests/api/test_cco.py::test_stream_manda_snapshot_evento_e_contador` | O mapa é do front. O teste não confere o evento `posicao`. |
| AR-6.1c | `trips`: linha do tempo da viagem (§6.1) | ✅ | `GET /events?tripId=`; `GET /eventos` | `tests/api/test_compat.py::test_get_events_no_formato_domain_event` | |
| AR-6.1d | `receivers`: ranking com espera média, ligações atendidas, estadia devida (§6.1) | ✅ | `GET /api/receivers` → `metricas.ranking_recebedores` | `tests/api/test_central_metricas_gps.py::test_ranking_de_recebedores` | |
| AR-6.1e | `calls`: log das ligações com a transcrição (§6.1) | ✅ | `GET /ligacoes`, `GET /ligacoes/{id}` | `tests/api/test_llm.py::test_recebedor_responde_doca_e_motorista_ouve` | O teste confere a transcrição no modelo, não pela rota. |
| AR-6.1f | Eventos por polling de 2 s (mock) ou Agora Signaling (P2) (§6.1) | ✅ | `GET /events?since=`; SSE `/cco/stream`; WS `/ws` | `tests/api/test_compat.py::test_get_events_since`; `tests/api/test_cco.py::test_ws_filtra_eventos_pela_rota` | Signaling (P2 opcional) não foi feito. SSE e WS entregam na hora. |
| AR-6.2.1 | KPI: horas paradas por entrega (§6.2) | ✅ | `metricas.calcular` (`horas_paradas_media`) | `tests/api/test_central_metricas_gps.py::test_metricas_do_dashboard` | |
| AR-6.2.2 | KPI: estadia devida × **cobrada** (§6.2) | ⚠️ | `estadia_devida_total` | `tests/api/test_central_metricas_gps.py::test_metricas_do_dashboard` | Só a estadia devida. Não existe registro de cobrança. |
| AR-6.2.3 | KPI: tempo de espera por recebedor (TMD) (§6.2) | ✅ | `ranking_recebedores` (`espera_media_h`) | `tests/api/test_central_metricas_gps.py::test_ranking_de_recebedores` | |
| AR-6.2.4 | KPI: % de recebedores avisados antes da chegada (§6.2) | 🟡 | `pct_recebedores_avisados` (`_avisados_antes`) | `tests/api/test_central_metricas_gps.py::test_metricas_do_dashboard` | O teste só confere que a chave existe, não o valor. |
| AR-6.2.5 | KPI: % de ligações ao recebedor atendidas (§6.2) | 🟡 | `pct_ligacoes_atendidas` | idem | Só a chave é conferida. |
| AR-6.2.6 | KPI: tempo até a ação do CCO (§6.2) | ✅ | `tempo_ate_acao_cco_min_media` | `tests/api/test_central_metricas_gps.py::test_metricas_do_dashboard` | O teste confere 30 min. |
| AR-6.2.7 | KPI: Tasks escaladas (3 tentativas) (§6.2) | 🟡 | `tasks_escaladas` | idem | O teste só cobre o caso com valor 0. |
| AR-6.2.8 | KPI: % de reportes completos na 1ª resposta (§6.2) | 🟡 | `pct_reportes_completos_1a` | idem | Só a chave é conferida. `perguntas_complemento` tem teste em `test_checkin_completo_gera_relatorio`. |
| AR-6.2.9 | KPI: ligações CCO ↔ motorista evitadas (§6.2) | 🟡 | `contatos_resolvidos_pelo_agente` (conta eventos de resposta) | — | É uma aproximação e não tem teste. |
| AR-6.2.10 | KPI: latência da voz p50 e p95 (do fim da fala ao início da resposta) (§6.2) | ⚠️ | `conversa.responder` (`c.latencias`) → `latencia_voz_ms` | idem (só a chave) | Mede só o nosso LLM até o 1º trecho. Fica de fora ASR, TTS e RTC, que o KPI do documento inclui. |
| AR-6.3a | CCO: card "chegando" + resultado do aviso ao recebedor (§6.3) | ✅ | eventos `aproximacao`, `aviso_recebedor`, `resposta_recebedor` | ver CP-3.5a a CP-3.5c | |
| AR-6.3b | CCO: Task criada com prioridade baixa + contador da estadia (§6.3) | ✅ | `on_chegada` (`prioridade=normal`); `_contador` | `tests/api/test_cco.py::test_stream_manda_snapshot_evento_e_contador` | |
| AR-6.3c | CCO: card de ocorrência com a transcrição (§6.3) | ✅ | `Ocorrencia.transcricao`; snapshot `ocorrencias` | `tests/api/test_llm.py::test_fila_vira_ocorrencia` | |
| AR-6.3d | CCO: operador assume → Task em atendimento (§6.3) | ✅ | `tasks.confirmar` (status `confirmada`) | `tests/api/test_cco.py::test_confirmar_task` | |
| AR-6.3e | CCO: tentativas 2/3 e 3/3, prioridade sobe e canal muda (push → destaque → ligação) (§6.3) | ⚠️ | `loop_escalonamento` | ver CP-3.5f | Mesma lacuna de CP-3.5f. |
| AR-6.3f | CCO: depois de 3/3, o agente liga e aparece o card da ligação (atendeu?, resposta, transcrição) (§6.3) | ✅ | `ligacoes.ligar`; `ReceiverCallResult.answered` | `tests/servicos/test_recebedor.py::test_resposta_do_recebedor_vai_para_task_e_motorista` | |
| AR-6.3g | CCO: descarga → Task fechada, estadia calculada, KPIs atualizados (§6.3) | ✅ | `confirmar_descarga`; `metricas.calcular` | `tests/api/test_central_metricas_gps.py::test_metricas_do_dashboard` | |
| AR-6.3h | CCO: exportar o ranking para renegociar com o embarcador (§6.3) | 🖥️ | `GET /api/receivers` (JSON) | — | O servidor entrega o JSON. A exportação é do front. |

### §7 Contrato de eventos

| # | Requisito (resumo + seção de origem) | Status | Onde (arquivo:função ou rota) | Teste (arquivo::teste) | Observação |
|---|---|---|---|---|---|
| AR-7.1 | `RouteAssigned` (§7) | ✅ | `publicacao.atribuir` → `rota_atribuida` | `tests/api/test_publicacao_rota.py::test_atribuir_motorista_gera_route_assigned` | O teste confere pelo `GET /events`. |
| AR-7.2 | `PickupConfirmed` (§7) | ✅ | `tasks.confirmar_retirada` → `retirada` | `tests/api/test_fluxos_viagem.py::test_motorista_confirma_retirada_por_voz` | O teste confere o evento interno; o nome do contrato sai do dict `TIPO_DOMINIO`. |
| AR-7.3 | `ReportSubmitted` (§7) | ✅ | `reportes.registrar` → `relatorio` | `tests/api/test_fluxos_viagem.py::test_checkin_completo_gera_relatorio` | |
| AR-7.4 | `ReportFieldMissing` (§7) | ✅ | `reportes.registrar` → `campo_faltante` | `tests/api/test_fluxos_viagem.py::test_checkin_incompleto_pede_so_o_que_faltou` | |
| AR-7.5 | `OccurrenceCreated` (§7) | ✅ | `tasks.registrar_ocorrencia` → `ocorrencia` | `tests/api/test_compat.py::test_post_events_e_idempotente` | |
| AR-7.6 | `ApproachDetected` (§7) | ✅ | `rotas.on_aproximacao` → `aproximacao` | `tests/api/test_geocercas.py::test_aproximacao_dispara_uma_vez_e_avisa_motorista` | |
| AR-7.7 | `ReceiverNotified` (§7) | ✅ | `ligacoes.ligar(motivo="aproximacao")` → `aviso_recebedor` | `tests/api/test_fluxos_viagem.py::test_aproximacao_liga_para_o_recebedor_por_padrao` | |
| AR-7.8 | `ReceiverCallResult` com `answered` (§7) | ✅ | `resposta_recebedor` (`answered=true`) e `ligacao_nao_atendida` (`answered=false`) em `compat.para_dominio` | `tests/servicos/test_recebedor.py::test_resposta_do_recebedor_vai_para_task_e_motorista`, `::test_sem_resposta_ate_o_timeout_vira_nao_atendida_e_prova` | |
| AR-7.9 | `ArrivalRegistered` (§7) | ✅ | `tasks.on_chegada` → `chegada` | `tests/api/test_compat.py::test_get_events_no_formato_domain_event` | |
| AR-7.10 | `TaskCreated` (§7) | ✅ | `on_chegada` → `task_criada` | `tests/api/test_compat.py::test_get_events_no_formato_domain_event` | |
| AR-7.11 | `TaskEscalated` (§7) | ✅ | `notificacao_cco` e `escalada_recebedor` | `tests/servicos/test_escalonamento.py::test_sem_resposta_do_cco_tres_tentativas_e_liga_para_recebedor` | |
| AR-7.12 | `TaskAcknowledged` (§7) | ✅ | `tasks.confirmar` → `task_confirmada` | `tests/servicos/test_escalonamento.py::test_cco_confirma_e_loop_para_sem_ligacao` | O teste confere o status e a fala, não o evento. |
| AR-7.13 | `UnloadConfirmed` + `DocumentQuestionAnswered` (§7) | ✅ | `confirmar_descarga` → `descarga`; `ferramentas._documento` → `pergunta_documento` | `tests/api/test_llm.py::test_descarreguei_encerra_estadia_e_task`, `::test_pergunta_sobre_a_nf_usa_ferramenta_e_registra_evento` | |
| AR-7.14 | Envelope `DomainEvent` {id, idempotencyKey, tripId, type, occurredAt, receivedAt, source, payload} (§7) | ✅ | `compat.para_dominio` | `tests/api/test_compat.py::test_get_events_no_formato_domain_event` | |
| AR-7.15 | `idempotencyKey` igual à do outbox; `occurredAt` = hora do celular (§7) | ⚠️ | `compat.post_event` + `_aplicar` | `tests/api/test_compat.py::test_post_events_e_idempotente` (só a deduplicação) | O evento que o app manda fica guardado como `evento_app`, que **não aparece** no `GET /events`. O efeito dele (por exemplo, `ocorrencia`) volta com `idempotencyKey=srv-N` e com o horário do servidor em `occurredAt`. Por isso o app não consegue casar o outbox com os eventos. Só 5 tipos são aplicados; os outros são aceitos (200) e ignorados sem aviso. |

### §8 Rotas do agent-server, §10 variáveis de ambiente e §9 plano

| # | Requisito (resumo + seção de origem) | Status | Onde (arquivo:função ou rota) | Teste (arquivo::teste) | Observação |
|---|---|---|---|---|---|
| AR-8.1 | `POST /agent/start` → `/join` com Basic auth, canal, token do agente, ASR, LLM, TTS e prompt (§8) | ✅ | `compat.agent_start` → `sessoes.iniciar_motorista` → `agora_payload.montar_join` | `tests/api/test_compat.py::test_agent_start_e_stop`; `tests/api/test_sessoes.py::test_dada_rota_quando_cria_sessao_entao_join_com_llm_proprio_e_ptbr`; `tests/integracoes/test_agora_rest.py::test_join_usa_basic_auth_quando_tem_customer_id` | O LLM é o nosso endpoint (`/v1/chat/completions`), chamado pela Agora. |
| AR-8.2 | `POST /agent/stop` (§8) | ✅ | `compat.agent_stop` → `sessoes.encerrar` | `tests/api/test_compat.py::test_agent_start_e_stop`; `tests/api/test_sessoes.py::test_quando_encerra_sessao_entao_leave_e_encerrada` | |
| AR-8.3 | `GET /token?channel&uid` (§8) | ✅ | `api/agentes.py:token` | `tests/api/test_tokens.py::test_dado_app_configurada_quando_pede_token_entao_recebe_token_rtc` (+3) | |
| AR-8.4 | `POST /call/receiver`: SIP ou plano B (§8) | ✅ | `compat.call_receiver` → `ligacoes.ligar` | `tests/api/test_compat.py::test_call_receiver` | |
| AR-8.5 | `POST /events` e `GET /events` (§8) | ✅ | `compat.post_event` / `get_events` | `tests/api/test_compat.py::test_post_events_e_idempotente`, `::test_get_events_since` | Guarda no Postgres, não em memória como diz o documento. Ver AR-7.15. |
| AR-8.6 | `GET /api/route`, `/api/receivers`, `/api/documents` (§8) | ✅ | `compat.api_route` / `api_receivers` / `api_documents` | `tests/api/test_compat.py::test_api_route_receivers_documents_sso` | |
| AR-8.7 | `POST /auth/sso` com token fake (§8) | ✅ | `compat.auth_sso` | `tests/api/test_compat.py::test_api_route_receivers_documents_sso` | |
| AR-8.8 | ASR em português (`pt-BR`) confirmado (§8) | ✅ | `agora_payload.montar_asr` (ARES pt-BR com palavras-chave; Deepgram e OpenAI como opção) | `tests/dominio/test_agora_payload.py::test_padrao_e_ares_com_palavras_chave`, `::test_deepgram_nova3_gerenciado_ptbr` | |
| AR-8.9 | Barge-in: o motorista interrompe o agente (estado `interrupted`, C1) (§3, §5.2) | ✅ | `montar_join`: `interruption.enable` (`start_of_speech`) | `tests/api/test_sessoes.py::test_dada_rota_quando_cria_sessao_entao_join_com_llm_proprio_e_ptbr` | O estado visual é do front. |
| AR-10.1 | Nomes de variáveis do documento (`AGORA_REST_KEY/SECRET`, `SIP_FROM_NUMBER`) (§10) | ✅ | `settings` (`AliasChoices`) | `tests/api/test_compat.py::test_aliases_de_env_do_doc` | `SIP_TRUNK_ADDRESS` não é usado (o `/call` usa o número importado na Agora). As chaves do Maps são do front. |
| AR-10.2 | `API_BASE_URL=http://localhost:8787` (§10) | 🟡 | `docker-compose.yml` (porta `8787:8000`) | — | |
| AR-9.1 | Tag de versão para a entrega (§9) | 🟡 | `git tag` → `v1.0-entrega` | — | |
| AR-9.2 | `check-rules.sh` (§9) | ❌ | — | — | Não existe no repositório. |

---

## Lacunas reais (❌ e ⚠️), em ordem de prioridade para a demo e a banca

1. **CP-3.1.1c / CP-6.8: a chegada não pede confirmação por voz e é validada sem ela.** Isso fragiliza a "dupla prova + voz", que é o argumento da estadia. *Sugestão:* em `on_chegada(origem="gps")`, falar "Chegou em X? Confirma a chegada?" e manter o `EventoGeo` como `nao_validado` até `confirmar_chegada`.
2. **CP-6.5: a estadia é calculada sobre o peso da carga, não sobre a capacidade do veículo (Lei 11.442).** Um jurado do setor percebe que o R$ está errado. *Sugestão:* criar `Rota.capacidade_t` (padrão = `carga_t`), aceitar no `POST /rotas` e usar em `Estadia(capacidade_t=...)`.
3. **AJ-1a: atraso na estrada não avisa o recebedor (❌).** É a primeira linha da tabela do foco pós-mentoria. *Sugestão:* quando houver ocorrência `atraso` ou o horário previsto passar da `janela_descarga`, chamar `ligacoes.ligar(motivo="atraso")` com o novo horário e registrar `ReceiverNotified`.
4. **CP-3.5f / CP-7.3 / AR-6.3e: os canais push → painel → ligação são só rótulos.** Já está declarado no README; o risco é a banca perguntar "e se o CCO ignorar?". *Sugestão:* no nível `ligacao`, usar `/speak` de um agente no canal do CCO (o `UID_CCO` já existe) ou dizer no pitch que é simulado.
5. **AR-7.15: o outbox não se reconcilia.** A `idempotencyKey` e o `occurredAt` do app não voltam no `GET /events`, e tipos não suportados são ignorados sem aviso. *Sugestão:* propagar `idempotency_key` e `occurredAt` para o evento derivado em `_aplicar` e responder 422 para tipo não suportado.
6. **CP-3.5j / CP-4.10 / CP-6.1: a `RegraEscalonamento` está pela metade.** `intervalo_s` e `acao_final` são ignorados e não há endpoint. *Sugestão:* usar `regra.intervalo_s` em `_regra` e expor `GET/PUT /regras/escalonamento`.
7. **CP-3.1.1f: GPS sem sinal não alerta o CCO.** *Sugestão:* sem rastreador, ou com `rastreador_em` antigo, registrar `divergencia_gps` com motivo `rastreador_sem_sinal`.
8. **CP-7.7: o prompt do recebedor não proíbe prometer em nome do CCO.** *Sugestão:* uma linha em `prompts.recebedor`: "Não prometa nada em nome da central; diga que vai repassar".
9. **AR-6.2.10: a latência p50/p95 mede só o LLM.** *Sugestão:* chamar o número de "latência do nosso LLM", ou ler as métricas da Agora (o `enable_metrics` já está ligado) para o tempo ponta a ponta.
10. **CP-2.5 / CP-4.5 / CP-7.11: os campos obrigatórios estão fixos e não há critério por campo.** *Sugestão:* `RegraReporte` por rota (JSON de campos e uma regex mínima por campo) lida em `reportes.registrar`.
11. **CP-3.3c: o motorista não tem como pedir o contato da central.** *Sugestão:* `Empresa.telefone_cco` e uma linha no `prompts._carga`.
12. **CP-4.6: `Reporte` sem localização.** *Sugestão:* gravar `Rota.ultima_lat/lng` no `reportes.registrar`.
13. **AR-6.2.2: não existe "estadia cobrada".** *Sugestão:* declarar como fora do MVP ou criar `Estadia.cobrada_em/valor_cobrado`.
14. **AR-2.2: os tipos TS em `clients/tipos.ts` estão desatualizados** (sem `DomainEvent`, `EventType` nem `pergunta_documento`). *Sugestão:* gerar a partir do `/openapi.json` e acrescentar o `EventType` do §7.
15. **AR-9.2: falta o `check-rules.sh` (❌, baixo impacto).** *Sugestão:* script que confere `.env` fora do git, a tag de versão e as seções obrigatórias do README.
