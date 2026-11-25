"""Chamados motorista→CCO: chegada, resposta e persistência."""

from app.infra.db import sessao
from app.infra.models import ChamadoCCO


async def test_chegada_abre_chamado_e_cco_responde(client):
    chegada = await client.post("/rotas/1/chegada")
    assert chegada.status_code == 200

    abertos = await client.get("/cco/chamados", params={"abertos": "true"})
    assert abertos.status_code == 200
    chamado = next(item for item in abertos.json() if item["tipo"] == "chegada")
    assert chamado["status"] == "aguardando_cco"
    assert chamado["tentativas"] == 0
    assert chamado["max_tentativas"] == 5
    assert chamado["intervalo_s"] == 30

    resposta = await client.post(
        f"/cco/chamados/{chamado['id']}/responder",
        json={"resposta": "Pode aguardar na doca 4.", "respondido_por": "CCO"},
    )
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "respondido"
    assert resposta.json()["resposta"] == "Pode aguardar na doca 4."

    with sessao() as s:
        persisted = s.get(ChamadoCCO, chamado["id"])
        assert persisted is not None
        assert persisted.status == "respondido"
