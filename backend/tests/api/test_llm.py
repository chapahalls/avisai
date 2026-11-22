"""Peça 3: LLM próprio OpenAI-compatível; a fala vira evento estruturado pelas ferramentas."""
import json

from sqlmodel import select

from app.infra.db import sessao
from app.infra.models import ChamadoCCO, Estadia, EventoGeo, LigacaoRecebedor, Ocorrencia, TaskCCO
from app.servicos import ligacoes
from tests.fakes import tool_call
from tests.helpers import eventos, obter

AUTH = {"Authorization": "Bearer segredo"}


def corpo(fala: str, stream: bool = True) -> dict:
    return {
        "model": "gpt-4o-mini",
        "stream": stream,
        "messages": [
            {"role": "system", "content": "prompt do agente"},
            {"role": "assistant", "content": "E aí!", "turn_id": 0, "timestamp": 1},
            {"role": "user", "content": fala, "turn_id": 1, "timestamp": 2},
        ],
    }


def sse(texto: str) -> tuple[list[str], bool]:
    partes, fim = [], False
    for linha in texto.splitlines():
        if not linha.startswith("data: "):
            continue
        d = linha[6:]
        if d == "[DONE]":
            fim = True
            continue
        delta = json.loads(d)["choices"][0]["delta"]
        if delta.get("content"):
            partes.append(delta["content"])
    return partes, fim


async def _sessao(client) -> int:
    return (await client.post("/sessions", json={"rota_id": 1})).json()["id"]


async def test_cheguei_na_portaria_vira_chegada_validada(client, fake_llm):
    sid = await _sessao(client)
    await client.post("/rotas/1/posicao", json={"lat": -22.9057, "lng": -47.0609})
    fake_llm.respostas = [tool_call("confirmar_chegada", '{"observacao":"na portaria"}'), "Chegada registrada, parceiro."]
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Cheguei na portaria"), headers=AUTH)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    partes, fim = sse(r.text)
    assert "".join(partes).strip() == "Chegada registrada, parceiro." and fim
    with sessao() as s:
        geo = s.exec(select(EventoGeo).where(EventoGeo.tipo == "CHEGADA")).one()
        assert len(s.exec(select(TaskCCO)).all()) == 1
    assert geo.status == "validado" and geo.confirmacao_voz_transcricao == "Cheguei na portaria"


