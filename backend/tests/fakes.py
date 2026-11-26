"""Fakes das portas de voz, LLM e relógio para testes de serviço e de API."""
import itertools
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from app.integracoes.livekit import LiveKitErro


@dataclass
class FakeLiveKit:
    dispatches: list = field(default_factory=list)
    removals: list = field(default_factory=list)
    speaks: list = field(default_factory=list)
    dial_requests: list = field(default_factory=list)
    falhar_dispatch: Optional[Exception] = None
    falhar_dial: Optional[Exception] = None
    sip_status: str = "active"
    participantes: set = field(default_factory=set)
    dispatch_id_by_identity: dict = field(default_factory=dict)
    _seq: Any = field(default_factory=lambda: itertools.count(1))

    async def dispatch(self, room: str, metadata: dict) -> str:
        if self.falhar_dispatch:
            raise self.falhar_dispatch
        dispatch_id = f"dispatch-{next(self._seq)}"
        self.dispatches.append({"id": dispatch_id, "room": room, "metadata": metadata})
        self.participantes.add((room, metadata["agent_identity"]))
        self.dispatch_id_by_identity[metadata["agent_identity"]] = dispatch_id
        return dispatch_id

    async def remove(self, room: str, identity: str) -> None:
        self.removals.append((room, identity))
        self.participantes.discard((room, identity))

    async def send_control(self, room: str, identity: str, message: dict) -> None:
        self.speaks.append({"agent_id": self.dispatch_id_by_identity.get(identity), "identity": identity,
                            "texto": message["text"],
                            "prioridade": message.get("priority", "APPEND")})

    async def dial(self, room: str, number: str, identity: str, *, wait: bool = False) -> str:
        if self.falhar_dial:
            raise self.falhar_dial
        self.dial_requests.append({"room": room, "number": number, "identity": identity})
        self.participantes.add((room, identity))
        return identity

    async def participant_present(self, room: str, identity: str) -> bool:
        return (room, identity) in self.participantes

    async def sip_call_status(self, room: str, identity: str) -> Optional[str]:
        return self.sip_status if (room, identity) in self.participantes else None

    def falas(self) -> list[str]:
        return [item["texto"] for item in self.speaks]


@dataclass
class FakeLLM:
    """Devolve mensagens roteirizadas; grava o que recebeu."""

    respostas: list = field(default_factory=list)
    recebidas: list = field(default_factory=list)
    falhar: bool = False

    async def stream(self, mensagens: list[dict], ferramentas: list[dict]):
        self.recebidas.append({"mensagens": [dict(m) for m in mensagens], "ferramentas": ferramentas})
        if self.falhar:
            raise RuntimeError("LLM fora do ar")
        r = self.respostas.pop(0) if self.respostas else "Certo."
        if isinstance(r, dict):
            yield {"tool_calls": r["tool_calls"]}
            return
        for parte in r.split(" "):
            yield {"texto": parte + " "}


@dataclass
class FakeTranscritor:
    """Transcrição roteirizada; grava os áudios recebidos."""

    texto: str = "Tem fila no km 120 da BR-116"
    recebidos: list = field(default_factory=list)
    falhar: bool = False

    async def transcrever(self, audio: bytes, nome: str, tipo_mime: str) -> str:
        self.recebidos.append({"bytes": len(audio), "nome": nome, "tipo_mime": tipo_mime})
        if self.falhar:
            raise RuntimeError("STT fora do ar")
        return self.texto


def tool_call(nome: str, args: str, cid: str = "call_1") -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": cid, "type": "function", "function": {"name": nome, "arguments": args}}],
    }


@dataclass
class RelogioFixo:
    t: datetime = field(default_factory=lambda: datetime(2026, 11, 22, 14, 0, 0, tzinfo=UTC))

    def agora(self) -> datetime:
        return self.t

    def avancar(self, **kw) -> None:
        self.t = self.t + timedelta(**kw)
