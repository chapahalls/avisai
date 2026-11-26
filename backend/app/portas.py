"""Contratos entre as áreas (typing.Protocol). Cada porta tem um adaptador real e um fake de teste."""
from datetime import datetime
from typing import AsyncIterator, Optional, Protocol


class LiveKitGateway(Protocol):
    """LiveKit Server API: dispatch, participantes, controlo e SIP."""

    async def dispatch(self, room: str, metadata: dict) -> str: ...
    async def remove(self, room: str, identity: str) -> None: ...
    async def send_control(self, room: str, identity: str, message: dict) -> None: ...
    async def dial(self, room: str, number: str, identity: str, *, wait: bool = False) -> str: ...
    async def participant_present(self, room: str, identity: str) -> bool: ...
    async def sip_call_status(self, room: str, identity: str) -> Optional[str]: ...


class LLM(Protocol):
    """LLM upstream (OpenAI-compatível). Implementação: integracoes/openai_llm.py."""

    def stream(self, mensagens: list[dict], ferramentas: list[dict]) -> AsyncIterator[dict]:
        """Eventos {"texto": str} conforme chegam, ou {"tool_calls": [...]} completo."""
        ...


class Transcritor(Protocol):
    """Fala gravada → texto (OpenAI-compatível). Implementação: integracoes/openai_stt.py."""

    async def transcrever(self, audio: bytes, nome: str, tipo_mime: str) -> str: ...


class Relogio(Protocol):
    def agora(self) -> datetime: ...


class Voz(Protocol):
    """Fala proativa com o motorista (por cima do LiveKitGateway)."""

    async def falar_motorista(self, rota_id: int, texto: str, prioridade: str = "APPEND") -> bool: ...


class Discador(Protocol):
    """Estratégia de ligação ao recebedor: RTC (plano B) ou SIP (plano A)."""

    modo: str

    async def ligar(self, room: str, numero: str, identity: str) -> str: ...
    async def encerrar(self, room: str, identity: str) -> None: ...
    async def estado(self, room: str, identity: str) -> Optional[str]: ...


class Geocodificador(Protocol):
    """Endereço digitado → lugares candidatos com coordenada. Implementação: integracoes/nominatim.py."""

    provedor: str
    atribuicao: str  # crédito exigido pelo provedor, mostrado junto dos resultados

    async def buscar(self, consulta: str, limite: int = 5) -> list[dict]:
        """[{id, endereco, lat, lng, tipo}] na ordem de relevância do provedor; [] quando nada casa."""
        ...
