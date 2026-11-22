import asyncio

from sqlmodel import select

from app.infra.db import sessao
from app.infra.models import Evento


async def esperar(cond, timeout: float = 3.0, passo: float = 0.02):
    """Espera uma condição de tarefa em segundo plano ficar verdadeira."""
    t = 0.0
    while t < timeout:
        v = cond()
        if v:
            return v
        await asyncio.sleep(passo)
        t += passo
    raise AssertionError("condição não ocorreu a tempo")


def eventos(tipo: str | None = None) -> list[Evento]:
    with sessao() as s:
        q = select(Evento).order_by(Evento.id)
        if tipo:
            q = q.where(Evento.tipo == tipo)
        return s.exec(q).all()


def obter(modelo, id_):
    with sessao() as s:
        return s.get(modelo, id_)
