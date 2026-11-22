"""Seed da demo: 1 empresa, 1 motorista, 1 rota, 1 recebedor, regra de 3 tentativas.

Uso: python -m app.seed [--reset]
Todos os nomes, placas e telefones são fictícios.
"""
import sys

from sqlalchemy import text
from sqlmodel import select

from .infra import container as ct
from .infra.db import engine, sessao
from .infra.models import Empresa, Motorista, RegraEscalonamento, Rota

ORIGEM = ("CD Jundiaí", -23.1857, -46.8978)
DESTINO = ("Mercadão Campinas, CD Norte", -22.9056, -47.0608)


def trajeto(n: int = 40, origem=None, destino=None) -> list[list[float]]:
    """Trajeto simulado em linha reta (o GPS da demo é simulado; ver README)."""
    (la1, lo1), (la2, lo2) = origem or ORIGEM[1:], destino or DESTINO[1:]
    return [[round(la1 + (la2 - la1) * i / n, 6), round(lo1 + (lo2 - lo1) * i / n, 6)] for i in range(n + 1)]


def limpar() -> None:
    with engine.begin() as c:
        tabelas = [r[0] for r in c.execute(text(
            "select tablename from pg_tables where schemaname='public' and tablename <> 'alembic_version'"))]
        if tabelas:
            c.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tabelas) + " RESTART IDENTITY CASCADE"))


def seed(reset: bool = False) -> int:
    """Idempotente: se já existe rota, devolve o id dela."""
    if reset:
        limpar()
    cfg = ct.atual().settings
    with sessao() as s:
        existente = s.exec(select(Rota)).first()
        if existente:
            return existente.id
        emp = Empresa(nome="Transportadora Rota Sul")
        s.add(emp)
        s.commit()
        s.refresh(emp)
        s.add(RegraEscalonamento(empresa_id=emp.id, max_tentativas=3, intervalo_s=cfg.cco_intervalo_s,
                                 niveis=["push", "painel", "ligacao"], acao_final="ligar_recebedor"))
        mot = Motorista(empresa_id=emp.id, nome="Carlos Andrade", telefone_e164="+5511900000001", email="carlos@rotasul.test")
        s.add(mot)
        s.commit()
        s.refresh(mot)
        rota = Rota(
            empresa_id=emp.id,
            motorista_id=mot.id,
            origem_nome=ORIGEM[0], origem_lat=ORIGEM[1], origem_lng=ORIGEM[2],
            destino_nome=DESTINO[0], destino_lat=DESTINO[1], destino_lng=DESTINO[2],
            trajeto=trajeto(),
            placa="RST-4B21",
            nota_fiscal="000.482.913",
            carga_descricao="28 paletes de bebidas",
            carga_t=28,
            janela_descarga="hoje, 14h às 16h",
            recebedor_empresa="Mercadão Campinas",
            recebedor_nome="Marcos, do recebimento",
            recebedor_telefone_e164=cfg.recebedor_telefone_e164,
            aproximacao_min=15,
            raio_chegada_m=300,
            publicada_em=None,
        )
        s.add(rota)
        s.commit()
        s.refresh(rota)
        return rota.id


if __name__ == "__main__":
    rid = seed(reset="--reset" in sys.argv)
    print(f"seed ok: rota_id={rid}")
