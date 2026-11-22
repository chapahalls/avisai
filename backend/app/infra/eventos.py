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
    """Filtro: por rota (rota_id) ou por motorista (motorista_id: as rotas dele + atribuições novas)."""

    def __init__(self, rota_id: Optional[int] = None, motorista_id: Optional[int] = None, rotas: Optional[set] = None):
        self.rota_id = rota_id
        self.motorista_id = motorista_id
        self.rotas: set = set(rotas or ())
        self.fila: asyncio.Queue = asyncio.Queue(maxsize=1000)

    def aceita(self, rota_id: Optional[int], motorista_id: Optional[int]) -> bool:
        if self.motorista_id is not None:
            if motorista_id == self.motorista_id and rota_id is not None:
                self.rotas.add(rota_id)  # rota recém-atribuída passa a ser acompanhada
                return True
            if rota_id not in self.rotas:
                return False
            # Uma reatribuição retira a viagem do filtro anterior. Isso é escopo
            # operacional do stream, não autenticação por motorista_id.
            from .models import Rota

            with sessao() as s:
                rota = s.get(Rota, rota_id)
                owned = rota is not None and rota.motorista_id == self.motorista_id
            if not owned:
                self.rotas.discard(rota_id)
            return owned
        return self.rota_id is None or rota_id is None or rota_id == self.rota_id


class Eventos:
    """Porta `Eventos`: registrar (grava + publica) e publicar (só stream)."""

    def __init__(self) -> None:
        self._assinantes: set[Assinatura] = set()

    def assinar(self, rota_id: Optional[int] = None, motorista_id: Optional[int] = None) -> Assinatura:
        rotas = None
        if motorista_id is not None:
            from sqlmodel import select

            from .models import Rota

            with sessao() as s:
                rotas = set(s.exec(select(Rota.id).where(Rota.motorista_id == motorista_id)).all())
        a = Assinatura(rota_id, motorista_id, rotas)
        self._assinantes.add(a)
        return a

    def cancelar(self, a: Assinatura) -> None:
        self._assinantes.discard(a)

    def publicar(self, canal: str, payload: dict, rota_id: Optional[int] = None, motorista_id: Optional[int] = None) -> None:
        msg = dumps(payload)
        for a in list(self._assinantes):
            if not a.aceita(rota_id, motorista_id):
                continue
            try:
                a.fila.put_nowait((canal, msg))
            except asyncio.QueueFull:
                pass

    def registrar(self, tipo: TipoEvento, mensagem: str, rota_id: Optional[int] = None, **dados: Any) -> Evento:
        fonte = dados.pop("_fonte", "system")
        dados_json = json.loads(dumps(dados))
        with sessao() as s:
            ev = Evento(rota_id=rota_id, tipo=str(tipo), mensagem=mensagem, dados=dados_json, source=fonte)
            s.add(ev)
            s.commit()
            s.refresh(ev)
        log.info("[%s] rota=%s %s", tipo, rota_id, mensagem)
        self.publicar("evento", envelope(ev), rota_id, dados.get("motorista_id"))
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
