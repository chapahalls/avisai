"""Peça 5: GPS simulado e geocercas de aproximação e chegada."""
from sqlmodel import select

from app.infra.db import sessao
from app.infra.models import Estadia, TaskCCO
from tests.helpers import eventos

LONGE = {"lat": -23.10, "lng": -46.95, "velocidade_kmh": 60}
PERTO = {"lat": -22.9956, "lng": -47.0608, "velocidade_kmh": 60}
DESTINO = {"lat": -22.9057, "lng": -47.0609, "velocidade_kmh": 5}


def _tasks():
    with sessao() as s:
        return s.exec(select(TaskCCO)).all()


async def test_posicao_longe_fica_em_transito_sem_disparos(client):
    r = (await client.post("/rotas/1/posicao", json=LONGE)).json()
    assert r["status"] == "em_transito" and r["disparos"] == []


async def test_aproximacao_dispara_uma_vez_e_avisa_motorista(client, fake_agora):
    await client.post("/sessions", json={"rota_id": 1})
    r = (await client.post("/rotas/1/posicao", json=PERTO)).json()
    assert r["disparos"] == ["APROXIMACAO"] and r["status"] == "aproximando"
    assert eventos("aproximacao")
    assert any("Faltam" in f for f in fake_agora.falas())
    r2 = (await client.post("/rotas/1/posicao", json=PERTO)).json()
    assert r2["disparos"] == []


async def test_chegada_cria_task_pendente_e_inicia_estadia(client, fake_agora):
    await client.post("/sessions", json={"rota_id": 1})
    r = (await client.post("/rotas/1/posicao", json=DESTINO)).json()
    assert "CHEGADA" in r["disparos"] and r["status"] == "no_destino"
    tasks = _tasks()
    assert len(tasks) == 1 and tasks[0].status in ("pendente", "escalada_recebedor")
    with sessao() as s:
        e = s.exec(select(Estadia)).one()
    assert e.capacidade_t == 28 and e.fim is None
    assert any("estadia" in f for f in fake_agora.falas())


async def test_chegada_repetida_nao_duplica_task(client):
    await client.post("/rotas/1/posicao", json=DESTINO)
    await client.post("/rotas/1/posicao", json=DESTINO)
    await client.post("/rotas/1/chegada")
    assert len(_tasks()) == 1


async def test_sem_sessao_do_motorista_fala_vira_evento_sem_erro(client, fake_agora):
    r = await client.post("/rotas/1/posicao", json=PERTO)
    assert r.status_code == 200
    assert fake_agora.speaks == []
    fala = eventos("fala_agente")[-1]
    assert fala.dados["entregue"] is False


async def test_rota_inexistente_404(client):
    assert (await client.post("/rotas/9/posicao", json=PERTO)).status_code == 404
