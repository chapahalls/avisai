"""Sessões de voz do motorista usando salas e dispatch LiveKit."""
from app.integracoes.livekit import LiveKitErro


async def test_criar_sessao_despacha_agente_e_devolve_token_livekit(client, fake_livekit):
    response = await client.post("/sessions", json={"rota_id": 1})
    assert response.status_code == 200, response.text
    session = response.json()
    assert session["canal"] == "rodar-rota-1"
    assert session["livekit_url"] == "wss://livekit.test"
    assert session["identity"] == "motorista-1"
    assert session["agent_id"] == "dispatch-1"
    assert session["token"].count(".") == 2
    dispatch = fake_livekit.dispatches[-1]
    assert dispatch["room"] == session["canal"]
    assert dispatch["metadata"]["agent_identity"] == f"rodar-agente-{session['id']}"
    assert dispatch["metadata"]["role"] == "motorista"
    prompt = dispatch["metadata"]["instructions"]
    for phrase in ("RST-4B21", "000.482.913", "Mercadão Campinas", "Carlos"):
        assert phrase in prompt
    assert "Carlos" in dispatch["metadata"]["greeting"]


async def test_falha_no_dispatch_marca_sessao_como_falha(client, fake_livekit):
    fake_livekit.falhar_dispatch = LiveKitErro(409, "conflict")
    response = await client.post("/sessions", json={"rota_id": 1})
    assert response.status_code == 502
    sessions = (await client.get("/sessions")).json()
    assert sessions[0]["status"] == "falhou"
    assert "409" in sessions[0]["erro"]


async def test_encerrar_sessao_remove_agente_da_sala(client, fake_livekit):
    session = (await client.post("/sessions", json={"rota_id": 1})).json()
    response = await client.delete(f"/sessions/{session['id']}")
    assert response.status_code == 200
    assert response.json()["status"] == "encerrada"
    assert fake_livekit.removals == [(session["canal"], f"rodar-agente-{session['id']}")]


async def test_rota_inexistente_entao_404(client):
    response = await client.post("/sessions", json={"rota_id": 99})
    assert response.status_code == 404


async def test_fala_manual_publica_comando_na_sala(client, fake_livekit):
    session = (await client.post("/sessions", json={"rota_id": 1})).json()
    response = await client.post(f"/sessions/{session['id']}/speak", json={"texto": "Teste de fala"})
    assert response.status_code == 200
    assert fake_livekit.speaks[-1]["identity"] == f"rodar-agente-{session['id']}"
    assert fake_livekit.speaks[-1]["texto"] == "Teste de fala"


async def test_nova_sessao_remove_agente_anterior_da_sala(client, fake_livekit):
    first = (await client.post("/sessions", json={"rota_id": 1})).json()
    second = (await client.post("/sessions", json={"rota_id": 1})).json()
    assert fake_livekit.removals == [(first["canal"], f"rodar-agente-{first['id']}")]
    sessions = {item["id"]: item for item in (await client.get("/sessions")).json()}
    assert sessions[first["id"]]["status"] == "encerrada"
    assert sessions[second["id"]]["status"] == "ativa"


async def test_clique_duplo_deixa_uma_sessao_ativa(client, fake_livekit):
    import asyncio

    await asyncio.gather(client.post("/sessions", json={"rota_id": 1}), client.post("/sessions", json={"rota_id": 1}))
    active = [item for item in (await client.get("/sessions")).json() if item["status"] == "ativa"]
    assert len(active) == 1 and len(fake_livekit.removals) == 1
