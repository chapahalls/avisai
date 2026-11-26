"""Fluxos CCO em tempo real: alerta, decisão, mensagem e fallback Twilio→LiveKit."""
import json

import jwt
from sqlmodel import select

from app.infra.db import sessao
from app.infra.models import ChamadaAgente, MensagemMotorista
from tests.fakes import tool_call
from tests.helpers import eventos

AUTH = {"Authorization": "Bearer segredo"}


def corpo(fala: str) -> dict:
    return {
        "model": "gpt-4o-mini",
        "stream": False,
        "messages": [{"role": "user", "content": fala}],
    }


async def _sessao(client) -> int:
    return (await client.post("/sessions", json={"rota_id": 1})).json()["id"]


async def test_fala_do_motorista_publica_alerta_critico_e_decisao(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.respostas = ["Vou registrar."]

    response = await client.post(
        f"/v1/chat/completions?sessao={sid}",
        json=corpo("Meu pneu furou, vou atrasar uma hora."),
        headers=AUTH,
    )

    assert response.status_code == 200
    alerta = eventos("alerta_motorista")[-1]
    assert alerta.dados["tipo"] == "problema"
    assert alerta.dados["prioridade"] == "critico"
    assert alerta.dados["transcricao"] == "Meu pneu furou, vou atrasar uma hora."
    decisao = eventos("decisao_agente")[-1]
    assert decisao.dados["decisao"]["executou"] == "Publicou alerta crítico em tempo real."


async def test_tool_ligar_registra_falha_twilio_e_fallback_livekit_atendivel(client, fake_llm):
    sid = await _sessao(client)
    fake_llm.respostas = [
        tool_call("ligar", '{"destino":"operador","motivo":"pneu furado na BR-381"}'),
        "Estou acionando o operador.",
    ]

    response = await client.post(f"/v1/chat/completions?sessao={sid}", json=corpo("Liga para o operador"), headers=AUTH)

    assert response.status_code == 200
    with sessao() as s:
        chamada = s.exec(select(ChamadaAgente)).one()
    assert chamada.status == "livekit_tocando"
    assert chamada.twilio_resultado == "Twilio não configurado"
    assert chamada.livekit_room == f"rodar-operador-{chamada.id}"
    assert "Twilio falhou" in eventos("decisao_agente")[-2].dados["decisao"]["percebeu"]

    pendente = (await client.get("/operador/chamadas/atual")).json()["chamada"]
    assert pendente["id"] == chamada.id
    # Token LiveKit (JWT) para a sala da chamada, assinado com a chave do fixture `settings`.
    claims = jwt.decode(pendente["token"], "test-secret", algorithms=["HS256"])
    assert claims["iss"] == "test-key" and claims["video"]["room"] == chamada.livekit_room
    atendida = await client.post(f"/operador/chamadas/{chamada.id}/atender")
    assert atendida.status_code == 200 and atendida.json()["status"] == "atendida"


async def test_mensagem_cco_e_falada_e_resposta_permanece_na_thread(client, fake_llm, fake_livekit):
    sid = await _sessao(client)
    enviada = await client.post(
        "/rotas/1/mensagens",
        json={"remetente": "Ana", "texto": "Siga para a doca 4 quando liberarem."},
    )
    assert enviada.status_code == 200 and enviada.json()["status"] == "falada"
    assert "Você recebeu uma mensagem de Ana do CCO" in fake_livekit.falas()[-1]

    fake_llm.respostas = [
        tool_call("responder_mensagem_motorista", json.dumps({"resposta": "Entendido, aguardando a liberação."})),
        "Avisei a CCO.",
    ]
    resposta = await client.post(
        f"/v1/chat/completions?sessao={sid}",
        json=corpo("Entendido, aguardando a liberação."),
        headers=AUTH,
    )
    assert resposta.status_code == 200
    with sessao() as s:
        mensagem = s.exec(select(MensagemMotorista)).one()
    assert mensagem.status == "respondida"
    assert mensagem.resposta == "Entendido, aguardando a liberação."
