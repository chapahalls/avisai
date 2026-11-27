"""Lacunas apontadas pela matriz de rastreabilidade (evidence/rastreabilidade.md).

1. Chegada pede confirmação por voz; a prova só fica validada com GPS + voz (contexto 3.1.1).
2. Estadia calculada sobre a capacidade do veículo (Lei 11.442, contexto §6).
3. Atraso na estrada avisa o recebedor com o novo horário (ajustes pós-mentoria, tabela do foco).
"""
from sqlmodel import select

from app.infra.db import sessao
from app.infra.models import Estadia, EventoGeo, LigacaoRecebedor
from tests.fakes import tool_call
from tests.helpers import esperar, eventos

DESTINO = {"lat": -22.9057, "lng": -47.0609, "velocidade_kmh": 5}
NO_CAMINHO = {"lat": -23.05, "lng": -46.98, "velocidade_kmh": 60}


def corpo(fala):
    return {"stream": True, "messages": [{"role": "system", "content": "p"}, {"role": "user", "content": fala}]}


def _chegada():
    with sessao() as s:
        return s.exec(select(EventoGeo).where(EventoGeo.tipo == "CHEGADA")).one()


# ---------- 1. confirmação da chegada por voz ----------

async def test_gps_detecta_chegada_e_agente_pede_confirmacao(client, fake_livekit):
    await client.post("/sessions", json={"rota_id": 1})
    await client.post("/rotas/1/posicao", json={**DESTINO, "fonte": "rastreador"})
    await client.post("/rotas/1/posicao", json=DESTINO)
    assert any("Confirma a chegada" in f for f in fake_livekit.falas())
    assert _chegada().status == "nao_validado"  # só GPS ainda não é a prova completa


async def test_voz_confirma_e_valida_a_chegada(client, fake_llm):
    sid = (await client.post("/sessions", json={"rota_id": 1})).json()["id"]
    await client.post("/rotas/1/posicao", json={**DESTINO, "fonte": "rastreador"})
    await client.post("/rotas/1/posicao", json=DESTINO)
    fake_llm.respostas = [tool_call("confirmar_chegada", "{}"), "Chegada confirmada."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Confirmo, cheguei"))
    geo = _chegada()
    assert geo.status == "validado" and geo.confirmacao_voz_transcricao == "Confirmo, cheguei"


async def test_voz_nao_valida_se_gps_divergir(client, fake_llm):
    sid = (await client.post("/sessions", json={"rota_id": 1})).json()["id"]
    await client.post("/rotas/1/posicao", json={"lat": -22.95, "lng": -47.0608, "fonte": "rastreador"})
    await client.post("/rotas/1/posicao", json=DESTINO)
    fake_llm.respostas = [tool_call("confirmar_chegada", "{}"), "Ok."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Confirmo"))
    assert _chegada().status == "nao_validado"


async def test_chegada_pendente_vai_no_estado_do_llm(client, fake_llm):
    sid = (await client.post("/sessions", json={"rota_id": 1})).json()["id"]
    await client.post("/rotas/1/posicao", json=DESTINO)
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("oi"))
    sistema = " ".join(m["content"] for m in fake_llm.recebidas[-1]["mensagens"] if m["role"] == "system")
    assert "Confirma a chegada" in sistema


async def test_contingencia_confirma_a_chegada(client, container):
    container.settings.llm_api_key = ""
    sid = (await client.post("/sessions", json={"rota_id": 1})).json()["id"]
    await client.post("/rotas/1/posicao", json={**DESTINO, "fonte": "rastreador"})
    await client.post("/rotas/1/posicao", json=DESTINO)
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Sim, confirmo"))
    assert _chegada().status == "validado"


# ---------- 2. estadia pela capacidade do veículo ----------

NOVA = {
    "origem": {"nome": "CD Jundiaí", "lat": -23.1857, "lng": -46.8978},
    "destino": {"nome": "Atacado Sorocaba", "lat": -23.5015, "lng": -47.4526},
    "recebedor": {"empresa": "Atacado Sorocaba", "nome": "Paula", "telefone_e164": "+5515900000003"},
    "carga_t": 18, "placa": "RST-7C88",
}


async def test_estadia_usa_a_capacidade_do_veiculo(client):
    rota = (await client.post("/rotas", json={**NOVA, "capacidade_t": 32})).json()
    assert rota["capacidade_t"] == 32
    await client.post(f"/rotas/{rota['id']}/chegada")
    with sessao() as s:
        e = s.exec(select(Estadia).where(Estadia.rota_id == rota["id"])).one()
    assert e.capacidade_t == 32


async def test_sem_capacidade_informada_usa_a_carga(client):
    rota = (await client.post("/rotas", json=NOVA)).json()
    await client.post(f"/rotas/{rota['id']}/chegada")
    with sessao() as s:
        assert s.exec(select(Estadia).where(Estadia.rota_id == rota["id"])).one().capacidade_t == 18


async def test_capacidade_menor_que_a_carga_e_recusada(client):
    assert (await client.post("/rotas", json={**NOVA, "capacidade_t": 10})).status_code == 422


# ---------- 3. atraso avisa o recebedor ----------

async def test_atraso_na_estrada_liga_para_o_recebedor_com_novo_horario(client, fake_llm, fake_livekit):
    sid = (await client.post("/sessions", json={"rota_id": 1})).json()["id"]
    await client.post("/rotas/1/posicao", json=NO_CAMINHO)
    fake_llm.respostas = [tool_call("registrar_ocorrencia", '{"tipo":"atraso","descricao":"trânsito parado, uns 40 min de atraso"}'),
                          "Registrei e vou avisar o recebimento."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Vou atrasar uns 40 minutos"))
    await esperar(lambda: eventos("aviso_recebedor"))
    with sessao() as s:
        lig = s.exec(select(LigacaoRecebedor)).one()
    assert lig.motivo == "atraso"
    aviso = eventos("aviso_recebedor")[-1]
    assert aviso.dados["motivo"] == "atraso"
    prompt = fake_livekit.dispatches[-1]["metadata"]["instructions"]
    assert "atras" in prompt and "40 min" in prompt


async def test_atraso_depois_da_chegada_nao_liga(client, fake_llm):
    sid = (await client.post("/sessions", json={"rota_id": 1})).json()["id"]
    await client.post("/rotas/1/chegada")
    fake_llm.respostas = [tool_call("registrar_ocorrencia", '{"tipo":"atraso","descricao":"atrasou a descarga"}'), "Ok."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("atrasou"))
    import asyncio

    await asyncio.sleep(0.2)
    assert not [e for e in eventos("aviso_recebedor") if e.dados.get("motivo") == "atraso"]
