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
            asr_language=s.asr_language, enable_rtm=s.agora_enable_rtm, sal=s.agora_sal,
            filler_words=list(s.filler_words), filler_espera_ms=s.filler_espera_ms,
            llm_model=s.llm_model, llm_max_tokens=s.llm_max_tokens, llm_shared_secret=s.llm_shared_secret,
        )


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
) -> dict:
    presets = [cfg.asr_preset]
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
        "asr": {"vendor": "deepgram", "language": cfg.asr_language, "params": {"language": cfg.asr_language}},
        "llm": llm,
        "tts": {"vendor": "minimax", "params": {"voice_setting": {"voice_id": voice_id}}},
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
