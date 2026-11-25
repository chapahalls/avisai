"""Fakes das portas (portas.py) para testes de serviço e de API."""
import itertools
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from app.integracoes.agora_rest import AgoraErro


@dataclass
class FakeAgora:
    """Grava as chamadas e devolve agent_ids previsíveis."""

    joins: list = field(default_factory=list)
    leaves: list = field(default_factory=list)
    speaks: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    hangups: list = field(default_factory=list)
    falhar_join: Optional[AgoraErro] = None
    falhar_call: Optional[AgoraErro] = None
    estado_call: dict = field(default_factory=lambda: {"state": "answered"})
    _seq: Any = field(default_factory=lambda: itertools.count(1))

    async def join(self, corpo: dict) -> str:
        if self.falhar_join:
            raise self.falhar_join
        self.joins.append(corpo)
        return f"agent-{next(self._seq)}"

    async def leave(self, agent_id: str, canal: str, agent_uid: int) -> None:
        self.leaves.append(agent_id)

    async def speak(self, agent_id: str, texto: str, prioridade: str, canal: str, agent_uid: int) -> None:
        self.speaks.append({"agent_id": agent_id, "texto": texto, "prioridade": prioridade})

    async def call(self, corpo: dict) -> str:
        if self.falhar_call:
            raise self.falhar_call
        self.calls.append(corpo)
        return f"call-{next(self._seq)}"

    async def call_status(self, agent_id: str, canal: str, agent_uid: int) -> dict:
        return self.estado_call

    async def hangup(self, agent_id: str, canal: str, agent_uid: int) -> None:
        self.hangups.append(agent_id)

    def ultimo_join(self) -> dict:
        return self.joins[-1]

    def falas(self) -> list[str]:
        return [s["texto"] for s in self.speaks]


@dataclass
class FakeLLM:
    """Devolve mensagens roteirizadas; grava o que recebeu."""

    respostas: list = field(default_factory=list)
    recebidas: list = field(default_factory=list)
    falhar: bool = False

    async def stream(self, mensagens: list[dict], ferramentas: list[dict]):
        """Cada resposta roteirizada: str (texto em pedaços) ou dict de tool_call()."""
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
    t: datetime = field(default_factory=lambda: datetime(2026, 11, 22, 14, 0, 0))

    def agora(self) -> datetime:
        return self.t

    def avancar(self, **kw) -> None:
        self.t = self.t + timedelta(**kw)
