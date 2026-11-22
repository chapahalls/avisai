"""Contratos entre as áreas (typing.Protocol). Cada porta tem um adaptador real e um fake de teste."""
from datetime import datetime
from typing import AsyncIterator, Optional, Protocol


class AgoraGateway(Protocol):
    """REST da Conversational AI (plano de controle). Implementação: integracoes/agora_rest.py."""

    async def join(self, corpo: dict) -> str: ...
    async def leave(self, agent_id: str, canal: str, agent_uid: int) -> None: ...
    async def speak(self, agent_id: str, texto: str, prioridade: str, canal: str, agent_uid: int) -> None: ...
    async def call(self, corpo: dict) -> str: ...
    async def call_status(self, agent_id: str, canal: str, agent_uid: int) -> dict: ...
    async def hangup(self, agent_id: str, canal: str, agent_uid: int) -> None: ...


class LLM(Protocol):
    """LLM upstream (OpenAI-compatível). Implementação: integracoes/openai_llm.py."""

    def stream(self, mensagens: list[dict], ferramentas: list[dict]) -> AsyncIterator[dict]:
        """Eventos {"texto": str} conforme chegam, ou {"tool_calls": [...]} completo."""
        ...


class Relogio(Protocol):
    def agora(self) -> datetime: ...


class Voz(Protocol):
    """Fala proativa com o motorista (por cima do AgoraGateway)."""

    async def falar_motorista(self, rota_id: int, texto: str, prioridade: str = "APPEND") -> bool: ...


class Discador(Protocol):
    """Estratégia de ligação ao recebedor: RTC (plano B) ou SIP (plano A)."""

    modo: str

    async def ligar(self, corpo_join: dict, numero: str) -> str: ...
    async def encerrar(self, agent_id: str, canal: str, agent_uid: int) -> None: ...
    async def estado(self, agent_id: str, canal: str, agent_uid: int) -> Optional[str]: ...
