"""Contrato com o front (aparece no /openapi.json; gere tipos com openapi-typescript)."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class TokenOut(BaseModel):
    app_id: str
    channel: str
    uid: int
    token: str


class NovaSessao(BaseModel):
    rota_id: int = 1


class SessaoOut(BaseModel):
    id: int
    rota_id: int
    papel: str
    canal: str
    agent_uid: int
    user_uid: int
    agent_id: Optional[str]
    status: str
    llm_mode: str
    criada_em: datetime
    encerrada_em: Optional[datetime] = None
    erro: Optional[str] = None
    app_id: Optional[str] = None
    token: Optional[str] = None


class Fala(BaseModel):
    texto: str
    prioridade: str = "APPEND"


class Posicao(BaseModel):
    lat: float
    lng: float
    velocidade_kmh: Optional[float] = None
    precisao_m: Optional[float] = None
    fonte: str = "celular"  # celular (GPS do app) | rastreador (GPS do caminhão)


class NovaSolicitacao(BaseModel):
    pergunta: str


class PosicaoOut(BaseModel):
    rota_id: int
    distancia_m: float
    eta_min: float
    status: str
    disparos: list[str]


class Confirmar(BaseModel):
    confirmado_por: str = "CCO"


class Descarga(BaseModel):
    por: str = "CCO"


class Ligar(BaseModel):
    motivo: str = "cco_sem_resposta"


class EventoStream(BaseModel):
    """Envelope dos eventos no SSE (/cco/stream, evento `evento`) e no WS (/ws)."""
    id: int
    tipo: str
    rota_id: Optional[int]
    timestamp: datetime
    mensagem: str
    dados: dict[str, Any]


class DomainEventIn(BaseModel):
    """Evento do outbox do app (docs/arquitetura-avisai.md, seção 7)."""
    id: Optional[str] = None
    idempotencyKey: str
    tripId: str
    type: str
    occurredAt: Optional[str] = None
    source: str = "driver"
    payload: dict[str, Any] = {}
