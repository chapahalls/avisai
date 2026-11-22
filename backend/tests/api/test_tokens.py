"""Peça 1: tokens RTC para motorista, CCO e recebedor."""
from app.infra.settings import Settings


async def test_dado_app_configurada_quando_pede_token_entao_recebe_token_rtc(client):
    r = await client.get("/token", params={"channel": "avisai-rota-1", "uid": 1001})
    assert r.status_code == 200
    d = r.json()
    assert d["channel"] == "avisai-rota-1"
    assert d["uid"] == 1001
    assert d["app_id"] == "0123456789abcdef0123456789abcdef"
    assert d["token"].startswith("007")


async def test_quando_uid_zero_entao_400(client):
    r = await client.get("/token", params={"channel": "c", "uid": 0})
    assert r.status_code == 400


async def test_sem_credenciais_entao_500_com_mensagem(client, container):
    container.settings = Settings(agora_app_id="", agora_app_certificate="")
    r = await client.get("/token", params={"channel": "c", "uid": 1001})
    assert r.status_code == 500
    assert "Agora" in r.json()["detail"]


async def test_credencial_com_tamanho_errado_entao_500_claro(client, container):
    container.settings = Settings(agora_app_id="abc ", agora_app_certificate="x" * 32)
    r = await client.get("/token", params={"channel": "c", "uid": 1001})
    assert r.status_code == 500
    assert "32" in r.json()["detail"]
