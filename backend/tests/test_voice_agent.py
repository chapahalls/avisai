"""Worker LiveKit (app/voice_agent.py) sem sala nem conexão real: parsing de metadata, montagem das
instruções e o wrapping das ferramentas do LLM como function_tool (a parte testável sem AgentSession)."""
import json

import httpx
import respx

from app import voice_agent as va
from app.infra.settings import Settings
from app.servicos import ferramentas


def test_backend_headers_leva_a_sessao():
    assert va._backend_headers(42) == {"x-avisai-sessao": "42"}


def test_metadata_com_json_valido():
    assert va._metadata('{"session_id": 1, "role": "motorista"}') == {"session_id": 1, "role": "motorista"}


def test_metadata_vazia_invalida_ou_sem_objeto_devolve_dict_vazio():
    assert va._metadata(None) == {}
    assert va._metadata("") == {}
    assert va._metadata("não é json") == {}
    assert va._metadata("[1, 2]") == {}  # JSON válido, mas não é um objeto


def test_instrucoes_inclui_vocabulario_da_operacao_e_filler(monkeypatch):
    monkeypatch.setattr(va, "settings", Settings(
        asr_keywords=["doca"], filler_words=["Um instante, parceiro."], filler_espera_ms=900,
    ))
    texto = va._instrucoes({"instructions": "Converse em português.", "asr_keyterms": ["Jundiaí", "doca"]})
    assert texto.startswith("Converse em português.")
    assert "Jundiaí" in texto
    assert texto.count("doca") == 1  # "doca" veio de settings e de asr_keyterms: não duplica
    assert "Um instante, parceiro." in texto and "900 ms" in texto


def test_instrucoes_sem_filler_words_nao_menciona_espera(monkeypatch):
    monkeypatch.setattr(va, "settings", Settings(asr_keywords=[], filler_words=[]))
    texto = va._instrucoes({"instructions": "Oi."})
    assert "ms" not in texto


def test_model_tools_so_expoe_as_ferramentas_do_papel():
    tools = va._model_tools("motorista", 1, {"text": ""})
    nomes = {t.info.name for t in tools}
    assert nomes == set(ferramentas.para("motorista"))
    assert "registrar_resposta_recebedor" not in nomes  # é do papel recebedor, não do motorista


def test_model_tools_para_papel_sem_ferramenta_registrada_devolve_lista_vazia():
    assert va._model_tools("cco", 1, {"text": ""}) == []


@respx.mock
async def test_ferramenta_chama_o_gateway_com_sessao_argumentos_e_fala(monkeypatch):
    monkeypatch.setattr(va.settings, "livekit_llm_url", "http://backend.test/v1")
    rota = respx.post("http://backend.test/v1/voice/tool").mock(
        return_value=httpx.Response(200, json={"ok": True, "mensagem": "Chegada registrada"})
    )
    tools = va._model_tools("motorista", 7, {"text": "cheguei na portaria"})
    confirmar = next(t for t in tools if t.info.name == "confirmar_chegada")

    resultado = await confirmar({"observacao": "na portaria"}, None)

    assert json.loads(resultado) == {"ok": True, "mensagem": "Chegada registrada"}
    pedido = rota.calls.last.request
    assert pedido.headers["x-avisai-sessao"] == "7"
    assert json.loads(pedido.content) == {
        "name": "confirmar_chegada", "arguments": {"observacao": "na portaria"}, "utterance": "cheguei na portaria",
    }


@respx.mock
async def test_ferramenta_com_gateway_fora_do_ar_devolve_erro_sem_derrubar_a_conversa(monkeypatch):
    monkeypatch.setattr(va.settings, "livekit_llm_url", "http://backend.test/v1")
    respx.post("http://backend.test/v1/voice/tool").mock(side_effect=httpx.ConnectError("sem conexão"))
    tools = va._model_tools("motorista", 1, {"text": ""})
    confirmar = next(t for t in tools if t.info.name == "confirmar_chegada")

    resultado = await confirmar({}, None)

    corpo = json.loads(resultado)
    assert corpo["ok"] is False and "erro" in corpo


def test_metadata_informa_identidade_do_agente_ou_usa_a_sala_como_fallback():
    assert va._metadata('{"agent_identity": "rodar-agente-9"}')["agent_identity"] == "rodar-agente-9"
    assert va._metadata("{}").get("agent_identity") is None
