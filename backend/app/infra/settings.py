"""Configuração. Em Docker vem do .env (env_file do compose)."""
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

FILLER_PADRAO = [
    "Só um instante, tô vendo aqui.",
    "Peraí, deixa eu registrar.",
    "Um segundinho, parceiro.",
]


class Settings(BaseSettings):
    # Agora
    agora_app_id: str = ""
    agora_app_certificate: str = ""
    # aceita também os nomes do docs/arquitetura-avisai.md (AGORA_REST_KEY/SECRET)
    agora_customer_id: str = Field("", validation_alias=AliasChoices("AGORA_CUSTOMER_ID", "AGORA_REST_KEY", "agora_customer_id"))
    agora_customer_secret: str = Field("", validation_alias=AliasChoices("AGORA_CUSTOMER_SECRET", "AGORA_REST_SECRET", "agora_customer_secret"))
    agora_api_base: str = "https://api.agora.io/api/conversational-ai-agent"
    agora_enable_rtm: bool = True
    agora_asr_preset: str = "deepgram_nova_3"
    agora_tts_preset: str = "minimax_speech_2_6_turbo"
    agora_llm_preset: str = "openai_gpt_4o_mini"
    agora_sal: bool = False
    asr_language: str = "pt-BR"
    # ASR: deepgram (gerenciado, nova-3|nova-2) | ares (ASR da Agora, gerenciado, com palavras-chave) | openai (BYOK)
    asr_vendor: str = "ares"
    asr_model: str = ""  # vazio = padrão do fornecedor (nova-3 / gpt-4o-mini-transcribe)
    asr_api_key: str = ""  # openai; vazio = usa LLM_API_KEY se o LLM for a OpenAI
    asr_keywords: list[str] = [
        "AvisAI", "doca", "portaria", "pátio", "descarga", "descarreguei", "estadia", "franquia", "recebimento",
        "recebedor", "CCO", "central", "nota fiscal", "NF-e", "CT-e", "DANFE", "palete", "paletes", "toneladas",
        "lacre", "canhoto", "avaria", "retirada", "check-in", "ocorrência", "fila", "placa", "frete",
    ]
    tts_voice_id: str = "Portuguese_Deep-VoicedGentleman"
    tts_voice_id_recebedor: str = "Portuguese_Wiselady"
    filler_words: list[str] = FILLER_PADRAO
    filler_espera_ms: int = 1500

    # Ligação ao recebedor: rtc (plano B, navegador) | sip (plano A, telefone)
    recebedor_modo: str = "rtc"
    agora_sip_from_number: str = Field("", validation_alias=AliasChoices("AGORA_SIP_FROM_NUMBER", "SIP_FROM_NUMBER", "agora_sip_from_number"))
    recebedor_telefone_e164: str = "+5519900000002"

    # LLM: custom = Agora chama o nosso /v1/chat/completions; agora = LLM gerenciado
    llm_mode: str = "custom"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_max_tokens: int = 150
    llm_shared_secret: str = ""

    # Público / túnel
    public_url: str = ""
    tunnel_metrics_url: str = ""

    # Banco
    database_url: str = "postgresql+psycopg://avisai:avisai@db:5432/avisai"

    # Ritmo da demo
    cco_intervalo_s: float = 20
    cco_max_tentativas: int = 3
    estadia_aceleracao: float = 1
    estadia_valor_t_h: float = 2.50
    estadia_franquia_h: float = 5
    ligar_recebedor_na_aproximacao: bool = True  # fluxo do repo de ideias: avisa o recebedor antes de chegar
    ligacao_timeout_s: float = 180
    ligacao_poll_s: float = 5
    encerrar_ligacao_apos_s: float = 20
    velocidade_padrao_kmh: float = 60
    divergencia_gps_max_m: float = 500
    model_config = SettingsConfigDict(extra="ignore", env_file=None, populate_by_name=True)

    def agora_configurada(self) -> bool:
        return bool(self.agora_app_id and self.agora_app_certificate)
