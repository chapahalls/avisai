"""Fluxos 4 a 6: pedido da central, métricas/ranking e divergência entre GPS do celular e rastreador."""

from sqlmodel import select

from app.infra.db import sessao
from app.infra.models import EventoGeo
from tests.fakes import tool_call
from tests.helpers import eventos

AUTH = {"Authorization": "Bearer segredo"}
DESTINO = {"lat": -22.9057, "lng": -47.0609}


def corpo(fala):
    return {"stream": True, "messages": [{"role": "system", "content": "p"}, {"role": "user", "content": fala}]}


# ---------- 4. pedido da central ----------

async def test_central_pergunta_agente_repassa_e_resposta_volta_estruturada(client, fake_agora, fake_llm):
    sid = (await client.post("/sessions", json={"rota_id": 1})).json()["id"]
    r = await client.post("/rotas/1/solicitacoes", json={"pergunta": "Qual o número do lacre?"})
    assert r.status_code == 200 and r.json()["status"] == "perguntada"
    assert any("A central pergunta" in f and "lacre" in f for f in fake_agora.falas())
    fake_llm.respostas = [tool_call("responder_central", '{"resposta":"lacre 4471"}'), "Passei pra central."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("o lacre é 4471"), headers=AUTH)
    sols = (await client.get("/rotas/1/solicitacoes")).json()
    assert sols[0]["status"] == "respondida" and sols[0]["resposta"] == "lacre 4471"
    assert eventos("resposta_central")


async def test_pergunta_pendente_vai_no_estado_do_llm(client, fake_llm):
    sid = (await client.post("/sessions", json={"rota_id": 1})).json()["id"]
    await client.post("/rotas/1/solicitacoes", json={"pergunta": "Qual o número do lacre?"})
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("oi"), headers=AUTH)
    sistema = " ".join(m["content"] for m in fake_llm.recebidas[-1]["mensagens"] if m["role"] == "system")
    assert "lacre" in sistema
    assert "responder_central" in {f["function"]["name"] for f in fake_llm.recebidas[-1]["ferramentas"]}


# ---------- 5. métricas e ranking ----------

async def test_metricas_do_dashboard(client, relogio, container):
    container.settings.cco_intervalo_s = 60
    await client.post("/rotas/1/chegada")
    relogio.avancar(minutes=30)
    t = (await client.get("/tasks")).json()[0]
    await client.post(f"/tasks/{t['id']}/confirmar", json={"confirmado_por": "Ana"})
    relogio.avancar(hours=6, minutes=30)
    await client.post("/rotas/1/descarga", json={"por": "CCO"})
    m = (await client.get("/api/metrics")).json()
    assert m["entregas"] == 1
    assert m["horas_paradas_media"] == 7.0
    assert m["estadia_devida_total"] == 150.0  # 2 h × 30 t (capacidade do veículo, não a carga) × 2,50
    assert m["tempo_ate_acao_cco_min_media"] == 30.0
    assert m["tasks_escaladas"] == 0
    assert set(m) >= {"pct_recebedores_avisados", "pct_ligacoes_atendidas", "pct_reportes_completos_1a", "latencia_voz_ms"}


async def test_ranking_de_recebedores(client, relogio, container):
    container.settings.cco_intervalo_s = 60
    await client.post("/rotas/1/chegada")
    relogio.avancar(hours=3)
    await client.post("/rotas/1/descarga")
    rec = (await client.get("/api/receivers")).json()
    assert rec[0]["recebedor"] == "Mercadão Campinas"
    assert rec[0]["entregas"] == 1 and rec[0]["espera_media_h"] == 3.0
    assert rec[0]["telefone_e164"].startswith("+")


# ---------- 6. divergência de GPS (celular × rastreador) ----------

def _chegada():
    with sessao() as s:
        return s.exec(select(EventoGeo).where(EventoGeo.tipo == "CHEGADA")).one()


async def test_gps_e_rastreador_concordam_e_aguardam_a_voz(client):
    """Os dois GPS juntos registram a prova; a validação completa vem com a voz (test_lacunas_rastreabilidade)."""
    await client.post("/rotas/1/posicao", json={**DESTINO, "fonte": "rastreador"})
    await client.post("/rotas/1/posicao", json={**DESTINO, "fonte": "celular"})
    geo = _chegada()
    assert geo.caminhao_lat is not None and geo.divergencia_m < 100
    assert geo.status == "nao_validado" and geo.confirmacao_voz_em is None
    assert not eventos("divergencia_gps")


async def test_rastreador_longe_marca_nao_validado_e_alerta_cco(client):
    await client.post("/rotas/1/posicao", json={"lat": -22.95, "lng": -47.0608, "fonte": "rastreador"})
    await client.post("/rotas/1/posicao", json={**DESTINO, "fonte": "celular"})
    geo = _chegada()
    assert geo.status == "nao_validado" and geo.divergencia_m > 500
    assert eventos("divergencia_gps")


async def test_so_rastreador_nao_dispara_geocerca(client):
    r = (await client.post("/rotas/1/posicao", json={**DESTINO, "fonte": "rastreador"})).json()
    assert r["disparos"] == []
