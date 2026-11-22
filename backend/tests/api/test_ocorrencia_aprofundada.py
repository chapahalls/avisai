"""O agente se aprofunda na ocorrência: pergunta uma coisa de cada vez e o CCO recebe o quadro completo."""
import json

from sqlmodel import select

from app.infra.db import sessao
from app.infra.models import Ocorrencia
from tests.fakes import tool_call
from tests.helpers import eventos

AUTH = {"Authorization": "Bearer segredo"}


def corpo(fala):
    return {"stream": True, "messages": [{"role": "system", "content": "p"}, {"role": "user", "content": fala}]}


def sse(txt):
    out = []
    for linha in txt.splitlines():
        if linha.startswith("data: ") and linha[6:] != "[DONE]":
            out.append(json.loads(linha[6:])["choices"][0]["delta"].get("content", ""))
    return "".join(out)


async def _sessao(client):
    return (await client.post("/sessions", json={"rota_id": 1})).json()["id"]


async def _falar(client, sid, fala):
    r = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo(fala), headers=AUTH)
    return sse(r.text)


def _oc():
    with sessao() as s:
        return s.exec(select(Ocorrencia)).one()


# ---------- sem LLM (contingência) ----------

async def test_contingencia_aprofunda_acidente_uma_pergunta_por_vez(client, container):
    container.settings.llm_api_key = ""
    sid = await _sessao(client)
    r1 = await _falar(client, sid, "Teve um acidente na pista")
    assert "ferido" in r1.lower()
    assert _oc().faltantes[0] == "feridos"
    r2 = await _falar(client, sid, "Não, ninguém se machucou")
    assert "outro veículo" in r2
    r3 = await _falar(client, sid, "Foi um carro na minha frente, não fui eu")
    assert "seguir" in r3
    r4 = await _falar(client, sid, "Tô bem, dá pra seguir")
    assert "quilômetro" in r4
    r5 = await _falar(client, sid, "BR-116, quilômetro 92")
    oc = _oc()
    assert oc.completa and oc.detalhes == {"feridos": "não", "envolvido": "Foi um carro na minha frente, não fui eu",
                                            "consegue_seguir": "sim", "local": "BR-116, quilômetro 92"}
    assert "CCO" in r5
    ev = eventos("ocorrencia_detalhada")[-1]
    assert "feridos: não" in ev.mensagem and "BR-116" in ev.mensagem


async def test_acidente_com_ferido_orienta_192_e_alerta_o_cco(client, container, fake_agora):
    container.settings.llm_api_key = ""
    sid = await _sessao(client)
    await _falar(client, sid, "Bateram aqui do lado, um acidente feio")
    r = await _falar(client, sid, "Sim, tem um motoqueiro ferido")
    assert "192" in r and "193" in r
    grave = eventos("ocorrencia_grave")
    assert grave and grave[-1].dados["prioridade"] == "critica"
    assert "ferido" in grave[-1].mensagem.lower()


async def test_ocorrencia_aberta_nao_engole_outros_comandos(client, container):
    container.settings.llm_api_key = ""
    sid = await _sessao(client)
    await _falar(client, sid, "Tem uma fila enorme aqui")
    r = await _falar(client, sid, "Qual o peso da nota?")  # pergunta no meio: responde e não grava como detalhe
    assert "kg" in r
    assert _oc().faltantes == ["quantos", "previsao"]


# ---------- com LLM ----------

async def test_llm_recebe_a_proxima_pergunta_e_detalha(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.respostas = [tool_call("registrar_ocorrencia", '{"tipo":"acidente","descricao":"acidente na pista"}'),
                          "Tem alguém ferido?"]
    await _falar(client, sid, "Teve um acidente na pista")
    tool = [m for m in fake_llm.recebidas[-1]["mensagens"] if m["role"] == "tool"][-1]["content"]
    assert "pergunte_agora" in tool and "ferido" in tool

    fake_llm.respostas = [tool_call("detalhar_ocorrencia", '{"feridos":"não","envolvido":"carro na frente"}'), "E dá pra seguir?"]
    await _falar(client, sid, "Ninguém ferido, foi um carro na frente")
    assert _oc().faltantes == ["consegue_seguir", "local"]
    await _falar(client, sid, "tá, e aí?")  # o estado vivo é montado no início de cada turno
    sistema = " ".join(m["content"] for m in fake_llm.recebidas[-1]["mensagens"] if m["role"] == "system")
    assert "seguir" in sistema  # a próxima pergunta vai como pendência


async def test_prompt_pede_para_se_aprofundar(client, fake_agora):
    await _sessao(client)
    prompt = fake_agora.ultimo_join()["properties"]["llm"]["system_messages"][0]["content"]
    assert "uma pergunta por vez" in prompt.lower() and "192" in prompt


async def test_outro_problema_no_meio_abre_nova_ocorrencia(client, container):
    container.settings.llm_api_key = ""
    sid = await _sessao(client)
    await _falar(client, sid, "Vou atrasar, trânsito parado")
    r = await _falar(client, sid, "Agora furou um pneu")
    assert "aconteceu com o caminhão" in r
    with sessao() as s:
        ocs = s.exec(select(Ocorrencia).order_by(Ocorrencia.id)).all()
    assert [o.tipo for o in ocs] == ["atraso", "avaria"]
    assert ocs[0].completa and not ocs[1].completa
