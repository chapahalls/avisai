"""Fluxos 1 a 3 do repo de ideias: retirada na origem, check-in com campos, aviso ao recebedor na aproximação."""
from sqlmodel import select

from app.infra.db import sessao
from app.infra.models import EventoGeo, LigacaoRecebedor, Reporte
from app.servicos import ligacoes
from tests.fakes import tool_call
from tests.helpers import esperar, eventos, obter

ORIGEM = {"lat": -23.1857, "lng": -46.8978, "velocidade_kmh": 0}
PERTO = {"lat": -22.9956, "lng": -47.0608, "velocidade_kmh": 60}
DESTINO = {"lat": -22.9057, "lng": -47.0609, "velocidade_kmh": 5}


def corpo(fala):
    return {"stream": True, "messages": [{"role": "system", "content": "p"}, {"role": "user", "content": fala}]}


async def _sessao(client):
    return (await client.post("/sessions", json={"rota_id": 1})).json()["id"]


def _geo(tipo):
    with sessao() as s:
        return s.exec(select(EventoGeo).where(EventoGeo.tipo == tipo)).first()


# ---------- 1. retirada na origem ----------

async def test_na_origem_agente_pergunta_se_confirma_a_retirada(client, fake_livekit):
    await _sessao(client)
    r = (await client.post("/rotas/1/posicao", json=ORIGEM)).json()
    assert "RETIRADA" in r["disparos"] and r["status"] == "na_origem"
    assert any("Confirma a retirada" in f for f in fake_livekit.falas())
    assert _geo("RETIRADA").status == "nao_validado"


async def test_motorista_confirma_retirada_por_voz(client, fake_llm):
    sid = await _sessao(client)
    await client.post("/rotas/1/posicao", json=ORIGEM)
    fake_llm.respostas = [tool_call("confirmar_retirada", '{"observacao":"carga ok"}'), "Retirada confirmada."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Confirmo, peguei a carga"))
    geo = _geo("RETIRADA")
    assert geo.status == "validado" and geo.confirmacao_voz_transcricao == "Confirmo, peguei a carga"
    assert eventos("retirada")
    assert (await client.get("/rotas/1")).json()["status"] == "em_transito"


async def test_retirada_dispara_uma_vez(client):
    await client.post("/rotas/1/posicao", json=ORIGEM)
    r = (await client.post("/rotas/1/posicao", json=ORIGEM)).json()
    assert r["disparos"] == []


# ---------- 2. check-in com campos obrigatórios ----------

async def test_checkin_incompleto_pede_so_o_que_faltou(client, fake_llm):
    sid = await _sessao(client)
    await client.post("/rotas/1/chegada")
    fake_llm.respostas = [tool_call("registrar_checkin", '{"status_carga":"carga inteira"}'), "E o tempo de viagem?"]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("A carga tá inteira"))
    tool_msg = [m for m in fake_llm.recebidas[-1]["mensagens"] if m["role"] == "tool"][-1]
    assert "tempo_viagem" in tool_msg["content"] and "problemas" in tool_msg["content"]
    with sessao() as s:
        rep = s.exec(select(Reporte).where(Reporte.tipo == "checkin")).one()
    assert not rep.completo and set(rep.faltantes) == {"tempo_viagem", "problemas"}
    assert eventos("campo_faltante")


async def test_checkin_completo_gera_relatorio(client, fake_llm):
    sid = await _sessao(client)
    await client.post("/rotas/1/chegada")
    fake_llm.respostas = [tool_call("registrar_checkin", '{"status_carga":"ok"}'), "E o resto?",
                          tool_call("registrar_checkin", '{"tempo_viagem":"3 horas","problemas":"nenhum"}'), "Fechado."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("carga ok"))
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("três horas, sem problema"))
    with sessao() as s:
        rep = s.exec(select(Reporte).where(Reporte.tipo == "checkin")).one()
    assert rep.completo and rep.campos == {"status_carga": "ok", "tempo_viagem": "3 horas", "problemas": "nenhum"}
    assert rep.perguntas_complemento == 1
    assert eventos("relatorio")


async def test_relatorio_inicial_por_voz(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.respostas = [tool_call("registrar_relatorio_inicial", '{"estado_caminhao":"ok","carga":"28 paletes"}'), "Boa viagem."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("caminhão ok, 28 paletes"))
    with sessao() as s:
        rep = s.exec(select(Reporte).where(Reporte.tipo == "inicial")).one()
    assert rep.completo


# ---------- 3. aviso ao recebedor na aproximação ----------

async def test_aproximacao_liga_para_o_recebedor_por_padrao(client, fake_livekit):
    await _sessao(client)
    await client.post("/rotas/1/posicao", json=PERTO)
    await esperar(lambda: eventos("ligacao_recebedor"))
    with sessao() as s:
        lig = s.exec(select(LigacaoRecebedor)).one()
    assert lig.motivo == "aproximacao"
    assert eventos("aviso_recebedor")  # ReceiverNotified


async def test_recebedor_nao_recebe_hoje_aplica_regra_e_avisa(client, fake_livekit, container):
    await _sessao(client)
    lig = await ligacoes.ligar(container, 1, "aproximacao")
    sa_id = obter(LigacaoRecebedor, lig.id).sessao_id
    await ligacoes.registrar_resposta(container, sa_id, previsao="só amanhã", doca=None, motivo="doca lotada",
                                      resumo="Hoje não recebemos, só amanhã.", recebe_hoje=False)
    ev = eventos("nao_recebe_hoje")[-1]
    assert "regra" in ev.dados and ev.dados["regra"]
    fala = fake_livekit.falas()[-1]
    assert "amanhã" in fala and ev.dados["regra"].split(".")[0].lower()[:15] in fala.lower()
