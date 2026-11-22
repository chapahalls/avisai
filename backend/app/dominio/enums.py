"""Vocabulário comum: banco, serviços, SSE/WS e front usam estes valores."""
from enum import StrEnum


class StatusRota(StrEnum):
    PUBLICADA = "publicada"  # transportadora publicou, sem motorista
    PLANEJADA = "planejada"  # atribuída a um motorista, viagem não iniciada
    NA_ORIGEM = "na_origem"
    EM_TRANSITO = "em_transito"
    APROXIMANDO = "aproximando"
    NO_DESTINO = "no_destino"
    DESCARREGADA = "descarregada"


class StatusTask(StrEnum):
    PENDENTE = "pendente"
    CONFIRMADA = "confirmada"
    ESCALADA_RECEBEDOR = "escalada_recebedor"
    CONCLUIDA = "concluida"


class StatusLigacao(StrEnum):
    CHAMANDO = "chamando"
    EM_ANDAMENTO = "em_andamento"
    RESPONDIDA = "respondida"
    NAO_ATENDIDA = "nao_atendida"
    FALHOU = "falhou"


class StatusSessao(StrEnum):
    INICIANDO = "iniciando"
    ATIVA = "ativa"
    ENCERRADA = "encerrada"
    FALHOU = "falhou"


class Papel(StrEnum):
    MOTORISTA = "motorista"
    RECEBEDOR = "recebedor"
    OPERADOR = "operador"


class TipoGeo(StrEnum):
    RETIRADA = "RETIRADA"
    APROXIMACAO = "APROXIMACAO"
    CHEGADA = "CHEGADA"
    DESCARGA = "DESCARGA"


class Canal(StrEnum):
    PUSH = "push"
    PAINEL = "painel"
    LIGACAO = "ligacao"


class Prioridade(StrEnum):
    NORMAL = "normal"
    ALTA = "alta"
    CRITICA = "critica"


class ModoLigacao(StrEnum):
    RTC = "rtc"  # plano B
    SIP = "sip"  # plano A


class TipoEvento(StrEnum):
    SESSAO_INICIADA = "sessao_iniciada"
    SESSAO_ENCERRADA = "sessao_encerrada"
    APROXIMACAO = "aproximacao"
    CHEGADA = "chegada"
    CHEGADA_CONFIRMADA_VOZ = "chegada_confirmada_voz"
    NOTIFICACAO_CCO = "notificacao_cco"
    ESCALADA_RECEBEDOR = "escalada_recebedor"
    TASK_CONFIRMADA = "task_confirmada"
    LIGACAO_RECEBEDOR = "ligacao_recebedor"
    LIGACAO_FALHOU = "ligacao_falhou"
    FALLBACK_PLANO_B = "fallback_plano_b"
    LIGACAO_NAO_ATENDIDA = "ligacao_nao_atendida"
    RESPOSTA_RECEBEDOR = "resposta_recebedor"
    OCORRENCIA = "ocorrencia"
    DESCARGA = "descarga"
    FALA_MOTORISTA = "fala_motorista"
    FALA_RECEBEDOR = "fala_recebedor"
    FALA_AGENTE = "fala_agente"
    RETIRADA_DETECTADA = "retirada_detectada"
    RETIRADA = "retirada"
    RELATORIO = "relatorio"
    CAMPO_FALTANTE = "campo_faltante"
    TASK_CRIADA = "task_criada"
    AVISO_RECEBEDOR = "aviso_recebedor"
    NAO_RECEBE_HOJE = "nao_recebe_hoje"
    PEDIDO_CENTRAL = "pedido_central"
    RESPOSTA_CENTRAL = "resposta_central"
    CHAMADO_CCO_ABERTO = "chamado_cco_aberto"
    CHAMADO_CCO_LEMBRETE = "chamado_cco_lembrete"
    CHAMADO_CCO_RESPONDIDO = "chamado_cco_respondido"
    CHAMADO_CCO_TIMEOUT = "chamado_cco_timeout"
    DIVERGENCIA_GPS = "divergencia_gps"
    EVENTO_APP = "evento_app"
    ROTA_PUBLICADA = "rota_publicada"
    ROTA_ATRIBUIDA = "rota_atribuida"
    PERGUNTA_DOCUMENTO = "pergunta_documento"
    OCORRENCIA_DETALHADA = "ocorrencia_detalhada"
    OCORRENCIA_GRAVE = "ocorrencia_grave"
    ARQUIVO_ADICIONADO = "arquivo_adicionado"
    ALERTA_MOTORISTA = "alerta_motorista"
    DECISAO_AGENTE = "decisao_agente"
    MENSAGEM_MOTORISTA_ENVIADA = "mensagem_motorista_enviada"
    MENSAGEM_MOTORISTA_FALADA = "mensagem_motorista_falada"
    MENSAGEM_MOTORISTA_RESPONDIDA = "mensagem_motorista_respondida"
    MOTORISTA_OFFLINE = "motorista_offline"
    CHAMADA_TWILIO_FALHOU = "chamada_twilio_falhou"
    CHAMADA_AGORA_INICIADA = "chamada_agora_iniciada"
    CHAMADA_AGORA_ATENDIDA = "chamada_agora_atendida"
    CHAMADA_SEM_RESPOSTA = "chamada_sem_resposta"
    ESCALADA_SUPERVISOR = "escalada_supervisor"
