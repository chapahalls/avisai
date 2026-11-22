"""Camada de compatibilidade com docs/arquitetura-avisai.md (contrato que os fronts seguem)."""
from sqlmodel import select

from app.infra.db import sessao
from app.infra.models import Ocorrencia, TaskCCO


def evento_app(tipo, payload, chave="k-1", trip="1"):
    return {"id": "uuid-" + chave, "idempotencyKey": chave, "tripId": trip, "type": tipo,
            "occurredAt": "2026-11-22T14:00:00Z", "source": "driver", "payload": payload}


async def test_agent_start_e_stop(client, fake_agora):
    r = await client.post("/agent/start", json={"tripId": "1"})
    assert r.status_code == 200
    d = r.json()
    assert {"appId", "channel", "uid", "token", "agentId", "sessionId", "agentUid"} <= set(d)
    assert d["channel"] == "avisai-rota-1" and d["uid"] == 1001
    r2 = await client.post("/agent/stop", json={"sessionId": d["sessionId"]})
    assert r2.status_code == 200 and fake_agora.leaves == [d["agentId"]]


async def test_call_receiver(client, fake_agora):
    r = await client.post("/call/receiver", json={"tripId": "1"})
    assert r.status_code == 200 and r.json()["channel"].startswith("avisai-recebedor-")


async def test_post_events_e_idempotente(client):
    e = evento_app("OccurrenceCreated", {"tipo": "fila", "descricao": "fila de 3 caminhões"})
    r1 = await client.post("/events", json=e)
    r2 = await client.post("/events", json=e)
    assert r1.status_code == 200 and r2.status_code == 409
    with sessao() as s:
        assert len(s.exec(select(Ocorrencia)).all()) == 1


async def test_post_events_arrival_cria_task(client):
    await client.post("/events", json=evento_app("ArrivalRegistered", {}, chave="k-2"))
    with sessao() as s:
        assert len(s.exec(select(TaskCCO)).all()) == 1


async def test_get_events_no_formato_domain_event(client):
    await client.post("/rotas/1/chegada")
    evs = (await client.get("/events", params={"tripId": "1"})).json()
    tipos = {e["type"] for e in evs}
    assert {"ArrivalRegistered", "TaskCreated"} <= tipos
    e = evs[0]
    assert {"id", "idempotencyKey", "tripId", "type", "occurredAt", "receivedAt", "source", "payload"} <= set(e)
    assert e["tripId"] == "1"


async def test_get_events_since(client):
    await client.post("/rotas/1/chegada")
    evs = (await client.get("/events")).json()
    ultimo = evs[-1]["receivedAt"]
    assert (await client.get("/events", params={"since": ultimo})).json() == []


async def test_api_route_receivers_documents_sso(client):
    rota = (await client.get("/api/route")).json()
    assert rota["tripId"] == "1" and len(rota["polyline"]) > 10 and rota["receiver"]["phone"].startswith("+")
    assert (await client.get("/api/receivers")).status_code == 200
    docs = (await client.get("/api/documents")).json()
    assert any(d["kind"] == "NF-e" for d in docs)
    sso = (await client.post("/auth/sso", json={"email": "carlos@rotasul.test"})).json()
    assert sso["token"] and sso["user"]["role"] in ("driver", "cco")


def test_aliases_de_env_do_doc(monkeypatch):
    from app.infra.settings import Settings

    monkeypatch.setenv("AGORA_REST_KEY", "k")
    monkeypatch.setenv("AGORA_REST_SECRET", "s")
    monkeypatch.setenv("SIP_FROM_NUMBER", "+15550001111")
    s = Settings()
    assert s.agora_customer_id == "k" and s.agora_customer_secret == "s" and s.agora_sip_from_number == "+15550001111"
