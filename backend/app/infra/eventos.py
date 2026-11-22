"""Barramento de eventos em memória (SSE do CCO e WS do app) + linha do tempo no banco."""
import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional

from ..dominio.enums import TipoEvento
from .db import sessao
from .models import Evento

log = logging.getLogger("avisai.eventos")


def serial(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat() + "Z"
    if hasattr(o, "model_dump"):
        return o.model_dump()
    raise TypeError(type(o))


def dumps(d: Any) -> str:
    return json.dumps(d, default=serial, ensure_ascii=False)


class Assinatura:
    def __init__(self, rota_id: Optional[int] = None):
        self.rota_id = rota_id
        self.fila: asyncio.Queue = asyncio.Queue(maxsize=1000)


class Eventos:
    """Porta `Eventos`: registrar (grava + publica) e publicar (só stream)."""

    def __init__(self) -> None:
        self._assinantes: set[Assinatura] = set()

    def assinar(self, rota_id: Optional[int] = None) -> Assinatura:
        a = Assinatura(rota_id)
        self._assinantes.add(a)
        return a

    def cancelar(self, a: Assinatura) -> None:
        self._assinantes.discard(a)

    def publicar(self, canal: str, payload: dict, rota_id: Optional[int] = None) -> None:
        msg = dumps(payload)
        for a in list(self._assinantes):
            if a.rota_id is not None and rota_id is not None and a.rota_id != rota_id:
                continue
            try:
                a.fila.put_nowait((canal, msg))
            except asyncio.QueueFull:
                pass

    def registrar(self, tipo: TipoEvento, mensagem: str, rota_id: Optional[int] = None, **dados: Any) -> Evento:
        dados_json = json.loads(dumps(dados))
        with sessao() as s:
            ev = Evento(rota_id=rota_id, tipo=str(tipo), mensagem=mensagem, dados=dados_json)
            s.add(ev)
            s.commit()
            s.refresh(ev)
        log.info("[%s] rota=%s %s", tipo, rota_id, mensagem)
        self.publicar("evento", envelope(ev), rota_id)
        return ev


def envelope(ev: Evento) -> dict:
    """Contrato EventoStream: {id, tipo, rota_id, timestamp, mensagem, dados}."""
    return {
        "id": ev.id,
        "tipo": ev.tipo,
        "rota_id": ev.rota_id,
        "timestamp": ev.timestamp,
        "mensagem": ev.mensagem,
        "dados": ev.dados,
    }
