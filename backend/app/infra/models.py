"""Modelo de dados (contexto-produto.md, seção 4), sem audio_url e sem saúde do motorista."""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def agora() -> datetime:
    """UTC sem tzinfo (o relógio injetável dos serviços usa o mesmo formato)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


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


class Motorista(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    empresa_id: int = Field(foreign_key="empresa.id")
    nome: str
    telefone_e164: Optional[str] = None


class Rota(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    empresa_id: int = Field(foreign_key="empresa.id")
    motorista_id: int = Field(foreign_key="motorista.id")
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
    janela_descarga: str = ""
    recebedor_empresa: str = ""
    recebedor_nome: str = ""
    recebedor_telefone_e164: str = ""
    aproximacao_min: float = 15
    raio_chegada_m: float = 300
    ultima_lat: Optional[float] = None
    ultima_lng: Optional[float] = None
    ultima_posicao_em: Optional[datetime] = None
    eta_min: Optional[float] = None
    distancia_m: Optional[float] = None


class Ocorrencia(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    rota_id: int = Field(foreign_key="rota.id")
    tipo: str
    descricao: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    timestamp: datetime = Field(default_factory=agora)
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
    """Uma instância de agente ConvoAI (motorista ou recebedor)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    rota_id: int = Field(foreign_key="rota.id")
    papel: str = "motorista"  # motorista | recebedor
    ligacao_id: Optional[int] = Field(default=None, foreign_key="ligacaorecebedor.id")
    canal: str
    agent_uid: int
    user_uid: int
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
    tipo: str
    mensagem: str
    dados: dict = Field(default_factory=dict, sa_column=Column(JSON))
    timestamp: datetime = Field(default_factory=agora)
