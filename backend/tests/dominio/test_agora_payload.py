"""Payload do /join por fornecedor de ASR (docs da Agora: ares, deepgram, openai)."""
from app.dominio import agora_payload as ap
from app.infra.settings import Settings


def _join(**kw):
    cfg = ap.ConfigVoz.de(Settings(**kw))
    return ap.montar_join(cfg, nome="n", canal="c", token="t", agent_uid=9001, remote_uid=1001, prompt="p",
                          saudacao="s", voice_id="v", llm_url="https://x/v1/chat/completions", sessao_id=1,
                          termos_rota=["Mercadão Campinas", "RST-4B21"])


def test_padrao_e_ares_com_palavras_chave():
    j = _join()
    asr = j["properties"]["asr"]
    assert asr["vendor"] == "ares" and asr["language"] == "pt-BR" and "doca" in asr["keywords"]
    assert "deepgram" not in j["preset"]


def test_deepgram_nova3_gerenciado_ptbr():
    j = _join(asr_vendor="deepgram")
    assert j["properties"]["asr"] == {"vendor": "deepgram", "language": "pt-BR", "params": {"language": "pt-BR"}}
    assert "deepgram_nova_3" in j["preset"]


def test_deepgram_nova2():
    j = _join(asr_vendor="deepgram", asr_model="nova-2")
    assert "deepgram_nova_2" in j["preset"] and "deepgram_nova_3" not in j["preset"]


def test_ares_com_palavras_chave_do_dominio_e_da_rota():
    j = _join(asr_vendor="ares")
    asr = j["properties"]["asr"]
    assert asr["vendor"] == "ares" and asr["language"] == "pt-BR"
    for termo in ("doca", "CT-e", "palete", "estadia", "Mercadão Campinas", "RST-4B21"):
        assert termo in asr["keywords"]
    assert len(asr["keywords"]) <= 128
    assert "deepgram" not in j["preset"]  # ARES não usa preset de ASR


def test_openai_transcribe_com_prompt_de_contexto():
    j = _join(asr_vendor="openai", asr_api_key="sk-x")
    asr = j["properties"]["asr"]
    assert asr["vendor"] == "openai" and asr["params"]["api_key"] == "sk-x"
    t = asr["params"]["input_audio_transcription"]
    assert t["model"] == "gpt-4o-mini-transcribe" and t["language"] == "pt"
    assert "doca" in t["prompt"] and "Mercadão Campinas" in t["prompt"]
    assert "deepgram" not in j["preset"]


def test_openai_sem_chave_usa_a_do_llm_openai():
    j = _join(asr_vendor="openai", llm_api_key="sk-llm", llm_base_url="https://api.openai.com/v1")
    assert j["properties"]["asr"]["params"]["api_key"] == "sk-llm"
