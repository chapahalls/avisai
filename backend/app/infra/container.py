"""Container de dependências: monta as portas reais; os testes trocam por fakes com `definir`."""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .eventos import Eventos
from .settings import Settings

log = logging.getLogger("avisai.container")


class RelogioSistema:
    def agora(self) -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class Container:
    settings: Settings
    agora: Any  # portas.AgoraGateway
    llm: Any  # portas.LLM
    relogio: Any = field(default_factory=RelogioSistema)  # portas.Relogio
    eventos: Eventos = field(default_factory=Eventos)
    tarefas: dict = field(default_factory=dict)

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
    from ..integracoes.agora_rest import AgoraRest
    from ..integracoes.openai_llm import OpenAILLM

    s = Settings()
    return Container(settings=s, agora=AgoraRest(s), llm=OpenAILLM(s))


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
