"""Monta os corpos de /join e /call da ConvoAI (domínio puro; sem IO).

Boas práticas (docs da Agora, via MCP): áudio do servidor nos padrões (sem overrides de VAD),
interrupção ligada, filler words para cobrir as ferramentas, nome único, métricas ligadas.
"""
import uuid
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ConfigVoz:
    asr_preset: str
    tts_preset: str
    llm_preset: str
    asr_language: str
    tts_sample_rate: int
    tts_language_boost: str
    tts_speed: float
    asr_vendor: str
    asr_model: str
    asr_api_key: str
    asr_keywords: list[str]
    enable_rtm: bool
    sal: bool
    filler_words: list[str]
    filler_espera_ms: int
    llm_model: str
    llm_max_tokens: int
    llm_shared_secret: str

    @classmethod
    def de(cls, s) -> "ConfigVoz":
        return cls(
            asr_preset=s.agora_asr_preset, tts_preset=s.agora_tts_preset, llm_preset=s.agora_llm_preset,
            asr_language=s.asr_language, tts_sample_rate=s.tts_sample_rate,
            tts_language_boost=s.tts_language_boost, tts_speed=s.tts_speed, asr_vendor=s.asr_vendor.strip().lower(), asr_model=s.asr_model.strip(),
            asr_api_key=s.asr_api_key or (s.llm_api_key if "api.openai.com" in s.llm_base_url else ""),
            asr_keywords=list(s.asr_keywords), enable_rtm=s.agora_enable_rtm, sal=s.agora_sal,
            filler_words=list(s.filler_words), filler_espera_ms=s.filler_espera_ms,
            llm_model=s.llm_model, llm_max_tokens=s.llm_max_tokens, llm_shared_secret=s.llm_shared_secret,
        )


def montar_asr(cfg: ConfigVoz, termos_rota: list[str]) -> tuple[dict, Optional[str]]:
    """Bloco `asr` do /join e o preset de ASR (se houver), conforme o fornecedor."""
    termos = list(dict.fromkeys([*cfg.asr_keywords, *[t for t in termos_rota if t]]))[:128]
    if cfg.asr_vendor == "ares":  # ASR da Agora: pt-BR suportado, palavras-chave até 128
        return {"vendor": "ares", "language": cfg.asr_language, "keywords": termos}, None
    if cfg.asr_vendor == "openai":
        prompt = ("Transcreva em português do Brasil a fala de um caminhoneiro ou de um recebedor de carga. "
                  "Termos comuns: " + ", ".join(termos) + ".")
        return {"vendor": "openai", "language": cfg.asr_language, "params": {
            "api_key": cfg.asr_api_key,
            "input_audio_transcription": {"model": cfg.asr_model or "gpt-4o-mini-transcribe", "prompt": prompt,
                                          "language": cfg.asr_language.split("-")[0]},
        }}, None
    modelo = cfg.asr_model or "nova-3"  # deepgram gerenciado pela Agora (preset)
    preset = {"nova-2": "deepgram_nova_2", "nova-3": "deepgram_nova_3"}.get(modelo, cfg.asr_preset)
    return {"vendor": "deepgram", "language": cfg.asr_language, "params": {"language": cfg.asr_language}}, preset


def nome_unico(prefixo: str) -> str:
    return f"{prefixo}-{uuid.uuid4().hex[:8]}"


def montar_join(
    cfg: ConfigVoz,
    *,
    nome: str,
    canal: str,
    token: str,
    agent_uid: int,
    remote_uid: int,
    prompt: str,
    saudacao: str,
    voice_id: str,
    llm_url: Optional[str],
    sessao_id: Optional[int] = None,
    idle_timeout: int = 120,
    termos_rota: Optional[list[str]] = None,
) -> dict:
    asr, preset_asr = montar_asr(cfg, termos_rota or [])
    presets = [preset_asr] if preset_asr else []
    llm: dict[str, Any] = {
        "style": "openai",
        "system_messages": [{"role": "system", "content": prompt}],
        "greeting_message": saudacao,
        "failure_message": "Só um instante, parceiro.",
        "max_history": 32,
        "params": {"max_tokens": cfg.llm_max_tokens},
    }
    if llm_url:
        llm.update(
            url=llm_url,
            vendor="custom",
            api_key=cfg.llm_shared_secret,
            headers={"X-Avisai-Sessao": str(sessao_id)},
            params={"model": cfg.llm_model, "max_tokens": cfg.llm_max_tokens},
        )
    else:
        presets.append(cfg.llm_preset)
    presets.append(cfg.tts_preset)

    props: dict[str, Any] = {
        "channel": canal,
        "token": token,
        "agent_rtc_uid": str(agent_uid),
        "remote_rtc_uids": [str(remote_uid)],
        "enable_string_uid": False,
        "idle_timeout": idle_timeout,
        "advanced_features": {"enable_rtm": cfg.enable_rtm},
        "asr": asr,
        "llm": llm,
        "tts": {"vendor": "minimax", "params": {
            "voice_setting": {"voice_id": voice_id, "speed": cfg.tts_speed},
            "audio_setting": {"sample_rate": cfg.tts_sample_rate},
            **({"language_boost": cfg.tts_language_boost} if cfg.tts_language_boost else {}),
        }},
        "interruption": {"enable": True, "mode": "start_of_speech"},  # barge-in
        "filler_words": {
            "enable": True,
            "trigger": {"mode": "fixed_time", "fixed_time_config": {"response_wait_ms": cfg.filler_espera_ms}},
            "content": {"mode": "static", "static_config": {"phrases": cfg.filler_words, "selection_rule": "shuffle"}},
        },
        "parameters": {
            "data_channel": "rtm" if cfg.enable_rtm else "datastream",
            "enable_metrics": True,
            "enable_error_message": True,
        },
    }
    if cfg.sal:
        props["sal"] = {"sal_mode": "locking"}
    return {"name": nome, "preset": ",".join(presets), "properties": props}


def montar_call(corpo_join: dict, *, para: str, de: str, sip_uid: int, sip_token: str) -> dict:
    """Plano A: /call usa o mesmo `properties` do /join + bloco `sip`."""
    return {
        "name": corpo_join["name"],
        "preset": corpo_join.get("preset"),
        "sip": {"to_number": para, "from_number": de, "rtc_uid": str(sip_uid), "rtc_token": sip_token},
        "properties": corpo_join["properties"],
    }
