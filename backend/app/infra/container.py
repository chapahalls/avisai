"""Container de dependências: monta as portas reais; os testes trocam por fakes com `definir`."""
import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any, Optional

from .eventos import Eventos
from .settings import Settings

log = logging.getLogger("avisai.container")


class RelogioSistema:
    def agora(self) -> datetime:
        return datetime.now(UTC)


@dataclass
class Container:
    settings: Settings
    livekit: Any  # portas.LiveKitGateway
    llm: Any  # portas.LLM
    twilio: Any = None  # integrações.twilio.TwilioGateway; opcional para testes sem PSTN
    transcritor: Any = None  # portas.Transcritor; sem ele a fala offline fica guardada sem texto
    relogio: Any = field(default_factory=RelogioSistema)  # portas.Relogio
    eventos: Eventos = field(default_factory=Eventos)
    tarefas: dict = field(default_factory=dict)
    latencias: deque = field(default_factory=lambda: deque(maxlen=200))  # ms até o 1º trecho do LLM

    def em_segundo_plano(self, chave: str, coro) -> asyncio.Task:
        antiga = self.tarefas.get(chave)
        if antiga and not antiga.done():
            antiga.cancel()
        t = asyncio.create_task(coro)
        self.tarefas[chave] = t

        def _fim(tt: asyncio.Task) -> None:
            if not tt.cancelled() and tt.exception():
                log.error("tarefa %s falhou", chave, exc_info=tt.exception())

        t.add_done_callback(_fim)
        return t


_atual: Optional[Container] = None


def padrao() -> Container:
    from ..integracoes.livekit import LiveKitGateway
    from ..integracoes.openai_llm import OpenAILLM
    from ..integracoes.openai_stt import OpenAITranscritor

    s = Settings()
    return Container(settings=s, livekit=LiveKitGateway(s), llm=OpenAILLM(s),
                     transcritor=OpenAITranscritor(s) if s.llm_api_key else None)


def atual() -> Container:
    global _atual
    if _atual is None:
        _atual = padrao()
    return _atual


def definir(c: Container) -> None:
    global _atual
    _atual = c


def cancelar_tarefas() -> None:
    if _atual:
        for t in _atual.tarefas.values():
            t.cancel()
        _atual.tarefas.clear()