async def test_fila_vira_ocorrencia(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.respostas = [tool_call(
        "registrar_ocorrencia",
        '{"tipo":"fila","descricao":"fila de 3 caminhões","km":230,"rodovia":"BR-381"}',
    ), "Registrei."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Tem fila de três caminhões"), headers=AUTH)
    with sessao() as s:
        o = s.exec(select(Ocorrencia)).one()
        chamado = s.exec(select(ChamadoCCO)).one()
    assert o.tipo == "fila" and o.transcricao == "Tem fila de três caminhões"
    assert o.km == 230 and o.rodovia == "BR-381"
    assert chamado.status == "aguardando_cco" and chamado.ocorrencia_id == o.id


async def test_ocorrencia_sem_km_ou_br_abre_chamado(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.respostas = [
        tool_call("registrar_ocorrencia", '{"tipo":"avaria","descricao":"Meu pneu furou"}'),
        "Registrei a avaria e avisei o CCO.",
    ]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Meu pneu furou"), headers=AUTH)
    with sessao() as s:
        o = s.exec(select(Ocorrencia)).one()
        chamado = s.exec(select(ChamadoCCO)).one()
    assert o.tipo == "avaria" and o.km is None and o.rodovia is None
    assert chamado.status == "aguardando_cco" and chamado.km is None and chamado.rodovia is None


async def test_descarreguei_encerra_estadia_e_task(client, fake_llm):
    sid = await _sessao(client)
    await client.post("/rotas/1/chegada")
    fake_llm.respostas = [tool_call("confirmar_descarga", "{}"), "Fechado."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Descarreguei"), headers=AUTH)
    with sessao() as s:
        e = s.exec(select(Estadia)).one()
        t = s.exec(select(TaskCCO)).one()
    assert e.fim is not None and t.status == "concluida"


async def test_recebedor_responde_doca_e_motorista_ouve(client, fake_llm, fake_agora, container):
    await _sessao(client)
    lig = await ligacoes.ligar(container, 1, "cco_sem_resposta")
    sid_rec = obter(LigacaoRecebedor, lig.id).sessao_id
    fake_llm.respostas = [
        tool_call("registrar_resposta_recebedor", '{"previsao":"em 40 minutos","doca":"4","resumo":"A doca 4 libera em 40 minutos."}'),
        "Então a doca 4 libera em 40 minutos, certo? Obrigada!",
    ]
    r = await client.post(f"/v1/chat/completions", json=corpo("A doca 4 libera em 40 minutos"),
                          headers={**AUTH, "X-Avisai-Sessao": str(sid_rec)})
    assert r.status_code == 200
    lig = obter(LigacaoRecebedor, lig.id)
    assert lig.status == "respondida" and lig.doca == "4"
    assert any(t["quem"] == "recebedor" for t in lig.transcricao)
    fala = fake_agora.speaks[-1]
    assert fala["prioridade"] == "INTERRUPT" and "doca 4" in fala["texto"]


async def test_estado_vivo_vai_para_o_llm_sem_campos_da_agora(client, fake_llm):
    sid = await _sessao(client)
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Como tá?"), headers=AUTH)
    msgs = fake_llm.recebidas[-1]["mensagens"]
    assert any(m["role"] == "system" and "ESTADO ATUAL" in (m["content"] or "") for m in msgs)
    assert all("turn_id" not in m and "timestamp" not in m for m in msgs)
    assert {f["function"]["name"] for f in fake_llm.recebidas[-1]["ferramentas"]} >= {
        "confirmar_chegada", "registrar_ocorrencia", "confirmar_descarga", "confirmar_retirada",
        "registrar_relatorio_inicial", "registrar_checkin", "responder_central"}
    ocorrencia = next(f for f in fake_llm.recebidas[-1]["ferramentas"] if f["function"]["name"] == "registrar_ocorrencia")
    assert ocorrencia["function"]["parameters"]["required"] == ["tipo", "descricao"]


async def test_texto_sai_em_varios_chunks(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.respostas = ["Tá parado há uma hora. Franquia restante de quatro horas."]
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Quanto tempo?"), headers=AUTH)
    partes, fim = sse(r.text)
    assert len(partes) >= 2 and fim


async def test_stream_false_devolve_json(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.respostas = ["Beleza."]
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Oi", stream=False), headers=AUTH)
    assert r.json()["choices"][0]["message"]["content"].strip() == "Beleza."


async def test_segredo_errado_401(client):
    sid = await _sessao(client)
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Oi"), headers={"Authorization": "Bearer x"})
    assert r.status_code == 401


async def test_llm_fora_do_ar_usa_heuristica_sem_500(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.falhar = True
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Cheguei"), headers=AUTH)
    assert r.status_code == 200
    partes, _ = sse(r.text)
    assert "".join(partes)
    with sessao() as s:
        assert len(s.exec(select(TaskCCO)).all()) == 1


async def test_fala_registrada_como_transcricao(client, fake_llm):
    sid = await _sessao(client)
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Tô na BR-116"), headers=AUTH)
    assert eventos("fala_motorista")[-1].mensagem == "Tô na BR-116"


def test_lgpd_sem_audio_nem_saude():
    from sqlmodel import SQLModel

    colunas = {c.name for t in SQLModel.metadata.tables.values() for c in t.columns}
    assert not any("audio" in c or "saude" in c for c in colunas)


async def test_chegada_por_voz_nao_fala_duas_vezes(client, fake_llm, fake_agora):
    """O próprio agente responde à fala; a fala proativa de chegada é só para GPS/manual."""
    sid = await _sessao(client)
    fake_llm.respostas = [tool_call("confirmar_chegada", "{}"), "Chegada registrada."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Cheguei"), headers=AUTH)
    assert not any("contador de estadia" in f for f in fake_agora.falas())


async def test_pergunta_sobre_a_nf_usa_ferramenta_e_registra_evento(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.respostas = [tool_call("consultar_documento", '{"pergunta":"qual o peso da nota?"}'), "Pela NF-e, 28 toneladas."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Qual o peso da nota?"), headers=AUTH)
    tool = [m for m in fake_llm.recebidas[-1]["mensagens"] if m["role"] == "tool"][-1]["content"]
    assert "28.000 kg" in tool and "NF-e" in tool
    ev = eventos("pergunta_documento")[-1]
    assert ev.dados["encontrado"] and ev.dados["campo"] == "peso_kg"
    evs = (await client.get("/events")).json()
    assert any(e["type"] == "DocumentQuestionAnswered" for e in evs)


async def test_sem_llm_a_contingencia_responde_a_nf(client, container):
    container.settings.llm_api_key = ""
    sid = await _sessao(client)
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("qual o número da nota fiscal?"), headers=AUTH)
    partes, _ = sse(r.text)
    assert "000.482.913" in "".join(partes)
