"""População da demo preserva escolhas e identificadores persistidos."""
import re

from sqlmodel import select

from app.infra.db import sessao
from app.infra.models import Empresa, Motorista, RegraEscalonamento, Rota, Usuario
from app.seed import seed
from app.servicos.usuarios import listar


async def test_seed_cria_dados_da_demo(container):
    rid = seed()
    with sessao() as s:
        assert len(s.exec(select(Empresa)).all()) == 1
        drivers = s.exec(select(Motorista)).all()
        assert len(drivers) == 4
        assert len(s.exec(select(Usuario)).all()) == 6
        routes = s.exec(select(Rota)).all()
        assert len(routes) == 3
        r = s.get(Rota, rid)
        regra = s.exec(select(RegraEscalonamento)).one()
    assert r.origem_nome and r.destino_nome and len(r.trajeto) > 10
    assert r.carga_t > 0
    assert re.fullmatch(r"\+[1-9]\d{7,14}", r.recebedor_telefone_e164)
    assert regra.max_tentativas == 3
    assert all(driver.telefone_e164 is None for driver in drivers if driver.email != "carlos@rotasul.test")
    added = [route for route in routes if route.id != rid]
    assert all(route.status == "planejada" and "fictício" in route.recebedor_nome for route in added)
    assert all(route.recebedor_telefone_e164 == "" for route in added)
    profiles = {profile["email"]: profile for profile in listar()}
    assert profiles["marina@rotasul.test"]["tripId"] != profiles["joao@rotasul.test"]["tripId"]
    assert profiles["fernanda@rotasul.test"]["tripId"] is None


async def test_seed_idempotente_e_nao_reabre_nem_reatribui(container):
    a = seed()
    with sessao() as s:
        before_profiles = [(u.id, u.email) for u in s.exec(select(Usuario).order_by(Usuario.id)).all()]
        before_ids = [r.id for r in s.exec(select(Rota).order_by(Rota.id)).all()]
        marina = s.exec(select(Rota).where(Rota.nota_fiscal == "DEMO-AVISAI-002")).one()
        joao = s.exec(select(Rota).where(Rota.nota_fiscal == "DEMO-AVISAI-003")).one()
        fernanda = s.exec(select(Motorista).where(Motorista.email == "fernanda@rotasul.test")).one()
        marina.status = "descarregada"
        joao.motorista_id = fernanda.id
        joao.destino_nome = "Destino alterado pelo operador"
        s.add_all([marina, joao])
        s.commit()
        expected = [(r.id, r.status, r.motorista_id, r.destino_nome) for r in s.exec(select(Rota).order_by(Rota.id)).all()]
    assert seed() == a
    assert seed() == a
    with sessao() as s:
        assert [(u.id, u.email) for u in s.exec(select(Usuario).order_by(Usuario.id)).all()] == before_profiles
        assert [r.id for r in s.exec(select(Rota).order_by(Rota.id)).all()] == before_ids
        assert [(r.id, r.status, r.motorista_id, r.destino_nome) for r in s.exec(select(Rota).order_by(Rota.id)).all()] == expected


async def test_seed_complementa_base_existente_sem_modificar_rota(container):
    with sessao() as s:
        company = Empresa(nome="Transportadora preexistente")
        s.add(company)
        s.flush()
        driver = Motorista(empresa_id=company.id, nome="Nome preservado", email=" CARLOS@ROTASUL.TEST ",
                           telefone_e164=None)
        s.add(driver)
        s.flush()
        route = Rota(empresa_id=company.id, motorista_id=driver.id, status="descarregada",
                     origem_nome="Origem preservada", origem_lat=-23.0, origem_lng=-47.0,
                     destino_nome="Destino preservado", destino_lat=-22.0, destino_lng=-46.0,
                     trajeto=[], nota_fiscal="NF-OPERADOR")
        s.add(route)
        s.commit()
        driver_id, route_id = driver.id, route.id
    assert seed() == route_id
    with sessao() as s:
        assert len(s.exec(select(Rota)).all()) == 3
        existing = s.get(Rota, route_id)
        assert (existing.status, existing.motorista_id, existing.nota_fiscal) == ("descarregada", driver_id, "NF-OPERADOR")
        assert s.get(Motorista, driver_id).nome == "Nome preservado"
        user = s.exec(select(Usuario).where(Usuario.email == "carlos@rotasul.test")).one()
        assert user.motorista_id == driver_id


async def test_seed_nao_escolhe_motorista_legado_ambiguo(container):
    seed()
    with sessao() as s:
        s.add_all([
            Motorista(empresa_id=1, nome="Legado A", email="duplicado@example.test"),
            Motorista(empresa_id=1, nome="Legado B", email=" DUPLICADO@EXAMPLE.TEST "),
        ])
        s.commit()
    seed()
    with sessao() as s:
        assert not s.exec(select(Usuario).where(Usuario.email == "duplicado@example.test")).all()
        assert len(s.exec(select(Motorista).where(Motorista.nome.in_(["Legado A", "Legado B"]))).all()) == 2



async def test_seed_reconhece_carlos_fixture_legado_sem_email(container):
    with sessao() as s:
        company = Empresa(nome="Transportadora Rota Sul")
        s.add(company)
        s.flush()
        driver = Motorista(empresa_id=company.id, nome="Carlos Andrade",
                           telefone_e164="+5511900000001", email=None)
        s.add(driver)
        s.flush()
        route = Rota(empresa_id=company.id, motorista_id=driver.id, status="em_transito",
                     origem_nome="CD Jundiaí", origem_lat=-23.1857, origem_lng=-46.8978,
                     destino_nome="Mercadão Campinas, CD Norte", destino_lat=-22.9056, destino_lng=-47.0608,
                     trajeto=[], placa="RST-4B21", nota_fiscal="000.482.913")
        s.add(route)
        s.commit()
        driver_id, route_id = driver.id, route.id
    assert seed() == route_id
    assert seed() == route_id
    with sessao() as s:
        assert len(s.exec(select(Motorista)).all()) == 4
        assert s.get(Motorista, driver_id).email == "carlos@rotasul.test"
        assert s.get(Rota, route_id).motorista_id == driver_id
        assert s.get(Rota, route_id).status == "em_transito"
        profile = s.exec(select(Usuario).where(Usuario.email == "carlos@rotasul.test")).one()
        assert profile.motorista_id == driver_id


async def test_seed_preserva_jornada_de_motorista_ja_atribuido(container):
    from app.servicos.publicacao import rota_atual

    with sessao() as s:
        company = Empresa(nome="Transportadora Rota Sul")
        s.add(company)
        s.flush()
        driver = Motorista(empresa_id=company.id, nome="Marina existente", email="marina@rotasul.test")
        s.add(driver)
        s.flush()
        route = Rota(empresa_id=company.id, motorista_id=driver.id, status="em_transito",
                     origem_nome="Origem existente", origem_lat=-23, origem_lng=-47,
                     destino_nome="Destino existente", destino_lat=-22, destino_lng=-46,
                     trajeto=[], nota_fiscal="OPERACAO-ATIVA")
        s.add(route)
        s.commit()
        driver_id, route_id = driver.id, route.id
    seed()
    assert rota_atual(driver_id).id == route_id
    with sessao() as s:
        route = s.get(Rota, route_id)
        route.status = "descarregada"
        s.add(route)
        s.commit()
    seed()
    assert rota_atual(driver_id) is None
    with sessao() as s:
        assert not s.exec(select(Rota).where(Rota.nota_fiscal == "DEMO-AVISAI-002")).all()
