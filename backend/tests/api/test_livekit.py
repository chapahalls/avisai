"""Porta de entrada do LiveKit: configuração pública sem segredo e token curto assinado pelo backend."""
import jwt
import pytest


def _configurar(container, agente: str = ""):
    s = container.settings
    s.livekit_url = "wss://rodar-teste.livekit.cloud"
    s.livekit_api_key = "APIteste"
    s.livekit_api_secret = "segredo-de-teste-com-tamanho-suficiente-32"
    s.livekit_agent_name = agente


async def test_config_sem_livekit_diz_que_nao_esta_configurado(client, container):
    s = container.settings  # o fixture compartilhado já vem com LiveKit configurado
    s.livekit_url = s.livekit_api_key = s.livekit_api_secret = s.livekit_agent_name = ""
    r = await client.get("/livekit/config")
    assert r.status_code == 200
    assert r.json() == {"configurado": False, "url": None, "agente": None}
    assert (await client.post("/livekit/token", json={})).status_code == 503


async def test_config_publica_url_e_agente_sem_expor_chave_ou_segredo(client, container):
    _configurar(container, agente="avisai")
    body = (await client.get("/livekit/config")).json()
    assert body == {"configurado": True, "url": "wss://rodar-teste.livekit.cloud", "agente": "avisai"}
    assert "APIteste" not in str(body) and "segredo" not in str(body)


async def test_token_assinado_com_grants_da_sala_e_despacho_do_agente(client, container):
    _configurar(container, agente="avisai")
    r = await client.post("/livekit/token", json={"sala": "rodar-demo-1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"] == "wss://rodar-teste.livekit.cloud" and body["sala"] == "rodar-demo-1"
    claims = jwt.decode(body["token"], "segredo-de-teste-com-tamanho-suficiente-32", algorithms=["HS256"])
    assert claims["iss"] == "APIteste" and claims["sub"] == body["identidade"]
    assert claims["video"] == {"room": "rodar-demo-1", "roomJoin": True, "canPublish": True, "canSubscribe": True, "canPublishData": True}
    assert claims["roomConfig"] == {"agents": [{"agentName": "avisai"}]}
    assert claims["exp"] - claims["nbf"] == 60 * 60


async def test_sem_sala_usa_sala_propria_e_rejeita_nome_invalido(client, container):
    _configurar(container)
    body = (await client.post("/livekit/token", json={})).json()
    assert body["sala"] == f"rodar-demo-{body['identidade']}"
    assert "roomConfig" not in jwt.decode(body["token"], options={"verify_signature": False})
    assert (await client.post("/livekit/token", json={"sala": "sala com espaço/../"})).status_code == 400


@pytest.mark.parametrize("sala", ["rodar-rota-1", "rodar-recebedor-1", "rodar-operador-1"])
async def test_token_de_demo_nao_abre_sala_de_sessao_real(client, container, sala):
    """O token de demo (sem dono nem checagem de rota) não pode assinar as salas das sessões
    reais do backend: só /token (GET), restrito ao dono da rota ou à central, pode."""
    _configurar(container)
    r = await client.post("/livekit/token", json={"sala": sala})
    assert r.status_code == 400, r.text


async def test_com_auth_obrigatoria_token_exige_login_e_usa_identidade_do_perfil(client, container):
    _configurar(container)
    container.settings.auth_obrigatoria = True
    assert (await client.post("/livekit/token", json={})).status_code == 401
    email = (await client.get("/usuarios", params={"role": "driver"})).json()[0]["email"]
    sso = (await client.post("/auth/sso", json={"email": email})).json()
    r = await client.post("/livekit/token", json={}, headers={"Authorization": f"Bearer {sso['token']}"})
    assert r.status_code == 200, r.text
    assert r.json()["identidade"] == f"driver-{sso['user']['id']}"
