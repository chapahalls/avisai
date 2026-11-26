"""Dado/quando/então: a central cancela a viagem antes do destino; depois disso nada operacional acontece nela."""
import pytest

from app.infra.models import Rota
from tests.helpers import eventos, obter

NOVA = {
    "origem": {"nome": "CD Jundiaí", "lat": -23.1857, "lng": -46.8978},
    "destino": {"nome": "Atacado Sorocaba", "lat": -23.5015, "lng": -47.4526},
    "recebedor": {"empresa": "Atacado Sorocaba", "nome": "Paula", "telefone_e164": "+5515900000003"},
    "carga_t": 18, "placa": "RST7C88",
}


async def _rota(client, **extra) -> dict:
    r = await client.post("/rotas", json={**NOVA, **extra})
    assert r.status_code == 200, r.text
    return r.json()


async def test_cancelar_rota_publicada_registra_motivo_e_evento(client, relogio):
    rota = await _rota(client)
    r = await client.post(f"/rotas/{rota['id']}/cancelar", json={"motivo": "Cliente desistiu do pedido"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["status"] == "cancelada"
    assert corpo["cancelamento_motivo"] == "Cliente desistiu do pedido" and corpo["cancelada_por"] == "CCO"
    assert corpo["cancelada_em"] is not None
    ev = eventos("rota_cancelada")[-1]
    assert ev.rota_id == rota["id"] and ev.source == "cco"
    assert ev.dados["status_anterior"] == "publicada" and ev.dados["motivo"] == "Cliente desistiu do pedido"


async def test_cancelamento_avisa_o_motorista_atribuido_e_some_da_rota_atual(client):
    m = (await client.post("/motoristas", json={"nome": "Marina", "telefone_e164": "+5511900000009",
                                                "email": "marina.cancel@rotasul.test"})).json()
    rota = await _rota(client, motorista_id=m["id"])
    assert (await client.get(f"/motoristas/{m['id']}/rota-atual")).json()["id"] == rota["id"]
    assert (await client.post(f"/rotas/{rota['id']}/cancelar", json={"motivo": "Carga remanejada"})).status_code == 200
    assert eventos("rota_cancelada")[-1].dados["motorista_id"] == m["id"]
    assert (await client.get(f"/motoristas/{m['id']}/rota-atual")).status_code == 404


async def test_nao_cancela_depois_da_chegada_nem_duas_vezes(client):
    rota = await _rota(client)
    assert (await client.post(f"/rotas/{rota['id']}/chegada")).status_code == 200
    r = await client.post(f"/rotas/{rota['id']}/cancelar", json={"motivo": "tarde demais"})
    assert r.status_code == 409
    outra = await _rota(client)
    assert (await client.post(f"/rotas/{outra['id']}/cancelar", json={"motivo": "primeira vez"})).status_code == 200
    assert (await client.post(f"/rotas/{outra['id']}/cancelar", json={"motivo": "segunda vez"})).status_code == 409
    assert len([e for e in eventos("rota_cancelada") if e.rota_id == outra["id"]]) == 1


@pytest.mark.parametrize("corpo", [{}, {"motivo": ""}, {"motivo": "ok"}, {"motivo": "x" * 501}])
async def test_motivo_e_obrigatorio(client, corpo):
    rota = await _rota(client)
    assert (await client.post(f"/rotas/{rota['id']}/cancelar", json=corpo)).status_code == 422
    assert obter(Rota, rota["id"]).status == "publicada"


async def test_rota_inexistente_404(client):
    assert (await client.post("/rotas/9999/cancelar", json={"motivo": "não existe"})).status_code == 404


async def test_rota_cancelada_ignora_gps_e_recusa_chegada_descarga_e_atribuicao(client):
    m = (await client.post("/motoristas", json={"nome": "João", "telefone_e164": "+5511900000008",
                                                "email": "joao.cancel@rotasul.test"})).json()
    rota = await _rota(client)
    await client.post(f"/rotas/{rota['id']}/cancelar", json={"motivo": "Pedido cancelado"})
    antes = obter(Rota, rota["id"])
    # Em cima do destino: sem cancelamento, isso dispararia chegada.
    gps = await client.post(f"/rotas/{rota['id']}/posicao", json={"lat": -23.5015, "lng": -47.4526})
    assert gps.status_code == 200 and gps.json()["status"] == "cancelada" and gps.json()["disparos"] == []
    depois = obter(Rota, rota["id"])
    assert depois.ultima_lat == antes.ultima_lat and depois.status == "cancelada"
    assert not [e for e in eventos("chegada") if e.rota_id == rota["id"]]
    assert (await client.post(f"/rotas/{rota['id']}/chegada")).status_code == 409
    assert (await client.post(f"/rotas/{rota['id']}/descarga", json={"por": "CCO"})).status_code == 409
    assert (await client.post(f"/rotas/{rota['id']}/atribuir", json={"motorista_id": m["id"]})).status_code == 409


async def test_evento_de_dominio_trip_cancelled(client):
    rota = await _rota(client)
    await client.post(f"/rotas/{rota['id']}/cancelar", json={"motivo": "Pedido cancelado"})
    tipos = [e["type"] for e in (await client.get("/events", params={"tripId": str(rota["id"])})).json()]
    assert "TripCancelled" in tipos


async def test_com_auth_obrigatoria_cancelar_exige_cco(client, container):
    container.settings.auth_obrigatoria = True
    rota = (await client.get("/rotas")).json()[0]
    sem_token = await client.post(f"/rotas/{rota['id']}/cancelar", json={"motivo": "sem login"})
    assert sem_token.status_code == 401
    email = (await client.get("/usuarios", params={"role": "driver"})).json()[0]["email"]
    token = (await client.post("/auth/sso", json={"email": email})).json()["token"]
    proibido = await client.post(f"/rotas/{rota['id']}/cancelar", json={"motivo": "motorista tentando"},
                                 headers={"Authorization": f"Bearer {token}"})
    assert proibido.status_code == 403
