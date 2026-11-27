"""Peça 3: LLM próprio OpenAI-compatível; a fala vira evento estruturado pelas ferramentas."""
import json

from sqlmodel import select

from app.infra.db import sessao
from app.infra.models import ChamadoCCO, Estadia, EventoGeo, LigacaoRecebedor, Ocorrencia, TaskCCO
from app.servicos import ligacoes
from tests.fakes import tool_call
from tests.helpers import eventos, obter


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
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Cheguei na portaria"))
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
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Tem fila de três caminhões"))
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
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Meu pneu furou"))
    with sessao() as s:
        o = s.exec(select(Ocorrencia)).one()
        chamado = s.exec(select(ChamadoCCO)).one()
    assert o.tipo == "avaria" and o.km is None and o.rodovia is None
    assert chamado.status == "aguardando_cco" and chamado.km is None and chamado.rodovia is None


async def test_descarreguei_encerra_estadia_e_task(client, fake_llm):
    sid = await _sessao(client)
    await client.post("/rotas/1/chegada")
    fake_llm.respostas = [tool_call("confirmar_descarga", "{}"), "Fechado."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Descarreguei"))
    with sessao() as s:
        e = s.exec(select(Estadia)).one()
        t = s.exec(select(TaskCCO)).one()
    assert e.fim is not None and t.status == "concluida"


async def test_recebedor_responde_doca_e_motorista_ouve(client, fake_llm, fake_livekit, container):
    await _sessao(client)
    lig = await ligacoes.ligar(container, 1, "cco_sem_resposta")
    sid_rec = obter(LigacaoRecebedor, lig.id).sessao_id
    fake_llm.respostas = [
        tool_call("registrar_resposta_recebedor", '{"previsao":"em 40 minutos","doca":"4","resumo":"A doca 4 libera em 40 minutos."}'),
        "Então a doca 4 libera em 40 minutos, certo? Obrigada!",
    ]
    r = await client.post("/v1/chat/completions", json=corpo("A doca 4 libera em 40 minutos"),
                          headers={"X-Avisai-Sessao": str(sid_rec)})
    assert r.status_code == 200
    lig = obter(LigacaoRecebedor, lig.id)
    assert lig.status == "respondida" and lig.doca == "4"
    assert any(t["quem"] == "recebedor" for t in lig.transcricao)
    fala = fake_livekit.speaks[-1]
    assert fala["prioridade"] == "INTERRUPT" and "doca 4" in fala["texto"]


async def test_estado_vivo_vai_para_o_llm_sem_campos_de_transporte(client, fake_llm):
    sid = await _sessao(client)
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Como tá?"))
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
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Quanto tempo?"))
    partes, fim = sse(r.text)
    assert len(partes) >= 2 and fim


async def test_stream_false_devolve_json(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.respostas = ["Beleza."]
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Oi", stream=False))
    assert r.json()["choices"][0]["message"]["content"].strip() == "Beleza."


async def test_llm_fora_do_ar_usa_heuristica_sem_500(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.falhar = True
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Cheguei"))
    assert r.status_code == 200
    partes, _ = sse(r.text)
    assert "".join(partes)
    with sessao() as s:
        assert len(s.exec(select(TaskCCO)).all()) == 1


async def test_fala_registrada_como_transcricao(client, fake_llm):
    sid = await _sessao(client)
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Tô na BR-116"))
    assert eventos("fala_motorista")[-1].mensagem == "Tô na BR-116"


def test_lgpd_sem_audio_nem_saude():
    from sqlmodel import SQLModel

    colunas = {c.name for t in SQLModel.metadata.tables.values() for c in t.columns}
    assert not any("audio" in c or "saude" in c for c in colunas)


async def test_chegada_por_voz_nao_fala_duas_vezes(client, fake_llm, fake_livekit):
    """O próprio agente responde à fala; a fala proativa de chegada é só para GPS/manual."""
    sid = await _sessao(client)
    fake_llm.respostas = [tool_call("confirmar_chegada", "{}"), "Chegada registrada."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Cheguei"))
    assert not any("contador de estadia" in f for f in fake_livekit.falas())


async def test_pergunta_sobre_a_nf_usa_ferramenta_e_registra_evento(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.respostas = [tool_call("consultar_documento", '{"pergunta":"qual o peso da nota?"}'), "Pela NF-e, 28 toneladas."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Qual o peso da nota?"))
    tool = [m for m in fake_llm.recebidas[-1]["mensagens"] if m["role"] == "tool"][-1]["content"]
    assert "28.000 kg" in tool and "NF-e" in tool
    ev = eventos("pergunta_documento")[-1]
    assert ev.dados["encontrado"] and ev.dados["campo"] == "peso_kg"
    evs = (await client.get("/events")).json()
    assert any(e["type"] == "DocumentQuestionAnswered" for e in evs)


async def test_sem_llm_a_contingencia_responde_a_nf(client, container):
    container.settings.llm_api_key = ""
    sid = await _sessao(client)
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("qual o número da nota fiscal?"))
    partes, _ = sse(r.text)
    assert "000.482.913" in "".join(partes)


def test_ultima_fala_do_agente_vem_do_historico():
    from app.servicos.conversa import ultima_fala_agente

    msgs = [
        {"role": "system", "content": "p"},
        {"role": "assistant", "content": "E aí!"},
        {"role": "user", "content": "oi"},
        {"role": "assistant", "content": "Confirma a retirada da carga?"},
        {"role": "user", "content": "sim"},
    ]
    assert ultima_fala_agente(msgs) == "Confirma a retirada da carga?"


async def test_estado_tem_situacao_e_proximo_passo_sem_ruido_de_falas(client, fake_llm):
    sid = await _sessao(client)
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("oi"))
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("tudo certo"))
    estado = next(m["content"] for m in fake_llm.recebidas[-1]["mensagens"] if m["content"].startswith("ESTADO ATUAL"))
    assert "SITUAÇÃO:" in estado and "PRÓXIMO PASSO" in estado
    assert "Fala do motorista" not in estado and "oi" not in estado.split("Últimos eventos:")[-1]


async def test_relatorio_inventado_pelo_llm_nao_e_gravado(client, fake_llm):
    from app.infra.models import Reporte

    sid = await _sessao(client)
    fake_llm.respostas = [
        tool_call("registrar_relatorio_inicial", '{"estado_caminhao":"pronto","carga":"28 paletes de bebidas"}'),
        "Como tá o caminhão?",
    ]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("peguei a carga já, bora"))
    with sessao() as s:
        assert s.exec(select(Reporte)).all() == []
    resultado = json.loads(fake_llm.recebidas[-1]["mensagens"][-1]["content"])
    assert resultado["ok"] is False and "pergunte_agora" in resultado


async def test_avaria_nao_pergunta_de_novo_o_que_a_descricao_ja_disse(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.respostas = [tool_call("registrar_ocorrencia", '{"tipo":"avaria","descricao":"furou o pneu"}'), "Registrei."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("furou o pneu aqui"))
    with sessao() as s:
        oc = s.exec(select(Ocorrencia)).one()
    assert oc.detalhes == {"o_que": "furou o pneu"} and oc.faltantes[0] == "consegue_seguir"


async def test_pneu_furado_chamado_de_outro_vira_avaria(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.respostas = [tool_call("registrar_ocorrencia", '{"tipo":"outro","descricao":"Furou o pneu."}'), "Registrei."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("furou o pneu aqui"))
    with sessao() as s:
        oc = s.exec(select(Ocorrencia)).one()
    assert oc.tipo == "avaria" and not oc.completa


async def test_detalhe_depois_de_fechar_vai_para_a_ultima_ocorrencia(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.respostas = [tool_call("registrar_ocorrencia", '{"tipo":"outro","descricao":"barulho estranho"}'), "Ok."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("tá fazendo um barulho estranho"))
    fake_llm.respostas = [tool_call("detalhar_ocorrencia", '{"consegue_seguir":"sim"}'), "Anotado."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("mas dá pra seguir"))
    with sessao() as s:
        oc = s.exec(select(Ocorrencia)).one()
    assert oc.detalhes.get("consegue_seguir") == "sim"


async def test_relatorio_vale_o_que_ele_disse_no_turno_anterior(client, fake_llm):
    from app.infra.models import Reporte

    sid = await _sessao(client)
    fake_llm.respostas = ["E a carga?"]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("o caminhão tá de boa"))
    fake_llm.respostas = [
        tool_call("registrar_relatorio_inicial", '{"estado_caminhao":"de boa","carga":"paletes de bebida"}'), "Fechado."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("são os paletes de bebida"))
    with sessao() as s:
        r = s.exec(select(Reporte)).one()
    assert r.campos == {"estado_caminhao": "de boa", "carga": "paletes de bebida"} and r.completo


async def test_detalhe_pega_tudo_o_que_a_fala_respondeu(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.respostas = [tool_call("registrar_ocorrencia", '{"tipo":"avaria","descricao":"furou o pneu"}'), "Registrei."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("furou o pneu"))
    fake_llm.respostas = [tool_call("detalhar_ocorrencia", '{"consegue_seguir":"sim"}'), "Anotado."]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("a carga tá inteira, consigo seguir sim"))
    with sessao() as s:
        oc = s.exec(select(Ocorrencia)).one()
    assert oc.completa and oc.detalhes["consegue_seguir"] == "sim" and "inteira" in oc.detalhes["carga"]
