"""Peça 2: sessão do agente ConvoAI no canal do motorista."""
from app.integracoes.agora_rest import AgoraErro


async def test_dada_rota_quando_cria_sessao_entao_join_com_llm_proprio_e_ptbr(client, fake_agora):
    r = await client.post("/sessions", json={"rota_id": 1})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["canal"] == "avisai-rota-1"
    assert s["user_uid"] == 1001
    assert s["agent_uid"] == 9001
    assert s["agent_id"] == "agent-1"
    assert s["status"] == "ativa"
    assert s["token"].startswith("007")

    corpo = fake_agora.ultimo_join()
    p = corpo["properties"]
    assert p["channel"] == "avisai-rota-1"
    assert p["agent_rtc_uid"] == "9001"
    assert p["remote_rtc_uids"] == ["1001"]
    assert p["asr"]["vendor"] == "ares" and p["asr"]["language"] == "pt-BR"
    assert {"doca", "RST-4B21", "Mercadão Campinas, CD Norte"} <= set(p["asr"]["keywords"])
    assert p["interruption"]["enable"] is True
    assert p["llm"]["vendor"] == "custom"
    assert p["llm"]["url"] == f"https://avisai.test/v1/chat/completions?sessao={s['id']}"
    assert p["llm"]["headers"]["X-Avisai-Sessao"] == str(s["id"])
    assert p["llm"]["api_key"] == "segredo"
    assert "openai_gpt_4o_mini" not in corpo["preset"]
    assert "minimax" in corpo["preset"] and "deepgram" not in corpo["preset"]


async def test_join_segue_boas_praticas_da_agora(client, fake_agora, container):
    await client.post("/sessions", json={"rota_id": 1})
    await client.post("/sessions", json={"rota_id": 1})
    a, b = fake_agora.joins
    assert a["name"] != b["name"]  # nome único (evita 409)
    p = a["properties"]
    assert "turn_detection" not in p  # áudio do servidor nos padrões da Agora
    assert p["filler_words"]["enable"] is True
    frases = p["filler_words"]["content"]["static_config"]["phrases"]
    assert frases and all(isinstance(f, str) for f in frases)
    assert p["parameters"]["enable_metrics"] is True
    assert "sal" not in p


async def test_com_sal_ligado_entao_join_tem_sal_locking(client, fake_agora, container):
    container.settings.agora_sal = True
    await client.post("/sessions", json={"rota_id": 1})
    assert fake_agora.ultimo_join()["properties"]["sal"]["sal_mode"] == "locking"


async def test_prompt_do_motorista_em_ptbr_com_dados_da_carga(client, fake_agora):
    await client.post("/sessions", json={"rota_id": 1})
    llm = fake_agora.ultimo_join()["properties"]["llm"]
    prompt = llm["system_messages"][0]["content"]
    for trecho in ("RST-4B21", "000.482.913", "Mercadão Campinas", "Carlos"):
        assert trecho in prompt
    assert "Carlos" in llm["greeting_message"]


async def test_com_llm_mode_agora_entao_preset_inclui_llm_gerenciado(client, fake_agora, container):
    container.settings.llm_mode = "agora"
    await client.post("/sessions", json={"rota_id": 1})
    corpo = fake_agora.ultimo_join()
    assert "openai_gpt_4o_mini" in corpo["preset"]
    assert "url" not in corpo["properties"]["llm"]


async def test_quando_agora_falha_entao_502_e_sessao_falhou(client, fake_agora):
    fake_agora.falhar_join = AgoraErro(409, '{"detail":"conflict"}')
    r = await client.post("/sessions", json={"rota_id": 1})
    assert r.status_code == 502
    sessoes = (await client.get("/sessions")).json()
    assert sessoes[0]["status"] == "falhou"
    assert "409" in sessoes[0]["erro"]


async def test_quando_encerra_sessao_entao_leave_e_encerrada(client, fake_agora):
    s = (await client.post("/sessions", json={"rota_id": 1})).json()
    r = await client.delete(f"/sessions/{s['id']}")
    assert r.status_code == 200
    assert r.json()["status"] == "encerrada"
    assert fake_agora.leaves == ["agent-1"]


async def test_rota_inexistente_entao_404(client):
    r = await client.post("/sessions", json={"rota_id": 99})
    assert r.status_code == 404


async def test_fala_manual_chama_speak(client, fake_agora):
    s = (await client.post("/sessions", json={"rota_id": 1})).json()
    r = await client.post(f"/sessions/{s['id']}/speak", json={"texto": "Teste de fala"})
    assert r.status_code == 200
    assert fake_agora.speaks[-1] == {"agent_id": "agent-1", "texto": "Teste de fala", "prioridade": "APPEND"}


async def test_nova_sessao_tira_o_agente_antigo_do_canal(client, fake_agora):
    """Dois agentes com o mesmo uid no canal brigam: a sessão nova faz /leave da antiga."""
    a = (await client.post("/sessions", json={"rota_id": 1})).json()
    b = (await client.post("/sessions", json={"rota_id": 1})).json()
    assert fake_agora.leaves == [a["agent_id"]]
    sessoes = {s["id"]: s for s in (await client.get("/sessions")).json()}
    assert sessoes[a["id"]]["status"] == "encerrada" and sessoes[b["id"]]["status"] == "ativa"


async def test_clique_duplo_deixa_uma_sessao_ativa(client, fake_agora):
    import asyncio

    await asyncio.gather(client.post("/sessions", json={"rota_id": 1}), client.post("/sessions", json={"rota_id": 1}))
    ativas = [s for s in (await client.get("/sessions")).json() if s["status"] == "ativa"]
    assert len(ativas) == 1 and len(fake_agora.leaves) == 1
