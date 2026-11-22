"""Peça 8: stream do CCO (SSE), WS do app e confirmação da Task."""
import asyncio

from app.api import cco
from app.dominio.enums import TipoEvento


async def _proximos(gen, n, timeout=2.0):
    itens = []
    async def pegar():
        async for x in gen:
            itens.append(x)
            if len(itens) >= n:
                return
    await asyncio.wait_for(pegar(), timeout)
    return itens


async def test_stream_manda_snapshot_evento_e_contador(client, container):
    container.settings.cco_intervalo_s = 60  # sem novas notificações no meio
    await client.post("/rotas/1/chegada")
    gen = cco.fluxo(container, intervalo_contador=0.05)
    primeiro = await _proximos(gen, 1)
    assert primeiro[0][0] == "snapshot"
    assert {"rotas", "tasks", "estadias", "ligacoes", "eventos"} <= set(primeiro[0][1])
    container.eventos.registrar(TipoEvento.OCORRENCIA, "teste de stream", 1)
    itens = await _proximos(gen, 6)
    tipos = [t for t, _ in itens]
    assert "evento" in tipos and "contador" in tipos
    ev = next(d for t, d in itens if t == "evento" and d["mensagem"] == "teste de stream")
    assert set(ev) >= {"id", "tipo", "rota_id", "timestamp", "mensagem", "dados"}
    cont = next(d for t, d in itens if t == "contador")
    assert cont["estadias"][0]["rota_id"] == 1
    await gen.aclose()


async def test_ws_filtra_eventos_pela_rota(client, container):
    gen = cco.fluxo(container, rota_id=1, intervalo_contador=60)
    await _proximos(gen, 1)  # snapshot
    container.eventos.registrar(TipoEvento.OCORRENCIA, "outra rota", 2)
    container.eventos.registrar(TipoEvento.OCORRENCIA, "minha rota", 1)
    (t, d), = await _proximos(gen, 1)
    assert t == "evento" and d["mensagem"] == "minha rota"
    await gen.aclose()


async def test_confirmar_task(client):
    t = (await client.post("/rotas/1/chegada")).json()
    r = await client.post(f"/tasks/{t['id']}/confirmar", json={"confirmado_por": "Ana (CCO)"})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "confirmada" and d["confirmado_por"] == "Ana (CCO)" and d["confirmado_em"]


async def test_estado_do_cco(client):
    await client.post("/rotas/1/chegada")
    d = (await client.get("/cco/estado")).json()
    assert d["tasks"][0]["status"] == "pendente"
    assert d["estadias"][0]["valor_fmt"].startswith("R$")
