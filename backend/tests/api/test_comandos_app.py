"""O agente comanda o app: a ferramenta comandar_app publica `acao_cliente` no WebSocket do motorista."""
import json

from tests.fakes import tool_call
from tests.helpers import eventos

AUTH = {"Authorization": "Bearer segredo"}


def corpo(fala: str) -> dict:
    return {"stream": True, "messages": [{"role": "system", "content": "p"}, {"role": "user", "content": fala}]}


def sse(txt: str) -> str:
    out = []
    for linha in txt.splitlines():
        if linha.startswith("data: ") and linha[6:] != "[DONE]":
            out.append(json.loads(linha[6:])["choices"][0]["delta"].get("content") or "")
    return "".join(out)


async def _sessao(client) -> int:
    return (await client.post("/sessions", json={"rota_id": 1})).json()["id"]


def _acoes(assinatura) -> list[dict]:
    out = []
    while not assinatura.fila.empty():
        canal, msg = assinatura.fila.get_nowait()
        if canal == "acao_cliente":
            out.append(json.loads(msg))
    return out


async def test_llm_abre_o_mapa_no_app(client, container, fake_llm):
    sid = await _sessao(client)
    ws = container.eventos.assinar(rota_id=1)
    fake_llm.respostas = [tool_call("comandar_app", '{"acao":"abrir_tela","tela":"mapa"}'), "Abrindo o mapa."]
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("abre o mapa aí"), headers=AUTH)
    assert sse(r.text).strip() == "Abrindo o mapa."
    assert _acoes(ws) == [{"rota_id": 1, "acao": "open_screen", "tela": "mapa"}]


async def test_sair_da_conta_sem_confirmacao_nao_chega_ao_app(client, container, fake_llm):
    sid = await _sessao(client)
    ws = container.eventos.assinar(rota_id=1)
    fake_llm.respostas = [tool_call("comandar_app", '{"acao":"sair_da_conta"}'), "Quer mesmo sair da conta?"]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("quero sair da conta"), headers=AUTH)
    assert _acoes(ws) == []
    fake_llm.respostas = [tool_call("comandar_app", '{"acao":"sair_da_conta","confirmado":true}'), "Até mais!"]
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("confirmo"), headers=AUTH)
    assert _acoes(ws) == [{"rota_id": 1, "acao": "logout"}]


async def test_sem_llm_a_contingencia_abre_documento_e_encerra(client, container):
    container.settings.llm_api_key = ""
    sid = await _sessao(client)
    ws = container.eventos.assinar(rota_id=1)
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Abre a nota fiscal"), headers=AUTH)
    assert "nota fiscal" in sse(r.text)
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("pode encerrar a conversa"), headers=AUTH)
    assert "encerrando" in sse(r.text)
    assert _acoes(ws) == [
        {"rota_id": 1, "acao": "open_document", "documento": "NF-e"},
        {"rota_id": 1, "acao": "end_voice"},
    ]


async def test_ferramenta_vai_para_o_llm_do_motorista(client, fake_llm):
    sid = await _sessao(client)
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("oi"), headers=AUTH)
    nomes = {f["function"]["name"] for f in fake_llm.recebidas[-1]["ferramentas"]}
    assert "comandar_app" in nomes


async def test_sem_llm_sair_da_conta_nao_vira_inicio_de_viagem(client, container):
    container.settings.llm_api_key = ""
    sid = await _sessao(client)
    ws = container.eventos.assinar(rota_id=1)
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("quero sair da conta"), headers=AUTH)
    assert "confirmo" in sse(r.text).lower()
    assert _acoes(ws) == []
    assert not eventos("retirada")
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("confirmo, sair da conta"), headers=AUTH)
    assert _acoes(ws) == [{"rota_id": 1, "acao": "logout"}]


def _avisos(assinatura) -> list[dict]:
    out = []
    while not assinatura.fila.empty():
        canal, msg = assinatura.fila.get_nowait()
        if canal == "aviso_motorista":
            out.append(json.loads(msg))
    return out


async def test_aviso_sem_conversa_vai_pro_app(client, container):
    from app.servicos.sessoes import VozAgora

    ws = container.eventos.assinar(rota_id=1)
    entregue = await VozAgora(container).falar_motorista(1, "A central pergunta: a carga está lacrada?")
    assert entregue is False
    [aviso] = _avisos(ws)
    assert aviso["texto"] == "A central pergunta: a carga está lacrada?" and aviso["pede_resposta"] is True
    await VozAgora(container).falar_motorista(1, "Faltam uns 15 minutos.")
    assert _avisos(ws)[0]["pede_resposta"] is False


async def test_aviso_com_conversa_aberta_vai_pela_voz(client, container):
    from app.servicos.sessoes import VozAgora

    await _sessao(client)
    ws = container.eventos.assinar(rota_id=1)
    assert await VozAgora(container).falar_motorista(1, "Faltam uns 15 minutos.") is True
    assert _avisos(ws) == []


async def test_sem_llm_navega_liga_gps_e_repete(client, container):
    from app.servicos.sessoes import VozAgora

    container.settings.llm_api_key = ""
    sid = await _sessao(client)
    ws = container.eventos.assinar(rota_id=1)
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("me leva até o recebedor"), headers=AUTH)
    assert "mapa" in sse(r.text)
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("liga o GPS"), headers=AUTH)
    assert [a["acao"] for a in _acoes(ws)] == ["open_navigation", "start_gps"]
    await VozAgora(container).falar_motorista(1, "O CCO respondeu: pode descarregar na doca 2.")
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("repete"), headers=AUTH)
    assert "doca 2" in sse(r.text)


async def test_sem_llm_documento_andando_avisa_que_abre_parado(client, container):
    from app.infra.db import sessao
    from app.infra.models import Rota

    container.settings.llm_api_key = ""
    sid = await _sessao(client)
    with sessao() as s:
        r = s.get(Rota, 1)
        r.status = "em_transito"
        s.add(r)
        s.commit()
    ws = container.eventos.assinar(rota_id=1)
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("abre a nota fiscal"), headers=AUTH)
    assert "parar" in sse(r.text)
    assert _acoes(ws) == [{"rota_id": 1, "acao": "open_document", "documento": "NF-e"}]  # o app adia


async def test_recado_ao_cco_abre_chamado_e_problema_vira_ocorrencia(client, container):
    from sqlmodel import select

    from app.infra.db import sessao
    from app.infra.models import ChamadoCCO, Ocorrencia

    container.settings.llm_api_key = ""
    sid = await _sessao(client)
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("avisa o CCO que vou parar pra almoçar"), headers=AUTH)
    assert "Mandei pro CCO" in sse(r.text)
    with sessao() as s:
        [ch] = s.exec(select(ChamadoCCO)).all()
        assert ch.tipo == "mensagem" and ch.descricao == "vou parar pra almoçar"
        assert s.exec(select(Ocorrencia)).all() == []
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("avisa o CCO que a doca tá ocupada"), headers=AUTH)
    with sessao() as s:
        assert [o.tipo for o in s.exec(select(Ocorrencia)).all()] == ["doca_ocupada"]


async def test_llm_recebe_a_ferramenta_de_recado(client, fake_llm):
    sid = await _sessao(client)
    await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("oi"), headers=AUTH)
    nomes = {f["function"]["name"] for f in fake_llm.recebidas[-1]["ferramentas"]}
    assert {"comandar_app", "enviar_mensagem_cco"} <= nomes
