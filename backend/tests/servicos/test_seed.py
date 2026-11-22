"""Peça 9: seed da demo."""
import re

from sqlmodel import select

from app.infra.db import sessao
from app.infra.models import Empresa, Motorista, RegraEscalonamento, Rota
from app.seed import seed


async def test_seed_cria_dados_da_demo(container):
    rid = seed()
    with sessao() as s:
        assert len(s.exec(select(Empresa)).all()) == 1
        assert len(s.exec(select(Motorista)).all()) == 1
        r = s.get(Rota, rid)
        regra = s.exec(select(RegraEscalonamento)).one()
    assert r.origem_nome and r.destino_nome and len(r.trajeto) > 10
    assert r.carga_t > 0
    assert re.fullmatch(r"\+[1-9]\d{7,14}", r.recebedor_telefone_e164)
    assert regra.max_tentativas == 3


async def test_seed_idempotente(container):
    a = seed()
    b = seed()
    assert a == b
    with sessao() as s:
        assert len(s.exec(select(Rota)).all()) == 1
