"""Contrato de perfis persistidos, seleção mock e cadastro atômico."""
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.infra.db import sessao
from app.infra.models import Motorista, Usuario


async def test_catalogo_e_alias_compartilham_dto_sso(client):
    response = await client.get("/usuarios")
    assert response.status_code == 200
    profiles = response.json()
    assert profiles == (await client.get("/api/users")).json()
    assert len(profiles) == 6
    assert all(set(profile) == {"id", "email", "name", "role", "driverId", "tripId"} for profile in profiles)
    assert all(profile["id"].isdigit() for profile in profiles)
    for profile in profiles:
        selected = await client.post("/auth/sso", json={"email": profile["email"]})
        assert selected.status_code == 200
        assert selected.json()["user"] == profile
    for role, expected in [("cco", 2), ("driver", 4)]:
        filtered = await client.get("/usuarios", params={"role": role})
        assert len(filtered.json()) == expected
        assert all(profile["role"] == role for profile in filtered.json())
        assert filtered.json() == (await client.get("/api/users", params={"role": role})).json()
    assert (await client.get("/usuarios", params={"role": "admin"})).status_code == 422


async def test_sso_desconhecido_nao_escolhe_motorista_ou_inventa_cco(client):
    for email in ["desconhecido@example.test", "cco.desconhecido@example.test"]:
        assert (await client.post("/auth/sso", json={"email": email})).status_code == 404
    default = (await client.post("/auth/sso", json={})).json()["user"]
    assert default["email"] == "carlos@rotasul.test"
    normalized = (await client.post("/auth/sso", json={"email": " CARLOS@ROTASUL.TEST "})).json()["user"]
    assert normalized == default


async def test_nome_motorista_tem_fonte_unica(client):
    with sessao() as s:
        driver = s.exec(select(Motorista).where(Motorista.email == "carlos@rotasul.test")).one()
        user = s.exec(select(Usuario).where(Usuario.motorista_id == driver.id)).one()
        assert user.nome is None
        driver.nome = "Carlos Nome Atualizado"
        s.add(driver)
        s.commit()
    profile = next(profile for profile in (await client.get("/usuarios")).json() if profile["email"] == "carlos@rotasul.test")
    assert profile["name"] == "Carlos Nome Atualizado"
    assert (await client.post("/auth/sso", json={})).json()["user"] == profile


async def test_post_motorista_cria_perfil_na_mesma_transacao(client):
    created = await client.post("/motoristas", json={"nome": "Nova motorista", "email": " NOVA@EXAMPLE.TEST "})
    assert created.status_code == 200, created.text
    driver = created.json()
    assert driver["email"] == "nova@example.test"
    profiles = (await client.get("/usuarios", params={"role": "driver"})).json()
    profile = next(profile for profile in profiles if profile["driverId"] == driver["id"])
    assert profile["name"] == driver["nome"] and profile["tripId"] is None
    assert (await client.post("/auth/sso", json={"email": driver["email"]})).json()["user"] == profile


async def test_post_email_duplicado_rejeita_sem_criar_outro_motorista(client):
    for email in [" CARLOS@ROTASUL.TEST ", "cco@avisai.test"]:
        response = await client.post("/motoristas", json={"nome": "Não deve criar", "email": email})
        assert response.status_code == 409
    with sessao() as s:
        assert len(s.exec(select(Motorista)).all()) == 4
        assert len(s.exec(select(Usuario)).all()) == 6


async def test_post_sem_email_nao_cria_perfil_e_email_invalido_nao_persiste(client):
    assert (await client.post("/motoristas", json={"nome": "Sem login"})).status_code == 200
    assert (await client.post("/motoristas", json={"nome": "Inválido", "email": "x@@example.test"})).status_code == 400
    with sessao() as s:
        assert len(s.exec(select(Motorista)).all()) == 5
        assert len(s.exec(select(Usuario)).all()) == 6


async def test_falha_no_perfil_reverte_motorista(client, monkeypatch):
    from app.servicos import usuarios

    def conflito(*args):
        raise IntegrityError("profile conflict", {}, Exception("unique"))

    monkeypatch.setattr(usuarios, "garantir_motorista", conflito)
    response = await client.post("/motoristas", json={"nome": "Reverter", "email": "reverter@example.test"})
    assert response.status_code == 409
    with sessao() as s:
        assert not s.exec(select(Motorista).where(Motorista.email == "reverter@example.test")).all()
        assert not s.exec(select(Usuario).where(Usuario.email == "reverter@example.test")).all()
