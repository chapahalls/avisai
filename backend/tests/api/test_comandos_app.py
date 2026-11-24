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
