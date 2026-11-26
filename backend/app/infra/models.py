"""Modelo de dados (contexto-produto.md, seção 4), sem audio_url e sem saúde do motorista."""
from datetime import datetime, UTC
from typing import Optional

from sqlalchemy import JSON, CheckConstraint, Column
from sqlmodel import Field, SQLModel


def agora() -> datetime:
    """Retorna o horário atual em UTC com timezone explícito."""
    return datetime.now(UTC)


class Empresa(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    nome: str


class RegraEscalonamento(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    empresa_id: int = Field(foreign_key="empresa.id")
    max_tentativas: int = 3
    intervalo_s: float = 20
    niveis: list = Field(default_factory=lambda: ["push", "painel", "ligacao"], sa_column=Column(JSON))
    acao_final: str = "ligar_recebedor"
    acao_nao_recebe: str = "Aguardar no pátio do recebedor e reagendar a descarga para amanhã às 8h. O CCO decide se o caminhão volta."


class Motorista(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    empresa_id: int = Field(foreign_key="empresa.id")
    nome: str
    telefone_e164: Optional[str] = None
    email: Optional[str] = Field(default=None, index=True)  # login SSO (mock)


class Usuario(SQLModel, table=True):
    """Perfil persistido da demo; não representa autenticação real."""
    __table_args__ = (
        CheckConstraint(
            "(papel = 'cco' AND motorista_id IS NULL AND nome IS NOT NULL) OR "
            "(papel = 'driver' AND motorista_id IS NOT NULL AND nome IS NULL)",
            name="ck_usuario_papel_identidade",
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    # O nome do motorista tem uma única fonte: Motorista.nome.
    nome: Optional[str] = None
    papel: str
    motorista_id: Optional[int] = Field(default=None, foreign_key="motorista.id", unique=True)


class Rota(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    empresa_id: int = Field(foreign_key="empresa.id")
    motorista_id: Optional[int] = Field(default=None, foreign_key="motorista.id")  # vazio = publicada sem motorista
    publicada_em: Optional[datetime] = None
    atribuida_em: Optional[datetime] = None
    origem_nome: str
    origem_lat: float
    origem_lng: float
    destino_nome: str
    destino_lat: float
    destino_lng: float
    trajeto: list = Field(default_factory=list, sa_column=Column(JSON))  # [[lat, lng], ...]
    # planejada | em_transito | aproximando | no_destino | descarregada
    status: str = "planejada"
    placa: str = ""
    nota_fiscal: str = ""
    carga_descricao: str = ""
    carga_t: float = 0
    capacidade_t: Optional[float] = None  # capacidade total do veículo (base da estadia, Lei 11.442)
    janela_descarga: str = ""
    recebedor_empresa: str = ""
    recebedor_nome: str = ""
    recebedor_telefone_e164: str = ""
    aproximacao_min: float = 15
    raio_chegada_m: float = 300
    raio_origem_m: float = 300
    rastreador_lat: Optional[float] = None  # GPS do caminhão (simulado na demo)
    rastreador_lng: Optional[float] = None
    rastreador_em: Optional[datetime] = None
    ultima_lat: Optional[float] = None
    ultima_lng: Optional[float] = None
    ultima_posicao_em: Optional[datetime] = None
    eta_min: Optional[float] = None
    distancia_m: Optional[float] = None


class ArquivoRota(SQLModel, table=True):
    """Anexo imutável da viagem; a chave interna nunca é fornecida pelo cliente."""
    __tablename__ = "arquivo_rota"
    id: Optional[int] = Field(default=None, primary_key=True)
    rota_id: int = Field(foreign_key="rota.id", index=True)
    nome_original: str
    tipo_mime: str
    tamanho_bytes: int
    categoria: str = "documento"
    descricao: Optional[str] = None
    chave_storage: str = Field(unique=True)
    criado_em: datetime = Field(default_factory=agora)


class Ocorrencia(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    rota_id: int = Field(foreign_key="rota.id")
    tipo: str
    descricao: str
    km: Optional[float] = None
    rodovia: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    timestamp: datetime = Field(default_factory=agora)
    transcricao: Optional[str] = None
    detalhes: dict = Field(default_factory=dict, sa_column=Column(JSON))  # respostas do aprofundamento
    faltantes: list = Field(default_factory=list, sa_column=Column(JSON))  # perguntas ainda não respondidas
    completa: bool = False


class ChamadoCCO(SQLModel, table=True):
    """Pedido aberto pelo motorista para o CCO, com resposta falada pelo agente."""
    id: Optional[int] = Field(default=None, primary_key=True)
    rota_id: int = Field(foreign_key="rota.id", index=True)
    tipo: str  # ocorrencia | chegada | mensagem
    assunto: str
    descricao: str
    km: Optional[float] = None
    rodovia: Optional[str] = None
    ocorrencia_id: Optional[int] = Field(default=None, foreign_key="ocorrencia.id")
    status: str = "aguardando_cco"  # coletando | aguardando_cco | respondido | timeout
    tentativas: int = 0
    max_tentativas: int = 5
    intervalo_s: float = 30
    criada_em: datetime = Field(default_factory=agora)
    ultima_notificacao: Optional[datetime] = None
    respondida_em: Optional[datetime] = None
    resposta: Optional[str] = None
    respondido_por: Optional[str] = None
    transcricao: Optional[str] = None


class EventoGeo(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    rota_id: int = Field(foreign_key="rota.id")
    tipo: str  # RETIRADA | APROXIMACAO | CHEGADA | DESCARGA
    lat: Optional[float] = None
    lng: Optional[float] = None
    precisao_m: Optional[float] = None
    timestamp: datetime = Field(default_factory=agora)
    distancia_m: Optional[float] = None
    caminhao_lat: Optional[float] = None
    caminhao_lng: Optional[float] = None
    divergencia_m: Optional[float] = None  # celular × rastreador
    confirmacao_voz_transcricao: Optional[str] = None
    confirmacao_voz_em: Optional[datetime] = None
    status: str = "nao_validado"  # validado | nao_validado


class TaskCCO(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    rota_id: int = Field(foreign_key="rota.id")
    tipo: str = "chegada"
    # pendente | confirmada | escalada_recebedor | concluida
    status: str = "pendente"
    prioridade: str = "normal"  # normal | alta | critica
    tentativas: int = 0
    canal_atual: Optional[str] = None  # push | painel | ligacao
    criada_em: datetime = Field(default_factory=agora)
    ultima_notificacao: Optional[datetime] = None
    confirmado_em: Optional[datetime] = None
    confirmado_por: Optional[str] = None
    resposta_recebedor: Optional[str] = None
    concluida_em: Optional[datetime] = None


class LigacaoRecebedor(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: Optional[int] = Field(default=None, foreign_key="taskcco.id")
    rota_id: int = Field(foreign_key="rota.id")
    motivo: str = "cco_sem_resposta"  # aproximacao | cco_sem_resposta
    modo: str = "rtc"  # sip (plano A) | rtc (plano B)
    numero: str = ""
    canal: Optional[str] = None
    sessao_id: Optional[int] = None  # SessaoAgente do agente que liga
    agent_id: Optional[str] = None
    # chamando | em_andamento | respondida | nao_atendida | falhou
    status: str = "chamando"
    iniciada_em: datetime = Field(default_factory=agora)
    encerrada_em: Optional[datetime] = None
    atendida: bool = False
    previsao: Optional[str] = None
    doca: Optional[str] = None
    motivo_espera: Optional[str] = None
    resposta_resumo: Optional[str] = None
    transcricao: list = Field(default_factory=list, sa_column=Column(JSON))
    erro: Optional[str] = None
    enviada_cco_em: Optional[datetime] = None
    enviada_motorista_em: Optional[datetime] = None


class Estadia(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    rota_id: int = Field(foreign_key="rota.id")
    inicio: datetime = Field(default_factory=agora)  # = chegada_em
    fim: Optional[datetime] = None
    franquia_h: float = 5
    capacidade_t: float = 0
    valor_t_h: float = 2.50


class SessaoAgente(SQLModel, table=True):
    """Uma instância de agente LiveKit (motorista, recebedor ou operador)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    rota_id: int = Field(foreign_key="rota.id")
    papel: str = "motorista"  # motorista | recebedor
    ligacao_id: Optional[int] = Field(default=None, foreign_key="ligacaorecebedor.id")
    canal: str
    agent_id: Optional[str] = None
    status: str = "iniciando"  # iniciando | ativa | encerrada | falhou
    llm_mode: str = "custom"
    criada_em: datetime = Field(default_factory=agora)
    encerrada_em: Optional[datetime] = None
    erro: Optional[str] = None


class Evento(SQLModel, table=True):
    """Linha do tempo: tudo o que o CCO vê no stream e o que vira prova."""
    id: Optional[int] = Field(default=None, primary_key=True)
    rota_id: Optional[int] = None
    idempotency_key: Optional[str] = Field(default=None, unique=True, index=True)  # outbox do app
    source: str = "system"  # driver | agent | cco | system
    tipo: str
    mensagem: str
    dados: dict = Field(default_factory=dict, sa_column=Column(JSON))
    timestamp: datetime = Field(default_factory=agora)


class Reporte(SQLModel, table=True):
    """Relatório por voz (inicial ou check-in) com validação de completude."""
    id: Optional[int] = Field(default=None, primary_key=True)
    rota_id: int = Field(foreign_key="rota.id")
    tipo: str  # inicial | checkin
    campos: dict = Field(default_factory=dict, sa_column=Column(JSON))
    faltantes: list = Field(default_factory=list, sa_column=Column(JSON))
    completo: bool = False
    perguntas_complemento: int = 0
    transcricao: list = Field(default_factory=list, sa_column=Column(JSON))
    criado_em: datetime = Field(default_factory=agora)
    completo_em: Optional[datetime] = None


class SolicitacaoCentral(SQLModel, table=True):
    """Pedido da central: o agente pergunta ao motorista e devolve a resposta estruturada."""
    id: Optional[int] = Field(default=None, primary_key=True)
    rota_id: int = Field(foreign_key="rota.id")
    pergunta: str
    resposta: Optional[str] = None
    status: str = "pendente"  # pendente | perguntada | respondida
    criada_em: datetime = Field(default_factory=agora)
    respondida_em: Optional[datetime] = None
    transcricao: Optional[str] = None


class MensagemMotorista(SQLModel, table=True):
    """Mensagem da CCO que o agente fala e cuja resposta mantém o vínculo original."""
    id: Optional[int] = Field(default=None, primary_key=True)
    rota_id: int = Field(foreign_key="rota.id", index=True)
    remetente: str
    texto: str
    # enviada | falada | respondida | offline
    status: str = "enviada"
    criada_em: datetime = Field(default_factory=agora)
    falada_em: Optional[datetime] = None
    respondida_em: Optional[datetime] = None
    resposta: Optional[str] = None
    transcricao_resposta: Optional[str] = None


class ChamadaAgente(SQLModel, table=True):
    """Cascata de chamada do agente: Twilio, RTC do operador e escalonamento."""
    id: Optional[int] = Field(default=None, primary_key=True)
    rota_id: int = Field(foreign_key="rota.id", index=True)
    destino: str  # operador | supervisor | motorista
    motivo: str
    # iniciada | twilio_atendida | livekit_tocando | atendida | sem_resposta | escalada | falhou
    status: str = "iniciada"
    twilio_sid: Optional[str] = None
    twilio_resultado: Optional[str] = None
    livekit_room: Optional[str] = None
    sessao_id: Optional[int] = Field(default=None, foreign_key="sessaoagente.id")
    iniciada_em: datetime = Field(default_factory=agora)
    atendida_em: Optional[datetime] = None
    encerrada_em: Optional[datetime] = None
    erro: Optional[str] = None
