"""Adaptador REST da Agora: URL, autenticação e payload exatos (respx)."""
import base64
import json

import httpx
import pytest
import respx

from app.infra.settings import Settings
from app.integracoes.agora_rest import AgoraErro, AgoraRest

APP = "0123456789abcdef0123456789abcdef"
BASE = f"https://api.agora.io/api/conversational-ai-agent/v2/projects/{APP}"


def _s(**kw) -> Settings:
    return Settings(agora_app_id=APP, agora_app_certificate="f" * 32, **kw)


@respx.mock
async def test_join_usa_basic_auth_quando_tem_customer_id():
    rota = respx.post(f"{BASE}/join").mock(return_value=httpx.Response(200, json={"agent_id": "A1", "status": "RUNNING"}))
    ag = AgoraRest(_s(agora_customer_id="cid", agora_customer_secret="sec"))
    agent_id = await ag.join({"name": "x", "properties": {"channel": "c", "agent_rtc_uid": "9001"}})
    assert agent_id == "A1"
    req = rota.calls.last.request
    assert req.headers["authorization"] == "Basic " + base64.b64encode(b"cid:sec").decode()
    assert json.loads(req.content)["name"] == "x"


@respx.mock
async def test_sem_customer_id_usa_token_auth():
    rota = respx.post(f"{BASE}/join").mock(return_value=httpx.Response(200, json={"agent_id": "A1"}))
    await AgoraRest(_s()).join({"name": "x", "properties": {"channel": "c", "agent_rtc_uid": "9001"}})
    assert rota.calls.last.request.headers["authorization"].startswith("agora token=007")


@respx.mock
async def test_speak_leave_call_hangup_nas_rotas_documentadas():
    ag = AgoraRest(_s(agora_customer_id="cid", agora_customer_secret="sec"))
    sp = respx.post(f"{BASE}/agents/A1/speak").mock(return_value=httpx.Response(200, json={}))
    lv = respx.post(f"{BASE}/agents/A1/leave").mock(return_value=httpx.Response(200))
    cl = respx.post(f"{BASE}/call").mock(return_value=httpx.Response(200, json={"agent_id": "C1"}))
    st = respx.get(f"{BASE}/calls/C1").mock(return_value=httpx.Response(200, json={"state": "answered"}))
    hg = respx.post(f"{BASE}/calls/C1/hangup").mock(return_value=httpx.Response(200, json={}))
    await ag.speak("A1", "olá " * 300, "INTERRUPT", "c", 9001)
    corpo = json.loads(sp.calls.last.request.content)
    assert corpo["priority"] == "INTERRUPT" and corpo["interruptable"] is True
    assert len(corpo["text"].encode()) <= 512
    await ag.leave("A1", "c", 9001)
    assert await ag.call({"name": "x", "sip": {}, "properties": {"channel": "c", "agent_rtc_uid": "9002"}}) == "C1"
    assert (await ag.call_status("C1", "c", 9002))["state"] == "answered"
    await ag.hangup("C1", "c", 9002)
    assert lv.called and st.called and hg.called and cl.called


@respx.mock
async def test_erro_http_vira_agoraerro_com_status():
    respx.post(f"{BASE}/join").mock(return_value=httpx.Response(409, json={"detail": "conflict"}))
    with pytest.raises(AgoraErro) as e:
        await AgoraRest(_s(agora_customer_id="c", agora_customer_secret="s")).join({"name": "x", "properties": {"channel": "c", "agent_rtc_uid": "1"}})
    assert e.value.status == 409


@respx.mock
async def test_leave_404_e_sucesso():
    respx.post(f"{BASE}/agents/A1/leave").mock(return_value=httpx.Response(404, json={"detail": "not found"}))
    await AgoraRest(_s(agora_customer_id="c", agora_customer_secret="s")).leave("A1", "c", 9001)


@respx.mock
async def test_falha_de_rede_vira_agoraerro():
    """DNS/conexão caindo não pode vazar como httpx.ConnectError e matar o fluxo."""
    respx.post(f"{BASE}/agents/A1/speak").mock(side_effect=httpx.ConnectError("Temporary failure in name resolution"))
    with pytest.raises(AgoraErro) as e:
        await AgoraRest(_s(agora_customer_id="c", agora_customer_secret="s")).speak("A1", "oi", "APPEND", "c", 9001)
    assert e.value.status == 503
